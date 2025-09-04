import os
import subprocess
from pathlib import Path
import toml
import typer

from picsellia_cli.utils.deployer import (
    build_docker_image_only,
    prompt_docker_image_if_missing,
)
from picsellia_cli.utils.env_utils import (
    ensure_env_vars,
    get_host_env_config,
    get_api_token_from_host,
)
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.logging import section, kv, bullet, hr

from picsellia_cli.commands.training.utils.test import (
    get_training_params,
    normalize_training_io,
)
from picsellia_cli.utils.initializer import init_client


def smoke_test_training(
    pipeline_name: str,
    host: str = typer.Option("prod", help="Target host (prod/staging/local or URL)"),
    run_config_file: str | None = typer.Option(None, help="Path to run-config TOML"),
    python_version: str = typer.Option(
        "3.10", help="Python version to run inside the container, e.g. 3.10"
    ),
):
    """
    Build l'image Docker et lance un smoke-test du script Picsellia dans un conteneur.
    - Si un run-config est fourni, on normalise + résout l'experiment_id via normalize_training_io.
    - Sinon, fallback interactif: on demande un experiment_id minimal.
    - La version de Python utilisée dans le container est paramétrable via --python-version.
    """
    ensure_env_vars(host=host)
    config = PipelineConfig(pipeline_name)
    prompt_docker_image_if_missing(pipeline_config=config)

    # Charger / normaliser le run-config
    if run_config_file:
        rc_path = Path(run_config_file)
        if not rc_path.exists():
            typer.echo(f"❌ Config file not found: {run_config_file}")
            raise typer.Exit()
        run_config = toml.load(rc_path)
    else:
        run_config = get_training_params(run_manager=None, config_file=None)

    # Host/env pour normalisation
    auth = run_config.setdefault("auth", {})
    desired_host = auth.get("host") or host
    host_cfg = get_host_env_config(host=desired_host)
    auth.setdefault("host", host_cfg["host"])
    auth.setdefault("organization_name", host_cfg["organization_name"])

    # Résoudre l'expérience + inputs
    client = init_client(host=auth["host"])
    normalize_training_io(client=client, run_config=run_config)

    exp = (run_config.get("output") or {}).get("experiment") or {}
    experiment_id = exp.get("id")
    if not experiment_id:
        typer.echo("❌ Could not resolve an experiment id from the run config.")
        raise typer.Exit()

    # Build image
    image_name = config.get("docker", "image_name")
    image_tag = config.get("docker", "image_tag")
    full_image_name = f"{image_name}:{image_tag}"

    section("🐳 Docker image")
    kv("Image", image_name)
    kv("Tag", image_tag)

    build_docker_image_only(
        pipeline_dir=config.pipeline_dir,
        full_image_name=full_image_name,
    )

    # Env vars
    api_token = get_api_token_from_host(host=host_cfg["host"])
    env_vars = {
        "api_token": api_token,
        "organization_name": auth["organization_name"],
        "experiment_id": str(experiment_id),
        "DEBUG": "True",
        "PICSELLIA_HOST": host_cfg["host"],
    }

    # Script & python
    script_rel = (
        f"{pipeline_name}/{config.get('execution', 'picsellia_pipeline_script')}"
    )
    python_bin = f"python{python_version}"

    section("🧪 Smoke test")
    kv("Workspace", auth["organization_name"])
    kv("Host", host_cfg["host"])
    kv("Experiment ID", experiment_id)
    kv("Script", script_rel)
    kv("Python", python_bin)

    run_smoke_test_container(
        image=full_image_name,
        script=script_rel,
        env_vars=env_vars,
        python_bin=python_bin,
    )


def run_smoke_test_container(image: str, script: str, env_vars: dict, python_bin: str):
    """
    Lance le conteneur en mode bash -c "run <python_bin> <script>"
    et stop si on détecte "--ec-- 1" dans les logs.
    """
    container_name = "smoke-test-temp"
    log_cmd = f"run {python_bin} {script}"

    # Cleanup éventuel
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    docker_command = [
        "docker",
        "run",
        "--gpus",
        "all",
        "--shm-size",
        "8g",
        "--name",
        container_name,
        "--entrypoint",
        "bash",
        "-v",
        f"{os.getcwd()}:/workspace",
    ]

    for k, v in env_vars.items():
        docker_command += ["-e", f"{k}={v}"]

    docker_command += [image, "-c", log_cmd]

    bullet("Launching Docker training container…", accent=True)
    proc = subprocess.Popen(
        docker_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    triggered = False
    if proc.stdout is None:
        typer.echo("❌ Failed to capture Docker logs.")
        return

    try:
        for line in proc.stdout:
            print(line, end="")
            if "--ec-- 1" in line:
                typer.echo(
                    "\n❌ '--ec-- 1' detected! Something went wrong during training."
                )
                typer.echo(
                    "📥 Copying training logs before stopping the container...\n"
                )
                triggered = True

                subprocess.run(
                    [
                        "docker",
                        "cp",
                        f"{container_name}:/experiment/training.log",
                        "training.log",
                    ],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                subprocess.run(["docker", "stop", container_name], check=False)
                break
    except Exception as e:
        typer.echo(f"❌ Error while monitoring Docker: {e}")
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            typer.echo("⚠️ Timeout reached. Killing process.")
            proc.kill()

    print(f"\n🚦 Docker container exited with code: {proc.returncode}")

    if triggered or proc.returncode != 0:
        typer.echo("\n🧾 Captured training.log content:\n" + "-" * 60)
        try:
            with open("training.log") as f:
                print(f.read())
        except Exception as e:
            typer.echo(f"⚠️ Could not read training.log: {e}")
        print("-" * 60 + "\n")
    else:
        typer.echo("✅ Docker pipeline ran successfully.")

    hr()

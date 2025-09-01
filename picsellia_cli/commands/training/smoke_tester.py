import os
import subprocess

import typer

from picsellia_cli.commands.training.tester import prompt_training_params
from picsellia_cli.utils.deployer import (
    build_docker_image_only,
    prompt_docker_image_if_missing,
)
from picsellia_cli.utils.env_utils import require_env_var, ensure_env_vars
from picsellia_cli.utils.pipeline_config import PipelineConfig


def smoke_test_training(pipeline_name: str):
    ensure_env_vars()
    config = PipelineConfig(pipeline_name)
    prompt_docker_image_if_missing(pipeline_config=config)

    stored_params: dict = {}
    params = prompt_training_params(stored_params)

    experiment_id = params["experiment_id"]

    image_name = config.get("docker", "image_name")
    image_tag = config.get("docker", "image_tag")

    full_image_name = f"{image_name}:{image_tag}"

    build_docker_image_only(
        pipeline_dir=config.pipeline_dir,
        full_image_name=full_image_name,
    )

    env_vars = {
        "api_token": require_env_var("PICSELLIA_API_TOKEN"),
        "organization_name": require_env_var("PICSELLIA_ORGANIZATION_NAME"),
        "experiment_id": experiment_id,
        "DEBUG": "True",
    }

    pipeline_script = (
        f"{pipeline_name}/{config.get('execution', 'picsellia_pipeline_script')}"
    )

    run_smoke_test_container(
        image=full_image_name, script=pipeline_script, env_vars=env_vars
    )


def run_smoke_test_container(image: str, script: str, env_vars: dict):
    container_name = "smoke-test-temp"
    log_cmd = f"run python3.10 {script}"

    # Clean up old container if needed
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        check=True,
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
        "8",
        "--name",
        container_name,
        "--entrypoint",
        "bash",
        "-v",
        f"{os.getcwd()}:/workspace",
    ]

    for key, value in env_vars.items():
        docker_command += ["-e", f"{key}={value}"]

    docker_command += [image, "-c", log_cmd]

    typer.echo("🚀 Launching Docker training container...\n")

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

                # Copy from /experiment instead of /workspace
                subprocess.run(
                    [
                        "docker",
                        "cp",
                        f"{container_name}:/experiment/training.log",
                        "training.log",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                subprocess.run(
                    ["docker", "stop", container_name],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
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

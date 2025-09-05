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
from picsellia_cli.utils.logging import section, kv

from picsellia_cli.commands.training.utils.test import (
    get_training_params,
    normalize_training_io,
)
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.smoke_tester import run_smoke_test_container


def smoke_test_training(
    pipeline_name: str,
    run_config_file: str | None = None,
    host: str = "prod",
    python_version: str = "3.10",
):
    """
    Build l'image Docker et lance un smoke-test du script Picsellia dans un conteneur.
    - Si un run-config est fourni, on normalise + résout l'experiment_id via normalize_training_io.
    - Sinon, fallback interactif: on demande un experiment_id minimal.
    - La version de Python utilisée dans le container est paramétrable via --python-version.
    """
    ensure_env_vars(host=host)
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    prompt_docker_image_if_missing(pipeline_config=pipeline_config)

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
    image_name = pipeline_config.get("docker", "image_name")
    image_tag = pipeline_config.get("docker", "image_tag")
    full_image_name = f"{image_name}:{image_tag}"

    section("🐳 Docker image")
    kv("Image", image_name)
    kv("Tag", image_tag)

    build_docker_image_only(
        pipeline_dir=pipeline_config.pipeline_dir,
        full_image_name=full_image_name,
    )

    # Env vars
    api_token = get_api_token_from_host(host=host_cfg["host"])
    env_vars = {
        "api_token": api_token,
        "organization_name": auth["organization_name"],
        "host": host_cfg["host"],
        "experiment_id": str(experiment_id),
        "DEBUG": "True",
    }

    pipeline_script = (
        f"{pipeline_name}/{pipeline_config.get('execution', 'pipeline_script')}"
    )

    python_bin = f"python{python_version}"

    section("🧪 Smoke test")
    kv("Workspace", auth["organization_name"])
    kv("Host", host_cfg["host"])
    kv("Experiment ID", experiment_id)
    kv("Script", pipeline_script)
    kv("Python", python_bin)

    run_smoke_test_container(
        image=full_image_name,
        script=pipeline_script,
        env_vars=env_vars,
        python_bin=python_bin,
    )

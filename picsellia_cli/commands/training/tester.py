import os
from pathlib import Path
import json
import toml
import typer
from picsellia import Client

from picsellia_cli.utils.env_utils import (
    ensure_env_vars,
    get_host_env_config,
    get_api_token_from_host,
)
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.runner import create_virtual_env, run_pipeline_command
from picsellia_cli.utils.tester import (
    merge_with_default_parameters,
    get_saved_run_config_path,
    build_pipeline_command,
)


def test_training(
    pipeline_name: str,
    reuse_dir: bool = False,
    run_config_file: str | None = None,
    host: str = "prod",
):
    ensure_env_vars()
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    run_manager = RunManager(pipeline_dir=pipeline_config.pipeline_dir)

    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir() or run_manager.get_next_run_dir()
    else:
        run_dir = run_manager.get_next_run_dir()

    run_config_path = Path(run_config_file) if run_config_file else None
    if reuse_dir and run_config_path is None:
        run_config_path = run_manager.get_latest_run_config_path()

    if run_config_path and run_config_path.exists():
        run_config = toml.load(run_config_path)
        run_config.setdefault("run", {})
        run_config["run"]["working_dir"] = str(run_dir)
    else:
        run_config = get_training_params(run_manager=run_manager, config_file=None)
        run_config.setdefault("run", {})
        run_config["run"]["working_dir"] = str(run_dir)

    if "auth" in run_config and "host" in run_config["auth"]:
        host = run_config["auth"]["host"]
        env_config = get_host_env_config(host=host)
    else:
        env_config = get_host_env_config(host=host.upper())
        run_config.setdefault("auth", {})
        run_config["auth"]["host"] = env_config["host"]

    if "organization_name" not in run_config["auth"]:
        org_env = os.getenv("PICSELLIA_ORGANIZATION_NAME")
        run_config["auth"]["organization_name"] = (
            org_env or env_config["organization_name"]
        )

    default_pipeline_params = pipeline_config.extract_default_parameters()
    run_config = merge_with_default_parameters(
        run_config=run_config, default_parameters=default_pipeline_params
    )

    client = init_client(host=run_config["auth"]["host"])
    enrich_run_config_with_metadata(client=client, run_config=run_config)

    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)
    saved_run_config_path = get_saved_run_config_path(
        run_manager=run_manager, run_dir=run_dir
    )

    env_path = create_virtual_env(
        requirements_path=pipeline_config.get_requirements_path()
    )
    python_executable = (
        Path(env_path) / ("Scripts" if os.name == "nt" else "bin") / "python"
    )

    command = build_pipeline_command(
        python_executable=python_executable,
        pipeline_script_path=pipeline_config.get_script_path("pipeline_script"),
        run_config_file=saved_run_config_path,
        mode="local",
    )

    api_token = get_api_token_from_host(host=run_config["auth"]["host"])

    run_pipeline_command(
        command=command,
        working_dir=str(run_dir),
        api_token=api_token,
    )

    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)

    typer.echo(
        typer.style(
            f"✅ Training pipeline '{pipeline_name}' run complete: {run_dir.name}",
            fg=typer.colors.GREEN,
        )
    )


def print_config_io_summary_for_training(config: dict):
    summary = {
        "experiment_id": config.get("experiment_id"),
        "parameters": config.get("parameters", {}),
        "auth": {
            "host": config.get("auth", {}).get("host"),
            "organization_name": config.get("auth", {}).get("organization_name"),
        },
        "run": {"working_dir": config.get("run", {}).get("working_dir")},
    }
    typer.echo(
        typer.style("🧾 Reusing previous training config:\n", fg=typer.colors.CYAN)
    )
    typer.echo(json.dumps(summary, indent=2))


def prompt_training_params(stored_params: dict) -> dict:
    experiment_id = typer.prompt(
        typer.style("🧪 Experiment ID", fg=typer.colors.CYAN),
        default=stored_params.get("experiment_id", ""),
    )
    return {"experiment_id": experiment_id}


def get_training_params(
    run_manager: RunManager,
    config_file: Path | None = None,
) -> dict:
    if config_file and config_file.exists():
        with config_file.open("r") as f:
            return toml.load(f)
    else:
        latest_config_path = run_manager.get_latest_run_config_path()
        if latest_config_path:
            with open(latest_config_path, "r") as f:
                latest_config = toml.load(f)
        else:
            latest_config = None

    params = {}
    stored_params = {}

    if latest_config:
        print_config_io_summary_for_training(latest_config)
        reuse = typer.confirm(
            typer.style("📝 Do you want to reuse this config?", fg=typer.colors.CYAN),
            default=True,
        )
        stored_params = latest_config
        if reuse:
            params = latest_config

    if not params:
        params = prompt_training_params(stored_params)

    return params


def enrich_run_config_with_metadata(client: Client, run_config: dict):
    try:
        experiment_id = run_config.get("experiment_id")
        if experiment_id:
            exp = None
            for getter in ("get_experiment_by_id", "get_experiment"):
                if hasattr(client, getter):
                    try:
                        exp = (
                            getattr(client, getter)(experiment_id)
                            if "by_id" in getter
                            else getattr(client, getter)(id=experiment_id)
                        )
                        break
                    except Exception:
                        continue
            if exp is not None:
                run_config.setdefault("input", {})
                run_config["input"]["experiment"] = {
                    "id": str(experiment_id),
                    "name": getattr(exp, "name", None),
                    "url": f"{client.connexion.host}/{client.connexion.organization_id}/experiment/{getattr(exp, 'id', experiment_id)}",
                }
    except Exception as e:
        typer.echo(f"⚠️ Could not resolve experiment metadata: {e}")

import os
from pathlib import Path

import typer

from picsellia_cli.utils.env_utils import require_env_var, ensure_env_vars
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.runner import (
    create_virtual_env,
    run_pipeline_command,
)

import toml


def test_training(
    pipeline_name: str,
    reuse_dir: bool = False,
    run_config_file: str | None = None,
):
    ensure_env_vars()
    config = PipelineConfig(pipeline_name)
    run_manager = RunManager(config.pipeline_dir)

    config_file_to_reuse = Path(run_config_file) if run_config_file else None
    if reuse_dir and config_file_to_reuse is None:
        config_file_to_reuse = run_manager.get_latest_run_config_path()

    params = get_training_params(
        run_manager=run_manager, config_file=config_file_to_reuse
    )

    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir()
        if not run_dir:
            run_dir = run_manager.get_next_run_dir()
    else:
        run_dir = run_manager.get_next_run_dir()

    run_manager.save_run_config(run_dir=run_dir, config_data=params)

    env_path = create_virtual_env(requirements_path=config.get_requirements_path())
    python_executable = os.path.join(
        env_path, "Scripts" if os.name == "nt" else "bin", "python"
    )

    command = [
        python_executable,
        str(config.get_script_path("local_pipeline_script")),
        "--api_token",
        require_env_var("PICSELLIA_API_TOKEN"),
        "--organization_name",
        require_env_var("PICSELLIA_ORGANIZATION_NAME"),
        "--experiment_id",
        params["experiment_id"],
        "--working_dir",
        str(run_dir),
    ]

    run_pipeline_command(command=command, working_dir=str(run_dir))

    typer.echo(
        typer.style(
            f"✅ Training pipeline '{pipeline_name}' run complete: {run_dir.name}",
            fg=typer.colors.GREEN,
        )
    )


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
    """
    Handles reuse or prompting of training parameters and determines the run directory.

    Returns:
        Tuple of selected params and the run directory path.
    """
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
        summary = " / ".join(f"{k}={v}" for k, v in latest_config.items())
        reuse = typer.confirm(f"📝 Reuse previous config? {summary}", default=True)
        stored_params = latest_config
        if reuse:
            params = latest_config

    if not params:
        params = prompt_training_params(stored_params)

    return params

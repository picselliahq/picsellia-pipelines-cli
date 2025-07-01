import os
from pathlib import Path
from typing import Any

import typer

from picsellia_cli.utils.env_utils import require_env_var, ensure_env_vars
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.runner import (
    create_virtual_env,
    run_pipeline_command,
)


def test_training(pipeline_name: str, reuse_dir: bool = False):
    ensure_env_vars()
    config = PipelineConfig(pipeline_name)
    run_manager = RunManager(config.pipeline_dir)

    stored_params: dict[str, Any] = {}
    params, run_dir = get_training_params_and_run_dir(
        run_manager, reuse_dir, stored_params
    )

    env_path = create_virtual_env(str(config.get_requirements_path()))
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

    run_pipeline_command(command, str(run_dir))

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


def get_training_params_and_run_dir(
    run_manager: RunManager,
    reuse_dir: bool,
    stored_params: dict[str, Any],
) -> tuple[dict, Path]:
    """
    Handles reuse or prompting of training parameters and determines the run directory.

    Returns:
        Tuple of selected params and the run directory path.
    """
    latest_config = run_manager.get_latest_run_config()

    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir()
        if not latest_config or not run_dir:
            typer.echo(
                typer.style(
                    "❌ No existing run/config found to reuse.", fg=typer.colors.RED
                )
            )
            raise typer.Exit(code=1)
        typer.echo(
            typer.style(
                f"🔁 Reusing latest run: {run_dir.name}", fg=typer.colors.YELLOW
            )
        )
        return latest_config, run_dir

    params = {}
    if latest_config:
        summary = " / ".join(f"{k}={v}" for k, v in latest_config.items())
        reuse = typer.confirm(f"📝 Reuse previous config? {summary}", default=True)
        if reuse:
            params = latest_config
        else:
            params = prompt_training_params(stored_params)

    if not params:
        params = prompt_training_params(stored_params)

    run_dir = run_manager.get_next_run_dir()
    run_manager.save_run_config(run_dir, params)
    return params, run_dir

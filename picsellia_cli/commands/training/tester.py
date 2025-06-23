import os
from typing import Dict, Any

import typer

from picsellia_cli.utils.env_utils import require_env_var, ensure_env_vars
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.runner import (
    create_virtual_env,
    run_pipeline_command,
)

app = typer.Typer(help="Test registered training pipelines locally.")


def prompt_training_params(stored_params: Dict) -> Dict:
    experiment_id = typer.prompt(
        typer.style("🧪 Experiment ID", fg=typer.colors.CYAN),
        default=stored_params.get("experiment_id", ""),
    )
    return {"experiment_id": experiment_id}


@app.command()
def test_training(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the training pipeline to test"
    ),
    reuse_dir: bool = typer.Option(
        False, "--reuse-dir", help="Reuse latest run directory and config"
    ),
):
    ensure_env_vars()
    config = PipelineConfig(pipeline_name)
    run_manager = RunManager(config.pipeline_dir)

    latest_config = run_manager.get_latest_run_config()
    stored_params: Dict[str, Any] = {}
    params: Dict[str, Any] = {}

    if reuse_dir:
        latest_config = run_manager.get_latest_run_config()
        run_dir = run_manager.get_latest_run_dir()
        if not latest_config or not run_dir:
            typer.echo(
                typer.style(
                    "❌ No existing run/config found to reuse.", fg=typer.colors.RED
                )
            )
            raise typer.Exit(code=1)
        params = latest_config
        typer.echo(
            typer.style(
                f"🔁 Reusing latest run: {run_dir.name}", fg=typer.colors.YELLOW
            )
        )
    else:
        params = prompt_training_params(stored_params=stored_params)
        run_dir = run_manager.get_next_run_dir()
        run_manager.save_run_config(run_dir, params)

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


if __name__ == "__main__":
    app()

import os
from typing import Dict

import typer

from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.runner import (
    create_virtual_env,
    run_pipeline_command,
)

app = typer.Typer(help="Test registered training pipelines locally.")


def prompt_training_params(stored_params: Dict) -> Dict:
    last_experiment_id = stored_params.get("experiment_id", "")

    if last_experiment_id:
        use_last = typer.confirm(
            f"ℹ️ Use previously used experiment ID: {last_experiment_id}?", default=True
        )
        experiment_id = (
            last_experiment_id
            if use_last
            else typer.prompt("🧪 Enter new Experiment ID")
        )
    else:
        experiment_id = typer.prompt("🧪 Enter Experiment ID")

    stored_params["experiment_id"] = experiment_id
    return stored_params


@app.command()
def test_training(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the training pipeline to test"
    ),
):
    config = PipelineConfig(pipeline_name)

    stored_params: dict = {}
    params = prompt_training_params(stored_params)

    working_dir = config.pipeline_dir / "runs" / params["experiment_id"]
    os.makedirs(working_dir, exist_ok=True)

    env_path = create_virtual_env(str(config.get_requirements_path()))
    pipeline_script = str(config.get_script_path("local_pipeline_script"))

    python_executable = (
        os.path.join(env_path, "bin", "python")
        if os.name != "nt"
        else os.path.join(env_path, "Scripts", "python.exe")
    )

    command = [
        python_executable,
        pipeline_script,
        "--api_token",
        config.env.get_api_token(),
        "--organization_name",
        config.env.get_organization_name(),
        "--experiment_id",
        params["experiment_id"],
        "--working_dir",
        str(working_dir),
    ]

    run_pipeline_command(command, working_dir)

    typer.echo(
        typer.style(
            f"✅ Training pipeline '{pipeline_name}' tested successfully!",
            fg=typer.colors.GREEN,
            bold=True,
        )
    )


if __name__ == "__main__":
    app()

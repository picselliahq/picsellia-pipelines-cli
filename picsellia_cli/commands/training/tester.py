import os
from typing import Dict

import typer

from picsellia_cli.utils.runner import (
    get_pipeline_data,
    get_global_session,
    create_virtual_env,
    run_pipeline_command,
)
from picsellia_cli.utils.session_manager import session_manager

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
    pipeline = get_pipeline_data(pipeline_name)
    global_data = get_global_session()
    stored_params = pipeline.get("last_test_params", {})

    pipeline["last_test_params"] = prompt_training_params(stored_params)
    session_manager.update_pipeline(name=pipeline_name, data=pipeline)
    env_path = create_virtual_env(pipeline["requirements_path"])

    repo_root = os.getcwd()
    working_dir = os.path.join(
        repo_root,
        "pipelines",
        pipeline_name,
        "tests",
        pipeline["last_test_params"]["experiment_id"],
    )
    os.makedirs(working_dir, exist_ok=True)

    pipeline_script = os.path.join(repo_root, pipeline["local_pipeline_script_path"])
    python_executable = (
        os.path.join(env_path, "bin", "python")
        if os.name != "nt"
        else os.path.join(env_path, "Scripts", "python.exe")
    )

    command = [
        python_executable,
        pipeline_script,
        "--api_token",
        global_data["api_token"],
        "--organization_name",
        global_data["organization_name"],
        "--experiment_id",
        pipeline["last_test_params"]["experiment_id"],
        "--working_dir",
        working_dir,
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

import os
import subprocess
import venv
from typing import Dict

import typer
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Test registered training pipelines locally.")


def get_pipeline_data(pipeline_name: str) -> Dict:
    session_manager.ensure_session_initialized()
    pipeline = session_manager.get_pipeline(pipeline_name)
    if not pipeline:
        typer.echo(f"❌ Pipeline '{pipeline_name}' not found.")
        raise typer.Exit()
    return pipeline


def get_global_session() -> Dict:
    global_data = session_manager.get_global_session()
    if not global_data:
        typer.echo("❌ Global session not initialized. Run `pipeline-cli init` first.")
        raise typer.Exit()
    return global_data


def create_virtual_env(requirements_path: str) -> str:
    env_path = os.path.join(os.path.dirname(requirements_path), ".venv")
    pip_executable = (
        os.path.join(env_path, "bin", "pip")
        if os.name != "nt"
        else os.path.join(env_path, "Scripts", "pip.exe")
    )

    if not os.path.exists(env_path):
        typer.echo(f"⚙️ Creating virtual environment at {env_path}...")
        venv.create(env_path, with_pip=True)

    if os.path.exists(requirements_path):
        typer.echo(f"📦 Installing dependencies from {requirements_path}...")
        subprocess.run([pip_executable, "install", "-r", requirements_path], check=True)
    else:
        typer.echo("⚠️ No requirements.txt found, skipping dependency installation.")

    typer.echo("📦 Installing picsellia-cv-engine from GitHub...")
    subprocess.run(
        [
            pip_executable,
            "install",
            "git+https://github.com/picselliahq/picsellia-cv-engine.git@feat/add-utils-for-training-template",
        ],
        check=True,
    )

    return env_path


def prompt_training_params(stored_params: Dict) -> Dict:
    last_experiment_id = stored_params.get("experiment_id", "")

    if last_experiment_id:
        use_last = typer.confirm(
            f"ℹ️ Use previously used experiment ID: {last_experiment_id}?", default=True
        )
        if use_last:
            experiment_id = last_experiment_id
        else:
            experiment_id = typer.prompt("🧪 Enter new Experiment ID")
    else:
        experiment_id = typer.prompt("🧪 Enter Experiment ID")

    return {
        "experiment_id": experiment_id,
    }


def run_training_pipeline(
    pipeline_name: str, pipeline: Dict, global_data: Dict, params: Dict, env_path: str
):
    pipeline_script = os.path.join(os.getcwd(), pipeline["local_pipeline_script_path"])
    if not os.path.exists(pipeline_script):
        typer.echo(f"❌ Pipeline script not found: {pipeline_script}")
        raise typer.Exit()

    python_executable = (
        os.path.join(env_path, "bin", "python")
        if os.name != "nt"
        else os.path.join(env_path, "Scripts", "python.exe")
    )
    experiment_id = params["experiment_id"]
    base_run_dir = os.path.join(
        os.getcwd(), f"pipelines/{pipeline_name}/tests/"
    )
    os.makedirs(base_run_dir, exist_ok=True)
    run_dir = os.path.join(base_run_dir, experiment_id)
    os.makedirs(run_dir, exist_ok=True)
    command = [
        python_executable,
        pipeline_script,
        "--api_token",
        global_data["api_token"],
        "--organization_name",
        global_data["organization_name"],
        "--experiment_id",
        experiment_id,
        "--working_dir",
        run_dir,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(os.getcwd())

    typer.echo(f"🚀 Running training pipeline with PYTHONPATH={os.getcwd()}...")

    try:
        subprocess.run(command, check=True, env=env)
    except subprocess.CalledProcessError as e:
        typer.echo(
            typer.style(
                "\n❌ Pipeline execution failed.", fg=typer.colors.RED, bold=True
            )
        )
        typer.echo("🔍 Most recent error output:\n")
        typer.echo(typer.style(str(e), fg=typer.colors.RED))
        raise typer.Exit(code=e.returncode)

    # Save params
    pipeline["last_test_params"] = params
    session_manager.add_pipeline(pipeline_name, pipeline)
    typer.echo(f"✅ Training pipeline '{pipeline_name}' tested successfully!")


@app.command()
def test(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the training pipeline to test"
    ),
):
    pipeline = get_pipeline_data(pipeline_name)
    global_data = get_global_session()
    stored_params = pipeline.get("last_test_params", {})
    params = prompt_training_params(stored_params)
    env_path = create_virtual_env(requirements_path=pipeline["requirements_path"]
    )
    run_training_pipeline(pipeline_name, pipeline, global_data, params, env_path)


if __name__ == "__main__":
    app()

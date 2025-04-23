import os
import subprocess
import venv
from typing import Dict

import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia_cli.utils.session_manager import session_manager
from picsellia_cli.utils.collect_params import update_processing_parameters

app = typer.Typer(help="Test registered pipelines locally.")


def get_pipeline_data(pipeline_name: str) -> Dict:
    """Retrieve pipeline data from session storage."""
    session_manager.ensure_session_initialized()
    pipeline = session_manager.get_pipeline(pipeline_name)
    if not pipeline:
        typer.echo(
            f"❌ Pipeline '{pipeline_name}' not found. Run `pipeline-cli list` to check available pipelines."
        )
        raise typer.Exit()
    return pipeline


def get_global_session() -> Dict:
    """Retrieve global session data or exit if uninitialized."""
    global_data = session_manager.get_global_session()
    if not global_data:
        typer.echo("❌ Global session not initialized. Run `pipeline-cli init` first.")
        raise typer.Exit()
    return global_data


def create_virtual_env(pipeline_name: str) -> str:
    env_path = os.path.join(os.getcwd(), pipeline_name, ".venv")
    pip_executable = (
        os.path.join(env_path, "bin", "pip")
        if os.name != "nt"
        else os.path.join(env_path, "Scripts", "pip.exe")
    )

    if not os.path.exists(env_path):
        typer.echo(f"⚙️ Creating virtual environment at {env_path}...")
        venv.create(env_path, with_pip=True)

    requirements_path = os.path.join(os.getcwd(), pipeline_name, "requirements.txt")
    if os.path.exists(requirements_path):
        typer.echo(f"📦 Installing dependencies from {requirements_path}...")
        subprocess.run([pip_executable, "install", "-r", requirements_path], check=True)
    else:
        typer.echo("⚠️ No requirements.txt found, skipping dependency installation.")

    return env_path


def prompt_for_parameters(pipeline_name: str, stored_params: Dict) -> Dict:
    """Prompt user for test parameters, using stored values as defaults."""
    results_dir = typer.prompt(
        "📂 Enter results directory",
        default=stored_params.get("results_dir", f"test_{pipeline_name}"),
    )

    if os.path.exists(results_dir):
        overwrite = typer.confirm(
            f"⚠️ Directory '{results_dir}' already exists. Do you want to overwrite it?"
        )
        if overwrite:
            os.system(f"rm -rf {results_dir}")
            os.makedirs(results_dir, exist_ok=True)
        else:
            results_dir = typer.prompt(
                "📂 Enter a new results directory", default=f"{results_dir}_new"
            )

    input_dataset_version_id = typer.prompt(
        "📥 Input dataset version ID",
        default=stored_params.get("input_dataset_version_id", ""),
    )
    output_dataset_version_name = typer.prompt(
        "📤 Output dataset version name",
        default=stored_params.get(
            "output_dataset_version_name", f"test_{pipeline_name}"
        ),
    )

    return {
        "results_dir": results_dir,
        "input_dataset_version_id": input_dataset_version_id,
        "output_dataset_version_name": output_dataset_version_name,
    }


def check_output_dataset_version(
    client: Client, input_dataset_version_id: str, output_dataset_version_name: str
) -> str:
    """Check if the output dataset version exists and prompt for overwrite or rename."""
    try:
        input_dataset_version = client.get_dataset_version_by_id(
            input_dataset_version_id
        )
        dataset = client.get_dataset_by_id(input_dataset_version.origin_id)
        dataset.get_version(version=output_dataset_version_name)

        overwrite = typer.confirm(
            f"⚠️ A dataset version named '{output_dataset_version_name}' already exists. Do you want to overwrite it?"
        )
        if overwrite:
            dataset.get_version(version=output_dataset_version_name).delete()
        else:
            output_dataset_version_name = typer.prompt(
                "📤 Enter a new output dataset version name",
                default=f"{output_dataset_version_name}_new",
            )

    except ResourceNotFoundError:
        pass  # The dataset version does not exist, proceed as normal

    return output_dataset_version_name


def run_pipeline_test(
    pipeline_name: str, pipeline: Dict, global_data: Dict, params: Dict, env_path: str
):
    """Execute the local pipeline test script."""
    repo_root = os.getcwd()
    pipeline_script = os.path.join(repo_root, pipeline["local_pipeline_script_path"])

    if not os.path.exists(pipeline_script):
        typer.echo(f"❌ Local pipeline script not found: {pipeline_script}")
        raise typer.Exit()

    update_processing_parameters(pipeline_script, pipeline["parameters"])

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
        "--organization_id",
        global_data["organization_id"],
        "--results_dir",
        params["results_dir"],
        "--job_type",
        pipeline["pipeline_type"],
        "--input_dataset_version_id",
        params["input_dataset_version_id"],
        "--output_dataset_version_name",
        params["output_dataset_version_name"],
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    typer.echo(f"🚀 Running the local pipeline script with PYTHONPATH={repo_root}...")
    subprocess.run(command, check=True, env=env)

    # Store last used parameters in TinyDB
    pipeline["last_test_params"] = params
    session_manager.add_pipeline(pipeline_name, pipeline)

    typer.echo(f"✅ Pipeline '{pipeline_name}' tested successfully!")


@app.command()
def test_pipeline(
    pipeline_name: str = typer.Argument(..., help="Name of the pipeline to test"),
):
    """
    Run a local test for a registered pipeline.

    This command executes the pipeline using the local processing script,
    verifying its behavior with user-provided dataset versions.

    If parameters have been set before, they will be used as defaults.
    """
    pipeline = get_pipeline_data(pipeline_name)
    global_data = get_global_session()
    stored_params = pipeline.get("last_test_params", {})

    params = prompt_for_parameters(pipeline_name, stored_params)

    client = Client(
        api_token=global_data["api_token"],
        organization_id=global_data["organization_id"],
    )
    params["output_dataset_version_name"] = check_output_dataset_version(
        client,
        params["input_dataset_version_id"],
        params["output_dataset_version_name"],
    )

    env_path = create_virtual_env(pipeline_name)

    run_pipeline_test(pipeline_name, pipeline, global_data, params, env_path)


if __name__ == "__main__":
    app()

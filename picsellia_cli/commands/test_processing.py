import os
import subprocess
import typer
from picsellia_cli.utils.prompt import fetch_processing_name
from picsellia_cli.utils.validation import validate_and_update_processing
from picsellia_cli.utils.collect_params import update_processing_parameters
from picsellia_cli.utils.session_manager import session_manager
from picsellia_cli.utils.dockerfile_generation import get_repository_root

app = typer.Typer(help="Processing testing utilities.")


@app.command()
def test():
    """
    Run a local test of a pipeline.
    """
    session_manager.ensure_session_initialized()

    processing_name = fetch_processing_name()
    if not processing_name:
        return

    processing = validate_and_update_processing(processing_name)
    if not processing:
        return

    results_dir: str = typer.prompt("Results directory", type=str)

    if os.path.exists(results_dir):
        override = typer.confirm(
            f"⚠️ Directory '{results_dir}' already exists. Do you want to override it?"
        )
        if not override:
            results_dir = typer.prompt("Enter a new results directory", type=str)
        else:
            os.system(f"rm -rf {results_dir}")
            os.makedirs(results_dir, exist_ok=True)

    input_dataset_version_id: str = typer.prompt("Input dataset version ID")
    output_dataset_version_name: str = typer.prompt("Output dataset version name")

    global_data = session_manager.get_global()

    try:
        repo_root = get_repository_root()

        pipeline_script = os.path.join(
            repo_root, processing["local_pipeline_script_path"]
        )
        if not os.path.exists(pipeline_script):
            raise FileNotFoundError(f"❌ Pipeline script not found: {pipeline_script}")

        update_processing_parameters(
            os.path.join(repo_root, processing["local_pipeline_script_path"]),
            processing["parameters"],
        )

        command = [
            "python",
            str(pipeline_script),
            "--api_token",
            global_data["api_token"],
            "--organization_id",
            global_data["organization_id"],
            "--results_dir",
            results_dir,
            "--job_type",
            processing["processing_type"],
            "--input_dataset_version_id",
            input_dataset_version_id,
            "--output_dataset_version_name",
            output_dataset_version_name,
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)

        typer.echo(
            f"🚀 Running the local pipeline script with PYTHONPATH={repo_root}..."
        )
        subprocess.run(command, check=True, env=env)
        typer.echo(f"✅ Processing '{processing_name}' tested successfully!")

    except FileNotFoundError as e:
        typer.echo(f"❌ File error: {e}")
    except subprocess.CalledProcessError as e:
        typer.echo(f"❌ Error running the pipeline script: {e}")
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    app()

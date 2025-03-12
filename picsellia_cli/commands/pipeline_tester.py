import os
import subprocess
from typing import Optional

import typer
from picsellia_cli.utils.session_manager import session_manager
from picsellia_cli.utils.collect_params import update_processing_parameters

app = typer.Typer(help="Test registered pipelines locally.")


@app.command()
def test_pipeline(
    pipeline_name: str = typer.Argument(..., help="Name of the pipeline to test"),
):
    """
    Run a local test for a registered pipeline.

    This command executes the pipeline using the local processing script,
    verifying its behavior with user-provided dataset versions.
    """
    session_manager.ensure_session_initialized()

    # Fetch pipeline details from session storage
    pipeline = session_manager.get_pipeline(pipeline_name)
    if not pipeline:
        typer.echo(
            f"❌ Pipeline '{pipeline_name}' not found. Run `pipeline-cli list` to check available pipelines."
        )
        raise typer.Exit()

    results_dir: str = typer.prompt("📂 Enter results directory", type=str)

    if os.path.exists(results_dir):
        overwrite = typer.confirm(
            f"⚠️ Directory '{results_dir}' already exists. Do you want to overwrite it?"
        )
        if not overwrite:
            results_dir = typer.prompt("📂 Enter a new results directory", type=str)
        else:
            os.system(f"rm -rf {results_dir}")
            os.makedirs(results_dir, exist_ok=True)

    input_dataset_version_id: str = typer.prompt("📥 Input dataset version ID")
    output_dataset_version_name: str = typer.prompt("📤 Output dataset version name")

    global_data: Optional[dict] = session_manager.get_global_session()
    if not global_data:
        typer.echo("❌ Global session not initialized. Run `pipeline-cli init` first.")
        raise typer.Exit()

    try:
        repo_root = os.getcwd()
        pipeline_script = os.path.join(
            repo_root, pipeline["local_pipeline_script_path"]
        )

        if not os.path.exists(pipeline_script):
            raise FileNotFoundError(
                f"❌ Local pipeline script not found: {pipeline_script}"
            )

        # Update processing parameters in the local pipeline script
        update_processing_parameters(
            pipeline_script,
            pipeline["parameters"],
        )

        command = [
            "python",
            pipeline_script,
            "--api_token",
            global_data["api_token"],
            "--organization_id",
            global_data["organization_id"],
            "--results_dir",
            results_dir,
            "--job_type",
            pipeline["pipeline_type"],  # Ensuring correct pipeline type
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

        typer.echo(f"✅ Pipeline '{pipeline_name}' tested successfully!")

    except FileNotFoundError as e:
        typer.echo(f"❌ File not found: {e}")
        raise typer.Exit()
    except subprocess.CalledProcessError as e:
        typer.echo(f"❌ Error executing the pipeline script: {e}")
        raise typer.Exit()
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}")
        raise typer.Exit()


if __name__ == "__main__":
    app()

import os
import typer
from picsellia_cli.utils.prompt import fetch_processing_name
from picsellia_cli.utils.validation import validate_and_update_processing
from picsellia_cli.utils.collect_params import update_processing_parameters
from picsellia_cli.utils.dockerfile_generation import (
    generate_dockerfile,
    copy_file,
    get_repository_root,
)

app = typer.Typer(help="Dockerized pipeline setup utilities.")


@app.command()
def setup_docker():
    """
    Generate a Dockerized environment for the pipeline.
    """
    processing_name = fetch_processing_name()
    if not processing_name:
        typer.echo("❌ No processing name provided.")
        return

    processing = validate_and_update_processing(processing_name)
    if not processing:
        typer.echo("❌ Invalid processing configuration.")
        return

    base_docker_image: str = typer.prompt(
        "Base Docker image",
        default="picsellia/cpu:python3.10",
        show_default=True,
    )

    try:
        repo_root = get_repository_root()
        pipeline_dir = os.path.join(repo_root, "dist", processing_name)
        os.makedirs(pipeline_dir, exist_ok=True)

        update_processing_parameters(
            os.path.join(repo_root, processing["picsellia_pipeline_script_path"]),
            processing["parameters"],
        )

        # Copy required files
        copy_file(
            source=os.path.join(
                repo_root, processing["picsellia_pipeline_script_path"]
            ),
            destination=os.path.join(pipeline_dir, "processing_pipeline.py"),
        )
        copy_file(
            source=os.path.join(repo_root, processing["requirements_path"]),
            destination=os.path.join(pipeline_dir, "requirements.txt"),
        )

        # Generate Dockerfile
        generate_dockerfile(processing_name, base_docker_image, pipeline_dir)

        typer.echo(
            f"✅ Dockerized pipeline '{processing_name}' setup successfully in '{pipeline_dir}'."
        )

    except Exception as e:
        typer.echo(f"❌ Error setting up dockerized pipeline: {e}")


if __name__ == "__main__":
    app()

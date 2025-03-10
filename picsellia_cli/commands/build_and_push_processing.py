import os
import subprocess
import typer
from picsellia_cli.utils.prompt import fetch_processing_name
from picsellia_cli.utils.validation import validate_and_update_processing
from picsellia_cli.utils.dockerfile_generation import get_repository_root

app = typer.Typer(help="Build and push Docker images for processing pipelines.")


@app.command()
def docker_build_and_push():
    """
    Build and push a Docker image for the pipeline.
    """
    # Fetch processing name
    processing_name = fetch_processing_name()
    if not processing_name:
        typer.echo("❌ No processing name provided.")
        return

    # Validate and update processing details
    processing = validate_and_update_processing(processing_name)
    if not processing:
        typer.echo("❌ Invalid processing configuration.")
        return

    # Docker image details
    image_name = processing.get("image_name")
    image_tag = processing.get("image_tag")
    full_image_name = f"{image_name}:{image_tag}"

    # Run Docker login
    typer.echo("🔑 Logging into Docker. Please enter your credentials:")
    try:
        subprocess.run(["docker", "login"], check=True)
    except subprocess.CalledProcessError:
        typer.echo("❌ Docker login failed. Please try again.")
        return

    # Verify the required files in the dist directory
    try:
        repo_root = get_repository_root()
        pipeline_dir = os.path.join("dist", processing_name)

        if not os.path.exists(pipeline_dir):
            typer.echo(
                f"⚠️ The directory '{pipeline_dir}' does not exist. Run `setup-docker-pipeline` first."
            )
            return

        dockerfile_path = os.path.join(pipeline_dir, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            typer.echo(
                f"⚠️ Dockerfile missing in '{pipeline_dir}'. Run `setup-docker-pipeline` first."
            )
            return

        # Build the Docker image
        typer.echo(f"🚀 Building Docker image '{full_image_name}'...")
        subprocess.run(
            ["docker", "build", "-t", full_image_name, "-f", dockerfile_path, "."],
            cwd=repo_root,
            check=True,
        )

        # Push the Docker image
        typer.echo(f"📤 Pushing Docker image '{full_image_name}'...")
        subprocess.run(["docker", "push", full_image_name], check=True)

        typer.echo(f"✅ Docker image '{full_image_name}' pushed successfully!")

    except FileNotFoundError as e:
        typer.echo(f"❌ File error: {e}")
    except subprocess.CalledProcessError as e:
        typer.echo(f"❌ Error during Docker operation: {e}")
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    app()

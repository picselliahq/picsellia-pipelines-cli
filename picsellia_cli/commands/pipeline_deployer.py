import os
import subprocess
from typing import Optional

import typer
from picsellia_cli.utils.session_manager import session_manager
from picsellia import Client
from picsellia.types.enums import ProcessingType

app = typer.Typer(
    help="Deploy pipelines: build, push Docker image, and register on Picsellia."
)


def build_and_push_docker_image(pipeline_name: str, image_name: str, image_tag: str):
    """
    Build and push the Docker image for a given pipeline, excluding virtual environments.
    """
    full_image_name = f"{image_name}:{image_tag}"
    repo_root = os.getcwd()
    pipeline_dir = os.path.join(repo_root, pipeline_name)

    if not os.path.exists(pipeline_dir):
        typer.echo(f"⚠️ Pipeline directory '{pipeline_dir}' not found.")
        raise typer.Exit()

    dockerfile_path = os.path.join(pipeline_dir, "Dockerfile")
    dockerignore_path = os.path.join(pipeline_dir, ".dockerignore")

    if not os.path.exists(dockerfile_path):
        typer.echo(f"⚠️ Missing Dockerfile in '{pipeline_dir}'.")
        raise typer.Exit()

    # Ensure .dockerignore exists to avoid including unnecessary files
    if not os.path.exists(dockerignore_path):
        with open(dockerignore_path, "w") as f:
            f.write(".venv/\nvenv/\n__pycache__/\n*.pyc\n*.pyo\n.DS_Store\n")

    # Build Docker Image
    typer.echo(
        f"🚀 Building Docker image '{full_image_name}', excluding virtual environments..."
    )
    subprocess.run(
        ["docker", "build", "-t", full_image_name, "-f", dockerfile_path, "."],
        cwd=repo_root,
        check=True,
    )

    # Push Docker Image
    typer.echo(f"📤 Pushing Docker image '{full_image_name}'...")
    subprocess.run(["docker", "push", full_image_name], check=True)

    typer.echo(f"✅ Docker image '{full_image_name}' pushed successfully!")


def register_pipeline_on_picsellia(
    pipeline_name: str, pipeline_data: dict, cpu: int, gpu: int
):
    """
    Register the pipeline on Picsellia.

    Args:
        pipeline_name (str): Name of the pipeline.
        pipeline_data (dict): Pipeline metadata including Docker details.
        cpu (int): Default CPU allocation.
        gpu (int): Default GPU allocation.
    """
    global_data: Optional[dict] = session_manager.get_global_session()
    if not global_data:
        typer.echo("❌ Global session not initialized. Run `pipeline-cli init` first.")
        raise typer.Exit()

    try:
        client = Client(
            api_token=global_data["api_token"],
            organization_id=global_data["organization_id"],
        )

        client.create_processing(
            name=pipeline_name,
            type=ProcessingType(pipeline_data["pipeline_type"]),
            default_cpu=cpu,
            default_gpu=gpu,
            default_parameters=pipeline_data["parameters"],
            docker_image=pipeline_data["image_name"],
            docker_tag=pipeline_data["image_tag"],
            docker_flags=None,
        )

        typer.echo(
            f"✅ Pipeline '{pipeline_name}' successfully registered on Picsellia!"
        )

    except Exception as e:
        typer.echo(f"❌ Error registering pipeline on Picsellia: {e}")
        raise typer.Exit()


@app.command()
def deploy_pipeline(
    pipeline_name: str = typer.Argument(..., help="Name of the pipeline to deploy"),
    cpu: int = typer.Option(4, "--cpu", "-c", help="Default CPU allocation"),
    gpu: int = typer.Option(0, "--gpu", "-g", help="Default GPU allocation"),
):
    """
    🚀 Deploy a pipeline: build & push its Docker image, then register it on Picsellia.

    This command ensures the pipeline exists, prompts for missing Docker image details,
    builds and pushes the image, and finally registers the pipeline on Picsellia.
    """
    session_manager.ensure_session_initialized()

    # Fetch pipeline details from TinyDB
    pipeline_data = session_manager.get_pipeline(pipeline_name)
    if not pipeline_data:
        typer.echo(
            f"❌ Pipeline '{pipeline_name}' not found. Run `pipeline-cli list` to check available pipelines."
        )
        raise typer.Exit()

    # Prompt for missing Docker image details
    if not pipeline_data.get("image_name") or not pipeline_data.get("image_tag"):
        pipeline_data["image_name"] = typer.prompt("📦 Enter Docker image name")
        pipeline_data["image_tag"] = typer.prompt(
            "🏷️ Enter Docker image tag", default="latest"
        )
        session_manager.add_pipeline(pipeline_name, pipeline_data)  # Save in TinyDB

    # Build & Push Docker Image
    build_and_push_docker_image(
        pipeline_name, pipeline_data["image_name"], pipeline_data["image_tag"]
    )

    # Register the pipeline on Picsellia
    register_pipeline_on_picsellia(pipeline_name, pipeline_data, cpu, gpu)


if __name__ == "__main__":
    app()

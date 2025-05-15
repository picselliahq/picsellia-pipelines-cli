import os
import typer
from typing import Optional

from picsellia import Client

from picsellia_cli.utils.deployer import (
    get_pipeline_data,
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
)
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(
    help="Deploy training pipeline: build, push Docker image, and update model version on Picsellia."
)


def update_model_version_on_picsellia(model_version_id: str, pipeline_data: dict):
    """
    Update the existing model version in Picsellia to attach the Docker image.
    """
    global_data: Optional[dict] = session_manager.get_global_session()
    if not global_data:
        typer.echo(
            typer.style(
                "❌ Global session not initialized. Run `pipeline-cli init` first.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit()

    client = Client(
        api_token=global_data["api_token"],
        organization_name=global_data["organization_name"],
        host=global_data["host"],
    )

    model_version = client.get_model_version_by_id(model_version_id)

    model_version.update(
        docker_image_name=pipeline_data["image_name"],
        docker_tag=pipeline_data["image_tag"],
        docker_flags=["--gpus all", "--name training", "--ipc host"],
    )

    typer.echo(
        f"✅ Updated model version (ID: {model_version_id}) with Docker image info."
    )


@app.command()
def deploy_training(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the training pipeline to deploy"
    ),
):
    """
    🚀 Deploy a training pipeline: build & push its Docker image, then update the model version in Picsellia.
    """
    pipeline_data = get_pipeline_data(pipeline_name)
    pipeline_data = prompt_docker_image_if_missing(pipeline_name, pipeline_data)

    repo_root = os.getcwd()
    pipeline_dir = os.path.join(repo_root, "pipelines", pipeline_name)

    # Build & Push
    build_and_push_docker_image(
        pipeline_dir,
        pipeline_data["image_name"],
        pipeline_data["image_tag"],
        force_login=True,
    )

    # Update model version
    if "model_version_id" not in pipeline_data:
        typer.echo(
            typer.style(
                "❌ No model_version_id associated with this pipeline. Did you properly initialize it?",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit()

    update_model_version_on_picsellia(pipeline_data["model_version_id"], pipeline_data)


if __name__ == "__main__":
    app()

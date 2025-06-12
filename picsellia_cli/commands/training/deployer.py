import os

import typer
from picsellia import Client

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
)
from picsellia_cli.utils.env_utils import require_env_var, ensure_env_vars
from picsellia_cli.utils.pipeline_config import PipelineConfig

app = typer.Typer(
    help="Deploy training pipeline: build, push Docker image, and update model version on Picsellia."
)


def update_model_version_on_picsellia(
    client: Client, model_version_id: str, image_name: str, image_tag: str
):
    """
    Update the existing model version in Picsellia to attach the Docker image.
    """
    model_version = client.get_model_version_by_id(model_version_id)

    model_version.update(
        docker_image_name=image_name,
        docker_tag=image_tag,
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
    ensure_env_vars()
    config = PipelineConfig(pipeline_name)

    prompt_docker_image_if_missing(pipeline_config=config)

    image_name = config.get("docker", "image_name")
    image_tag = config.get("docker", "image_tag")
    model_version_id = config.get("model", "model_version_id")

    if not model_version_id:
        typer.echo(
            typer.style(
                "❌ No model_version_id found in config.toml. Did you initialize the pipeline properly?",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit()

    # Build & Push Docker image
    build_and_push_docker_image(
        pipeline_dir=str(config.pipeline_dir),
        image_name=image_name,
        image_tag=image_tag,
        force_login=True,
    )

    # Update model version
    client = Client(
        api_token=require_env_var("API_TOKEN"),
        organization_name=require_env_var("ORGANIZATION_NAME"),
        host=os.getenv("HOST", "https://app.picsellia.com"),
    )

    update_model_version_on_picsellia(client, model_version_id, image_name, image_tag)


if __name__ == "__main__":
    app()

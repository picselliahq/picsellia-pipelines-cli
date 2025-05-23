import typer

from picsellia import Client
from picsellia.types.enums import ProcessingType

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
)
from picsellia_cli.utils.pipeline_config import PipelineConfig

app = typer.Typer(help="Deploy a processing pipeline to Picsellia.")


def register_processing_pipeline_on_picsellia(
    config: PipelineConfig,
    cpu: int,
    gpu: int,
):
    """
    Register a processing pipeline in Picsellia.
    """
    api_token = config.env.get_api_token()
    organization_name = config.env.get_organization_name()
    host = config.env.get_host()

    if not (api_token and organization_name and host):
        typer.echo(
            "❌ Missing credentials. Ensure API_TOKEN, ORGANIZATION_NAME, and HOST are set in your .env file."
        )
        raise typer.Exit()

    client = Client(
        api_token=api_token,
        organization_name=organization_name,
        host=host,
    )

    try:
        client.create_processing(
            name=config.pipeline_name,
            type=ProcessingType(config.get("metadata", "type")),
            default_cpu=cpu,
            default_gpu=gpu,
            default_parameters=config.get_parameters(),
            docker_image=config.get("image", "image_name"),
            docker_tag=config.get("image", "image_tag"),
            docker_flags=None,
        )
        typer.echo(
            f"✅ Processing pipeline '{config.pipeline_name}' successfully registered on Picsellia!"
        )

    except Exception as e:
        typer.echo(f"❌ Error registering pipeline on Picsellia: {e}")
        raise typer.Exit()


@app.command()
def deploy_processing(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the processing pipeline to deploy"
    ),
):
    """
    🚀 Deploy a processing pipeline: build & push its Docker image, then register it on Picsellia.
    """
    config = PipelineConfig(pipeline_name)

    # Prompt user for image name/tag if not filled
    prompt_docker_image_if_missing(
        pipeline_config=config,
    )
    config.save()

    cpu = int(typer.prompt("Enter CPU allocation", default=4))
    gpu = int(typer.prompt("Enter GPU allocation", default=0))

    build_and_push_docker_image(
        pipeline_dir=str(config.pipeline_dir),
        image_name=config.get("image", "image_name"),
        image_tag=config.get("image", "image_tag"),
        force_login=False,
    )

    register_processing_pipeline_on_picsellia(
        config=config,
        cpu=cpu,
        gpu=gpu,
    )


if __name__ == "__main__":
    app()

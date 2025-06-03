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
    pipeline_config: PipelineConfig,
):
    """
    Register a processing pipeline in Picsellia.
    """
    api_token = pipeline_config.env.get_api_token()
    organization_name = pipeline_config.env.get_organization_name()
    host = pipeline_config.env.get_host()

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
            name=pipeline_config.pipeline_name,
            type=ProcessingType(pipeline_config.get("metadata", "type")),
            default_cpu=int(pipeline_config.get("docker", "cpu")),
            default_gpu=int(pipeline_config.get("docker", "gpu")),
            default_parameters=pipeline_config.extract_default_parameters(),
            docker_image=pipeline_config.get("docker", "image_name"),
            docker_tag=pipeline_config.get("docker", "image_tag"),
            docker_flags=None,
        )
        typer.echo(
            f"✅ Processing pipeline '{pipeline_config.pipeline_name}' successfully registered on Picsellia!"
        )

    except Exception as e:
        typer.echo(f"❌ Error registering pipeline on Picsellia: {e}")
        raise typer.Exit()


def prompt_allocation_if_missing(pipeline_config: PipelineConfig):
    docker_section = pipeline_config.config.get("docker", {})
    cpu = docker_section.get("cpu", "")
    gpu = docker_section.get("gpu", "")

    if cpu and gpu:
        typer.echo(f"🔧 Current Docker config: CPU: {cpu} | GPU: {gpu}")
        if not typer.confirm(
            "Do you want to keep the current Docker configuration?", default=True
        ):
            cpu = typer.prompt("🧠 Enter CPU config", default=cpu)
            gpu = typer.prompt("💻 Enter GPU config", default=gpu)
    else:
        if not cpu:
            cpu = typer.prompt("🧠 Enter CPU config")
        if not gpu:
            gpu = typer.prompt("💻 Enter GPU config")

    typer.echo(f"🔧 Docker config will be saved as: CPU: {cpu} | GPU: {gpu}")
    pipeline_config.config["docker"]["cpu"] = cpu
    pipeline_config.config["docker"]["gpu"] = gpu

    pipeline_config.save()


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
    prompt_allocation_if_missing(
        pipeline_config=config,
    )

    build_and_push_docker_image(
        pipeline_dir=str(config.pipeline_dir),
        image_name=config.get("docker", "image_name"),
        image_tag=config.get("docker", "image_tag"),
        force_login=False,
    )

    register_processing_pipeline_on_picsellia(
        pipeline_config=config,
    )


if __name__ == "__main__":
    app()

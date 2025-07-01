import os

import typer

from picsellia import Client
from picsellia.types.enums import ProcessingType

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
)
from picsellia_cli.utils.env_utils import require_env_var, ensure_env_vars
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia.exceptions import ResourceConflictError


def deploy_processing(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the processing pipeline to deploy"
    ),
):
    """
    🚀 Deploy a processing pipeline: build & push its Docker image, then register it on Picsellia.
    """
    ensure_env_vars()
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
        force_login=True,
    )

    register_processing_pipeline_on_picsellia(
        pipeline_config=config,
    )


def register_processing_pipeline_on_picsellia(
    pipeline_config: PipelineConfig,
):
    """
    Register a processing pipeline in Picsellia.
    """
    api_token = require_env_var("PICSELLIA_API_TOKEN")
    organization_name = require_env_var("PICSELLIA_ORGANIZATION_NAME")
    host = os.getenv("PICSELLIA_HOST", "https://app.picsellia.com")

    client = Client(
        api_token=api_token,
        organization_name=organization_name,
        host=host,
    )

    # Compute docker flags
    docker_flags = None
    try:
        gpu_count = int(pipeline_config.get("docker", "gpu"))
        if gpu_count > 0:
            docker_flags = ["--gpus=all", "--ipc=host"]
    except ValueError:
        typer.echo(
            "⚠️ Could not parse GPU value from pipeline config. Skipping docker flags."
        )

    try:
        client.create_processing(
            name=pipeline_config.pipeline_name,
            description=pipeline_config.get("metadata", "description"),
            type=ProcessingType(pipeline_config.get("metadata", "type")),
            default_cpu=int(pipeline_config.get("docker", "cpu")),
            default_gpu=int(pipeline_config.get("docker", "gpu")),
            default_parameters=pipeline_config.extract_default_parameters(),
            docker_image=pipeline_config.get("docker", "image_name"),
            docker_tag=pipeline_config.get("docker", "image_tag"),
            docker_flags=docker_flags,
        )
        typer.echo(
            f"✅ Processing pipeline '{pipeline_config.pipeline_name}' successfully registered on Picsellia!"
        )

    except ResourceConflictError as e:
        typer.echo(f"⚠️ Processing '{pipeline_config.pipeline_name}' already exists.")
        if typer.confirm(
            "Do you want to update the existing processing?", default=True
        ):
            processing = client.get_processing(name=pipeline_config.pipeline_name)
            processing.update(
                description=pipeline_config.get("metadata", "description"),
                default_cpu=int(pipeline_config.get("docker", "cpu")),
                default_gpu=int(pipeline_config.get("docker", "gpu")),
                default_parameters=pipeline_config.extract_default_parameters(),
                docker_image=pipeline_config.get("docker", "image_name"),
                docker_tag=pipeline_config.get("docker", "image_tag"),
            )
            typer.echo(
                f"🔁 Processing '{pipeline_config.pipeline_name}' updated successfully!"
            )
            return
        typer.echo(f"❌ Error registering pipeline: {e}")
        raise typer.Exit()

    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}")
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

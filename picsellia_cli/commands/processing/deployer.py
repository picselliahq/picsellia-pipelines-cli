import typer

from picsellia import Client
from picsellia.types.enums import ProcessingType
from picsellia.exceptions import ResourceConflictError

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
    bump_pipeline_version,
)
from picsellia_cli.utils.env_utils import ensure_env_vars, get_available_envs
from picsellia_cli.utils.pipeline_config import PipelineConfig


def deploy_processing(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the processing pipeline to deploy"
    ),
    host: str = typer.Option(None, help="If provided, deploy only to this host"),
):
    """
    🚀 Deploy a processing pipeline to all available environments in the .env.
    """
    ensure_env_vars()
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)

    prompt_docker_image_if_missing(pipeline_config=pipeline_config)
    bump_pipeline_version(pipeline_config=pipeline_config)
    prompt_allocation_if_missing(pipeline_config=pipeline_config)

    version = pipeline_config.get("metadata", "version")
    image_name = pipeline_config.get("docker", "image_name")

    tags_to_push = [version]
    if "-rc" in version:
        tags_to_push.append("test")
    else:
        tags_to_push.append("latest")

    build_and_push_docker_image(
        pipeline_dir=pipeline_config.pipeline_dir,
        image_name=image_name,
        image_tags=tags_to_push,
        force_login=True,
    )

    all_envs = get_available_envs()
    target_envs = (
        [env for env in all_envs if env["suffix"] == host.upper()] if host else all_envs
    )

    if host and not target_envs:
        raise typer.Exit(f"❌ No environment found for host '{host}'")

    for env in target_envs:
        typer.echo(f"\n🌍 Deploying on: {env['host']}")
        try:
            register_pipeline_on_host(
                pipeline_config=pipeline_config,
                api_token=env["api_token"],
                organization_name=env["organization_name"],
                host=env["host"],
            )
        except Exception as e:
            typer.echo(f"❌ Failed to register on {env['host']}: {e}")


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

    pipeline_config.config["docker"]["cpu"] = cpu
    pipeline_config.config["docker"]["gpu"] = gpu
    pipeline_config.save()


def register_pipeline_on_host(
    pipeline_config: PipelineConfig,
    api_token: str,
    organization_name: str,
    host: str,
):
    client = Client(
        api_token=api_token,
        organization_name=organization_name,
        host=host,
    )

    docker_flags = None
    try:
        gpu_count = int(pipeline_config.get("docker", "gpu"))
        if gpu_count > 0:
            docker_flags = ["--gpus=all", "--ipc=host"]
    except ValueError:
        typer.echo("⚠️ Invalid GPU config, skipping docker flags.")

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
            f"✅ Registered pipeline '{pipeline_config.pipeline_name}' on {host}"
        )

    except ResourceConflictError:
        typer.echo(
            f"⚠️ Pipeline '{pipeline_config.pipeline_name}' already exists on {host}"
        )
        if typer.confirm("Update existing pipeline?", default=True):
            processing = client.get_processing(name=pipeline_config.pipeline_name)
            processing.update(
                description=pipeline_config.get("metadata", "description"),
                default_cpu=int(pipeline_config.get("docker", "cpu")),
                default_gpu=int(pipeline_config.get("docker", "gpu")),
                default_parameters=pipeline_config.extract_default_parameters(),
                docker_image=pipeline_config.get("docker", "image_name"),
                docker_tag=pipeline_config.get("docker", "image_tag"),
            )
            typer.echo(f"🔁 Updated pipeline on {host}")
        else:
            raise typer.Exit("❌ Aborted by user.")

    except Exception as e:
        raise typer.Exit(f"❌ Error while registering on {host}: {e}")

import typer
from picsellia import Client

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
    bump_pipeline_version,
)
from picsellia_cli.utils.env_utils import ensure_env_vars, get_available_envs
from picsellia_cli.utils.pipeline_config import PipelineConfig


def deploy_training(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the training pipeline to deploy"
    ),
    host: str = typer.Option(None, help="If provided, deploy only to this host"),
):
    """
    🚀 Deploy a training pipeline: build & push its Docker image, then update the model version in Picsellia.
    """
    ensure_env_vars()
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)

    prompt_docker_image_if_missing(pipeline_config=pipeline_config)
    bump_pipeline_version(pipeline_config=pipeline_config)

    version = pipeline_config.get("metadata", "version")
    image_name = pipeline_config.get("docker", "image_name")

    tags_to_push = [version, "test" if "-rc" in version else "latest"]

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
        typer.echo(f"\n🌍 Deploying training on: {env['host']} [{env['suffix']}]")
        try:
            model_version_id = get_model_version_id_for_env(
                env_suffix=env["suffix"], pipeline_config=pipeline_config
            )
            if not model_version_id:
                raise typer.Exit(
                    f"❌ Missing model_version_id for {env['suffix']} "
                    f"(set PICSELLIA_MODEL_VERSION_ID_{env['suffix']} in .env or 'model.model_version_id' in config.toml)."
                )

            client = Client(
                api_token=env["api_token"],
                organization_name=env["organization_name"],
                host=env["host"],
            )

            register_training_on_host(
                pipeline_config=pipeline_config,
                client=client,
                model_version_id=model_version_id,
            )
        except Exception as e:
            typer.echo(f"❌ Failed on {env['host']}: {e}")


def get_model_version_id_for_env(
    env_suffix: str, pipeline_config: PipelineConfig
) -> str | None:
    try:
        mv_cfg = pipeline_config.get("model", "model_version_id")
        if mv_cfg:
            return mv_cfg
    except KeyError:
        pass

    return (
        typer.prompt(
            typer.style(f"🧪 Model version ID for {env_suffix}", fg=typer.colors.CYAN),
            default="",
        )
        or None
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


def register_training_on_host(
    pipeline_config: PipelineConfig,
    client: Client,
    model_version_id: str,
):
    image_name = pipeline_config.get("docker", "image_name")
    image_tag = pipeline_config.get("docker", "version")

    model_version = client.get_model_version_by_id(model_version_id)
    model_version.update(
        docker_image_name=image_name,
        docker_tag=image_tag,
        docker_flags=["--gpus all", "--name training", "--ipc host"],
    )

    typer.echo(
        f"✅ Updated model version on {client.connexion.host} (ID: {model_version_id}) "
        f"→ image={image_name}:{image_tag}"
    )

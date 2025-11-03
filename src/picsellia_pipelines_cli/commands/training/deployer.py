import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

from picsellia_pipelines_cli.utils.deployer import (
    Bump,
    build_and_push_docker_image,
    bump_pipeline_version,
    prompt_docker_image_if_missing,
)
from picsellia_pipelines_cli.utils.env_utils import Environment, get_env_config
from picsellia_pipelines_cli.utils.logging import bullet, kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig


def deploy_training(
    pipeline_name: str,
    env: Environment,
    organization: str | None = None,
    bump: Bump | None = None,
):
    """Deploy a training pipeline to Picsellia.

    Steps performed:
        1. Ensure environment variables and load pipeline config.
        2. Display pipeline metadata (name, type, description).
        3. Ensure model + version exist on the target host(s).
        4. Build & push Docker image (new version + "latest" or "test").
        5. Update model version with Docker details and default parameters.

    Args:
        pipeline_name: The name of the pipeline project to deploy.
        env: The environment to deploy.
        organization: The organization to deploy to.
        bump: The version to bump the pipeline from.

    Raises:
        typer.Exit: If no environment matches the provided host.
    """
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)

    # ── Environment ─────────────────────────────────────────────────────────
    section("🌍 Environment")
    env_config = get_env_config(organization=organization, env=env)
    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    # ── Pipeline details ─────────────────────────────────────────────────────
    section("🧩 Pipeline")
    kv("Type", pipeline_config.get("metadata", "type"))
    kv("Description", pipeline_config.get("metadata", "description"))

    prompt_docker_image_if_missing(pipeline_config=pipeline_config)
    new_version = bump_pipeline_version(pipeline_config=pipeline_config, bump=bump)
    runtime_tag = "test" if "-rc" in new_version else "latest"
    tags_to_push = [new_version, runtime_tag]

    image_name = pipeline_config.get("docker", "image_name")

    # ── Ensure model/version exist before build ──────────────────────────────
    section("Model / Version (Pre-check)")
    bullet(f"Checking {env_config['host']}...", accent=True)
    client = Client(
        api_token=env_config["api_token"],
        organization_name=env_config["organization_name"],
        host=env_config["host"],
    )
    _ensure_model_and_version_on_host(
        client=client,
        cfg=pipeline_config,
    )

    section("Docker")
    kv("Image", image_name)
    kv("Will push tags", ", ".join(tags_to_push))

    bullet("Building and pushing image…", accent=True)
    build_and_push_docker_image(
        pipeline_dir=pipeline_config.pipeline_dir,
        image_name=image_name,
        image_tags=tags_to_push,
        force_login=True,
    )
    bullet("Image pushed ✅", accent=False)

    pipeline_config.config["metadata"]["version"] = str(new_version)
    pipeline_config.config["docker"]["image_tag"] = str(runtime_tag)
    pipeline_config.save()

    # ── Register/Update Model + Version with Docker info ────────────────────
    section("Model / Version (Update)")
    bullet(f"→ {env_config['host']}", accent=True)
    try:
        client = Client(
            api_token=env_config["api_token"],
            organization_name=env_config["organization_name"],
            host=env_config["host"],
        )
        _ensure_model_and_version_on_host(
            client=client,
            cfg=pipeline_config,
            image_name=image_name,
            image_tag=pipeline_config.get("docker", "image_tag"),
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_model_settings(cfg: PipelineConfig) -> dict:
    """Extract model settings from the pipeline config.

    Expected keys in `config.toml`:
        [model]
        model_name = "..."
        model_version_name = "..."
        framework = "ONNX" | "PYTORCH" | "TENSORFLOW" (optional, default ONNX)
        inference_type = "OBJECT_DETECTION" | "CLASSIFICATION" | ... (optional, default OBJECT_DETECTION)

    Args:
        cfg: Pipeline configuration object.

    Returns:
        dict: Model settings with keys `model_name`, `version_name`, `framework`, `inference_type`.

    Raises:
        typer.Exit: If required fields are missing.
    """
    model_name = cfg.get("model_version", "origin_name")
    version_name = cfg.get("model_version", "name")
    framework = (cfg.get("model_version", "framework") or "NOT_CONFIGURED").upper()
    inference_type = (
        cfg.get("model_version", "inference_type") or "NOT_CONFIGURED"
    ).upper()

    if not model_name or not version_name:
        typer.echo(
            "Missing model configuration.\n"
            "Please provide:\n"
            "model_version.name, model_version.origin_name, model_version.framework, and model_version.inference_type"
        )
        raise typer.Exit()

    return {
        "model_name": model_name,
        "version_name": version_name,
        "framework": framework,
        "inference_type": inference_type,
    }


def _ensure_model_and_version_on_host(
    client: Client,
    cfg: PipelineConfig,
    image_name: str | None = None,
    image_tag: str | None = None,
):
    """Ensure the model and version exist on the target host, and update them with Docker info.

    Args:
        client: Authenticated Picsellia client.
        cfg: Pipeline configuration object.
        image_name: Docker image name to attach.
        image_tag: Docker tag to attach.
    """
    model_settings = _get_model_settings(cfg)
    defaults = cfg.extract_default_parameters()
    docker_flags = ["--gpus all", "--ipc host", "--name training"]
    created = False

    try:
        model = client.get_model(name=model_settings["model_name"])
    except ResourceNotFoundError:
        model = client.create_model(name=model_settings["model_name"])
        created = True

    try:
        mv = model.get_version(version=model_settings["version_name"])
    except ResourceNotFoundError:
        mv = model.create_version(
            name=model_settings["version_name"],
            framework=Framework[model_settings["framework"]],
            type=InferenceType[model_settings["inference_type"]],
            docker_image_name=image_name,
            docker_tag=image_tag,
            docker_flags=docker_flags,
            base_parameters=defaults or {},
        )
        created = True

    if not created:
        mv.update(
            name=model_settings["version_name"],
            framework=Framework[model_settings["framework"]],
            type=InferenceType[model_settings["inference_type"]],
            docker_image_name=image_name,
            docker_tag=image_tag,
            docker_flags=docker_flags,
            base_parameters=defaults or {},
        )

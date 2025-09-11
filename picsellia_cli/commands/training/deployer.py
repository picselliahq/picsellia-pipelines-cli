import typer

from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
    bump_pipeline_version,
)
from picsellia_cli.utils.env_utils import ensure_env_vars, get_available_envs
from picsellia_cli.utils.logging import kv, bullet, section
from picsellia_cli.utils.pipeline_config import PipelineConfig


def deploy_training(
    pipeline_name: str,
    host: str = "prod",
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
        host: Target environment (e.g., "prod", "staging"). Defaults to "prod".

    Raises:
        typer.Exit: If no environment matches the provided host.
    """
    ensure_env_vars(host=host)
    cfg = PipelineConfig(pipeline_name=pipeline_name)

    # ── Pipeline details ─────────────────────────────────────────────────────
    section("Pipeline")
    kv("Name", cfg.get("metadata", "name"))
    kv("Type", cfg.get("metadata", "type"))
    kv("Description", cfg.get("metadata", "description"))

    # ── Targets ─────────────────────────────────────────────────────────────
    section("Targets")
    all_envs = get_available_envs()
    targets = (
        [env for env in all_envs if env["suffix"] == host.upper()] if host else all_envs
    )
    if host and not targets:
        typer.echo(f"No environment found for host '{host}'")
        raise typer.Exit()

    for env in targets:
        kv(env["suffix"], f"{env['organization_name']} @ {env['host']}")

    # ── Ensure model/version exist before build ──────────────────────────────
    section("Model / Version (Pre-check)")
    for env in targets:
        bullet(f"Checking {env['host']}...", accent=True)
        client = Client(
            api_token=env["api_token"],
            organization_name=env["organization_name"],
            host=env["host"],
        )
        _ensure_model_and_version_on_host(
            client=client,
            cfg=cfg,
            image_name="placeholder",
            image_tag="placeholder",
        )

    # ── Docker build & push ─────────────────────────────────────────────────
    prompt_docker_image_if_missing(pipeline_config=cfg)
    new_version = bump_pipeline_version(pipeline_config=cfg)

    image_name = cfg.get("docker", "image_name")
    tags_to_push = [new_version, "test" if "-rc" in new_version else "latest"]

    section("Docker")
    kv("Image", image_name)
    kv("Will push tags", ", ".join(tags_to_push))

    bullet("Building and pushing image...", accent=True)
    build_and_push_docker_image(
        pipeline_dir=cfg.pipeline_dir,
        image_name=image_name,
        image_tags=tags_to_push,
        force_login=True,
    )
    bullet("Image pushed successfully")

    cfg.config["metadata"]["version"] = str(new_version)
    cfg.config["docker"]["image_tag"] = str(new_version)
    cfg.save()

    # ── Register/Update Model + Version with Docker info ────────────────────
    section("Model / Version (Update)")
    for env in targets:
        bullet(f"→ {env['host']}", accent=True)
        try:
            client = Client(
                api_token=env["api_token"],
                organization_name=env["organization_name"],
                host=env["host"],
            )
            _ensure_model_and_version_on_host(
                client=client,
                cfg=cfg,
                image_name=image_name,
                image_tag=cfg.get("docker", "image_tag"),
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
        raise typer.Exit(
            "Missing model configuration.\n"
            "Please provide:\n"
            "model_version.name, model_version.origin_name, model_version.framework, and model_version.inference_type"
        )

    return {
        "model_name": model_name,
        "version_name": version_name,
        "framework": framework,
        "inference_type": inference_type,
    }


def _ensure_model_and_version_on_host(
    client: Client,
    cfg: PipelineConfig,
    image_name: str,
    image_tag: str,
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

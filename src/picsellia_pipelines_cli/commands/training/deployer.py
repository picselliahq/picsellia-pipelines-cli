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


def _validate_enum_name(value: str, enum_cls, field_name: str) -> str:
    candidate = (value or "NOT_CONFIGURED").upper()
    if candidate not in enum_cls.__members__:
        allowed = ", ".join(enum_cls.__members__.keys())
        typer.echo(f"❌ Invalid {field_name} '{value}'. Allowed values: {allowed}.")
        raise typer.Exit(code=1)
    return candidate


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

    model_targets = _get_model_targets(pipeline_config)
    section("Model targets")
    kv("Count", str(len(model_targets)))
    for idx, target in enumerate(model_targets, start=1):
        kv(
            f"Target {idx}",
            f"{target['origin_name']}:{target['name']} "
            f"[{target['framework']}/{target['inference_type']}]",
        )

    # ── Ensure model/version exist before build ──────────────────────────────
    section("Model / Version (Pre-check)")
    bullet(f"Checking {env_config['host']}...", accent=True)
    client = Client(
        api_token=env_config["api_token"],
        organization_name=env_config["organization_name"],
        host=env_config["host"],
        session=env_config["session"]
    )
    _ensure_model_versions_on_host(
        client=client,
        cfg=pipeline_config,
        model_targets=model_targets,
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
            session=env_config["session"]
        )
        _ensure_model_versions_on_host(
            client=client,
            cfg=pipeline_config,
            model_targets=model_targets,
            image_name=image_name,
            image_tag=pipeline_config.get("docker", "image_tag"),
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_model_target(target: dict, index: int | None = None) -> dict:
    """Validate and normalize a model version target from config."""
    origin_name = target.get("origin_name")
    version_name = target.get("name")
    if not origin_name or not version_name:
        prefix = f"model_versions[{index}]" if index is not None else "model_version"
        typer.echo(
            "Missing model configuration.\n"
            f"Please provide '{prefix}.origin_name' and '{prefix}.name'."
        )
        raise typer.Exit(code=1)

    framework = _validate_enum_name(
        value=target.get("framework") or "NOT_CONFIGURED",
        enum_cls=Framework,
        field_name="framework",
    )
    inference_type = _validate_enum_name(
        value=target.get("inference_type") or "NOT_CONFIGURED",
        enum_cls=InferenceType,
        field_name="inference_type",
    )
    return {
        "origin_name": origin_name,
        "name": version_name,
        "framework": framework,
        "inference_type": inference_type,
    }


def _get_model_targets(cfg: PipelineConfig) -> list[dict]:
    """Extract one or many model version targets from config.

    Supported formats:
      - Legacy single target:
            [model_version]
            origin_name = "MyModel"
            name = "v1"
      - Multi-target:
            [[model_versions]]
            origin_name = "MyModel"
            name = "v1"
            ...
    """
    config = cfg.config or {}
    raw_multi = config.get("model_versions")
    defaults = config.get("model_version") if isinstance(config.get("model_version"), dict) else {}
    if raw_multi:
        if not isinstance(raw_multi, list):
            typer.echo(
                "❌ Invalid config: 'model_versions' must be an array of tables "
                "(use [[model_versions]] in TOML)."
            )
            raise typer.Exit(code=1)
        normalized_targets: list[dict] = []
        for i, target in enumerate(raw_multi):
            if not isinstance(target, dict):
                typer.echo(f"❌ Invalid model_versions[{i}] entry.")
                raise typer.Exit(code=1)
            merged_target = {**defaults, **target}
            normalized_targets.append(
                _normalize_model_target(target=merged_target, index=i)
            )
        return normalized_targets

    single_target = config.get("model_version") or {}
    if single_target:
        if not isinstance(single_target, dict):
            typer.echo("❌ Invalid config: 'model_version' must be a table.")
            raise typer.Exit(code=1)
        return [_normalize_model_target(target=single_target)]

    typer.echo(
        "Missing model configuration.\n"
        "Please provide either:\n"
        "- [model_version] (single target)\n"
        "- [[model_versions]] (multiple targets)"
    )
    raise typer.Exit(code=1)


def _ensure_model_versions_on_host(
    client: Client,
    cfg: PipelineConfig,
    model_targets: list[dict],
    image_name: str | None = None,
    image_tag: str | None = None,
):
    """Ensure each configured model version exists and is updated on the target host.

    Args:
        client: Authenticated Picsellia client.
        cfg: Pipeline configuration object.
        model_targets: List of normalized targets from config.
        image_name: Docker image name to attach.
        image_tag: Docker tag to attach.
    """
    defaults = cfg.extract_default_parameters()
    docker_flags = ["--gpus all", "--ipc host", "--name training"]
    for target in model_targets:
        target_label = f"{target['origin_name']}:{target['name']}"
        created_version = False

        try:
            model = client.get_model(name=target["origin_name"])
        except ResourceNotFoundError:
            model = client.create_model(name=target["origin_name"])

        try:
            mv = model.get_version(version=target["name"])
        except ResourceNotFoundError:
            mv = model.create_version(
                name=target["name"],
                framework=Framework[target["framework"]],
                type=InferenceType[target["inference_type"]],
                docker_image_name=image_name,
                docker_tag=image_tag,
                docker_flags=docker_flags,
                base_parameters=defaults or {},
            )
            created_version = True
            bullet(f"Created model version {target_label}", accent=False)

        if not created_version:
            mv.update(
                name=target["name"],
                framework=Framework[target["framework"]],
                type=InferenceType[target["inference_type"]],
                docker_image_name=image_name,
                docker_tag=image_tag,
                docker_flags=docker_flags,
                base_parameters=defaults or {},
            )
            bullet(f"Updated model version {target_label}", accent=False)

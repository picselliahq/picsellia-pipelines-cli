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
from picsellia_pipelines_cli.utils.logging import bullet, hr, kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig

ModelVersionDeployResult = tuple[str, str, str]  # (target_label, status, details)


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
    default_parameters = pipeline_config.extract_default_parameters()
    precheck_results = _ensure_model_versions_on_host(
        client=client,
        model_targets=model_targets,
        default_parameters=default_parameters,
        apply_deployment=False,
    )
    _log_model_version_results(precheck_results, title="Pre-check results")

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
    section("📦 Model versions (deploy)")
    kv("Host", env_config["host"])
    deploy_results: list[ModelVersionDeployResult] = []
    try:
        client = Client(
            api_token=env_config["api_token"],
            organization_name=env_config["organization_name"],
            host=env_config["host"],
            session=env_config["session"],
        )
        deploy_results = _ensure_model_versions_on_host(
            client=client,
            model_targets=model_targets,
            default_parameters=default_parameters,
            image_name=image_name,
            image_tag=pipeline_config.get("docker", "image_tag"),
            apply_deployment=True,
        )
        _log_model_version_results(deploy_results, title="Deploy results")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        deploy_results = [
            (target["origin_name"] + ":" + target["name"], "Error", str(e))
            for target in model_targets
        ]

    section("✅ Summary")
    kv("Pipeline", pipeline_name)
    kv("Host", env_config["host"])
    kv("Docker image", f"{image_name}:{pipeline_config.get('docker', 'image_tag')}")
    kv("Pipeline version", str(new_version))
    for target_label, status, details in deploy_results:
        kv(target_label, f"{status} — {details}")
    typer.echo("")
    hr()
    typer.secho(
        f"Training pipeline '{pipeline_name}' deployed to "
        f"{len(deploy_results)} model version(s)",
        fg=typer.colors.GREEN,
        bold=True,
    )


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


_MODEL_VERSION_DEPLOY_KEYS = frozenset(
    {"origin_name", "name", "framework", "inference_type"}
)


def _model_version_section_is_defined(table: dict) -> bool:
    """True when [model_version] declares deploy fields (not just init metadata like id)."""
    return bool(_MODEL_VERSION_DEPLOY_KEYS.intersection(table.keys()))


def _dedupe_model_targets(targets: list[dict]) -> list[dict]:
    """Keep one entry per (origin_name, name); later entries override earlier ones."""
    by_key: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for target in targets:
        key = (target["origin_name"], target["name"])
        if key not in by_key:
            order.append(key)
        by_key[key] = target
    return [by_key[key] for key in order]


def _get_model_targets(cfg: PipelineConfig) -> list[dict]:
    """Extract model version targets from config.

    Use exactly one of:
      - [model_version] for a single deploy target
      - [[model_versions]] for multiple deploy targets (each row must be complete)
    """
    config = cfg.config or {}
    raw_multi = config.get("model_versions")
    single = (
        config.get("model_version")
        if isinstance(config.get("model_version"), dict)
        else {}
    )

    has_multi = bool(raw_multi)
    has_single = _model_version_section_is_defined(single)

    if has_multi and has_single:
        typer.echo(
            "❌ Ambiguous model configuration: use either [model_version] OR "
            "[[model_versions]], not both.\n"
            "  • Single target  → [model_version] with origin_name, name, framework, inference_type\n"
            "  • Many targets   → [[model_versions]] only (repeat full fields on each row)"
        )
        raise typer.Exit(code=1)

    if has_multi:
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
            normalized_targets.append(
                _normalize_model_target(target=target, index=i)
            )
        return _dedupe_model_targets(normalized_targets)

    if has_single:
        return [_normalize_model_target(target=single)]

    typer.echo(
        "Missing model configuration.\n"
        "Define exactly one of:\n"
        "  [model_version]        — single target\n"
        "  [[model_versions]]     — multiple targets"
    )
    raise typer.Exit(code=1)


def _log_model_version_results(
    results: list[ModelVersionDeployResult], *, title: str
) -> None:
    """Print per-target deploy outcomes in a consistent key–value layout."""
    if not results:
        return
    typer.echo("")
    typer.echo(typer.style(title, bold=True))
    for target_label, status, details in results:
        level = "ok" if status in {"Created", "Updated", "Verified"} else "error"
        kv("Target", target_label, level=level)
        kv("Status", status, level=level)
        kv("Details", details, level=level)
        typer.echo("")


def _ensure_model_versions_on_host(
    client: Client,
    model_targets: list[dict],
    default_parameters: dict,
    image_name: str | None = None,
    image_tag: str | None = None,
    *,
    apply_deployment: bool = False,
) -> list[ModelVersionDeployResult]:
    """Ensure each configured model version exists and optionally deploy to it.

    Args:
        client: Authenticated Picsellia client.
        model_targets: List of normalized targets from config.
        default_parameters: Pipeline default hyperparameters (extracted once upstream).
        image_name: Docker image name to attach (deploy phase only).
        image_tag: Docker tag to attach (deploy phase only).
        apply_deployment: When False, only verify/create resources without updating
            existing versions. When True, push docker image + parameters to each target.

    Returns:
        One (target_label, status, details) tuple per configured target.
    """
    results: list[ModelVersionDeployResult] = []
    docker_flags = ["--gpus all", "--ipc host", "--name training"]
    base_parameters = default_parameters or {}

    for target in model_targets:
        target_label = f"{target['origin_name']}:{target['name']}"
        framework = Framework[target["framework"]]
        inference_type = InferenceType[target["inference_type"]]

        try:
            model = client.get_model(name=target["origin_name"])
        except ResourceNotFoundError:
            model = client.create_model(name=target["origin_name"])

        version_existed = True
        try:
            mv = model.get_version(version=target["name"])
        except ResourceNotFoundError:
            version_existed = False
            mv = model.create_version(
                name=target["name"],
                framework=framework,
                type=inference_type,
                docker_image_name=image_name if apply_deployment else None,
                docker_tag=image_tag if apply_deployment else None,
                docker_flags=docker_flags if apply_deployment else None,
                base_parameters=base_parameters,
            )

        if not apply_deployment:
            if version_existed:
                results.append(
                    (target_label, "Verified", "Model version already exists")
                )
            else:
                results.append(
                    (
                        target_label,
                        "Created",
                        "Model version created (docker will be set on deploy)",
                    )
                )
            continue

        docker_ref = (
            f"{image_name}:{image_tag}"
            if image_name and image_tag
            else (image_name or "not set")
        )
        if version_existed:
            mv.update(
                name=target["name"],
                framework=framework,
                type=inference_type,
                docker_image_name=image_name,
                docker_tag=image_tag,
                docker_flags=docker_flags,
                base_parameters=base_parameters,
            )
            results.append(
                (
                    target_label,
                    "Updated",
                    f"{target['framework']}/{target['inference_type']} — {docker_ref}",
                )
            )
        else:
            results.append(
                (
                    target_label,
                    "Created",
                    f"{target['framework']}/{target['inference_type']} — {docker_ref}",
                )
            )

    return results

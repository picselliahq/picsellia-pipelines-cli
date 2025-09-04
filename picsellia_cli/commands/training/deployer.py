import typer
from typing import Optional

from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
    bump_pipeline_version,
)
from picsellia_cli.utils.env_utils import ensure_env_vars, get_available_envs
from picsellia_cli.utils.logging import kv, bullet, section, hr
from picsellia_cli.utils.pipeline_config import PipelineConfig


def deploy_training(
    pipeline_name: str,
    host: str = "prod",
):
    """
    🚀 Deploy a training pipeline:
      1) Build & push Docker image (version + latest/test)
      2) Ensure Model + Model Version on Picsellia (create if missing, else update)
      3) Attach docker image/tag and default parameters to the model version
    """
    ensure_env_vars(host=host)
    cfg = PipelineConfig(pipeline_name=pipeline_name)

    # ── Pipeline details ─────────────────────────────────────────────────────
    section("🧩 Pipeline")
    kv("Name", cfg.get("metadata", "name"))
    kv("Type", cfg.get("metadata", "type"))
    kv("Description", cfg.get("metadata", "description"))

    # ── Docker build & push ─────────────────────────────────────────────────
    prompt_docker_image_if_missing(pipeline_config=cfg)
    bump_pipeline_version(pipeline_config=cfg)

    version = cfg.get("metadata", "version")
    image_name = cfg.get("docker", "image_name")

    tags_to_push = [version, "test" if "-rc" in version else "latest"]

    section("🐳 Docker")
    kv("Image", image_name)
    kv("Will push tags", ", ".join(tags_to_push))

    bullet("Building and pushing image…", accent=True)
    build_and_push_docker_image(
        pipeline_dir=cfg.pipeline_dir,
        image_name=image_name,
        image_tags=tags_to_push,
        force_login=True,
    )
    bullet("Image pushed ✅")

    # ── Targets ─────────────────────────────────────────────────────────────
    section("🌍 Targets")
    all_envs = get_available_envs()
    print(f"all_envs: {all_envs}")
    targets = (
        [env for env in all_envs if env["suffix"] == (host or "").upper()]
        if host
        else all_envs
    )
    print(f"targets: {targets}")
    if host and not targets:
        raise typer.Exit(f"❌ No environment found for host '{host}'")

    for env in targets:
        kv(env["suffix"], f"{env['organization_name']} @ {env['host']}")

    # ── Register/Update Model + Version on each host ────────────────────────
    section("📦 Model / Version (Create or Update)")
    results: list[tuple[str, str]] = []

    for env in targets:
        bullet(f"→ {env['host']}", accent=True)
        try:
            client = Client(
                api_token=env["api_token"],
                organization_name=env["organization_name"],
                host=env["host"],
            )
            status = _ensure_model_and_version_on_host(
                client=client,
                cfg=cfg,
                image_name=image_name,
                image_tag=cfg.get("docker", "image_tag"),
            )
            kv("Result", status)
            results.append((env["host"], status))
        except Exception as e:
            kv("Result", "Error")
            kv("Info", str(e))
            results.append((env["host"], f"Error: {e}"))

    # ── Summary ─────────────────────────────────────────────────────────────
    section("✅ Summary")
    for host_url, status in results:
        bullet(f"{host_url} — {status}")
    hr()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _infer_docker_flags(cfg: PipelineConfig) -> Optional[list[str]]:
    """Derive docker flags from GPU needs."""
    try:
        gpu = int(cfg.get("docker", "gpu") or 0)
        if gpu > 0:
            return ["--gpus all", "--ipc host"]
    except Exception:
        pass
    return None


def _get_model_settings(cfg: PipelineConfig) -> dict:
    """
    Read model settings from config.toml:
      [model]
      model_name = "..."
      model_version_name = "..."
      framework = "ONNX" | "PYTORCH" | "TENSORFLOW" (optional, default ONNX)
      inference_type = "OBJECT_DETECTION" | "CLASSIFICATION" | ... (optional, default OBJECT_DETECTION)
    """
    model_name = cfg.get("model_version", "name")
    version_name = cfg.get("model_version", "origin_name")
    framework = (cfg.get("model_version", "framework") or "ONNX").upper()
    inference_type = (
        cfg.get("model_version", "inference_type") or "OBJECT_DETECTION"
    ).upper()

    if not model_name or not version_name:
        raise typer.Exit(
            "❌ Missing model configuration.\n"
            "Provide:\n"
            "  model_version.name and model_version.origin_name and model_version.framework and model_version.inference_type)."
        )

    return {
        "model_name": model_name,
        "version_name": version_name,
        "framework": framework,
        "inference_type": inference_type,
    }


def _model_get_version_safe(model, version_name: str):
    """
    Try multiple signatures to fetch a model version by name.
    """
    for kwargs in (
        {"version_name": version_name},
        {"version": version_name},
    ):
        try:
            return model.get_version(**kwargs)
        except TypeError:
            continue
        except ResourceNotFoundError:
            raise
        except Exception:
            continue
    # last resort: positional (SDK-dependent)
    try:
        return model.get_version(version_name)  # type: ignore[arg-type]
    except Exception:
        raise ResourceNotFoundError("Model version not found")


def _ensure_model_and_version_on_host(
    client: Client,
    cfg: PipelineConfig,
    image_name: str,
    image_tag: str,
) -> str:
    """
    Ensure the model + version exist on the target host, then update the version with docker info.
    Returns a status summary string.
    """
    model_settings = _get_model_settings(cfg)
    defaults = cfg.extract_default_parameters()
    docker_flags = _infer_docker_flags(cfg)

    # Shortcut: update a specific version by id if provided
    if model_settings["origin_name"] and model_settings["name"]:
        mv = client.get_model(name=model_settings["origin_name"]).get_version(
            version=model_settings["name"]
        )
        mv.update(
            docker_image_name=image_name,
            docker_tag=image_tag,
            docker_flags=docker_flags,
            base_parameters=defaults or {},
        )
        return f"Updated existing version {mv.name} (origin_name={mv.origin_name})"

    # Ensure model
    created_model = False
    try:
        model = client.get_model(name=model_settings["model_name"])
    except ResourceNotFoundError:
        model = client.create_model(name=model_settings["model_name"])
        created_model = True

    # Ensure version
    created_version = False
    try:
        mv = _model_get_version_safe(model, model_settings["version_name"])
    except ResourceNotFoundError:
        mv = model.create_version(
            name=model_settings["version_name"],
            framework=Framework[model_settings["framework"]],
            type=InferenceType[model_settings["inference_type"]],
            base_parameters=defaults or {},
        )
        created_version = True

    # Update docker infos (+ refresh base params on update too)
    mv.update(
        docker_image_name=image_name,
        docker_tag=image_tag,
        docker_flags=docker_flags,
        base_parameters=defaults or {},
    )

    # Pretty status
    parts = []
    parts.append("Created model" if created_model else "Model ok")
    parts.append("Created version" if created_version else "Version ok")
    parts.append(f"image={image_name}:{image_tag}")

    # Optional URL
    try:
        org_id = client.connexion.organization_id
        url = f"{client.connexion.host}/{org_id}/model/{model.id}/version/{mv.id}"
        parts.append(f"url={url}")
    except Exception:
        pass

    return " · ".join(parts)

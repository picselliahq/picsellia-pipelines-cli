from typing import Optional

import typer

from picsellia import Client
from picsellia.types.enums import ProcessingType
from picsellia.exceptions import ResourceConflictError

from picsellia_cli.utils.deployer import (
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
    bump_pipeline_version,
)
from picsellia_cli.utils.env_utils import (
    get_env_config,
    Environment,
    resolve_env,
    get_organization_for_env,
)
from picsellia_cli.utils.logging import kv, bullet, section, hr
from picsellia_cli.utils.pipeline_config import PipelineConfig


def deploy_processing(
    pipeline_name: str,
    env: Environment,
    organization: str | None = None,
):
    """
    🚀 Deploy a processing pipeline to all available environments in the .env.
    """
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)

    # ── Environment ─────────────────────────────────────────────────────────
    section("🌍 Environment")
    selected_env = resolve_env(env or Environment.PROD.value)
    if not organization:
        organization = get_organization_for_env(env=selected_env)
    env_config = get_env_config(organization=organization, env=selected_env)

    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    # ── Pipeline details ─────────────────────────────────────────────────────
    section("🧩 Pipeline")
    kv("Type", pipeline_config.get("metadata", "type"))
    kv("Description", pipeline_config.get("metadata", "description"))

    prompt_docker_image_if_missing(pipeline_config=pipeline_config)
    new_version = bump_pipeline_version(pipeline_config=pipeline_config)
    prompt_allocation_if_missing(pipeline_config=pipeline_config)

    image_name = pipeline_config.get("docker", "image_name")

    tags_to_push = [new_version, "test" if "-rc" in new_version else "latest"]

    section("🐳 Docker")
    kv("Image", image_name)
    kv("Will push tags", ", ".join(tags_to_push))
    kv("CPU (default)", pipeline_config.get("docker", "cpu"))
    kv("GPU (default)", pipeline_config.get("docker", "gpu"))

    build_and_push_docker_image(
        pipeline_dir=pipeline_config.pipeline_dir,
        image_name=image_name,
        image_tags=tags_to_push,
        force_login=True,
    )
    bullet("Image pushed ✅", accent=False)

    pipeline_config.config["metadata"]["version"] = str(new_version)
    pipeline_config.config["docker"]["image_tag"] = str(new_version)
    pipeline_config.save()

    # ── Register on each host ────────────────────────────────────────────────
    section("📦 Register / Update")
    results: list[tuple[str, str, Optional[str]]] = []
    try:
        status, msg = _register_or_update(
            cfg=pipeline_config,
            api_token=env_config["api_token"],
            organization_name=env_config["organization_name"],
            host=env_config["host"],
        )
        kv("Status", status)
        if msg:
            kv("Details", msg)
        results.append((env_config["host"], status, msg))
    except Exception as e:
        kv("Status", "Error")
        kv("Details", str(e))
        results.append((env_config["host"], "Error", str(e)))

    # ── Summary ──────────────────────────────────────────────────────────────
    section("✅ Summary")
    for host_url, status, msg in results:
        kv("Host", host_url)
        kv("Status", status)
        if msg:
            kv("Info", msg)
        typer.echo("")

    hr()
    typer.secho(
        f"Processing pipeline '{pipeline_name}' deployed successfully",
        fg=typer.colors.GREEN,
        bold=True,
    )


def prompt_allocation_if_missing(pipeline_config: PipelineConfig):
    docker_section = pipeline_config.config.get("docker", {})
    cpu = docker_section.get("cpu", "")
    gpu = docker_section.get("gpu", "")

    section("⚙️ Resources")

    if cpu and gpu:
        kv("Current CPU", cpu)
        kv("Current GPU", gpu)
        if not typer.confirm("Keep the current Docker defaults?", default=True):
            cpu = typer.prompt("CPU (default)", default=cpu)
            gpu = typer.prompt("GPU (default)", default=gpu)
    else:
        if not cpu:
            cpu = typer.prompt("CPU (default)")
        if not gpu:
            gpu = typer.prompt("GPU (default)")

    pipeline_config.config["docker"]["cpu"] = cpu
    pipeline_config.config["docker"]["gpu"] = gpu
    pipeline_config.save()
    kv("Saved CPU", cpu)
    kv("Saved GPU", gpu)


def _infer_docker_flags(cfg: PipelineConfig) -> Optional[list]:
    """Return docker flags implied by GPU allocation."""
    try:
        gpu_count = int(cfg.get("docker", "gpu") or 0)
        if gpu_count > 0:
            return ["--gpus=all", "--ipc=host"]
    except Exception:
        pass
    return None


def _register_or_update(
    cfg: PipelineConfig,
    api_token: str,
    organization_name: str,
    host: str,
) -> tuple[str, Optional[str]]:
    """
    Create or update the processing on a given host.
    Returns:
        status: "Created" | "Updated"
        message: optional details
    """
    client = Client(api_token=api_token, organization_name=organization_name, host=host)
    docker_flags = _infer_docker_flags(cfg)

    name = cfg.get("metadata", "name")
    description = cfg.get("metadata", "description")
    ptype = ProcessingType(cfg.get("metadata", "type"))
    default_cpu = int(cfg.get("docker", "cpu"))
    default_gpu = int(cfg.get("docker", "gpu"))
    default_parameters = cfg.extract_default_parameters()
    docker_image = cfg.get("docker", "image_name")
    docker_tag = cfg.get("docker", "image_tag")

    try:
        client.create_processing(
            name=name,
            description=description,
            type=ptype,
            default_cpu=default_cpu,
            default_gpu=default_gpu,
            default_parameters=default_parameters,
            docker_image=docker_image,
            docker_tag=docker_tag,
            docker_flags=docker_flags,
        )
        return "Created", f"{name} ({docker_image}:{docker_tag})"

    except ResourceConflictError:
        # already exists → update
        processing = client.get_processing(name=name)
        processing.update(
            description=description,
            default_cpu=default_cpu,
            default_gpu=default_gpu,
            default_parameters=default_parameters,
            docker_image=docker_image,
            docker_tag=docker_tag,
        )
        return "Updated", f"{name} ({docker_image}:{docker_tag})"

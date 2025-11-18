import typer
from picsellia import Client
from picsellia.exceptions import ResourceConflictError
from picsellia.types.enums import ProcessingType

from picsellia_pipelines_cli.utils.deployer import (
    Bump,
    build_and_push_docker_image,
    bump_pipeline_version,
    prompt_docker_image_if_missing,
)
from picsellia_pipelines_cli.utils.env_utils import (
    Environment,
    get_env_config,
)
from picsellia_pipelines_cli.utils.logging import bullet, hr, kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig


def deploy_processing(
    pipeline_name: str,
    env: Environment,
    organization: str | None = None,
    bump: Bump | None = None,
):
    """
    🚀 Deploy a processing pipeline.

    Args:
        pipeline_name: The pipeline to deploy.
        env: Target environment.
        organization: Target organization (optional).
        bump: Optional version bump to apply. One of:
              "patch", "minor", "major", "rc", "final".
              If None, the user will be prompted.
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
    prompt_allocation_if_missing(pipeline_config=pipeline_config)
    runtime_tag = "test" if "-rc" in new_version else "latest"

    image_name = pipeline_config.get("docker", "image_name")

    tags_to_push = [new_version, runtime_tag]

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
    pipeline_config.config["docker"]["image_tag"] = str(runtime_tag)
    pipeline_config.save()

    # ── Register on each host ────────────────────────────────────────────────
    section("📦 Register / Update")
    results: list[tuple[str, str, str | None]] = []
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
    """
    Ensure docker CPU/GPU defaults are set for running the processing on the platform.

    - If both docker.cpu and docker.gpu exist: do not prompt; just display what will be used.
    - If any is missing: prompt with clear wording, validate, save to config.toml.
    """
    docker_section = pipeline_config.config.get("docker", {}) or {}
    cpu = docker_section.get("cpu")
    gpu = docker_section.get("gpu")

    section("⚙️ Resources")

    if cpu is not None and gpu is not None:
        kv("Default CPU (platform)", cpu)
        kv("Default GPU (platform)", gpu)
        typer.echo(
            "To change these defaults, edit docker.cpu / docker.gpu in config.toml."
        )
        return

    def _coerce_nonneg_int(label: str, value: str | int) -> int:
        try:
            n = int(value)
        except Exception as e:
            raise typer.Exit(f"❌ {label} must be an integer.") from e
        if n < 0:
            raise typer.Exit(f"❌ {label} must be ≥ 0.")
        return n

    if cpu is None:
        cpu = typer.prompt(
            "Default CPU cores to allocate when this processing runs on Picsellia",
            default="4",
        )
    if gpu is None:
        gpu = typer.prompt(
            "Default number of GPUs to allocate when this processing runs on Picsellia",
            default="0",
        )

    cpu_i = _coerce_nonneg_int("CPU", cpu)
    gpu_i = _coerce_nonneg_int("GPU", gpu)

    pipeline_config.config.setdefault("docker", {})
    pipeline_config.config["docker"]["cpu"] = cpu_i
    pipeline_config.config["docker"]["gpu"] = gpu_i
    pipeline_config.save()

    kv("Saved CPU", cpu_i)
    kv("Saved GPU", gpu_i)
    typer.echo("You can adjust these later in config.toml (docker.cpu / docker.gpu).")


def _infer_docker_flags(cfg: PipelineConfig) -> list | None:
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
) -> tuple[str, str | None]:
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

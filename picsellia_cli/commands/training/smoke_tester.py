from pathlib import Path
import toml
import typer

from picsellia_cli.utils.deployer import (
    build_docker_image_only,
    prompt_docker_image_if_missing,
)
from picsellia_cli.utils.env_utils import (
    ensure_env_vars,
    get_host_env_config,
    get_api_token_from_host,
)
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.logging import section, kv

from picsellia_cli.commands.training.utils.test import (
    get_training_params,
    normalize_training_io,
)
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.smoke_tester import run_smoke_test_container
from picsellia_cli.utils.tester import (
    build_pipeline_command,
)


from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.tester import (
    merge_with_default_parameters,
    get_saved_run_config_path,
)
from picsellia_cli.commands.training.tester import _print_training_io_summary


def smoke_test_training(
    pipeline_name: str,
    run_config_file: str | None = None,
    host: str = "prod",
    python_version: str = "3.10",
):
    ensure_env_vars(host=host)
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    prompt_docker_image_if_missing(pipeline_config=pipeline_config)

    # ── Pipeline ─────────────────────────────────────────────────────────────
    section("🧩 Pipeline")
    kv("Name", pipeline_config.get("metadata", "name"))
    kv("Type", pipeline_config.get("metadata", "type"))

    # ── Run directory ────────────────────────────────────────────────────────
    run_manager = RunManager(pipeline_dir=pipeline_config.pipeline_dir)
    run_dir = run_manager.get_next_run_dir()

    # ── Config source ────────────────────────────────────────────────────────
    run_config_path = Path(run_config_file) if run_config_file else None

    if run_config_path and run_config_path.exists():
        run_config = toml.load(run_config_path)
    else:
        run_config = get_training_params(run_manager=run_manager, config_file=None)

    run_config.setdefault("run", {})
    run_config["run"]["working_dir"] = str(run_dir)

    # ── Environment ─────────────────────────────────────────────────────────
    section("🌍 Environment")
    if "auth" in run_config and "host" in run_config["auth"]:
        host = run_config["auth"]["host"]
        env_config = get_host_env_config(host=host)
    else:
        env_config = get_host_env_config(host=host.upper())
        run_config.setdefault("auth", {})
        run_config["auth"]["host"] = env_config["host"]

    if "organization_name" not in run_config["auth"]:
        run_config["auth"]["organization_name"] = env_config["organization_name"]

    kv("Host", run_config["auth"]["host"])
    kv("Organization", run_config["auth"]["organization_name"])

    # ── Defaults & parameters ────────────────────────────────────────────────
    section("⚙️ Parameters")
    default_pipeline_params = pipeline_config.extract_default_parameters()
    run_config = merge_with_default_parameters(
        run_config=run_config,
        default_parameters=default_pipeline_params,
        parameters_name="hyperparameters",
    )

    # ── Normalize IO (resolve IDs/URLs) ─────────────────────────────────────
    section("📥 Inputs / 📤 Outputs")
    client = init_client(host=run_config["auth"]["host"])
    try:
        normalize_training_io(client=client, run_config=run_config)
    except typer.Exit as e:
        kv("❌ IO normalization failed", str(e))
        raise

    _print_training_io_summary(run_config)

    # ── Persist run config to run dir ────────────────────────────────────────
    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)
    saved_run_config_path = get_saved_run_config_path(
        run_manager=run_manager, run_dir=run_dir
    )
    kv("Saved config", str(saved_run_config_path))

    # Build image
    image_name = pipeline_config.get("docker", "image_name")
    image_tag = pipeline_config.get("docker", "image_tag")
    full_image_name = f"{image_name}:{image_tag}"

    section("🐳 Docker image")
    kv("Image", image_name)
    kv("Tag", image_tag)

    build_docker_image_only(
        pipeline_dir=pipeline_config.pipeline_dir,
        full_image_name=full_image_name,
    )

    # Env vars
    api_token = get_api_token_from_host(host=run_config["auth"]["host"])
    env_vars = {
        "api_token": api_token,
        "organization_name": run_config["auth"]["organization_name"],
        "host": run_config["auth"]["host"],
        "experiment_id": run_config["output"]["experiment"]["id"],
        "DEBUG": "True",
    }

    pipeline_script = (
        f"{pipeline_name}/{pipeline_config.get('execution', 'pipeline_script')}"
    )

    python_bin = f"python{python_version}"

    pipeline_script_path = Path(pipeline_script)
    command = build_pipeline_command(
        python_executable=Path(python_bin),
        pipeline_script_path=pipeline_script_path,
        run_config_file=saved_run_config_path,
        mode="local",
    )

    run_smoke_test_container(
        image=full_image_name,
        command=command,
        env_vars=env_vars,
    )

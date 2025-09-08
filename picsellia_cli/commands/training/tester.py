import os
from pathlib import Path

import toml
import typer

from picsellia_cli.commands.training.utils.test import (
    get_training_params,
    normalize_training_io,
)
from picsellia_cli.utils.env_utils import (
    ensure_env_vars,
    get_host_env_config,
    get_api_token_from_host,
)
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.runner import create_virtual_env, run_pipeline_command
from picsellia_cli.utils.tester import (
    merge_with_default_parameters,
    get_saved_run_config_path,
    build_pipeline_command,
)
from picsellia_cli.utils.logging import section, kv, bullet, hr


def test_training(
    pipeline_name: str,
    reuse_dir: bool = False,
    run_config_file: str | None = None,
    host: str = "prod",
):
    ensure_env_vars(host=host)
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)

    # ── Pipeline ─────────────────────────────────────────────────────────────
    section("🧩 Pipeline")
    kv("Name", pipeline_config.get("metadata", "name"))
    kv("Type", pipeline_config.get("metadata", "type"))

    # ── Run directory ────────────────────────────────────────────────────────
    run_manager = RunManager(pipeline_dir=pipeline_config.pipeline_dir)
    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir() or run_manager.get_next_run_dir()
        bullet(f"Reusing last run dir if possible → {run_dir}", accent=False)
    else:
        run_dir = run_manager.get_next_run_dir()

    # ── Config source ────────────────────────────────────────────────────────
    run_config_path = Path(run_config_file) if run_config_file else None
    if reuse_dir and run_config_path is None:
        run_config_path = run_manager.get_latest_run_config_path()

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

    # ── Virtualenv / Python ─────────────────────────────────────────────────
    section("🐍 Virtual env")
    env_path = create_virtual_env(
        requirements_path=pipeline_config.get_requirements_path()
    )
    python_executable = (
        Path(env_path) / ("Scripts" if os.name == "nt" else "bin") / "python"
    )

    # ── Build command ────────────────────────────────────────────────────────
    section("▶️ Run")
    command = build_pipeline_command(
        python_executable=python_executable,
        pipeline_script_path=pipeline_config.get_script_path("pipeline_script"),
        run_config_file=saved_run_config_path,
        mode="local",
    )

    api_token = get_api_token_from_host(host=run_config["auth"]["host"])

    typer.echo("Launching pipeline...")
    run_pipeline_command(
        command=command,
        working_dir=str(run_dir),
        api_token=api_token,
    )

    # ── Save final config (enriched after run if needed) ─────────────────────
    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)

    section("✅ Done")
    bullet(f"Training pipeline '{pipeline_name}' completed.", accent=True)
    kv("Run dir", run_dir.name)
    hr()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (display)
# ─────────────────────────────────────────────────────────────────────────────


def _print_training_io_summary(run_config: dict) -> None:
    """Pretty-print experiment + input bindings if present."""
    out = run_config.get("output", {}) or {}
    exp = out.get("experiment", {}) or {}
    if exp:
        if exp.get("url"):
            kv("Experiment URL", exp["url"])

    inp = run_config.get("input", {}) or {}

    mv = inp.get("model_version") or {}
    if mv:
        if mv.get("url"):
            kv("Model URL", mv["url"])

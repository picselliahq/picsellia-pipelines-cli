from pathlib import Path
from datetime import datetime
from typing import Optional, Any

import toml
import typer

from picsellia_cli.commands.training.utils.test import (
    normalize_training_io,
    get_training_params,
)
from picsellia_cli.utils.env_utils import (
    get_host_env_config,
    ensure_env_vars,
)
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.logging import hr, section, kv, step
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.tester import merge_with_default_parameters


def launch_training(
    pipeline_name: str,
    run_config_file: str,
    host: str = "prod",
):
    ensure_env_vars(host=host)
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    run_manager = RunManager(pipeline_dir=pipeline_config.pipeline_dir)

    # ── Pipeline
    section("🧩 Pipeline")
    kv("Name", pipeline_config.get("metadata", "name"))
    kv("Type", pipeline_config.get("metadata", "type"))
    kv("Directory", str(pipeline_config.pipeline_dir))

    # ── Run dir
    run_dir = run_manager.get_next_run_dir()
    kv("Working dir", str(run_dir))

    # ── Run config (source)
    section("🧪 Run config")
    run_config_path = Path(run_config_file) if run_config_file else None

    if run_config_path and run_config_path.exists():
        run_config = toml.load(run_config_path)
        kv("Source", str(run_config_path))
    else:
        run_config = get_training_params(run_manager=run_manager, config_file=None)
        kv("Source", "interactive / last-known")

    run_config.setdefault("run", {})
    run_config["run"]["working_dir"] = str(run_dir)

    # ── Environment
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

    # ── Merge defaults
    section("⚙️ Parameters")
    default_pipeline_params = pipeline_config.extract_default_parameters()
    run_config = merge_with_default_parameters(
        run_config=run_config, default_parameters=default_pipeline_params
    )
    kv("Defaults merged", "yes")
    kv(
        "Parameter keys",
        ", ".join(sorted((run_config.get("parameters") or {}).keys())) or "none",
    )

    # ── Normalize IO (resolve IDs, URLs, ensure bindings)
    section("📥 Inputs / 📤 Outputs")
    client = init_client(host=run_config["auth"]["host"])
    try:
        normalize_training_io(client=client, run_config=run_config)
    except typer.Exit as e:
        kv("❌ IO normalization failed", str(e))
        raise

    _print_training_io_summary(run_config)

    # Persist config to run dir
    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)
    kv("Saved config", str(run_manager.get_latest_run_config_path()))

    # ── Launch
    section("🟩 Launch")

    # Experiment target (from normalized config)
    exp = (run_config.get("output") or {}).get("experiment") or {}
    exp_id = exp.get("id")
    if not exp_id:
        raise typer.Exit("❌ Missing output.experiment.id after normalization.")

    kv("Experiment ID", exp_id)
    if exp.get("name"):
        kv("Experiment", exp["name"])
    if exp.get("url"):
        kv("Experiment URL", exp["url"])

    step(1, "Submitting training job…", accent=True)
    try:
        experiment = client.get_experiment_by_id(exp_id)
    except Exception as e:
        raise typer.Exit(f"❌ Could not fetch experiment '{exp_id}': {e}")

    try:
        resp = experiment.launch()  # Picsellia SDK: start training
    except Exception as e:
        raise typer.Exit(f"❌ Launch failed: {e}")

    # Try extracting job/run and build URL
    job_id, run_id = _extract_job_and_run(resp)
    org_id = getattr(getattr(client, "connexion", None), "organization_id", None)
    host_base = getattr(getattr(client, "connexion", None), "host", "").rstrip("/")

    kv("Status", "Launched ✅")
    if job_id:
        kv("Job ID", job_id)
    if run_id:
        kv("Run ID", run_id)
    if job_id and org_id:
        url = (
            f"{host_base}/{org_id}/jobs/{job_id}/runs/{run_id}"
            if run_id
            else f"{host_base}/{org_id}/jobs/{job_id}"
        )
        kv("Job URL", url, color=typer.colors.BLUE)

    hr()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (display & parsing)
# ─────────────────────────────────────────────────────────────────────────────


def _print_training_io_summary(run_config: dict) -> None:
    out = run_config.get("output", {}) or {}
    exp = out.get("experiment", {}) or {}
    if exp:
        kv("Experiment", f"{exp.get('name') or exp.get('id')}")
        if exp.get("project_name"):
            kv("Project", exp["project_name"])
        if exp.get("url"):
            kv("Experiment URL", exp["url"])

    inp = run_config.get("input", {}) or {}

    def _show_dsv(slot_key: str, label: str):
        d = inp.get(slot_key) or {}
        if not d:
            return
        name = d.get("version_name") or d.get("name")
        origin = d.get("origin_name")
        ident = d.get("id")
        txt = " / ".join([x for x in [origin, name, ident] if x])
        kv(label, txt)
        if d.get("url"):
            kv(f"{label} URL", d["url"])

    _show_dsv("train_dataset_version", "Train dataset")
    _show_dsv("test_dataset_version", "Test dataset")
    _show_dsv("validation_dataset_version", "Val dataset")

    mv = inp.get("model_version") or {}
    if mv:
        base = " / ".join(
            [
                x
                for x in [
                    mv.get("origin_name"),
                    mv.get("name") or mv.get("version_name"),
                    mv.get("id"),
                ]
                if x
            ]
        )
        if mv.get("visibility"):
            base += f" ({mv['visibility']})"
        kv("Model version", base)
        if mv.get("url"):
            kv("Model URL", mv["url"])


def _extract_job_and_run(resp: Any) -> tuple[Optional[str], Optional[str]]:
    """
    Best-effort extraction of job_id / run_id from various SDK response shapes.
    """
    job_id: Optional[str] = None
    run_id: Optional[str] = None

    if resp is None:
        return job_id, run_id

    # dict-like
    if isinstance(resp, dict):
        job_id = (
            resp.get("job_id") or resp.get("id") or (resp.get("job") or {}).get("id")
        )
        runs = resp.get("runs") or []
        if isinstance(runs, list) and runs:
            latest = _pick_latest_run(runs)
            if latest and isinstance(latest, dict):
                run_id = latest.get("id")
        if not run_id:
            run_id = resp.get("run_id") or (resp.get("run") or {}).get("id")
        return job_id, run_id

    # object-like
    jid = getattr(resp, "id", None) or getattr(resp, "job_id", None)
    if jid:
        job_id = str(jid)

    # maybe resp.runs or resp.run
    runs = getattr(resp, "runs", None)
    if isinstance(runs, list) and runs:
        latest = _pick_latest_run(runs)
        rid = (
            latest.get("id")
            if isinstance(latest, dict)
            else getattr(latest, "id", None)
        )
        run_id = str(rid) if rid else None
    else:
        run = getattr(resp, "run", None)
        if run is not None:
            rid = getattr(run, "id", None)
            run_id = str(rid) if rid else None

    return job_id, run_id


def _pick_latest_run(runs: list[dict]) -> Optional[dict]:
    if not runs:
        return None

    def _parse_dt(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:
            return None

    def key(r: dict) -> datetime:
        return (
            _parse_dt(r.get("updated_at"))
            or _parse_dt(r.get("created_at"))
            or datetime.min
        )

    return max(runs, key=key)

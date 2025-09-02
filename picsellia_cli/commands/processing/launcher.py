from pathlib import Path
from typing import Optional

import toml
import typer
from orjson import orjson
from picsellia import Client

from picsellia_cli.utils.env_utils import (
    get_host_env_config,
    ensure_env_vars,
    get_api_token_from_host,
)
from picsellia_cli.utils.logging import section, kv, bullet, hr
from picsellia_cli.utils.pipeline_config import PipelineConfig

from datetime import datetime


def launch_processing(
    pipeline_name: str,
    run_config_file: str,
    host: str = "prod",
):
    """
    🚀 Launch a processing on Picsellia from a run-config TOML.

    Job types:
      - DATASET_VERSION_CREATION
          Endpoint: /api/dataset/version/{dataset_version_id}/processing/launch
          Payload: processing_id, parameters, cpu, gpu, [target_version_name]
      - PRE_ANNOTATION
          Endpoint: /api/dataset/version/{dataset_version_id}/processing/launch
          Payload: processing_id, parameters, cpu, gpu, model_version_id
      - DATA_AUTO_TAGGING
          Endpoint: /api/datalake/{datalake_id}/processing/launch
          Payload: processing_id, parameters, cpu, gpu, model_version_id, [data_ids], [target_datalake_name]
    """
    ensure_env_vars(host=host)

    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    pipeline_type = pipeline_config.get("metadata", "type")

    config_file_to_reuse = Path(run_config_file) if run_config_file else None

    if not config_file_to_reuse:
        typer.echo(f"❌ Config file not found: {run_config_file}")
        raise typer.Exit(code=1)

    run_config = toml.load(run_config_file)

    # Load auth
    auth = run_config.get("auth", {})
    host = auth.get("host") or host
    host_config = get_host_env_config(host=auth.get("host") or host)
    api_token = get_api_token_from_host(host=host_config["host"])
    organization_name = auth.get("organization_name", host_config["organization_name"])

    client = Client(
        api_token=api_token,
        organization_name=organization_name,
        host=host_config["host"],
    )

    try:
        processing = client.get_processing(name=pipeline_name)
    except Exception:
        effective_name = pipeline_config.get("metadata", "name")
        typer.echo(
            f"❌ Processing with name {effective_name} not found on {host}, please deploy it before with 'pxl-pipeline deploy {pipeline_name} --host {host}'"
        )
        raise typer.Exit()

    section("🌍 Environment")
    org_id = getattr(getattr(client, "connexion", None), "organization_id", None)
    kv("Workspace", f"{organization_name} ({org_id})" if org_id else organization_name)
    kv("Host", host_config["host"])

    payload = {
        "processing_id": str(processing.id),
        "parameters": run_config.get("parameters", {}),
        "cpu": int(pipeline_config.config["docker"].get("cpu", 4)),
        "gpu": int(pipeline_config.config["docker"].get("gpu", 0)),
    }
    inputs = run_config.get("input", {}) or {}
    output = run_config.get("output", {}) or {}

    section("📥 Inputs / 📤 Outputs")

    if pipeline_type == "DATASET_VERSION_CREATION":
        ds_ver = inputs.get("dataset_version") or {}
        dataset_version_id = ds_ver.get("id")
        if not dataset_version_id:
            typer.echo("❌ DATASET_VERSION_CREATION requires input.dataset_version.id.")
            raise typer.Exit(code=1)

        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"
        kv("Input dataset version ID", dataset_version_id)

        # Optional: target version name
        out_ds = output.get("dataset_version") or {}
        target_version_name = out_ds.get("name")
        if target_version_name:
            payload["target_version_name"] = target_version_name
            kv("Target dataset version name", target_version_name)

    elif pipeline_type == "PRE_ANNOTATION":
        ds_ver = inputs.get("dataset_version") or {}
        dataset_version_id = ds_ver.get("id")
        if not dataset_version_id:
            typer.echo("❌ PRE_ANNOTATION requires input.dataset_version.id.")
            raise typer.Exit(code=1)

        mv = inputs.get("model_version") or {}
        model_version_id = mv.get("id")
        if not model_version_id:
            typer.echo("❌ PRE_ANNOTATION requires input.model_version.id.")
            raise typer.Exit(code=1)

        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"
        payload["model_version_id"] = model_version_id

        kv("Input dataset version ID", dataset_version_id)
        kv("Model version ID", model_version_id)

    elif pipeline_type == "DATA_AUTO_TAGGING":
        dl = inputs.get("datalake") or {}
        datalake_id = dl.get("id")
        if not datalake_id:
            typer.echo("❌ DATA_AUTO_TAGGING requires input.datalake.id.")
            raise typer.Exit(code=1)

        mv = inputs.get("model_version") or {}
        model_version_id = mv.get("id")
        if not model_version_id:
            typer.echo("❌ DATA_AUTO_TAGGING requires input.model_version.id.")
            raise typer.Exit(code=1)

        endpoint = f"/api/datalake/{datalake_id}/processing/launch"
        payload["model_version_id"] = model_version_id

        # Optional: data_ids (try multiple places)
        data_ids = (
            inputs.get("data_ids")
            or (run_config.get("run_parameters") or {}).get("data_ids")
            or (run_config.get("parameters") or {}).get("data_ids")
        )
        if data_ids:
            payload["data_ids"] = data_ids

        # Optional: target_datalake_name
        target_name = (output.get("datalake") or {}).get("name") or run_config.get(
            "target_datalake_name"
        )
        if target_name:
            payload["target_datalake_name"] = target_name

        kv("Input datalake ID", datalake_id)
        kv("Model version ID", model_version_id)
        kv("Target datalake name", target_name)

    else:
        typer.echo(f"❌ Unknown job type: {pipeline_type}")
        raise typer.Exit(code=1)

    # Resources preview
    section("⚙️ Resources")
    kv("CPU", payload["cpu"])
    kv("GPU", payload["gpu"])

    # Launch
    try:
        section("🟩 Launch")
        bullet(f"Submitting job for processing '{pipeline_name}'…", accent=True)
        resp = client.connexion.post(endpoint, data=orjson.dumps(payload)).json()

        # Extract job & run IDs per your example response
        job_id = None
        run_id = None

        if isinstance(resp, dict):
            # job id can be at top level
            job_id = (
                resp.get("job_id")
                or resp.get("id")
                or (resp.get("job") or {}).get("id")
            )

            # run id may be in runs list (pick the latest), or at top-level
            runs = resp.get("runs") or []
            latest_run = _pick_latest_run(runs) if isinstance(runs, list) else None
            if latest_run and isinstance(latest_run, dict):
                run_id = latest_run.get("id")
            if not run_id:
                run_id = resp.get("run_id") or (resp.get("run") or {}).get("id")

        kv("Status", "Launched ✅")

        # Build URL(s)
        base = client.connexion.host.rstrip("/")
        org_id = getattr(client.connexion, "organization_id", None)
        if job_id and org_id:
            if run_id:
                job_url = f"{base}/{org_id}/jobs/{job_id}/runs/{run_id}"
            else:
                job_url = f"{base}/{org_id}/jobs/{job_id}"
            kv("Job URL", job_url, color=typer.colors.BLUE)

    except Exception as e:
        typer.echo(typer.style(f"❌ Error during launch: {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    hr()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # fromisoformat handles offsets like "+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _pick_latest_run(runs: list[dict]) -> Optional[dict]:
    if not runs:
        return None

    # use updated_at, fallback to created_at
    def key(r: dict) -> datetime:
        return (
            _parse_dt(r.get("updated_at"))
            or _parse_dt(r.get("created_at"))
            or datetime.min
        )

    return max(runs, key=key)

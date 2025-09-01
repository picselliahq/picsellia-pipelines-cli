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
from picsellia_cli.utils.pipeline_config import PipelineConfig


# ──────────────────────────────────────────────────────────────────────────────
# Small CLI formatting helpers
# ──────────────────────────────────────────────────────────────────────────────


def _hr() -> None:
    typer.echo(typer.style("─" * 72, dim=True))


def _section(title: str) -> None:
    _hr()
    typer.echo(typer.style(f" {title}", bold=True))
    _hr()


def _kv(label: str, value: object, *, color: Optional[str] = None) -> None:
    if value is None:
        return
    s = str(value).strip()
    if not s:
        return
    label_txt = typer.style(f"{label}:", bold=True)
    val_txt = typer.style(s, fg=color) if color else s
    typer.echo(f"{label_txt} {val_txt}")


def _bullet(text: str, *, accent: bool = False) -> None:
    prefix = "•"
    line = f"{prefix} {text}"
    typer.echo(typer.style(line, fg=typer.colors.GREEN, bold=True) if accent else line)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


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
    except Exception as e:
        typer.echo(f"❌ Error during launch: {e}")
        raise typer.Exit()

    _section("🚀 Launch processing")
    _kv("Processing", pipeline_name)
    _kv("Job type", pipeline_type)

    _section("🌍 Environment")
    org_name = getattr(getattr(client, "connexion", None), "organization_name", None)
    org_id = getattr(getattr(client, "connexion", None), "organization_id", None)
    _kv("Workspace", f"{org_name} ({org_id})" if org_id else org_name)
    _kv("Host", client.connexion.host)

    payload = {
        "processing_id": str(processing.id),
        "parameters": run_config.get("parameters", {}),
        "cpu": int(pipeline_config.config["docker"].get("cpu", 4)),
        "gpu": int(pipeline_config.config["docker"].get("gpu", 0)),
    }
    inputs = run_config.get("input", {}) or {}
    output = run_config.get("output", {}) or {}

    _section("📥 Inputs / 📤 Outputs")

    if pipeline_type == "DATASET_VERSION_CREATION":
        ds_ver = inputs.get("dataset_version") or {}
        dataset_version_id = ds_ver.get("id")
        if not dataset_version_id:
            typer.echo("❌ DATASET_VERSION_CREATION requires input.dataset_version.id.")
            raise typer.Exit(code=1)

        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"
        _kv("Input dataset version ID", dataset_version_id)

        # Optional: target version name
        out_ds = output.get("dataset_version") or {}
        target_version_name = out_ds.get("name")
        if target_version_name:
            payload["target_version_name"] = target_version_name
            _kv("Target dataset version name", target_version_name)

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

        _kv("Input dataset version ID", dataset_version_id)
        _kv("Model version ID", model_version_id)

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

        _kv("Input datalake ID", datalake_id)
        _kv("Model version ID", model_version_id)
        _kv("Target datalake name", target_name)

    else:
        typer.echo(f"❌ Unknown job type: {pipeline_type}")
        raise typer.Exit(code=1)

    # Resources preview
    _section("⚙️ Resources")
    _kv("CPU", payload["cpu"])
    _kv("GPU", payload["gpu"])

    # Endpoint preview
    _section("🔗 Endpoint")
    _kv("API", endpoint, color=typer.colors.BLUE)

    # Launch
    try:
        _section("🟩 Launch")
        _bullet(f"Submitting job for processing '{pipeline_name}'…", accent=True)
        resp = client.connexion.post(endpoint, data=orjson.dumps(payload)).json()

        # Try to extract job/run IDs from various possible shapes
        job_id = (
            isinstance(resp, dict)
            and (resp.get("job_id") or (resp.get("job") or {}).get("id"))
        ) or None
        run_id = (
            isinstance(resp, dict)
            and (
                resp.get("run_id")
                or resp.get("id")
                or (resp.get("run") or {}).get("id")
            )
        ) or None

        _kv("Status", "Launched ✅")
        if job_id:
            _kv("Job ID", job_id)
        if run_id:
            _kv("Run ID", run_id)

        # Build job URL if we have both IDs
        if job_id and run_id:
            org_id = client.connexion.organization_id
            base = client.connexion.host.rstrip("/")
            job_url = f"{base}/{org_id}/jobs/{job_id}/runs/{run_id}"
            _kv("Job URL", job_url, color=typer.colors.BLUE)

    except Exception as e:
        typer.echo(typer.style(f"❌ Error during launch: {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    _hr()

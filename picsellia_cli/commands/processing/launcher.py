from pathlib import Path
from typing import Optional

import toml
import typer
from orjson import orjson
from picsellia import Client

from picsellia_cli.commands.processing.tester import (
    enrich_run_config_with_metadata,
)
from picsellia_cli.utils.env_utils import (
    get_host_env_config,
    ensure_env_vars,
    get_api_token_from_host,
)
from picsellia_cli.utils.logging import section, kv, bullet, hr
from picsellia_cli.utils.pipeline_config import PipelineConfig

from datetime import datetime

from picsellia_cli.utils.tester import merge_with_default_parameters


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

    run_config_path = Path(run_config_file) if run_config_file else None

    if not run_config_path:
        typer.echo(f"❌ Config file not found: {run_config_path}")
        raise typer.Exit(code=1)

    run_config = toml.load(run_config_path)

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
    effective_name = pipeline_config.get("metadata", "name")

    try:
        processing = client.get_processing(name=effective_name)
    except Exception:
        typer.echo(
            f"❌ Processing with name {effective_name} not found on {host}, please deploy it before with 'pxl-pipeline deploy {pipeline_name} --host {host}'"
        )
        raise typer.Exit()

    section("🌍 Environment")
    org_id = getattr(getattr(client, "connexion", None), "organization_id", None)
    kv("Workspace", f"{organization_name} ({org_id})" if org_id else organization_name)
    kv("Host", host_config["host"])

    inputs = run_config.get("input", {}) or {}
    outputs = run_config.get("output", {}) or {}

    section("📥 Inputs / 📤 Outputs")

    endpoint, payload = build_processing_payload(
        processing_id=processing.id,
        pipeline_type=pipeline_type,
        inputs=inputs,
        outputs=outputs,
        run_config=run_config,
        client=client,
    )

    # Resources preview
    section("⚙️ Resources")
    kv("CPU", payload["cpu"])
    kv("GPU", payload["gpu"])

    default_pipeline_params = pipeline_config.extract_default_parameters()
    run_config = merge_with_default_parameters(
        run_config=run_config, default_parameters=default_pipeline_params
    )

    enrich_run_config_with_metadata(client=client, run_config=run_config)

    with run_config_path.open("w") as f:
        toml.dump(run_config, f)

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


def build_processing_payload(
    processing_id: str,
    pipeline_type: str,
    inputs: dict,
    outputs: dict,
    run_config: dict,
    client: Client,
) -> tuple[str, dict]:
    payload = {
        "processing_id": processing_id,
        "parameters": run_config.get("parameters", {}),
        "cpu": run_config.get("docker", {}).get("cpu", 4),
        "gpu": run_config.get("docker", {}).get("gpu", 0),
    }

    if pipeline_type == "DATASET_VERSION_CREATION":
        dataset_version_id = inputs.get("dataset_version", {}).get("id")
        if not dataset_version_id:
            raise typer.Exit("Missing dataset_version.id for DATASET_VERSION_CREATION")
        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"

    elif pipeline_type == "PRE_ANNOTATION":
        dataset_version_id = inputs.get("dataset_version", {}).get("id")
        if not dataset_version_id:
            raise typer.Exit("Missing dataset_version.id for PRE_ANNOTATION")
        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"

    elif pipeline_type == "DATA_AUTO_TAGGING":
        datalake_id = inputs.get("datalake", {}).get("id")
        if not datalake_id:
            raise typer.Exit("Missing datalake.id for DATA_AUTO_TAGGING")
        endpoint = f"/api/datalake/{datalake_id}/processing/launch"
    else:
        raise typer.Exit(f"Unsupported pipeline type: {pipeline_type}")

    if "model_version" in inputs and "id" in inputs["model_version"]:
        payload["model_version_id"] = inputs["model_version"]["id"]

    if "dataset_version" in outputs and "name" in outputs["dataset_version"]:
        payload["target_version_name"] = outputs["dataset_version"]["name"]

    if "datalake" in outputs and "name" in outputs["datalake"]:
        payload["target_datalake_name"] = outputs["datalake"]["name"]

    data_ids = inputs.get("data_ids") or run_config.get("parameters", {}).get(
        "data_ids"
    )
    if data_ids:
        payload["data_ids"] = data_ids

    return endpoint, payload

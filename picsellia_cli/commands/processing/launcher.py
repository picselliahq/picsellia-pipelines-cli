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


def launch_processing(
    pipeline_name: str,
    run_config_file: str,
    host: str = "prod",
):
    """
    🚀 Launch a processing directly on the Picsellia platform using a run config file.
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

    payload = {
        "processing_id": str(processing.id),
        "parameters": run_config.get("parameters", {}),
        "cpu": int(pipeline_config.config["docker"].get("cpu", 4)),
        "gpu": int(pipeline_config.config["docker"].get("gpu", 0)),
    }
    inputs = run_config.get("input", {}) or {}
    output = run_config.get("output", {}) or {}

    # Resolve endpoint + payload details by job type
    endpoint: Optional[str] = None

    if pipeline_type == "DATASET_VERSION_CREATION":
        ds_ver = inputs.get("dataset_version") or {}
        dataset_version_id = ds_ver.get("id")
        if not dataset_version_id:
            typer.echo("❌ DATASET_VERSION_CREATION requires input.dataset_version.id.")
            raise typer.Exit(code=1)

        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"

        # Optional: target version name
        out_ds = output.get("dataset_version") or {}
        target_version_name = out_ds.get("name")
        if target_version_name:
            payload["target_version_name"] = target_version_name

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

    else:
        typer.echo(f"❌ Unknown job type: {pipeline_type}")
        raise typer.Exit(code=1)

    # Launch
    try:
        typer.echo(f"🚀 Launching processing '{pipeline_name}' ({pipeline_type})…")
        resp = client.connexion.post(endpoint, data=orjson.dumps(payload)).json()
        typer.echo("✅ Processing launched successfully!")
        if isinstance(resp, dict):
            run_id = resp.get("id") or resp.get("run_id")
            if run_id:
                typer.echo(f"📦 Run ID: {run_id}")
        typer.echo(f"🔗 Endpoint: {endpoint}")
    except Exception as e:
        typer.echo(f"❌ Error during launch: {e}")
        raise typer.Exit(code=1)

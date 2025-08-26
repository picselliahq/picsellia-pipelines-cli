from pathlib import Path

import toml
import typer
from orjson import orjson
from picsellia import Client

from picsellia_cli.utils.env_utils import (
    get_host_env_config,
    ensure_env_vars,
    get_api_token_from_host,
)


def launch_processing(
    pipeline_name: str,
    run_config_file: str,
    host: str = "prod",
):
    """
    🚀 Launch a processing directly on the Picsellia platform using a run config file.
    """
    ensure_env_vars()

    config_file_to_reuse = Path(run_config_file) if run_config_file else None

    if not config_file_to_reuse:
        typer.echo(f"❌ Config file not found: {run_config_file}")
        raise typer.Exit(code=1)

    config_data = toml.load(run_config_file)

    # Load auth
    auth = config_data.get("auth", {})
    host_config = get_host_env_config(host=auth.get("host") or host)
    api_token = get_api_token_from_host(host=host_config["host"])
    organization_name = auth.get("organization_name", host_config["organization_name"])

    client = Client(
        api_token=api_token,
        organization_name=organization_name,
        host=host_config["host"],
    )

    job_type = config_data.get("job", {}).get("type")
    if not job_type:
        typer.echo("❌ Missing job type in config.")
        raise typer.Exit()

    try:
        processing = client.get_processing(name=pipeline_name)
    except Exception as e:
        typer.echo(f"❌ Error during launch: {e}")
        raise typer.Exit()

    typer.echo(f"🚀 Launching processing '{pipeline_name}' ({job_type})...")

    payload = {
        "processing_id": str(processing.id),
        "parameters": config_data.get("parameters", {}),
        "cpu": int(config_data.get("docker", {}).get("cpu", 4)),
        "gpu": int(config_data.get("docker", {}).get("gpu", 0)),
    }

    # Optional dataset/datalake/model input/output resolution
    input = config_data.get("input", {})
    output = config_data.get("output", {})

    if "dataset_version" in input:
        dataset_id = input["dataset_version"]["id"]
        endpoint = f"/api/dataset/version/{dataset_id}/processing/launch"
    elif "datalake" in input:
        datalake_id = input["datalake"]["id"]
        endpoint = f"/api/datalake/{datalake_id}/processing/launch"
    else:
        typer.echo("❌ Could not detect a valid input (dataset_version or datalake).")
        raise typer.Exit()

    # Optionally add output name (e.g., for dataset version creation)
    if "dataset_version" in output:
        payload["target_version_name"] = output["dataset_version"].get("name")

    try:
        response = client.connexion.post(endpoint, data=orjson.dumps(payload)).json()
        typer.echo("✅ Processing launched successfully!")
        typer.echo(f"📦 Run ID: {response.get('id')}")
    except Exception as e:
        typer.echo(f"❌ Error during launch: {e}")
        raise typer.Exit()

from pathlib import Path

import toml
import typer
from orjson import orjson

from picsellia_cli.commands.processing.tester import (
    enrich_run_config_with_metadata,
)
from picsellia_cli.utils.env_utils import Environment
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.launcher import extract_job_and_run_ids, build_job_url
from picsellia_cli.utils.logging import section, kv, bullet, hr
from picsellia_cli.utils.pipeline_config import PipelineConfig


from picsellia_cli.utils.tester import (
    merge_with_default_parameters,
    prepare_auth_and_env,
)


def launch_processing(
    pipeline_name: str,
    run_config_file: str,
    organization: str | None = None,
    env: Environment | None = None,
):
    """
    🚀 Launch a processing on Picsellia from a run-config TOML.
    """
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    pipeline_type = pipeline_config.get("metadata", "type")

    run_config_path = Path(run_config_file)
    if not run_config_path.exists():
        typer.echo(f"❌ Config file not found: {run_config_path}")
        raise typer.Exit(code=1)

    run_config = toml.load(run_config_path)

    # ── Environment & auth ─────────────────────────────────────────────
    section("🌍 Environment")
    run_config, env_config = prepare_auth_and_env(
        run_config=run_config,
        organization=organization,
        env=env,
    )

    kv("Workspace", env_config["organization_name"])
    kv("Host", env_config["host"])

    client = init_client(env_config=env_config)

    effective_name = pipeline_config.get("metadata", "name")
    try:
        processing = client.get_processing(name=effective_name)
    except Exception:
        env_name = env_config["env"]
        typer.echo(
            f"❌ Processing with name {effective_name} not found on {env_name}, "
            f"please deploy it before with 'pxl-pipeline deploy {pipeline_name} --env {env_name}'"
        )
        raise typer.Exit()

    # ── Inputs / Outputs ──────────────────────────────────────────────
    section("📥 Inputs / 📤 Outputs")
    inputs = run_config.get("input", {}) or {}
    outputs = run_config.get("output", {}) or {}

    endpoint, payload = build_processing_payload(
        processing_id=str(processing.id),
        pipeline_type=pipeline_type,
        inputs=inputs,
        outputs=outputs,
        run_config=run_config,
    )

    # ── Resources ─────────────────────────────────────────────────────
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

    # ── Launch ─────────────────────────────────────────────────────────
    try:
        section("🟩 Launch")
        bullet(f"Submitting job for processing '{pipeline_name}'…", accent=True)
        resp = client.connexion.post(endpoint, data=orjson.dumps(payload)).json()

        job_id, run_id = extract_job_and_run_ids(resp)

        kv("Status", "Launched ✅")
        if job_id and getattr(client.connexion, "organization_id", None):
            job_url = build_job_url(client, job_id, run_id)
            kv("Job URL", job_url, color=typer.colors.BLUE)

    except Exception as e:
        typer.echo(typer.style(f"❌ Error during launch: {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    hr()


def build_processing_payload(
    processing_id: str,
    pipeline_type: str,
    inputs: dict,
    outputs: dict,
    run_config: dict,
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
            typer.echo("Missing dataset_version.id for DATASET_VERSION_CREATION")
            raise typer.Exit()
        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"

    elif pipeline_type == "PRE_ANNOTATION":
        dataset_version_id = inputs.get("dataset_version", {}).get("id")
        if not dataset_version_id:
            typer.echo("Missing dataset_version.id for PRE_ANNOTATION")
            raise typer.Exit()
        endpoint = f"/api/dataset/version/{dataset_version_id}/processing/launch"

    elif pipeline_type == "DATA_AUTO_TAGGING":
        datalake_id = inputs.get("datalake", {}).get("id")
        if not datalake_id:
            typer.echo("Missing datalake.id for DATA_AUTO_TAGGING")
            raise typer.Exit()
        endpoint = f"/api/datalake/{datalake_id}/processing/launch"
    else:
        typer.echo(f"Unsupported pipeline type: {pipeline_type}")
        raise typer.Exit()

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

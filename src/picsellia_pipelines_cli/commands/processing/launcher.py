from pathlib import Path

import toml
import typer
from orjson import orjson
from picsellia.exceptions import ResourceNotFoundError

from picsellia_pipelines_cli.commands.processing.tester import (
    enrich_run_config_with_metadata,
)
from picsellia_pipelines_cli.utils.initializer import init_client
from picsellia_pipelines_cli.utils.launcher import (
    build_job_url,
    extract_job_and_run_ids,
)
from picsellia_pipelines_cli.utils.logging import bullet, hr, kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig
from picsellia_pipelines_cli.utils.tester import (
    merge_with_default_parameters,
    prepare_auth_and_env,
)


def launch_processing(
    pipeline_name: str,
    run_config_file: str,
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
    run_config, env_config = prepare_auth_and_env(run_config=run_config)
    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    client = init_client(env_config=env_config)

    effective_name = pipeline_config.get("metadata", "name")
    try:
        processing = client.get_processing(name=effective_name)
    except Exception as e:
        env_name = env_config["env"]
        typer.echo(
            f"❌ Processing with name {effective_name} not found on {env_name}, "
            f"please deploy it before with 'pxl-pipeline deploy {pipeline_name} --env {env_name}'"
        )
        raise typer.Exit() from e

    # ── Inputs / Outputs ──────────────────────────────────────────────
    section("📥 Inputs / 📤 Outputs")
    inputs = run_config.get("input", {}) or {}
    outputs = run_config.get("output", {}) or {}

    if pipeline_type == "DATASET_VERSION_CREATION":
        _apply_override_for_dataset_version_creation(
            client=client,
            inputs=inputs,
            outputs=outputs,
            override=bool(run_config.get("override_outputs", False)),
        )

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
        raise typer.Exit() from e

    hr()


def _apply_override_for_dataset_version_creation(
    client, inputs: dict, outputs: dict, override: bool
) -> None:
    if not override:
        return

    in_dsv = (inputs or {}).get("dataset_version") or {}
    out_dsv = (outputs or {}).get("dataset_version") or {}
    out_name = out_dsv.get("name")
    in_id = in_dsv.get("id")

    if not (in_id and out_name):
        return

    try:
        in_version = client.get_dataset_version_by_id(id=in_id)
        dataset = client.get_dataset_by_id(id=in_version.origin_id)
        try:
            existing = dataset.get_version(version=out_name)
        except ResourceNotFoundError:
            existing = None

        if existing is not None:
            existing.delete()
            typer.echo(
                typer.style(
                    f"🧹 Deleted existing output dataset version '{out_name}' (override enabled).",
                    fg=typer.colors.YELLOW,
                )
            )
    except Exception as e:
        typer.echo(
            typer.style(
                f"⚠️ Override skipped for dataset version '{out_name}': {e}",
                fg=typer.colors.YELLOW,
            )
        )


def get_base_payload(processing_id: str, run_config: dict) -> dict:
    """Extract common payload fields shared by all processing types."""
    docker_cfg = run_config.get("docker", {})
    return {
        "processing_id": processing_id,
        "parameters": run_config.get("parameters", {}),
        "cpu": docker_cfg.get("cpu", 4),
        "gpu": docker_cfg.get("gpu", 0),
    }


def get_dataset_version_id(inputs: dict) -> str | None:
    """Return dataset version ID from inputs if present."""
    return inputs.get("dataset_version", {}).get("id")


def get_datalake_id(inputs: dict) -> str | None:
    """Return datalake ID from inputs if present."""
    return inputs.get("datalake", {}).get("id")


def validate_required_id(
    resource_name: str, resource_id: str | None, pipeline_type: str
):
    """Ensure a required input resource ID exists, otherwise exit gracefully."""
    if not resource_id:
        typer.echo(f"Missing {resource_name}.id for {pipeline_type}")
        raise typer.Exit()


def build_endpoint(pipeline_type: str, inputs: dict) -> str:
    """Return the endpoint path based on the pipeline type."""
    if pipeline_type in ("DATASET_VERSION_CREATION", "PRE_ANNOTATION"):
        dataset_id = get_dataset_version_id(inputs)
        validate_required_id("dataset_version", dataset_id, pipeline_type)
        return f"/api/dataset/version/{dataset_id}/processing/launch"

    if pipeline_type == "DATA_AUTO_TAGGING":
        datalake_id = get_datalake_id(inputs)
        validate_required_id("datalake", datalake_id, pipeline_type)
        return f"/api/datalake/{datalake_id}/processing/launch"

    if pipeline_type == "MODEL_CONVERSION" or pipeline_type == "MODEL_COMPRESSION":
        model_version_id = inputs.get("model_version", {}).get("id")
        validate_required_id("model_version", model_version_id, pipeline_type)
        return f"/api/model/version/{model_version_id}/processing/launch"

    typer.echo(f"Unsupported pipeline type: {pipeline_type}")
    raise typer.Exit()


def add_optional_fields(payload: dict, inputs: dict, outputs: dict, run_config: dict):
    """Attach optional fields to the payload when present."""
    # Optional: model version
    model_id = inputs.get("model_version", {}).get("id")
    if model_id:
        payload["model_version_id"] = model_id

    # Optional: dataset version output name
    dataset_name = outputs.get("dataset_version", {}).get("name")
    if dataset_name:
        payload["target_version_name"] = dataset_name

    # Optional: datalake output name
    datalake_name = outputs.get("datalake", {}).get("name")
    if datalake_name:
        payload["target_datalake_name"] = datalake_name

    # Optional: data_ids
    data_ids = inputs.get("data_ids") or run_config.get("parameters", {}).get(
        "data_ids"
    )
    if data_ids:
        payload["data_ids"] = data_ids


def build_processing_payload(
    processing_id: str,
    pipeline_type: str,
    inputs: dict,
    outputs: dict,
    run_config: dict,
) -> tuple[str, dict]:
    """
    Build the API endpoint and payload for launching a processing job.

    Returns:
        tuple[str, dict]: (endpoint, payload)
    """
    payload = get_base_payload(processing_id, run_config)
    endpoint = build_endpoint(pipeline_type, inputs)
    add_optional_fields(payload, inputs, outputs, run_config)

    return endpoint, payload

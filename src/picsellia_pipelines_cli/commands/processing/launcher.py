from pathlib import Path

import toml
import typer
from orjson import orjson

from picsellia_pipelines_cli.commands.processing.tester import (
    enrich_run_config_with_metadata,
)
from picsellia_pipelines_cli.commands.processing.utils.tester import (
    delete_existing_dataset_version_if_any,
    delete_existing_model_file_if_any,
    ensure_processing_run_config_defaults,
)
from picsellia_pipelines_cli.utils.initializer import init_client
from picsellia_pipelines_cli.utils.launcher import (
    build_job_url,
    extract_job_and_run_ids,
)
from picsellia_pipelines_cli.utils.logging import bullet, hr, kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig
from picsellia_pipelines_cli.utils.pipeline_types import (
    ProcessingLaunchTarget,
    get_processing_launch_target,
    parse_processing_type,
    valid_processing_type_values,
)
from picsellia_pipelines_cli.utils.processing_launch import (
    build_processing_launch_request,
    resolve_dataset_version_output_name,
    resolve_launch_target_id,
    uses_dataset_version_outputs,
    uses_model_version_target,
)
from picsellia_pipelines_cli.utils.tester import (
    merge_with_default_inputs,
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
    run_config = ensure_processing_run_config_defaults(
        run_config=run_config, pipeline_type=pipeline_type
    )

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

    try:
        ptype = parse_processing_type(pipeline_type)
    except ValueError:
        valid_types = ", ".join(valid_processing_type_values())
        typer.echo(
            f"❌ Invalid metadata.type '{pipeline_type}' in config.toml.\n"
            f"👉 Use a ProcessingType value ({valid_types})."
        )
        raise typer.Exit()

    # ── Inputs / Outputs ──────────────────────────────────────────────
    section("📥 Inputs / 📤 Outputs")
    _apply_launch_overrides(client=client, run_config=run_config, ptype=ptype)

    endpoint, payload = build_processing_launch_request(
        processing_id=str(processing.id),
        pipeline_type=pipeline_type,
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
    run_config = merge_with_default_inputs(
        run_config=run_config, default_inputs=pipeline_config.extract_default_inputs()
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


def _apply_launch_overrides(client, run_config: dict, ptype) -> None:
    """Apply non-interactive override_outputs cleanup before launch."""
    if not bool(run_config.get("override_outputs", False)):
        return

    launch_target = get_processing_launch_target(ptype)

    if uses_dataset_version_outputs(ptype):
        in_id = resolve_launch_target_id(run_config=run_config, launch_target=launch_target)
        out_name = resolve_dataset_version_output_name(run_config=run_config)
        if not (in_id and out_name):
            return
        try:
            deleted = delete_existing_dataset_version_if_any(
                client=client,
                input_dataset_version_id=in_id,
                output_name=out_name,
            )
            if deleted:
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

    if uses_model_version_target(ptype):
        model_id = resolve_launch_target_id(
            run_config=run_config,
            launch_target=ProcessingLaunchTarget.MODEL_VERSION,
        )
        file_name = (run_config.get("parameters", {}) or {}).get("output_model_file_name")
        if not (model_id and file_name):
            return
        try:
            deleted = delete_existing_model_file_if_any(
                client=client,
                model_version_id=model_id,
                file_name=file_name,
            )
            if deleted:
                typer.echo(
                    typer.style(
                        f"🧹 Deleted existing model file '{file_name}' (override enabled).",
                        fg=typer.colors.YELLOW,
                    )
                )
        except Exception as e:
            typer.echo(
                typer.style(
                    f"⚠️ Override skipped for model file '{file_name}': {e}",
                    fg=typer.colors.YELLOW,
                )
            )

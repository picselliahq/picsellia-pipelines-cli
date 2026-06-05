"""Build launch endpoint and payload for processing jobs."""

from typing import Any

import typer

from picsellia.types.enums import ProcessingType

from picsellia_pipelines_cli.utils.pipeline_types import (
    ProcessingLaunchTarget,
    get_processing_launch_target,
    parse_processing_type,
    processing_types_with_launch_support,
)


def resolve_launch_target_id(
    run_config: dict[str, Any], launch_target: ProcessingLaunchTarget
) -> str | None:
    """Resolve the platform target resource ID from run config (new or legacy shape)."""
    target_id = run_config.get("target_id")
    if target_id:
        return str(target_id)

    legacy_input = run_config.get("input") or {}
    resource = legacy_input.get(launch_target.value) or {}
    resource_id = resource.get("id")
    return str(resource_id) if resource_id else None


def build_launch_endpoint(launch_target: ProcessingLaunchTarget, target_id: str) -> str:
    if launch_target == ProcessingLaunchTarget.DATASET_VERSION:
        return f"/api/dataset/version/{target_id}/processing/launch"
    if launch_target == ProcessingLaunchTarget.DATALAKE:
        return f"/api/datalake/{target_id}/processing/launch"
    if launch_target == ProcessingLaunchTarget.MODEL_VERSION:
        return f"/api/model/version/{target_id}/processing/launch"
    raise ValueError(f"Unsupported launch target: {launch_target}")


def _get_legacy_input(run_config: dict[str, Any]) -> dict[str, Any]:
    return run_config.get("input") or {}


def _get_legacy_output(run_config: dict[str, Any]) -> dict[str, Any]:
    return run_config.get("output") or {}


def _get_declared_inputs(run_config: dict[str, Any]) -> dict[str, Any]:
    return run_config.get("inputs") or {}


def add_launch_optional_fields(
    payload: dict[str, Any], run_config: dict[str, Any]
) -> None:
    """Attach optional API fields from legacy IO and declared processing inputs."""
    legacy_input = _get_legacy_input(run_config)
    legacy_output = _get_legacy_output(run_config)
    declared_inputs = _get_declared_inputs(run_config)

    model_id = legacy_input.get("model_version", {}).get("id") or declared_inputs.get(
        "model_version_id"
    )
    if model_id:
        payload["model_version_id"] = model_id

    dataset_output_name = legacy_output.get("dataset_version", {}).get(
        "name"
    ) or declared_inputs.get("target_version_name")
    if dataset_output_name:
        payload["target_version_name"] = dataset_output_name

    datalake_output_name = legacy_output.get("datalake", {}).get("name")
    if datalake_output_name:
        payload["target_datalake_name"] = datalake_output_name

    data_ids = (
        legacy_input.get("data_ids")
        or declared_inputs.get("data_ids")
        or run_config.get("parameters", {}).get("data_ids")
    )
    if data_ids:
        payload["data_ids"] = data_ids

    run_parameters = run_config.get("run_parameters")
    if run_parameters:
        if "offset" in run_parameters:
            payload["offset"] = run_parameters["offset"]
        if "limit" in run_parameters:
            payload["limit"] = run_parameters["limit"]


def get_base_launch_payload(processing_id: str, run_config: dict[str, Any]) -> dict[str, Any]:
    docker_cfg = run_config.get("docker", {})
    payload: dict[str, Any] = {
        "processing_id": processing_id,
        "parameters": run_config.get("parameters", {}),
        "cpu": docker_cfg.get("cpu", 4),
        "gpu": docker_cfg.get("gpu", 0),
    }

    declared_inputs = _get_declared_inputs(run_config)
    if declared_inputs:
        payload["inputs"] = declared_inputs

    return payload


def build_processing_launch_request(
    processing_id: str,
    pipeline_type: str,
    run_config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    Build the API endpoint and payload for launching a processing job.

    Returns:
        tuple[str, dict]: (endpoint, payload)
    """
    try:
        ptype = parse_processing_type(pipeline_type)
    except ValueError:
        valid_types = ", ".join(processing_types_with_launch_support())
        typer.echo(
            f"❌ Invalid processing type '{pipeline_type}'.\n"
            f"👉 Use a ProcessingType value ({valid_types})."
        )
        raise typer.Exit() from None

    try:
        launch_target = get_processing_launch_target(ptype)
    except ValueError as e:
        typer.echo(f"❌ {e}")
        raise typer.Exit() from e

    target_id = resolve_launch_target_id(run_config=run_config, launch_target=launch_target)
    if not target_id:
        typer.echo(
            f"❌ Missing target for {ptype.value}: set top-level target_id or "
            f"input.{launch_target.value}.id in the run config."
        )
        raise typer.Exit()

    payload = get_base_launch_payload(processing_id=processing_id, run_config=run_config)
    add_launch_optional_fields(payload=payload, run_config=run_config)
    endpoint = build_launch_endpoint(launch_target=launch_target, target_id=target_id)
    return endpoint, payload


def uses_dataset_version_outputs(ptype: ProcessingType) -> bool:
    return (
        get_processing_launch_target(ptype) == ProcessingLaunchTarget.DATASET_VERSION
        and ptype == ProcessingType.DATASET_VERSION_CREATION
    )


def uses_model_version_target(ptype: ProcessingType) -> bool:
    return get_processing_launch_target(ptype) == ProcessingLaunchTarget.MODEL_VERSION


def resolve_dataset_version_output_name(run_config: dict[str, Any]) -> str | None:
    legacy_output = _get_legacy_output(run_config)
    declared_inputs = _get_declared_inputs(run_config)
    return legacy_output.get("dataset_version", {}).get("name") or declared_inputs.get(
        "target_version_name"
    )

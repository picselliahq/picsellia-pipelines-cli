import json
from pathlib import Path
from typing import Any

import toml
import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError

from picsellia_pipelines_cli.utils.run_manager import RunManager

TARGET_ID_PROMPT_LABELS: dict[str, str] = {
    "DATASET_VERSION_CREATION": "Dataset version ID (target)",
    "PRE_ANNOTATION": "Dataset version ID (target)",
    "DATA_AUTO_TAGGING": "Datalake ID (target)",
    "MODEL_CONVERSION": "Model version ID (target)",
    "MODEL_COMPRESSION": "Model version ID (target)",
}

INPUT_TYPE_PROMPT_HINTS: dict[str, str] = {
    "TEXT": "text value",
    "DATASET_VERSION": "dataset version ID",
    "MODEL_VERSION": "model version ID",
    "DATALAKE": "datalake ID",
    "BOOLEAN": "true or false",
    "INTEGER": "integer",
    "FLOAT": "float",
}


def get_processing_params(
    run_manager: RunManager,
    pipeline_type: str,
    pipeline_name: str,
    config_file: Path | None = None,
    default_inputs: list[dict[str, Any]] | None = None,
) -> dict:
    if config_file and config_file.exists():
        with config_file.open("r") as f:
            return ensure_processing_run_config_defaults(
                run_config=toml.load(f), pipeline_type=pipeline_type
            )

    latest_config_path = run_manager.get_latest_run_config_path()
    latest_config = None
    if latest_config_path:
        with open(latest_config_path) as f:
            latest_config = toml.load(f)

    stored_params: dict = latest_config or {}

    if latest_config:
        print_config_io_summary(latest_config)
        reuse = typer.confirm(
            typer.style("📝 Do you want to reuse this config?", fg=typer.colors.CYAN),
            default=True,
        )
        if reuse:
            return ensure_processing_run_config_defaults(
                run_config=latest_config, pipeline_type=pipeline_type
            )

    run_config = prompt_processing_run_config(
        stored_params=stored_params,
        pipeline_type=pipeline_type,
        default_inputs=default_inputs,
    )
    return ensure_processing_run_config_defaults(
        run_config=run_config, pipeline_type=pipeline_type
    )


def ensure_processing_run_config_defaults(
    run_config: dict, pipeline_type: str
) -> dict:
    """Align run config with processing-type requirements from cv-engine."""
    run_config.setdefault("job", {})
    run_config["job"]["type"] = pipeline_type

    if pipeline_type == "DATA_AUTO_TAGGING":
        run_config.setdefault("run_parameters", {})
        run_params = run_config["run_parameters"]
        run_params.setdefault("offset", 0)
        run_params.setdefault("limit", 10)

    return run_config


def prompt_processing_run_config(
    stored_params: dict,
    pipeline_type: str,
    default_inputs: list[dict[str, Any]] | None,
) -> dict:
    """Build a run config by prompting for target_id and declared processing inputs."""
    run_config: dict[str, Any] = {
        "job": {"type": pipeline_type},
        "override_outputs": stored_params.get("override_outputs", True),
    }

    target_label = TARGET_ID_PROMPT_LABELS.get(pipeline_type)
    if target_label:
        run_config["target_id"] = typer.prompt(
            typer.style(f"🎯 {target_label}", fg=typer.colors.CYAN),
            default=stored_params.get("target_id", ""),
        )

    stored_inputs = stored_params.get("inputs") or {}
    if default_inputs:
        run_config["inputs"] = prompt_declared_inputs(
            default_inputs=default_inputs,
            stored_inputs=stored_inputs,
        )

    if pipeline_type == "DATA_AUTO_TAGGING":
        stored_run_params = stored_params.get("run_parameters") or {}
        offset = typer.prompt(
            typer.style("↪ Offset", fg=typer.colors.CYAN),
            default=str(stored_run_params.get("offset", 0)),
        )
        limit = typer.prompt(
            typer.style("🔗 Limit", fg=typer.colors.CYAN),
            default=str(stored_run_params.get("limit", 10)),
        )
        run_config["run_parameters"] = {
            "offset": int(offset),
            "limit": int(limit),
        }

    return run_config


def prompt_declared_inputs(
    default_inputs: list[dict[str, Any]],
    stored_inputs: dict[str, Any],
) -> dict[str, str]:
    """Prompt the user for each input declared in the pipeline's inputs class."""
    inputs: dict[str, str] = {}

    for inp in default_inputs:
        name = inp["name"]
        input_type = inp.get("input_type", "TEXT")
        required = inp.get("required", True)
        hint = INPUT_TYPE_PROMPT_HINTS.get(input_type, input_type.lower().replace("_", " "))
        optional_tag = "" if required else " (optional)"
        label = f"📥 {name} — {hint}{optional_tag}"

        default_value = stored_inputs.get(name, "")
        if default_value is None:
            default_value = ""

        value = typer.prompt(
            typer.style(label, fg=typer.colors.CYAN),
            default=str(default_value),
            show_default=bool(default_value) or not required,
        )
        inputs[name] = value

    return inputs


def delete_existing_dataset_version_if_any(
    client: Client,
    input_dataset_version_id: str,
    output_name: str,
) -> bool:
    """
    Delete an existing dataset version named `output_name` on the dataset
    originating from `input_dataset_version_id`, if it exists.

    Returns:
        True if a version was deleted, False otherwise.
    """
    input_dataset_version = client.get_dataset_version_by_id(
        id=input_dataset_version_id
    )
    dataset = client.get_dataset_by_id(id=input_dataset_version.origin_id)

    try:
        existing = dataset.get_version(version=output_name)
    except ResourceNotFoundError:
        return False

    existing.delete()
    return True


def check_output_dataset_version(
    client: Client,
    input_dataset_version_id: str,
    output_name: str,
    override_outputs: bool = False,
) -> str:
    try:
        if override_outputs:
            deleted = delete_existing_dataset_version_if_any(
                client=client,
                input_dataset_version_id=input_dataset_version_id,
                output_name=output_name,
            )
            if deleted:
                typer.echo(
                    typer.style(
                        f"🧹 Deleted existing dataset version '{output_name}' (override enabled).",
                        fg=typer.colors.YELLOW,
                    )
                )
            return output_name

        deleted = delete_existing_dataset_version_if_any(
            client=client,
            input_dataset_version_id=input_dataset_version_id,
            output_name=output_name,
        )
        if deleted:
            overwrite = typer.confirm(
                typer.style(
                    f"⚠️ A dataset version named '{output_name}' already existed and has been deleted. "
                    "Use the same name again?",
                    fg=typer.colors.YELLOW,
                ),
                default=True,
            )
            if overwrite:
                return output_name

        return typer.prompt(
            typer.style(
                "📄 Enter a new output dataset version name", fg=typer.colors.CYAN
            ),
            default=f"{output_name}_new",
        )

    except Exception as e:
        typer.echo(f"⚠️ Could not resolve dataset metadata: {e}")
        return output_name


def delete_existing_model_file_if_any(
    client: Client,
    model_version_id: str,
    file_name: str,
) -> bool:
    """
    Delete existing model file `file_name` on a given model version, if present.

    Returns:
        True if a file was deleted, False otherwise.
    """
    model_version = client.get_model_version_by_id(model_version_id)

    try:
        existing_file = model_version.get_file(name=file_name)
    except ResourceNotFoundError:
        return False

    existing_file.delete()
    return True


def check_output_model_file(
    client: Client,
    input_model_version_id: str,
    output_name: str,
    override_outputs: bool = False,
) -> str:
    model_version = client.get_model_version_by_id(input_model_version_id)

    try:
        existing_file = model_version.get_file(name=output_name)
    except ResourceNotFoundError:
        return output_name

    if override_outputs:
        existing_file.delete()
        return output_name

    overwrite = typer.confirm(
        typer.style(
            f"⚠️ A model file named '{output_name}' already exists on this model version. Overwrite?",
            fg=typer.colors.YELLOW,
        ),
        default=False,
    )

    if overwrite:
        existing_file.delete()
        return output_name
    else:
        return typer.prompt(
            typer.style("📄 Enter a new output model file name", fg=typer.colors.CYAN),
            default=f"{output_name}_new",
        )


def enrich_run_config_with_metadata(client: Client, run_config: dict):
    if (
        "input" in run_config
        and "dataset_version" in run_config["input"]
        and "id" in run_config["input"]["dataset_version"]
    ):
        dataset_version_id = run_config["input"]["dataset_version"]["id"]
        try:
            dataset_version = client.get_dataset_version_by_id(dataset_version_id)
            run_config["input"]["dataset_version"] = {
                "id": dataset_version_id,
                "name": dataset_version.version,
                "origin_name": dataset_version.name,
                "url": f"{client.connexion.host}/{client.connexion.organization_id}/dataset/{dataset_version.origin_id}/version/{dataset_version.id}/assets?offset=0&q=&order_by=-created_at",
            }
        except Exception as e:
            typer.echo(f"⚠️ Could not resolve dataset metadata: {e}")

    if (
        "input" in run_config
        and "model_version" in run_config["input"]
        and "id" in run_config["input"]["model_version"]
    ):
        model_version_id = run_config["input"]["model_version"]["id"]
        try:
            model_version = client.get_model_version_by_id(model_version_id)
            run_config["input"]["model_version"] = {
                "id": model_version_id,
                "name": model_version.name,
                "origin_name": model_version.origin_name,
                "url": f"{client.connexion.host}/{client.connexion.organization_id}/model/{model_version.origin_id}/version/{model_version.id}",
                "visibility": run_config["input"]["model_version"]["visibility"]
                if "visibility" in run_config["input"]["model_version"]
                else "private",
            }
        except Exception as e:
            typer.echo(f"⚠️ Could not resolve model metadata: {e}")

    if (
        "input" in run_config
        and "datalake" in run_config["input"]
        and "id" in run_config["input"]["datalake"]
    ):
        datalake_id = run_config["input"]["datalake"]["id"]
        try:
            datalake = client.get_datalake(id=datalake_id)
            run_config["input"]["datalake"] = {
                "id": datalake_id,
                "name": datalake.name,
                "url": f"{client.connexion.host}/{client.connexion.organization_id}/datalake/{datalake_id}?offset=0&q=&order_by=-created_at",
            }
        except Exception as e:
            typer.echo(f"⚠️ Could not resolve model metadata: {e}")


def enrich_output_metadata_after_run(client: Client, run_config: dict):
    if (
        run_config.get("job", {}).get("type") == "DATASET_VERSION_CREATION"
        and "output" in run_config
        and "dataset_version" in run_config["output"]
        and "name" in run_config["output"]["dataset_version"]
    ):
        try:
            input_dataset_id = run_config["input"]["dataset_version"]["id"]
            dataset_version_name = run_config["output"]["dataset_version"]["name"]
            input_dataset = client.get_dataset_version_by_id(input_dataset_id)
            dataset = client.get_dataset_by_id(input_dataset.origin_id)
            new_version = dataset.get_version(version=dataset_version_name)

            run_config["output"]["dataset_version"].update(
                {
                    "id": str(new_version.id),
                    "version_name": new_version.version,
                    "origin_name": dataset.name,
                    "url": f"{client.connexion.host}/{client.connexion.organization_id}/dataset/{dataset.id}/version/{new_version.id}/assets?offset=0&q=&order_by=-created_at",
                }
            )

        except Exception as e:
            typer.echo(f"⚠️ Could not fetch output dataset version metadata: {e}")


def print_config_io_summary(config: dict):
    io_summary = {
        "target_id": config.get("target_id"),
        "inputs": config.get("inputs", {}),
        "override_outputs": config.get("override_outputs"),
    }

    typer.echo(typer.style("🧾 Reusing previous config:\n", fg=typer.colors.CYAN))
    typer.echo(json.dumps(io_summary, indent=2))

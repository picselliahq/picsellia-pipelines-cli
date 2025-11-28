import json
from pathlib import Path

import toml
import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError

from picsellia_pipelines_cli.utils.run_manager import RunManager


def get_processing_params(
    run_manager: RunManager,
    pipeline_type: str,
    pipeline_name: str,
    config_file: Path | None = None,
) -> dict:
    if config_file and config_file.exists():
        with config_file.open("r") as f:
            return toml.load(f)
    else:
        latest_config_path = run_manager.get_latest_run_config_path()
        if latest_config_path:
            with open(latest_config_path) as f:
                latest_config = toml.load(f)
        else:
            latest_config = None

    stored_params = {}

    if latest_config:
        print_config_io_summary(latest_config)
        reuse = typer.confirm(
            typer.style("📝 Do you want to reuse this config?", fg=typer.colors.CYAN),
            default=True,
        )
        stored_params = latest_config
        if reuse:
            return latest_config

    if pipeline_type == "PRE_ANNOTATION":
        return prompt_preannotation_params(stored_params=stored_params)
    elif pipeline_type == "DATA_AUTO_TAGGING":
        return prompt_data_auto_tagging_params(stored_params=stored_params)
    elif pipeline_type == "DATASET_VERSION_CREATION":
        return prompt_dataset_version_creation_params(
            stored_params=stored_params, pipeline_name=pipeline_name
        )
    elif pipeline_type == "MODEL_CONVERSION" or pipeline_type == "MODEL_COMPRESSION":
        return prompt_model_process_params(
            stored_params=stored_params, pipeline_type=pipeline_type
        )
    else:
        raise Exception(f"Unknown pipeline_type: {pipeline_type}")


def prompt_dataset_version_creation_params(
    stored_params: dict, pipeline_name: str
) -> dict:
    input = stored_params.get("input", {})
    output = stored_params.get("output", {})

    input_dataset = input.get("dataset_version", {})
    output_dataset = output.get("dataset_version", {})

    input_dataset_version_id = typer.prompt(
        typer.style("📅 Input dataset version ID", fg=typer.colors.CYAN),
        default=input_dataset.get("id", ""),
    )
    output_dataset_version_name = typer.prompt(
        typer.style("📄 Output dataset version name", fg=typer.colors.CYAN),
        default=output_dataset.get("name", f"processed_{pipeline_name}"),
    )
    return {
        "job": {"type": "DATASET_VERSION_CREATION"},
        "input": {"dataset_version": {"id": input_dataset_version_id}},
        "output": {"dataset_version": {"name": output_dataset_version_name}},
    }


def prompt_preannotation_params(stored_params: dict) -> dict:
    input = stored_params.get("input", {})
    dataset = input.get("dataset_version", {})
    model = input.get("model_version", {})

    input_dataset_version_id = typer.prompt(
        typer.style("📅 Input dataset version ID", fg=typer.colors.CYAN),
        default=dataset.get("id", ""),
    )
    model_version_id = typer.prompt(
        typer.style("🧠 Model version ID", fg=typer.colors.CYAN),
        default=model.get("id", ""),
    )

    return {
        "job": {"type": "PRE_ANNOTATION"},
        "input": {
            "dataset_version": {"id": input_dataset_version_id},
            "model_version": {"id": model_version_id},
        },
    }


def prompt_data_auto_tagging_params(stored_params: dict) -> dict:
    input = stored_params.get("input", {})
    output = stored_params.get("output", {})
    parameters = input.get("parameters", {})
    run_parameters = input.get("run_parameters", {})

    model = input.get("model_version", {})
    input_datalake = input.get("datalake", {})

    output_datalake = output.get("datalake", {})

    input_datalake_id = typer.prompt(
        typer.style("📅 Input datalake ID", fg=typer.colors.CYAN),
        default=input_datalake.get("id", ""),
    )
    model_version_id = typer.prompt(
        typer.style("🧠 Model version ID", fg=typer.colors.CYAN),
        default=model.get("model_version_id", ""),
    )

    output_datalake_id = typer.prompt(
        typer.style("📄 Output datalake ID", fg=typer.colors.CYAN),
        default=output_datalake.get("id", ""),
    )

    tags_list = typer.prompt(
        typer.style("🏷️ Tags to use (comma-separated)", fg=typer.colors.CYAN),
        default=parameters.get("tags_list", ""),
    )
    offset = typer.prompt(
        typer.style("↪ Offset", fg=typer.colors.CYAN),
        default=run_parameters.get("offset", "0"),
    )
    limit = typer.prompt(
        typer.style("🔗 Limit", fg=typer.colors.CYAN),
        default=run_parameters.get("limit", "100"),
    )

    return {
        "job": {"type": "DATA_AUTO_TAGGING"},
        "input": {
            "datalake": {"id": input_datalake_id},
            "model_version": {"id": model_version_id},
        },
        "output": {"datalake": {"id": output_datalake_id}},
        "parameters": {"tags_list": tags_list},
        "run_parameters": {"offset": int(offset), "limit": int(limit)},
    }


def prompt_model_process_params(stored_params: dict, pipeline_type: str) -> dict:
    input = stored_params.get("input", {})
    model = input.get("model_version", {})

    model_version_id = typer.prompt(
        typer.style("🧠 Model version ID", fg=typer.colors.CYAN),
        default=model.get("id", ""),
    )

    return {
        "job": {"type": pipeline_type},
        "input": {
            "model_version": {"id": model_version_id},
        },
    }


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
    input_section = config.get("input", {})
    output_section = config.get("output", {})

    io_summary = {
        "input": input_section,
        "output": output_section,
    }

    typer.echo(typer.style("🧾 Reusing previous config:\n", fg=typer.colors.CYAN))
    typer.echo(json.dumps(io_summary, indent=2))

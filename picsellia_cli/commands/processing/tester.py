import os
from pathlib import Path

import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError

from picsellia_cli.utils.env_utils import (
    ensure_env_vars,
    get_api_token_from_host,
    get_host_env_config,
)
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.runner import (
    create_virtual_env,
    run_pipeline_command,
)
import toml
import json


def test_processing(
    pipeline_name: str,
    reuse_dir: bool,
    run_config_file: str | None = None,
    host: str = "prod",
):
    ensure_env_vars()
    piepline_config = PipelineConfig(pipeline_name=pipeline_name)
    pipeline_type = piepline_config.get("metadata", "type")
    run_manager = RunManager(piepline_config.pipeline_dir)

    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir()
        if not run_dir:
            run_dir = run_manager.get_next_run_dir()
    else:
        run_dir = run_manager.get_next_run_dir()

    run_config_path = Path(run_config_file) if run_config_file else None
    if reuse_dir and run_config_path is None:
        run_config_path = run_manager.get_latest_run_config_path()

    if run_config_path and run_config_path.exists():
        run_config = toml.load(run_config_path)
        run_config.setdefault("run", {})
        run_config["run"]["working_dir"] = str(run_dir)
    else:
        run_config = get_processing_params(
            run_manager=run_manager,
            pipeline_type=pipeline_type,
            pipeline_name=pipeline_name,
            config_file=None,
        )
        run_config.setdefault("run", {})
        run_config["run"]["working_dir"] = str(run_dir)

    if "auth" in run_config and "host" in run_config["auth"]:
        host = run_config["auth"]["host"]
        env_config = get_host_env_config(host=host)
    else:
        env_config = get_host_env_config(host=host.upper())
        run_config.setdefault("auth", {})
        run_config["auth"]["host"] = env_config["host"]

    if "organization_name" not in run_config["auth"]:
        run_config["auth"]["organization_name"] = env_config["organization_name"]

    client = init_client(host=run_config["auth"]["host"])

    if pipeline_type == "DATASET_VERSION_CREATION":
        run_config["output"]["dataset_version"]["name"] = check_output_dataset_version(
            client=client,
            input_dataset_version_id=run_config["input"]["dataset_version"]["id"],
            output_name=run_config["output"]["dataset_version"]["name"],
        )

    default_pipeline_params = piepline_config.extract_default_parameters()
    run_config = merge_with_default_parameters(run_config, default_pipeline_params)

    enrich_run_config_with_metadata(client=client, run_config=run_config)
    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)
    saved_run_config_path = _get_saved_run_config_path(run_manager, run_dir)

    env_path = create_virtual_env(
        requirements_path=piepline_config.get_requirements_path()
    )
    python_executable = (
        env_path / "Scripts" / "python.exe"
        if os.name == "nt"
        else env_path / "bin" / "python"
    )

    command = build_processing_command(
        python_executable=python_executable,
        pipeline_script_path=piepline_config.get_script_path("pipeline_script"),
        run_config_file=saved_run_config_path,
        mode="local",
    )

    api_token = get_api_token_from_host(host=run_config["auth"]["host"])

    run_pipeline_command(
        command=command,
        working_dir=str(run_dir),
        api_token=api_token,
    )

    enrich_output_metadata_after_run(client=client, run_config=run_config)
    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)

    typer.echo(
        typer.style(
            f"✅ Processing pipeline '{pipeline_name}' run complete: {run_dir.name}",
            fg=typer.colors.GREEN,
        )
    )


def _get_saved_run_config_path(run_manager: RunManager, run_dir: Path) -> Path:
    if hasattr(run_manager, "get_run_config_path"):
        return run_manager.get_run_config_path(run_dir)
    return run_dir / "run_config.toml"


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
            with open(latest_config_path, "r") as f:
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


def check_output_dataset_version(
    client: Client, input_dataset_version_id: str, output_name: str
) -> str:
    try:
        input_dataset_version = client.get_dataset_version_by_id(
            input_dataset_version_id
        )
        dataset = client.get_dataset_by_id(input_dataset_version.origin_id)
        dataset.get_version(version=output_name)

        overwrite = typer.confirm(
            typer.style(
                f"⚠️ A dataset version named '{output_name}' already exists. Overwrite?",
                fg=typer.colors.YELLOW,
            ),
            default=False,
        )
        if overwrite:
            dataset.get_version(version=output_name).delete()
        else:
            output_name = typer.prompt(
                typer.style(
                    "📄 Enter a new output dataset version name", fg=typer.colors.CYAN
                ),
                default=f"{output_name}_new",
            )
    except ResourceNotFoundError:
        pass
    return output_name


def build_processing_command(
    python_executable: Path,
    pipeline_script_path: Path,
    run_config_file: Path,
    mode: str = "local",
) -> list[str]:
    return [
        str(python_executable),
        str(pipeline_script_path),
        "--config-file",
        str(run_config_file),
        "--mode",
        mode,
    ]


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
            print(f"Resolving model version id: {model_version_id}")
            print(f"Client connexion: {client.connexion.organization_id}")
            model_version = client.get_model_version_by_id(model_version_id)
            run_config["input"]["model_version"] = {
                "id": model_version_id,
                "name": model_version.name,
                "origin_name": model_version.origin_name,
                "url": f"{client.connexion.host}/{client.connexion.organization_id}/model/{model_version.origin_id}/version/{model_version.id}",
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


def merge_with_default_parameters(run_config: dict, default_parameters: dict) -> dict:
    """
    Merge existing run config parameters with default parameters from the pipeline.

    - Keeps existing values in `run_config["parameters"]`
    - Adds missing defaults from `default_parameters`

    Args:
        run_config (dict): The current parameters dictionary (typically from run_config.toml)
        default_parameters (dict): The default parameters from the pipeline config

    Returns:
        dict: The merged parameters dictionary (with all required defaults)
    """
    run_config.setdefault("parameters", {})
    merged_params = default_parameters.copy()

    # Override defaults with existing values from run config
    merged_params.update(run_config["parameters"])

    # Set back merged values into run_config
    run_config["parameters"] = merged_params
    return run_config

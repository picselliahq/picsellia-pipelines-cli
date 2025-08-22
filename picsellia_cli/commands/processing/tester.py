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


def test_processing(
    pipeline_name: str,
    reuse_dir: bool,
    run_config_file: str | None = None,
    host: str = "prod",
):
    ensure_env_vars()
    config = PipelineConfig(pipeline_name=pipeline_name)
    pipeline_type = config.get("metadata", "type")
    run_manager = RunManager(config.pipeline_dir)

    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir()
        if not run_dir:
            run_dir = run_manager.get_next_run_dir()
    else:
        run_dir = run_manager.get_next_run_dir()

    config_file_to_reuse = Path(run_config_file) if run_config_file else None
    if reuse_dir and config_file_to_reuse is None:
        config_file_to_reuse = run_manager.get_latest_run_config_path()

    client = init_client(host=host)

    if config_file_to_reuse and config_file_to_reuse.exists():
        params = toml.load(config_file_to_reuse)
        params.setdefault("run", {})
        params["run"]["working_dir"] = str(run_dir)
    else:
        params = get_processing_params(
            run_manager=run_manager,
            pipeline_type=pipeline_type,
            pipeline_name=pipeline_name,
            config_file=None,
        )
        params.setdefault("run", {})
        params["run"]["working_dir"] = str(run_dir)

    if "auth" in params and "host" in params["auth"]:
        host = params["auth"]["host"]
        env_config = get_host_env_config(host=host)
    else:
        env_config = get_host_env_config(host=host.upper())
        params.setdefault("auth", {})
        params["auth"]["host"] = env_config["host"]

    if "organization_name" not in params["auth"]:
        params["auth"]["organization_name"] = env_config["organization_name"]

    if pipeline_type == "DATASET_VERSION_CREATION":
        params["output"]["dataset_version"]["name"] = check_output_dataset_version(
            client=client,
            input_dataset_version_id=params["input"]["dataset_version"]["id"],
            output_name=params["output"]["dataset_version"]["name"],
        )

    enrich_run_config_with_metadata(client=client, params=params)
    run_manager.save_run_config(run_dir=run_dir, config_data=params)
    saved_run_config_path = _get_saved_run_config_path(run_manager, run_dir)

    env_path = create_virtual_env(requirements_path=config.get_requirements_path())
    python_executable = (
        env_path / "Scripts" / "python.exe"
        if os.name == "nt"
        else env_path / "bin" / "python"
    )

    command = build_processing_command(
        python_executable=python_executable,
        pipeline_script_path=config.get_script_path("pipeline_script"),
        run_config_file=saved_run_config_path,
        mode="local",
    )

    api_token = get_api_token_from_host(host=params["auth"]["host"])

    run_pipeline_command(
        command=command,
        working_dir=str(run_dir),
        api_token=api_token,
    )

    enrich_output_metadata_after_run(client=client, params=params)
    run_manager.save_run_config(run_dir=run_dir, config_data=params)

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
        summary = " / ".join(f"{k}={v}" for k, v in latest_config.items())
        reuse = typer.confirm(f"📝 Reuse previous config? {summary}", default=True)
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
            "model_version": {"model_version_id": model_version_id},
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


def enrich_run_config_with_metadata(client: Client, params: dict):
    if (
        "input" in params
        and "dataset_version" in params["input"]
        and "id" in params["input"]["dataset_version"]
    ):
        dataset_version_id = params["input"]["dataset_version"]["id"]
        try:
            dataset_version = client.get_dataset_version_by_id(dataset_version_id)
            params["input"]["dataset_version"] = {
                "id": dataset_version_id,
                "name": dataset_version.version,
                "origin_name": dataset_version.name,
                "url": f"{client.connexion.host}/{client.connexion.organization_id}/dataset/{dataset_version.origin_id}/version/{dataset_version.id}/assets?offset=0&q=&order_by=-created_at",
            }
        except Exception as e:
            typer.echo(f"⚠️ Could not resolve dataset metadata: {e}")

    if (
        "input" in params
        and "model_version" in params["input"]
        and "id" in params["input"]["model_version"]
    ):
        model_version_id = params["input"]["model_version"]["id"]
        try:
            model_version = client.get_model_version_by_id(model_version_id)
            params["input"]["model_version"] = {
                "id": model_version_id,
                "name": model_version.name,
                "origin_name": model_version.origin_name,
                "url": f"{client.connexion.host}/{client.connexion.organization_id}/model/{model_version.origin_id}/version/{model_version.id}",
            }
        except Exception as e:
            typer.echo(f"⚠️ Could not resolve model metadata: {e}")


def enrich_output_metadata_after_run(client: Client, params: dict):
    if (
        params.get("job", {}).get("type") == "DATASET_VERSION_CREATION"
        and "output" in params
        and "dataset_version" in params["output"]
        and "name" in params["output"]["dataset_version"]
    ):
        try:
            input_dataset_id = params["input"]["dataset_version"]["id"]
            dataset_version_name = params["output"]["dataset_version"]["name"]
            input_dataset = client.get_dataset_version_by_id(input_dataset_id)
            dataset = client.get_dataset_by_id(input_dataset.origin_id)
            new_version = dataset.get_version(version=dataset_version_name)

            params["output"]["dataset_version"].update(
                {
                    "id": new_version.id,
                    "version_name": new_version.version,
                    "origin_name": dataset.name,
                    "url": f"{client.connexion.host}/{client.connexion.organization_id}/dataset/{dataset.id}/version/{new_version.id}/assets?offset=0&q=&order_by=-created_at",
                }
            )

        except Exception as e:
            typer.echo(f"⚠️ Could not fetch output dataset version metadata: {e}")

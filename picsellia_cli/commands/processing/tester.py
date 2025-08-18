import os
from pathlib import Path

import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError

from picsellia_cli.utils.env_utils import require_env_var, ensure_env_vars
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
    config_file: Path | None = None,
):
    ensure_env_vars()
    config = PipelineConfig(pipeline_name=pipeline_name)
    pipeline_type = config.get(
        "metadata", "type"
    )  # Ex: "PRE_ANNOTATION" or "DATASET_VERSION_CREATION"
    run_manager = RunManager(config.pipeline_dir)

    config_file_to_reuse = config_file
    if reuse_dir and config_file_to_reuse is None:
        config_file_to_reuse = run_manager.get_latest_run_config_path()

    params = get_processing_params(
        run_manager=run_manager,
        pipeline_type=pipeline_type,
        pipeline_name=pipeline_name,
        config_file=config_file_to_reuse,
    )

    client = init_client()

    # Only ask output name confirmation for non-pre-annotation
    if pipeline_type == "DATASET_VERSION_CREATION":
        params["output_dataset_version_name"] = check_output_dataset_version(
            client=client,
            input_dataset_version_id=params["input_dataset_version_id"],
            output_name=params["output_dataset_version_name"],
        )

    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir()
        if not run_dir:
            run_dir = run_manager.get_next_run_dir()
    else:
        run_dir = run_manager.get_next_run_dir()

    run_manager.save_run_config(run_dir=run_dir, config_data=params)

    env_path = create_virtual_env(requirements_path=config.get_requirements_path())
    python_executable = (
        env_path / "Scripts" / "python.exe"
        if os.name == "nt"
        else env_path / "bin" / "python"
    )

    command = build_processing_command(
        python_executable=python_executable,
        config=config,
        pipeline_type=pipeline_type,
        run_dir=run_dir,
        params=params,
    )

    run_pipeline_command(command, str(run_dir))

    typer.echo(
        typer.style(
            f"✅ Processing pipeline '{pipeline_name}' run complete: {run_dir.name}",
            fg=typer.colors.GREEN,
        )
    )


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

    params = {}
    stored_params = {}

    if latest_config:
        summary = " / ".join(f"{k}={v}" for k, v in latest_config.items())
        reuse = typer.confirm(f"📝 Reuse previous config? {summary}", default=True)
        stored_params = latest_config
        if reuse:
            params = latest_config

    if not params:
        if pipeline_type == "PRE_ANNOTATION":
            params = prompt_preannotation_params(stored_params)
        elif pipeline_type == "DATA_AUTO_TAGGING":
            params = prompt_data_auto_tagging_params(stored_params)
        else:
            params = prompt_default_params(pipeline_name, stored_params)

    return params


def prompt_default_params(pipeline_name: str, stored_params: dict) -> dict:
    input_dataset_version_id = typer.prompt(
        typer.style("📥 Input dataset version ID", fg=typer.colors.CYAN),
        default=stored_params.get("input_dataset_version_id", ""),
    )
    output_dataset_version_name = typer.prompt(
        typer.style("📤 Output dataset version name", fg=typer.colors.CYAN),
        default=stored_params.get(
            "output_dataset_version_name", f"processed_{pipeline_name}"
        ),
    )
    return {
        "input_dataset_version_id": input_dataset_version_id,
        "output_dataset_version_name": output_dataset_version_name,
    }


def prompt_preannotation_params(stored_params: dict) -> dict:
    input_dataset_version_id = typer.prompt(
        typer.style("📥 Input dataset version ID", fg=typer.colors.CYAN),
        default=stored_params.get("input_dataset_version_id", ""),
    )
    model_version_id = typer.prompt(
        typer.style("🧠 Model version ID", fg=typer.colors.CYAN),
        default=stored_params.get("model_version_id", ""),
    )
    return {
        "input_dataset_version_id": input_dataset_version_id,
        "model_version_id": model_version_id,
    }


def prompt_data_auto_tagging_params(stored_params: dict) -> dict:
    input_datalake_id = typer.prompt(
        typer.style("📥 Input datalake ID", fg=typer.colors.CYAN),
        default=stored_params.get("input_datalake_id", ""),
    )
    output_datalake_id = typer.prompt(
        typer.style("📤 Output datalake ID", fg=typer.colors.CYAN),
        default=stored_params.get("output_datalake_id", ""),
    )
    model_version_id = typer.prompt(
        typer.style("🧠 Model version ID", fg=typer.colors.CYAN),
        default=stored_params.get("model_version_id", ""),
    )
    tags_list = typer.prompt(
        typer.style("🏷️ Tags to use (comma-separated)", fg=typer.colors.CYAN),
        default=stored_params.get("tags_list", ""),
    )
    offset = typer.prompt(
        typer.style("↪ Offset", fg=typer.colors.CYAN),
        default=stored_params.get("offset", "0"),
    )
    limit = typer.prompt(
        typer.style("🔢 Limit", fg=typer.colors.CYAN),
        default=stored_params.get("limit", "100"),
    )

    return {
        "input_datalake_id": input_datalake_id,
        "output_datalake_id": output_datalake_id,
        "model_version_id": model_version_id,
        "tags_list": tags_list,
        "offset": offset,
        "limit": limit,
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
                    "📤 Enter a new output dataset version name", fg=typer.colors.CYAN
                ),
                default=f"{output_name}_new",
            )
    except ResourceNotFoundError:
        pass
    return output_name


def build_processing_command(
    python_executable: Path,
    config: PipelineConfig,
    pipeline_type: str,
    run_dir: Path,
    params: dict[str, str],
) -> list:
    command = [
        str(python_executable),
        str(config.get_script_path("local_pipeline_script")),
        "--api_token",
        require_env_var("PICSELLIA_API_TOKEN"),
        "--organization_name",
        require_env_var("PICSELLIA_ORGANIZATION_NAME"),
        "--working_dir",
        str(run_dir),
        "--job_type",
        pipeline_type,
    ]

    if pipeline_type == "DATASET_VERSION_CREATION":
        command += [
            "--input_dataset_version_id",
            params["input_dataset_version_id"],
            "--output_dataset_version_name",
            params["output_dataset_version_name"],
        ]
    elif pipeline_type == "PRE_ANNOTATION":
        command += [
            "--input_dataset_version_id",
            params["input_dataset_version_id"],
            "--model_version_id",
            params["model_version_id"],
        ]
    elif pipeline_type == "DATA_AUTO_TAGGING":
        command += [
            "--input_datalake_id",
            params["input_datalake_id"],
            "--output_datalake_id",
            params["output_datalake_id"],
            "--model_version_id",
            params["model_version_id"],
            "--tags_list",
            params["tags_list"],
            "--offset",
            str(params["offset"]),
            "--limit",
            str(params["limit"]),
        ]

    return command

import os
from pathlib import Path

import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError

from picsellia_cli.utils.env_utils import ensure_env_vars, require_env_var
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

        if pipeline_type == "DATASET_VERSION_CREATION":
            client = init_client()
            params["io"]["output_dataset_version_name"] = check_output_dataset_version(
                client=client,
                input_dataset_version_id=params["io"]["input_dataset_version_id"],
                output_name=params["io"]["output_dataset_version_name"],
            )

        params.setdefault("run", {})
        params["run"]["working_dir"] = str(run_dir)
        params.setdefault("auth", {})
        params["auth"]["organization_name"] = require_env_var(
            "PICSELLIA_ORGANIZATION_NAME"
        )
        host = os.environ.get("PICSELLIA_HOST")
        if host:
            params["auth"]["host"] = host

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

    run_pipeline_command(command=command, working_dir=str(run_dir))

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
        return prompt_preannotation_params(stored_params)
    elif pipeline_type == "DATA_AUTO_TAGGING":
        return {
            "job": {"type": pipeline_type},
            **prompt_data_auto_tagging_params(stored_params),
        }
    else:
        return {
            "job": {"type": pipeline_type},
            "io": prompt_default_params(pipeline_name, stored_params.get("io", {})),
        }


def prompt_default_params(pipeline_name: str, stored_io: dict) -> dict:
    input_dataset_version_id = typer.prompt(
        typer.style("📅 Input dataset version ID", fg=typer.colors.CYAN),
        default=stored_io.get("input_dataset_version_id", ""),
    )
    output_dataset_version_name = typer.prompt(
        typer.style("📄 Output dataset version name", fg=typer.colors.CYAN),
        default=stored_io.get(
            "output_dataset_version_name", f"processed_{pipeline_name}"
        ),
    )
    return {
        "input_dataset_version_id": input_dataset_version_id,
        "output_dataset_version_name": output_dataset_version_name,
    }


def prompt_preannotation_params(stored_params: dict) -> dict:
    io = stored_params.get("io", {})
    model = stored_params.get("model", {})

    input_dataset_version_id = typer.prompt(
        typer.style("📅 Input dataset version ID", fg=typer.colors.CYAN),
        default=io.get("input_dataset_version_id", ""),
    )
    model_version_id = typer.prompt(
        typer.style("🧠 Model version ID", fg=typer.colors.CYAN),
        default=model.get("model_version_id", ""),
    )

    return {
        "job": {"type": "PRE_ANNOTATION"},
        "io": {"input_dataset_version_id": input_dataset_version_id},
        "model": {"model_version_id": model_version_id},
    }


def prompt_data_auto_tagging_params(stored_params: dict) -> dict:
    io = stored_params.get("io", {})
    model = stored_params.get("model", {})
    input_datalake_id = typer.prompt(
        typer.style("📅 Input datalake ID", fg=typer.colors.CYAN),
        default=io.get("input_datalake_id", ""),
    )
    output_datalake_id = typer.prompt(
        typer.style("📄 Output datalake ID", fg=typer.colors.CYAN),
        default=io.get("output_datalake_id", ""),
    )
    model_version_id = typer.prompt(
        typer.style("🧠 Model version ID", fg=typer.colors.CYAN),
        default=model.get("model_version_id", ""),
    )
    tags_list = typer.prompt(
        typer.style("🏷️ Tags to use (comma-separated)", fg=typer.colors.CYAN),
        default=stored_params.get("parameters", {}).get("tags_list", ""),
    )
    offset = typer.prompt(
        typer.style("↪ Offset", fg=typer.colors.CYAN),
        default=stored_params.get("run_parameters", {}).get("offset", "0"),
    )
    limit = typer.prompt(
        typer.style("🔗 Limit", fg=typer.colors.CYAN),
        default=stored_params.get("run_parameters", {}).get("limit", "100"),
    )

    return {
        "io": {
            "input_datalake_id": input_datalake_id,
            "output_datalake_id": output_datalake_id,
        },
        "model": {"model_version_id": model_version_id},
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

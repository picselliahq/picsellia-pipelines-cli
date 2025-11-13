import os
from pathlib import Path

import toml
import typer

from picsellia_pipelines_cli.utils.env_utils import (
    get_env_config,
)
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig
from picsellia_pipelines_cli.utils.run_manager import RunManager
from picsellia_pipelines_cli.utils.runner import (
    create_virtual_env,
    run_pipeline_command,
)


def get_saved_run_config_path(run_manager: RunManager, run_dir: Path) -> Path:
    """Return the path to the run configuration file.

    If the provided `run_manager` implements a custom `get_run_config_path` method,
    this will be used. Otherwise, the function defaults to `<run_dir>/run_config.toml`.

    Args:
        run_manager: RunManager instance responsible for managing pipeline runs.
        run_dir: Directory where the run files are stored.

    Returns:
        Path: Path to the run configuration file.
    """
    if hasattr(run_manager, "get_run_config_path"):
        return run_manager.get_run_config_path(run_dir)
    return run_dir / "run_config.toml"


def build_pipeline_command(
    python_executable: Path,
    pipeline_script_path: Path,
    run_config_file: Path,
    mode: str = "local",
) -> list[str]:
    """Build the command used to launch a pipeline.

    Args:
        python_executable: Path to the Python executable to use.
        pipeline_script_path: Path to the pipeline script (entrypoint).
        run_config_file: Path to the run configuration file.
        mode: Execution mode (e.g., "local", "remote"). Defaults to "local".

    Returns:
        list[str]: List of command-line arguments ready to be executed.
    """
    return [
        str(python_executable),
        str(pipeline_script_path),
        "--config-file",
        str(run_config_file),
        "--mode",
        mode,
    ]


def merge_with_default_parameters(
    run_config: dict, default_parameters: dict, parameters_name: str = "parameters"
) -> dict:
    """Merge run configuration parameters with default pipeline parameters.

    - Existing values in `run_config[parameters_name]` are preserved.
    - Missing values are filled in from `default_parameters`.

    Args:
        run_config: Current configuration dictionary (typically loaded from `run_config.toml`).
        default_parameters: Default parameters defined in the pipeline configuration.
        parameters_name: Key under which parameters are stored. Defaults to "parameters".

    Returns:
        dict: Updated run configuration with merged parameters.
    """
    run_config.setdefault(parameters_name, {})
    merged_params = default_parameters.copy()

    # Override defaults with values from run_config
    merged_params.update(run_config[parameters_name])

    # Update run_config with merged values
    run_config[parameters_name] = merged_params
    return run_config


def prepare_auth_and_env(run_config: dict) -> tuple[dict, dict]:
    """
    Use the current CLI context (set via `pxl-pipeline login`) to fill auth info.
    Never prompts. If no context/token, get_env_config() will exit with a clear message.
    """
    env_config = get_env_config()  # reads current context
    run_config.setdefault("auth", {}).update(
        {
            "organization_name": env_config["organization_name"],
            "env": env_config["env"],
            "host": env_config["host"],
        }
    )
    return run_config, env_config


def load_or_init_run_config(
    run_config_path: Path | None,
    run_manager,
    pipeline_type: str,
    pipeline_name: str,
    get_params_func,
    default_params: dict,
    working_dir: Path,
    parameters_name: str = "parameters",
) -> dict:
    if run_config_path and run_config_path.exists():
        run_config = toml.load(run_config_path)
    else:
        run_config = get_params_func(
            run_manager=run_manager,
            pipeline_type=pipeline_type,
            pipeline_name=pipeline_name,
            config_file=None,
        )

    run_config.setdefault("run", {})
    run_config["run"]["working_dir"] = str(working_dir)

    run_config = merge_with_default_parameters(
        run_config=run_config,
        default_parameters=default_params,
        parameters_name=parameters_name,
    )
    return run_config


def select_run_dir(run_manager: RunManager, reuse_dir: bool) -> Path:
    if reuse_dir:
        run_dir = run_manager.get_latest_run_dir()
        if not run_dir:
            run_dir = run_manager.get_next_run_dir()
    else:
        run_dir = run_manager.get_next_run_dir()
    return run_dir


def resolve_run_config_path(
    run_manager: RunManager, reuse_dir: bool, run_config_file: str | None
) -> Path | None:
    if run_config_file:
        run_config_path = Path(run_config_file)
        if not run_config_path.exists():
            typer.echo(f"❌ Run config file not found: {run_config_path}")
            raise typer.Exit(code=1)
        return run_config_path

    if reuse_dir:
        return run_manager.get_latest_run_config_path()

    return None


def save_and_get_run_config_path(
    run_manager: RunManager, run_dir: Path, run_config: dict
) -> Path:
    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)
    return get_saved_run_config_path(run_manager=run_manager, run_dir=run_dir)


def prepare_python_executable(pipeline_config: PipelineConfig) -> Path:
    env_path = create_virtual_env(
        requirements_path=pipeline_config.get_requirements_path()
    )
    return (
        env_path / "Scripts" / "python.exe"
        if os.name == "nt"
        else env_path / "bin" / "python"
    )


def run_pipeline(
    pipeline_config: PipelineConfig,
    run_config_path: Path,
    python_executable: Path,
    api_token: str,
):
    command = build_pipeline_command(
        python_executable=python_executable,
        pipeline_script_path=pipeline_config.get_script_path("pipeline_script"),
        run_config_file=run_config_path,
        mode="local",
    )

    run_pipeline_command(
        command=command,
        api_token=api_token,
    )

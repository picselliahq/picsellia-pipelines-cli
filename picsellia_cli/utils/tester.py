from pathlib import Path

from picsellia_cli.utils.run_manager import RunManager


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

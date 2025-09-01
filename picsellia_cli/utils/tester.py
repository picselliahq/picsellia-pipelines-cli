from pathlib import Path

from picsellia_cli.utils.run_manager import RunManager


def get_saved_run_config_path(run_manager: RunManager, run_dir: Path) -> Path:
    if hasattr(run_manager, "get_run_config_path"):
        return run_manager.get_run_config_path(run_dir)
    return run_dir / "run_config.toml"


def build_pipeline_command(
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

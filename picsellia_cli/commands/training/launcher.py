from pathlib import Path

import toml

from picsellia_cli.commands.training.utils.test import (
    normalize_training_io,
    get_training_params,
)
from picsellia_cli.utils.env_utils import (
    get_host_env_config,
    ensure_env_vars,
)
from picsellia_cli.utils.initializer import init_client
from picsellia_cli.utils.logging import hr
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.run_manager import RunManager
from picsellia_cli.utils.tester import merge_with_default_parameters


def launch_training(
    pipeline_name: str,
    run_config_file: str,
    host: str = "prod",
):
    ensure_env_vars(host=host)
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)
    run_manager = RunManager(pipeline_dir=pipeline_config.pipeline_dir)

    run_dir = run_manager.get_next_run_dir()

    run_config_path = Path(run_config_file) if run_config_file else None

    if run_config_path and run_config_path.exists():
        run_config = toml.load(run_config_path)
        run_config.setdefault("run", {})
        run_config["run"]["working_dir"] = str(run_dir)
    else:
        run_config = get_training_params(run_manager=run_manager, config_file=None)
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

    default_pipeline_params = pipeline_config.extract_default_parameters()
    run_config = merge_with_default_parameters(
        run_config=run_config, default_parameters=default_pipeline_params
    )

    client = init_client(host=run_config["auth"]["host"])
    normalize_training_io(client=client, run_config=run_config)

    run_manager.save_run_config(run_dir=run_dir, config_data=run_config)

    experiment = client.get_experiment_by_id(run_config["output"]["experiment"]["id"])

    experiment.launch()

    hr()

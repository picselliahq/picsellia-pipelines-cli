from picsellia_cli.utils.deployer import (
    build_docker_image_only,
    prompt_docker_image_if_missing,
)
from picsellia_cli.utils.env_utils import ensure_env_vars, get_host_env_config
from picsellia_cli.utils.pipeline_config import PipelineConfig
from picsellia_cli.utils.smoke_tester import run_smoke_test_container


def smoke_test_processing(
    pipeline_name: str,
    host: str = "prod",
):
    ensure_env_vars(host=host)
    config = PipelineConfig(pipeline_name=pipeline_name)
    prompt_docker_image_if_missing(pipeline_config=config)

    image_name = config.get("docker", "image_name")
    image_tag = config.get("docker", "image_tag")

    full_image_name = f"{image_name}:{image_tag}"

    build_docker_image_only(
        pipeline_dir=config.pipeline_dir,
        full_image_name=full_image_name,
    )

    env_config = get_host_env_config(host=host)

    env_vars = {
        "api_token": env_config["api_token"],
        "organization_name": env_config["organization_name"],
        "host": env_config["host"],
        "DEBUG": "True",
    }

    pipeline_script = (
        f"{pipeline_name}/{config.get('execution', 'picsellia_pipeline_script')}"
    )

    run_smoke_test_container(
        image=full_image_name, script=pipeline_script, env_vars=env_vars
    )

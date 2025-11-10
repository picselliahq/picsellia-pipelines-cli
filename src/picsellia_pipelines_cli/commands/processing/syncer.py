import json
import re

import typer
from picsellia.exceptions import ResourceNotFoundError

from picsellia_pipelines_cli.utils.env_utils import Environment, get_env_config
from picsellia_pipelines_cli.utils.initializer import init_client
from picsellia_pipelines_cli.utils.logging import kv, section
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig


def sync_processing_params(
    pipeline_name: str,
    organization: str,
    env: Environment | None = None,
):
    pipeline_config = PipelineConfig(pipeline_name=pipeline_name)

    # ── Environment ─────────────────────────────────────────────────────────
    section("🌍 Environment")
    env_config = get_env_config(organization=organization, env=env)
    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    client = init_client(env_config=env_config)

    params = pipeline_config.extract_default_parameters()
    if not params:
        typer.echo("❌ No 'default_parameters' section found in config.toml.")
        raise typer.Exit()

    # Step 1: Update local scripts
    for script_key in ["picsellia_pipeline_script", "local_pipeline_script"]:
        path = pipeline_config.get_script_path(script_key)
        update_script_parameters(str(path), params)
        typer.echo(f"✅ Updated parameters in: {path.name}")

    try:
        processing = client.get_processing(name=pipeline_config.get("metadata", "name"))
        processing.update(default_parameters=params)
        typer.echo(
            f"☁️ Updated processing '{pipeline_config.pipeline_name}' on Picsellia."
        )
    except ResourceNotFoundError:
        typer.echo(
            "ℹ️ Processing does not exist yet on Picsellia. Skipped remote update."
        )


def update_script_parameters(script_path: str, new_params: dict):
    with open(script_path) as f:
        content = f.read()

    new_param_str = json.dumps(new_params, indent=4)
    pattern = r"processing_parameters=\{[\s\S]*?\}"  # matches full param block
    replacement = f"processing_parameters={new_param_str}"

    new_content = re.sub(pattern, replacement, content)

    with open(script_path, "w") as f:
        f.write(new_content)

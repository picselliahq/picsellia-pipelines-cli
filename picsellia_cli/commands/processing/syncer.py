import json
import re
import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError

from picsellia_cli.utils.pipeline_config import PipelineConfig, EnvConfig

app = typer.Typer(help="Sync processing parameters across code and remote.")


def update_script_parameters(script_path: str, new_params: dict):
    with open(script_path, "r") as f:
        content = f.read()

    new_param_str = json.dumps(new_params, indent=4)
    pattern = r"processing_parameters=\{[\s\S]*?\}"  # matches full param block
    replacement = f"processing_parameters={new_param_str}"

    new_content = re.sub(pattern, replacement, content)

    with open(script_path, "w") as f:
        f.write(new_content)


@app.command()
def sync_processing_params(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the processing pipeline to sync"
    ),
):
    config = PipelineConfig(pipeline_name)
    env = EnvConfig()

    params = config.get_parameters()
    if not params:
        typer.echo("❌ No 'default_parameters' section found in config.toml.")
        raise typer.Exit()

    # Step 1: Update local scripts
    for script_key in ["picsellia_pipeline_script", "local_pipeline_script"]:
        path = config.get_script_path(script_key)
        update_script_parameters(str(path), params)
        typer.echo(f"✅ Updated parameters in: {path.name}")

    # Step 2: Try syncing to Picsellia if processing exists
    client = Client(
        api_token=env.get_api_token(),
        organization_name=env.get_organization_name(),
        host=env.get_host(),
    )

    try:
        processing = client.get_processing(name=config.pipeline_name)
        processing.update(default_parameters=params)
        typer.echo(f"☁️ Updated processing '{config.pipeline_name}' on Picsellia.")
    except ResourceNotFoundError:
        typer.echo(
            "ℹ️ Processing does not exist yet on Picsellia. Skipped remote update."
        )

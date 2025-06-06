import os

import typer
from picsellia import Client

from picsellia_cli.utils.env_utils import require_env_var


def init_client() -> Client:
    return Client(
        api_token=require_env_var("API_TOKEN"),
        organization_name=require_env_var("ORGANIZATION_NAME"),
        host=os.getenv("HOST", "https://app.picsellia.com"),
    )


def handle_pipeline_name(pipeline_name: str) -> str:
    """
    This function checks if the pipeline name contains dashes ('-') and prompts the user to either
    replace them with underscores ('_') or modify the name entirely.

    Args:
        pipeline_name (str): The original pipeline name to check and modify.

    Returns:
        str: The modified pipeline name.
    """
    if "-" in pipeline_name:
        replace_dashes = typer.prompt(
            f"The pipeline name '{pipeline_name}' contains a dash ('-'). "
            "Would you like to replace all dashes with underscores? (yes/no)",
            type=str,
            default="yes",
        ).lower()

        if replace_dashes == "yes":
            pipeline_name = pipeline_name.replace("-", "_")
            typer.echo(f"✅ The pipeline name has been updated to: '{pipeline_name}'")
        else:
            pipeline_name = typer.prompt(
                "Please enter a new pipeline name without dashes ('-'):",
                type=str,
            )
            typer.echo(f"✅ The pipeline name has been updated to: '{pipeline_name}'")

    return pipeline_name

import typer
from picsellia import Client


def init_client(env_config: dict) -> Client:
    return Client(
        api_token=env_config["api_token"],
        organization_name=env_config["organization_name"],
        host=env_config["host"],
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

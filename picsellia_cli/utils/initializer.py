import os

from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType
import typer


def write_pipeline_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def create_or_get_model_version(
    client: Client,
    model_name: str,
    version_name: str,
    framework: str,
    inference_type: str,
):
    try:
        model = client.get_model(name=model_name)
    except ResourceNotFoundError:
        model = client.create_model(name=model_name)

    try:
        model.get_version(version_name)
        raise ValueError("Version already exists.")
    except ResourceNotFoundError:
        return model.create_version(
            name=version_name,
            framework=Framework(framework),
            type=InferenceType(inference_type),
            base_parameters={
                "epochs": 2,
                "batch_size": 8,
                "image_size": 640,
            },
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

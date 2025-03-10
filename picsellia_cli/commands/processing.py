import typer
from picsellia_cli.utils.collect_params import collect_parameters
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Manage processing configurations.")


@app.command()
def add():
    """
    Add a new pipeline configuration (processing or training).
    """
    processing_name: str = typer.prompt("Processing name")

    processing_data = {
        "processing_type": typer.prompt(
            "Processing type", default="DATASET_VERSION_CREATION"
        ),
        "picsellia_pipeline_script_path": typer.prompt(
            "Picsellia pipeline script path",
            default="examples/processing/augmentation/augmentations_pipeline.py",
        ),
        "local_pipeline_script_path": typer.prompt(
            "Local pipeline script path",
            default="examples/processing/augmentation/local_augmentations_pipeline.py",
        ),
        "requirements_path": typer.prompt(
            "Requirements file path",
            default="examples/processing/augmentation/requirements.txt",
        ),
        "image_name": typer.prompt("Docker image name"),
        "image_tag": typer.prompt("Docker image tag", default="latest"),
        "parameters": {},
    }

    # Collect parameters
    parameters_mode = typer.prompt(
        "Enter 'manual', 'file', or 'none' for parameters", default="none"
    )

    if parameters_mode == "manual":
        parameters: dict[str, str] = {}
        while True:
            key = typer.prompt("Parameter key (leave empty to stop)", default="")
            if not key:
                break
            value = typer.prompt(f"Value for '{key}'")
            parameters[key] = value
        processing_data["parameters"] = parameters

    elif parameters_mode == "file":
        json_path = typer.prompt("Path to JSON file")
        processing_data["parameters"] = collect_parameters("file", json_path)

    # Save processing
    session_manager.add_processing(processing_name, processing_data)
    typer.echo(f"✅ Processing '{processing_name}' added or updated successfully!")


@app.command()
def remove(name: str):
    """
    Remove an existing pipeline configuration.
    """
    try:
        session_manager.remove_processing(name)
        typer.echo(f"✅ Processing '{name}' deleted successfully!")
    except KeyError as e:
        typer.echo(f"⚠️ {e}")


@app.command(name="list")
def list_():
    """
    List all registered pipelines.
    """
    processings = session_manager.list_processings()
    if not processings:
        typer.echo("⚠️ No processings registered.")
    else:
        typer.echo("📋 Registered processings:")
        for processing in processings:
            typer.echo(f"  - {processing}")


if __name__ == "__main__":
    app()

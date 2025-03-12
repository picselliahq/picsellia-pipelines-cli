import os
import typer

from picsellia_cli.utils.templates import (
    get_picsellia_pipeline_template,
    get_local_pipeline_template,
    get_dockerfile_template,
    get_requirements_template,
    get_process_dataset_template,
    get_dockerignore_template,
)
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Initialize and register a new pipeline.")


@app.command(name="init")
def init_pipeline(pipeline_name: str):
    """
    Creates a new pipeline directory with the necessary files and registers it in the session.

    This command generates a pipeline structure including:
    - `picsellia_pipeline.py`
    - `local_pipeline.py`
    - `process_dataset.py`
    - `Dockerfile`
    - `requirements.txt`
    - `.dockerignore`

    The pipeline is automatically registered in the session manager but does not yet have a Docker image assigned.
    """
    session_manager.ensure_session_initialized()

    os.makedirs(pipeline_name, exist_ok=True)

    # Generate pipeline files from templates
    with open(os.path.join(pipeline_name, "picsellia_pipeline.py"), "w") as f:
        f.write(get_picsellia_pipeline_template(pipeline_name))

    with open(os.path.join(pipeline_name, "local_pipeline.py"), "w") as f:
        f.write(get_local_pipeline_template(pipeline_name))

    with open(os.path.join(pipeline_name, "process_dataset.py"), "w") as f:
        f.write(get_process_dataset_template())

    with open(os.path.join(pipeline_name, "Dockerfile"), "w") as f:
        f.write(get_dockerfile_template(pipeline_name))

    with open(os.path.join(pipeline_name, "requirements.txt"), "w") as f:
        f.write(get_requirements_template())

    with open(os.path.join(pipeline_name, ".dockerignore"), "w") as f:
        f.write(get_dockerignore_template())

    # Register pipeline in TinyDB (session manager)
    pipeline_data = {
        "pipeline_name": pipeline_name,
        "pipeline_type": "DATASET_VERSION_CREATION",
        "picsellia_pipeline_script_path": f"{pipeline_name}/picsellia_pipeline.py",
        "local_pipeline_script_path": f"{pipeline_name}/local_pipeline.py",
        "requirements_path": f"{pipeline_name}/requirements.txt",
        "image_name": None,  # To be set during deployment
        "image_tag": None,  # To be set during deployment
        "parameters": {
            "datalake": "default",
            "data_tag": "processed",
        },
    }

    session_manager.add_pipeline(pipeline_name, pipeline_data)

    # Confirmation messages
    typer.echo(
        f"\n ✅ Pipeline '{pipeline_name}' successfully initialized and registered!"
    )
    typer.echo(
        "📂 Navigate to the pipeline directory and modify your scripts as needed."
    )
    typer.echo("🛠️ Modify the `process_images` function in `process_dataset.py`.")
    typer.echo("🚀 Run the pipeline locally using `pipeline-cli test`.")
    typer.echo(
        "📦 When ready, deploy the pipeline to Picsellia using `pipeline-cli deploy`."
    )


if __name__ == "__main__":
    app()

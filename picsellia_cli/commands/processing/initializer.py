import os
import typer

from picsellia_cli.commands.processing.utils.template_loader import (
    get_processing_dockerignore_template,
    get_processing_requirements_template,
    get_processing_dockerfile_template,
    get_processing_dataset_function_template,
    get_processing_local_pipeline_template,
    get_processing_picsellia_pipeline_template,
)
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Initialize and register a new pipeline.")


@app.command(name="init")
def init_processing_pipeline(pipeline_name: str):
    """
    Initialize a new dataset processing pipeline.

    This command sets up the basic structure and registers the pipeline locally.
    It includes:

    - `picsellia_pipeline.py`: Script for cloud execution (Picsellia)
    - `local_pipeline.py`: Script for local testing
    - `process_dataset.py`: Entry point for your processing logic
    - `Dockerfile`, `requirements.txt`, `.dockerignore`

    After generation:
    - The pipeline is stored in local session
    - You can run it locally using `pipeline-cli processing test`
    - Then deploy it with `pipeline-cli processing deploy`
    """
    session_manager.ensure_session_initialized()

    os.makedirs(pipeline_name, exist_ok=True)

    with open(os.path.join(pipeline_name, "picsellia_pipeline.py"), "w") as f:
        f.write(get_processing_picsellia_pipeline_template(pipeline_name))

    with open(os.path.join(pipeline_name, "local_pipeline.py"), "w") as f:
        f.write(get_processing_local_pipeline_template(pipeline_name))

    with open(os.path.join(pipeline_name, "process_dataset.py"), "w") as f:
        f.write(get_processing_dataset_function_template())

    with open(os.path.join(pipeline_name, "Dockerfile"), "w") as f:
        f.write(get_processing_dockerfile_template(pipeline_name))

    with open(os.path.join(pipeline_name, "requirements.txt"), "w") as f:
        f.write(get_processing_requirements_template())

    with open(os.path.join(pipeline_name, ".dockerignore"), "w") as f:
        f.write(get_processing_dockerignore_template())

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

    typer.echo(
        f"\n✅ Processing pipeline '{pipeline_name}' initialized and registered."
    )
    typer.echo("📁 Files created in:")
    typer.echo(f"   → {pipeline_name}/")
    typer.echo("🛠️  You can now edit `process_dataset.py` to define your logic.")
    typer.echo("🧪 Run it locally using `pipeline-cli processing test`.")
    typer.echo("🚀 Deploy to Picsellia using `pipeline-cli processing deploy`.")


if __name__ == "__main__":
    app()

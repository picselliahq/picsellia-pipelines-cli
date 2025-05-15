import os
import typer
from typing import Optional

from picsellia import Client
from picsellia.types.enums import ProcessingType

from picsellia_cli.utils.deployer import (
    get_pipeline_data,
    prompt_docker_image_if_missing,
    build_and_push_docker_image,
)
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Deploy a processing pipeline to Picsellia.")


def register_processing_pipeline_on_picsellia(
    pipeline_name: str,
    pipeline_data: dict,
    cpu: int,
    gpu: int,
):
    """
    Register a processing pipeline in Picsellia.
    """
    global_data: Optional[dict] = session_manager.get_global_session()
    if not global_data:
        typer.echo("❌ Global session not initialized. Run `pipeline-cli init` first.")
        raise typer.Exit()

    client = Client(
        api_token=global_data["api_token"],
        organization_name=global_data["organization_name"],
        host=global_data["host"],
    )

    try:
        client.create_processing(
            name=pipeline_name,
            type=ProcessingType(pipeline_data["pipeline_type"]),
            default_cpu=cpu,
            default_gpu=gpu,
            default_parameters=pipeline_data["parameters"],
            docker_image=pipeline_data["image_name"],
            docker_tag=pipeline_data["image_tag"],
            docker_flags=None,
        )
        typer.echo(
            f"✅ Processing pipeline '{pipeline_name}' successfully registered on Picsellia!"
        )

    except Exception as e:
        typer.echo(f"❌ Error registering pipeline on Picsellia: {e}")
        raise typer.Exit()


@app.command()
def deploy_processing(
    pipeline_name: str = typer.Argument(
        ..., help="Name of the processing pipeline to deploy"
    ),
):
    """
    🚀 Deploy a processing pipeline: build & push its Docker image, then register it on Picsellia.
    """
    pipeline_data = get_pipeline_data(pipeline_name)
    pipeline_data = prompt_docker_image_if_missing(pipeline_name, pipeline_data)

    cpu = int(typer.prompt("Enter CPU allocation", default=4))
    gpu = int(typer.prompt("Enter GPU allocation", default=0))

    repo_root = os.getcwd()
    pipeline_dir = os.path.join(repo_root, "pipelines", pipeline_name)

    build_and_push_docker_image(
        pipeline_dir,
        pipeline_data["image_name"],
        pipeline_data["image_tag"],
        force_login=False,
    )

    register_processing_pipeline_on_picsellia(
        pipeline_name=pipeline_name,
        pipeline_data=pipeline_data,
        cpu=cpu,
        gpu=gpu,
    )


if __name__ == "__main__":
    app()

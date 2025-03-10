import typer
from picsellia_cli.utils.prompt import fetch_processing_name
from picsellia_cli.utils.validation import validate_and_update_processing
from picsellia_cli.utils.session_manager import session_manager

from picsellia import Client
from picsellia.types.enums import ProcessingType

app = typer.Typer(help="Push processing pipeline to Picsellia.")


@app.command()
def picsellia_push():
    """
    Push the pipeline to Picsellia.
    """
    session_manager.ensure_session_initialized()

    processing_name = fetch_processing_name()
    if not processing_name:
        typer.echo("❌ No processing name provided.")
        return

    processing = validate_and_update_processing(processing_name)
    if not processing:
        typer.echo("❌ Invalid processing configuration.")
        return

    default_cpu: int = typer.prompt("Default CPU", default=4)
    default_gpu: int = typer.prompt("Default GPU", default=0)

    global_data = session_manager.get_global()

    try:
        client = Client(
            api_token=global_data["api_token"],
            organization_id=global_data["organization_id"],
        )

        client.create_processing(
            name=processing_name,
            type=ProcessingType(processing["processing_type"]),
            default_cpu=default_cpu,
            default_gpu=default_gpu,
            default_parameters=processing["parameters"],
            docker_image=processing["image_name"],
            docker_tag=processing["image_tag"],
            docker_flags=None,
        )

        typer.echo(
            f"✅ Processing '{processing_name}' pushed successfully to Picsellia!"
        )

    except Exception as e:
        typer.echo(f"❌ Error pushing processing to Picsellia: {e}")


if __name__ == "__main__":
    app()

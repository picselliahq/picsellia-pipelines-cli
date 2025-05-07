import typer
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Manage registered pipelines.")


@app.command(name="remove")
def remove_pipeline(pipeline_name: str):
    """
    Delete a registered pipeline from the session manager.

    This removes the pipeline from the session storage but does not delete
    any associated files from disk.
    """
    try:
        session_manager.remove_pipeline(pipeline_name)
        typer.echo(f"✅ Pipeline '{pipeline_name}' successfully removed!")
    except KeyError:
        typer.echo(f"⚠️ Pipeline '{pipeline_name}' not found.")


@app.command(name="list")
def list_pipelines():
    """
    Display all registered pipelines.

    Shows a list of all pipelines stored in the session manager.
    """
    pipelines = session_manager.list_pipelines()
    if not pipelines:
        typer.echo("⚠️ No pipelines registered.")
    else:
        typer.echo("📋 Registered pipelines:")
        for pipeline in pipelines:
            typer.echo(f"  - {pipeline}")


if __name__ == "__main__":
    app()

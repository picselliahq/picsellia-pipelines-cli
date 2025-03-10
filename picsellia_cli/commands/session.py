import typer
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Session management commands.")


@app.command()
def session_init():
    """
    Initialize a session for managing pipelines.
    """
    session_manager.ensure_session_initialized()
    typer.echo("✅ Global session initialized successfully!")


if __name__ == "__main__":
    app()

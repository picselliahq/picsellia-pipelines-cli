import typer

from picsellia_cli.commands.build_and_push_processing import docker_build_and_push
from picsellia_cli.commands.docker_pipeline import setup_docker
from picsellia_cli.commands.processing import add, remove, list_
from picsellia_cli.commands.push_processing_on_picsellia import picsellia_push
from picsellia_cli.commands.session import session_init
from picsellia_cli.commands.test_processing import test

app = typer.Typer(help="CLI for managing pipelines with session support.")

# Registering commands
app.command("session-init", help="Initialize a session for managing pipelines.")(
    session_init
)
app.command("add", help="Add a new pipeline configuration (processing or training).")(
    add
)
app.command("remove", help="Remove an existing pipeline configuration.")(remove)
app.command("list", help="List all registered pipelines.")(list_)
app.command("test", help="Run a local test of a pipeline.")(test)
app.command("setup-docker", help="Generate a Dockerized environment for the pipeline.")(
    setup_docker
)
app.command("build", help="Build a Docker image for the pipeline.")(
    docker_build_and_push
)
app.command("push", help="Push the pipeline to Picsellia.")(picsellia_push)

if __name__ == "__main__":
    app()

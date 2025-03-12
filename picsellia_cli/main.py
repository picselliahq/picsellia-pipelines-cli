import typer
from picsellia_cli.commands.pipeline_initializer import init_pipeline
from picsellia_cli.commands.pipeline_manager import remove_pipeline, list_pipelines
from picsellia_cli.commands.pipeline_tester import test_pipeline
from picsellia_cli.commands.pipeline_deployer import deploy_pipeline

app = typer.Typer(help="CLI for managing pipelines with session support.")

# Register commands
app.command("init", help="Initialize a new pipeline project.")(init_pipeline)
app.command("remove", help="Remove an existing pipeline configuration.")(
    remove_pipeline
)
app.command("list", help="List all registered pipelines.")(list_pipelines)
app.command("test", help="Run a local test of a pipeline.")(test_pipeline)
app.command(
    "deploy", help="Build & push Docker image, then register pipeline on Picsellia."
)(deploy_pipeline)

if __name__ == "__main__":
    app()

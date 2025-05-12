import typer

from picsellia_cli.commands.processing.deployer import deploy_processing
from picsellia_cli.commands.processing.initializer import init_processing
from picsellia_cli.commands.processing.tester import test_processing
from picsellia_cli.commands.training.deployer import deploy_training
from picsellia_cli.commands.training.initializer import init_training
from picsellia_cli.commands.training.tester import test_training
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer()


@app.command(name="init")
def init(
    pipeline_name: str,
    type: str = typer.Option(..., help="Type of pipeline ('training' or 'processing')"),
    template: str = typer.Option("simple", help="Template to use"),
):
    if type == "training":
        init_training(pipeline_name=pipeline_name, template=template)
    elif type == "processing":
        init_processing(pipeline_name=pipeline_name, template=template)
    else:
        typer.echo(
            f"❌ Invalid pipeline type '{type}'. Must be 'training' or 'processing'."
        )
        raise typer.Exit()


@app.command(name="test")
def test(pipeline_name: str):
    pipeline_data = session_manager.get_pipeline(pipeline_name)
    if not pipeline_data:
        typer.echo(f"❌ Pipeline '{pipeline_name}' not found.")
        raise typer.Exit()

    pipeline_type = pipeline_data.get("pipeline_type")
    if pipeline_type == "TRAINING":
        test_training(pipeline_name=pipeline_name)
    elif pipeline_type == "DATASET_VERSION_CREATION":
        test_processing(pipeline_name=pipeline_name)
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="deploy")
def deploy(pipeline_name: str):
    pipeline_data = session_manager.get_pipeline(pipeline_name)
    if not pipeline_data:
        typer.echo(f"❌ Pipeline '{pipeline_name}' not found.")
        raise typer.Exit()

    pipeline_type = pipeline_data.get("pipeline_type")
    if pipeline_type == "TRAINING":
        deploy_training(pipeline_name=pipeline_name)
    elif pipeline_type == "DATASET_VERSION_CREATION":
        deploy_processing(pipeline_name=pipeline_name)
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


if __name__ == "__main__":
    app()

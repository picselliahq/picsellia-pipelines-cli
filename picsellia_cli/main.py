import typer

from picsellia_cli.commands.processing.deployer import deploy_processing
from picsellia_cli.commands.processing.initializer import init_processing
from picsellia_cli.commands.processing.syncer import sync_processing_params
from picsellia_cli.commands.processing.tester import test_processing
from picsellia_cli.commands.training.deployer import deploy_training
from picsellia_cli.commands.training.initializer import init_training
from picsellia_cli.commands.training.tester import test_training
from picsellia_cli.utils.pipeline_config import PipelineConfig

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


def get_pipeline_type(pipeline_name: str) -> str:
    try:
        config = PipelineConfig(pipeline_name)
        pipeline_type = config.get("metadata", "type")
        if not pipeline_type:
            raise ValueError
        return pipeline_type
    except Exception:
        typer.echo(f"❌ Could not determine type for pipeline '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="test")
def test(pipeline_name: str):
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type == "TRAINING":
        test_training(pipeline_name=pipeline_name)
    elif pipeline_type == "DATASET_VERSION_CREATION":
        test_processing(pipeline_name=pipeline_name)
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="deploy")
def deploy(pipeline_name: str):
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type == "TRAINING":
        deploy_training(pipeline_name=pipeline_name)
    elif pipeline_type == "DATASET_VERSION_CREATION":
        deploy_processing(pipeline_name=pipeline_name)
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="sync")
def sync(pipeline_name: str):
    pipeline_type = get_pipeline_type(pipeline_name)

    if pipeline_type == "DATASET_VERSION_CREATION":
        sync_processing_params(pipeline_name=pipeline_name)
    elif pipeline_type == "TRAINING":
        typer.echo("⚠️ Syncing training parameters is not implemented yet.")
        # sync_training_params(pipeline_name=pipeline_name)
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


if __name__ == "__main__":
    app()

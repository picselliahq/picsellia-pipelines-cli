import typer

from picsellia_cli.commands.processing.deployer import deploy_processing
from picsellia_cli.commands.processing.initializer import init_processing
from picsellia_cli.commands.processing.launcher import launch_processing
from picsellia_cli.commands.processing.smoke_tester import smoke_test_processing
from picsellia_cli.commands.processing.syncer import sync_processing_params
from picsellia_cli.commands.processing.tester import test_processing
from picsellia_cli.commands.training.deployer import deploy_training
from picsellia_cli.commands.training.initializer import init_training
from picsellia_cli.commands.training.launcher import launch_training
from picsellia_cli.commands.training.smoke_tester import smoke_test_training
from picsellia_cli.commands.training.tester import test_training
from picsellia_cli.utils.env_utils import Environment
from picsellia_cli.utils.pipeline_config import PipelineConfig

app = typer.Typer()

VALID_PIPELINE_TYPES = ["training", "processing"]
PROCESSING_TEMPLATES = [
    "dataset_version_creation",
    "pre_annotation",
    "data_auto_tagging",
]
TRAINING_TEMPLATES = ["yolov8"]
PROCESSING_TYPES_MAPPING = {
    "dataset_version_creation": "DATASET_VERSION_CREATION",
    "pre_annotation": "PRE_ANNOTATION",
    "data_auto_tagging": "DATA_AUTO_TAGGING",
}


@app.command(name="init")
def init(
    pipeline_name: str,
    type: str = typer.Option(
        None, help="Type of pipeline ('training' or 'processing')"
    ),
    template: str = typer.Option(None, help="Template to use"),
    output_dir: str = typer.Option(".", help="Where to create the pipeline"),
    use_pyproject: bool = typer.Option(True, help="Use pyproject.toml"),
):
    if type is None:
        typer.secho(
            f"❌ Missing required option: --type. Choose from {VALID_PIPELINE_TYPES}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    available_templates = (
        PROCESSING_TEMPLATES if type == "processing" else TRAINING_TEMPLATES
    )

    if template is None:
        typer.secho(
            f"❌ Missing required option: --template. Choose from: {', '.join(available_templates)}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if type not in VALID_PIPELINE_TYPES:
        typer.secho(
            f"❌ Invalid type: '{type}'. Choose from {VALID_PIPELINE_TYPES}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if template not in available_templates:
        typer.echo(
            f"❌ Invalid template '{template}' for type '{type}'.\n"
            f"👉 Available: {', '.join(available_templates)}"
        )
        raise typer.Exit(code=1)

    if type == "training":
        init_training(
            pipeline_name=pipeline_name,
            template=template,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
    elif type == "processing":
        init_processing(
            pipeline_name=pipeline_name,
            template=template,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
    else:
        typer.echo(
            f"❌ Invalid pipeline type '{type}'. Must be 'training' or 'processing'."
        )
        raise typer.Exit()


def get_pipeline_type(pipeline_name: str) -> str:
    try:
        config = PipelineConfig(pipeline_name=pipeline_name)
        pipeline_type = config.get("metadata", "type")
        if not pipeline_type:
            raise ValueError
        return pipeline_type
    except Exception:
        typer.echo(f"❌ Could not determine type for pipeline '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="test")
def test(
    pipeline_name: str,
    run_config_file: str = typer.Option(None, help="Path to a custom run config file"),
    reuse_dir: bool = typer.Option(
        False, help="Reuse previous run directory if available"
    ),
    organization: str | None = typer.Option(
        None, "--organization", help="Organization name"
    ),
    env: Environment = typer.Option(
        Environment.PROD, "--env", help="Target environment"
    ),
):
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type == "TRAINING":
        test_training(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            reuse_dir=reuse_dir,
            organization=organization,
            env=env,
        )
    elif pipeline_type in PROCESSING_TYPES_MAPPING.values():
        test_processing(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            reuse_dir=reuse_dir,
            organization=organization,
            env=env,
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="smoke-test")
def smoke_test(
    pipeline_name: str,
    run_config_file: str = typer.Option(None, help="Path to a custom run config file"),
    reuse_dir: bool = typer.Option(
        False, help="Reuse previous run directory if available"
    ),
    python_version: str = typer.Option("3.10", help="Python version for container"),
    use_gpu: bool = typer.Option(False, help="Run with GPU support"),
    organization: str | None = typer.Option(
        None, "--organization", help="Organization name"
    ),
    env: Environment = typer.Option(
        Environment.PROD, "--env", help="Target environment"
    ),
):
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type == "TRAINING":
        smoke_test_training(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            python_version=python_version,
            reuse_dir=reuse_dir,
            organization=organization,
            env=env,
        )
    elif pipeline_type in PROCESSING_TYPES_MAPPING.values():
        smoke_test_processing(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            python_version=python_version,
            use_gpu=use_gpu,
            reuse_dir=reuse_dir,
            organization=organization,
            env=env,
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="deploy")
def deploy(
    pipeline_name: str,
    organization: str | None = typer.Option(
        None,
        "--organization",
        help="Organization name",
    ),
    env: Environment = typer.Option(
        Environment.PROD, "--env", help="Target environment"
    ),
):
    pipeline_type = get_pipeline_type(pipeline_name=pipeline_name)
    if pipeline_type == "TRAINING":
        deploy_training(pipeline_name=pipeline_name, organization=organization, env=env)
    elif pipeline_type in PROCESSING_TYPES_MAPPING.values():
        deploy_processing(
            pipeline_name=pipeline_name, organization=organization, env=env
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="sync")
def sync(
    pipeline_name: str,
    organization: str = typer.Option("--organization", help="Organization name"),
    env: Environment = typer.Option(
        Environment.PROD, "--env", help="Target environment"
    ),
):
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type in PROCESSING_TYPES_MAPPING.values():
        sync_processing_params(
            pipeline_name=pipeline_name, organization=organization, env=env
        )
    elif pipeline_type == "TRAINING":
        typer.echo("⚠️ Syncing training parameters is not implemented yet.")
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="launch")
def launch(
    pipeline_name: str,
    run_config_file: str = typer.Option(help="Path to a custom run config file"),
    organization: str | None = typer.Option(
        None, "--organization", help="Organization name"
    ),
    env: Environment = typer.Option(
        Environment.PROD, "--env", help="Target environment"
    ),
):
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type in PROCESSING_TYPES_MAPPING.values():
        launch_processing(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            organization=organization,
            env=env,
        )
    elif pipeline_type == "TRAINING":
        launch_training(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            organization=organization,
            env=env,
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


if __name__ == "__main__":
    app()

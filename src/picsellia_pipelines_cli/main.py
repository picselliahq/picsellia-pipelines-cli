from __future__ import annotations

from typing import Annotated

import typer

from picsellia_pipelines_cli.commands.auth import login, logout, whoami
from picsellia_pipelines_cli.commands.auth import switch as auth_switch
from picsellia_pipelines_cli.commands.processing.deployer import deploy_processing
from picsellia_pipelines_cli.commands.processing.initializer import init_processing
from picsellia_pipelines_cli.commands.processing.launcher import launch_processing
from picsellia_pipelines_cli.commands.processing.smoke_tester import (
    smoke_test_processing,
)
from picsellia_pipelines_cli.commands.processing.syncer import sync_processing_params
from picsellia_pipelines_cli.commands.processing.tester import test_processing
from picsellia_pipelines_cli.commands.training.deployer import deploy_training
from picsellia_pipelines_cli.commands.training.initializer import init_training
from picsellia_pipelines_cli.commands.training.launcher import launch_training
from picsellia_pipelines_cli.commands.training.smoke_tester import smoke_test_training
from picsellia_pipelines_cli.commands.training.tester import test_training
from picsellia_pipelines_cli.utils.deployer import Bump
from picsellia_pipelines_cli.utils.env_utils import Environment
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main():
    """
    Manage Picsellia training and processing pipelines.

    Examples:

        \b
      - Authenticate and set the context:

        \b
        pxl-pipeline login

        \b
      - Initialize a new processing pipeline:

        \b
        pxl-pipeline init my_pipeline --type processing --template pre_annotation

        \b
      - Run local tests:

        \b
        pxl-pipeline test my_pipeline --run-config-file my_pipeline/runs/run_config.toml

        \b
      - Deploy to production:

        \b
        pxl-pipeline deploy my_pipeline
    """
    # No runtime logic needed; Typer just uses the docstring for `--help`.
    ...


app.command("login")(login)
app.command("logout")(logout)
app.command("whoami")(whoami)
app.command("switch")(auth_switch)


VALID_PIPELINE_TYPES = ["training", "processing"]
PROCESSING_TEMPLATES = [
    "dataset_version_creation",
    "pre_annotation",
    "data_auto_tagging",
    "model_conversion",
]
TRAINING_TEMPLATES = ["yolov8"]
PROCESSING_TYPES_MAPPING = {
    "dataset_version_creation": "DATASET_VERSION_CREATION",
    "pre_annotation": "PRE_ANNOTATION",
    "data_auto_tagging": "DATA_AUTO_TAGGING",
    "model_conversion": "MODEL_CONVERSION",
    "model_compression": "MODEL_COMPRESSION",
}


@app.command(name="init")
def init(
    pipeline_name: str,
    type: Annotated[
        str | None, typer.Option(help="Type of pipeline ('training' or 'processing')")
    ] = None,
    template: Annotated[str | None, typer.Option(help="Template to use")] = None,
    output_dir: Annotated[str, typer.Option(help="Where to create the pipeline")] = ".",
    use_pyproject: Annotated[bool, typer.Option(help="Use pyproject.toml")] = True,
):
    """Initialize a new training or processing pipeline from a template."""
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
    except Exception as e:
        typer.echo(f"❌ Could not determine type for pipeline '{pipeline_name}'.")
        raise typer.Exit() from e


@app.command(name="test")
def test(
    pipeline_name: str,
    run_config_file: Annotated[
        str | None, typer.Option(help="Path to a custom run config file")
    ] = None,
    reuse_dir: Annotated[bool, typer.Option(help="Reuse previous run directory")] = (
        False
    ),
):
    """Run local tests for a pipeline using a run config."""
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type == "TRAINING":
        test_training(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            reuse_dir=reuse_dir,
        )
    elif pipeline_type in PROCESSING_TYPES_MAPPING.values():
        test_processing(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            reuse_dir=reuse_dir,
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="smoke-test")
def smoke_test(
    pipeline_name: str,
    run_config_file: Annotated[
        str | None, typer.Option(help="Path to a custom run config file")
    ] = None,
    reuse_dir: Annotated[bool, typer.Option(help="Reuse previous run directory")] = (
        False
    ),
    python_version: Annotated[
        str, typer.Option(help="Python version for container")
    ] = "3.10",
    use_gpu: Annotated[bool, typer.Option(help="Run with GPU support")] = False,
):
    """Run a containerized smoke test for a pipeline."""
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type == "TRAINING":
        smoke_test_training(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            python_version=python_version,
            reuse_dir=reuse_dir,
        )
    elif pipeline_type in PROCESSING_TYPES_MAPPING.values():
        smoke_test_processing(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
            python_version=python_version,
            use_gpu=use_gpu,
            reuse_dir=reuse_dir,
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="deploy")
def deploy(
    pipeline_name: str,
    organization: Annotated[
        str | None, typer.Option("--organization", help="Organization name")
    ] = None,
    env: Annotated[
        Environment, typer.Option("--env", help="Target environment")
    ] = Environment.PROD,
    bump: Annotated[
        Bump | None, typer.Option("--bump", help="Version bump to apply (skip prompt)")
    ] = None,
):
    """Deploy a training or processing pipeline version to Picsellia."""
    pipeline_type = get_pipeline_type(pipeline_name=pipeline_name)
    if pipeline_type == "TRAINING":
        deploy_training(
            pipeline_name=pipeline_name, organization=organization, env=env, bump=bump
        )
    elif pipeline_type in PROCESSING_TYPES_MAPPING.values():
        deploy_processing(
            pipeline_name=pipeline_name, organization=organization, env=env, bump=bump
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


@app.command(name="sync")
def sync(
    pipeline_name: str,
    organization: Annotated[
        str | None, typer.Option("--organization", help="Organization name")
    ] = None,
    env: Annotated[
        Environment, typer.Option("--env", help="Target environment")
    ] = Environment.PROD,
):
    """Sync processing pipeline parameters from code to Picsellia."""
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
    run_config_file: Annotated[
        str, typer.Option(help="Path to a custom run config file")
    ],
):
    """Launch a remote run for a training or processing pipeline."""
    pipeline_type = get_pipeline_type(pipeline_name)
    if pipeline_type in PROCESSING_TYPES_MAPPING.values():
        launch_processing(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
        )
    elif pipeline_type == "TRAINING":
        launch_training(
            pipeline_name=pipeline_name,
            run_config_file=run_config_file,
        )
    else:
        typer.echo(f"❌ Unknown pipeline type for '{pipeline_name}'.")
        raise typer.Exit()


if __name__ == "__main__":
    app()

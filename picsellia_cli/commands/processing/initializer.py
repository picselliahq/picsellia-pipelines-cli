from typing import Optional

import typer

from picsellia_cli.commands.processing.templates.pre_annotation_template import (
    PreAnnotationTemplate,
)
from picsellia_cli.commands.processing.templates.dataset_version_creation_template import (
    DatasetVersionCreationProcessingTemplate,
)

from picsellia_cli.utils.base_template import BaseTemplate
from picsellia_cli.utils.env_utils import ensure_env_vars
from picsellia_cli.utils.initializer import handle_pipeline_name

app = typer.Typer(help="Initialize and register a new processing pipeline.")


def get_template_instance(
    template_name: str, pipeline_name: str, output_dir: str, use_pyproject: bool = True
):
    match template_name:
        case "dataset_version_creation":
            return DatasetVersionCreationProcessingTemplate(
                pipeline_name=pipeline_name,
                output_dir=output_dir,
                use_pyproject=use_pyproject,
            )
        case "pre_annotation":
            return PreAnnotationTemplate(
                pipeline_name=pipeline_name,
                output_dir=output_dir,
                use_pyproject=use_pyproject,
            )
        case _:
            typer.echo(
                typer.style(
                    f"❌ Unknown template '{template_name}'",
                    fg=typer.colors.RED,
                    bold=True,
                )
            )
            raise typer.Exit(code=1)


@app.command(name="init")
def init_processing(
    pipeline_name: str,
    template: str = typer.Option(
        "dataset_version_creation",
        help="Template to use: 'dataset_version_creation' or 'pre_annotation'",
    ),
    output_dir: Optional[str] = typer.Option(
        None, help="Where to create the pipeline folder"
    ),
    use_pyproject: Optional[bool] = typer.Option(
        True, help="Use pyproject.toml instead of requirements.txt"
    ),
):
    """
    Initialize a new dataset processing pipeline.
    """
    ensure_env_vars()
    output_dir = output_dir or "."
    use_pyproject = use_pyproject if use_pyproject is not None else True

    pipeline_name = handle_pipeline_name(pipeline_name=pipeline_name)

    template_instance = get_template_instance(
        template_name=template,
        pipeline_name=pipeline_name,
        output_dir=output_dir,
        use_pyproject=use_pyproject,
    )

    template_instance.write_all_files()
    template_instance.post_init_environment()

    _show_success_message(
        pipeline_name=pipeline_name, template_instance=template_instance
    )


def _show_success_message(pipeline_name, template_instance: BaseTemplate):
    typer.echo("")
    typer.echo(
        typer.style(
            "✅ Processing pipeline initialized and registered",
            fg=typer.colors.GREEN,
            bold=True,
        )
    )
    typer.echo(f"📁 Structure created at: {template_instance.pipeline_dir}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("- Edit your steps in: " + typer.style("steps.py", bold=True))
    typer.echo(
        "- Test locally with: "
        + typer.style(f"pipeline-cli test {pipeline_name}", fg=typer.colors.GREEN)
    )
    typer.echo(
        "- Deploy to Picsellia with: "
        + typer.style(f"pipeline-cli deploy {pipeline_name}", fg=typer.colors.GREEN)
    )
    typer.echo("")


if __name__ == "__main__":
    app()

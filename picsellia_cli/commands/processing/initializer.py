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


def init_processing(
    pipeline_name: str,
    template: str,
    output_dir: Optional[str] = None,
    use_pyproject: Optional[bool] = True,
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
        + typer.style(f"pxl-pipeline test {pipeline_name}", fg=typer.colors.GREEN)
    )
    typer.echo(
        "- Deploy to Picsellia with: "
        + typer.style(f"pxl-pipeline deploy {pipeline_name}", fg=typer.colors.GREEN)
    )
    typer.echo("")

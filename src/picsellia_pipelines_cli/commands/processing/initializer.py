import typer

from picsellia_pipelines_cli.commands.processing.templates.data_auto_tagging_template import (
    DataAutoTaggingProcessingTemplate,
)
from picsellia_pipelines_cli.commands.processing.templates.dataset_version_creation_template import (
    DatasetVersionCreationProcessingTemplate,
)
from picsellia_pipelines_cli.commands.processing.templates.model_conversion_template import (
    ModelConversionProcessingTemplate,
)
from picsellia_pipelines_cli.commands.processing.templates.pre_annotation_template import (
    PreAnnotationTemplate,
)
from picsellia_pipelines_cli.utils.base_template import BaseTemplate
from picsellia_pipelines_cli.utils.initializer import handle_pipeline_name


def init_processing(
    pipeline_name: str,
    template: str,
    output_dir: str | None = None,
    use_pyproject: bool | None = True,
):
    """
    Initialize a new **processing pipeline** project.

    This command will:
    - Validate environment variables required for Picsellia.
    - Generate a pipeline scaffold from a chosen template.
    - Write all necessary configuration and step files.
    - Set up the environment (e.g., pyproject / requirements).

    Args:
        pipeline_name (str): The name of the pipeline to initialize.
        template (str): The processing template to use.
            Supported values:
              - `"dataset_version_creation"`
              - `"pre_annotation"`
              - `"data_auto_tagging"`
        output_dir (Optional[str], default="."): Target directory where the pipeline will be created.
        use_pyproject (Optional[bool], default=True): Whether to create a `pyproject.toml` for dependency management.
        host (str, default="prod"): Picsellia host environment to target (e.g., `"prod"`, `"staging"`).
    """
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
) -> BaseTemplate:
    """
    Resolve the appropriate template class based on the provided name.

    Args:
        template_name (str): The template identifier.
        pipeline_name (str): Name of the pipeline to generate.
        output_dir (str): Output directory path.
        use_pyproject (bool, default=True): Whether to create a `pyproject.toml`.

    Returns:
        BaseTemplate: An instantiated template class.

    Raises:
        typer.Exit: If the template name is not recognized.
    """
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
        case "data_auto_tagging":
            return DataAutoTaggingProcessingTemplate(
                pipeline_name=pipeline_name,
                output_dir=output_dir,
                use_pyproject=use_pyproject,
            )
        case "model_conversion":
            return ModelConversionProcessingTemplate(
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
    typer.echo(f"📁 Files generated at: {template_instance.pipeline_dir}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("1. Edit your custom steps in: " + typer.style("steps.py", bold=True))
    typer.echo(
        "2. Test locally with: "
        + typer.style(
            f"pxl-pipeline test {pipeline_name}", fg=typer.colors.GREEN, bold=True
        )
    )
    typer.echo(
        "3. Deploy to Picsellia with: "
        + typer.style(
            f"pxl-pipeline deploy {pipeline_name}", fg=typer.colors.GREEN, bold=True
        )
    )
    typer.echo("")

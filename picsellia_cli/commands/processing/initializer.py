import typer

from picsellia_cli.commands.processing.templates.simple_template import (
    SimpleProcessingTemplate,
)
from picsellia_cli.utils.session_manager import session_manager

app = typer.Typer(help="Initialize and register a new processing pipeline.")


def get_template_instance(template_name: str, pipeline_name: str):
    match template_name:
        case "simple":
            return SimpleProcessingTemplate(pipeline_name)
        case _:
            typer.echo(
                typer.style(
                    f"❌ Unknown template '{template_name}'",
                    fg=typer.colors.RED,
                    bold=True,
                )
            )
            raise typer.Exit(code=1)


def register_pipeline(pipeline_name: str, template_instance):
    pipeline_data = {
        "pipeline_name": pipeline_name,
        "pipeline_type": "DATASET_VERSION_CREATION",
        "pipeline_dir": template_instance.pipeline_dir,
        "picsellia_pipeline_script_path": f"{template_instance.pipeline_dir}/picsellia_pipeline.py",
        "local_pipeline_script_path": f"{template_instance.pipeline_dir}/local_pipeline.py",
        "requirements_path": f"{template_instance.pipeline_dir}/requirements.txt",
        "image_name": None,
        "image_tag": None,
        "parameters": {
            "datalake": "default",
            "data_tag": "processed",
        },
    }

    return session_manager.add_pipeline(pipeline_name, pipeline_data)


@app.command(name="init")
def init_processing(
    pipeline_name: str,
    template: str = typer.Option("simple", help="Template to use: 'simple'"),
):
    """
    Initialize a new dataset processing pipeline.
    """

    session_manager.ensure_session_initialized()

    template_instance = get_template_instance(template, pipeline_name)

    if not register_pipeline(pipeline_name, template_instance):
        typer.echo("❌ Pipeline registration failed. Exiting.")
        raise typer.Exit()

    template_instance.write_all_files()
    _show_success_message(template_instance)


def _show_success_message(template_instance: SimpleProcessingTemplate):
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
        + typer.style("pipeline-cli processing test", fg=typer.colors.GREEN)
    )
    typer.echo(
        "- Deploy to Picsellia with: "
        + typer.style("pipeline-cli processing deploy", fg=typer.colors.GREEN)
    )
    typer.echo("")


if __name__ == "__main__":
    app()

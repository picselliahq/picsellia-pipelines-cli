import typer

from picsellia_cli.commands.training.utils.simple_template import SimpleTrainingTemplate
from picsellia_cli.utils.initializer import get_picsellia_client_from_session
from picsellia_cli.utils.session_manager import session_manager
from picsellia_cli.commands.training.utils.ultralytics_template import (
    UltralyticsTrainingTemplate,
)
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

app = typer.Typer(help="Initialize and register a new training pipeline.")


@app.command(name="init")
def init_training_pipeline(
    pipeline_name: str,
    template: str = typer.Option(
        "simple", help="Template to use: 'simple' or 'ultralytics'"
    ),
):
    
    client, global_session = get_picsellia_client_from_session()

    # Initialize pipeline from template
    template_instance = get_template_instance(template, pipeline_name)
    template_instance.write_all_files()

    global_session = session_manager.get_global_session()
    client = Client(
        api_token=global_session["api_token"],
        organization_name=global_session["organization_name"],
    )

    typer.echo("\nModel association")
    use_existing = typer.confirm(
        "Do you want to use an existing model version?", default=False
    )

    if use_existing:
        model_version_id = typer.prompt("Enter the model version ID")
        try:
            model_version = client.get_model_version_by_id(model_version_id)
            model_name = model_version.origin_name
            typer.echo(
                f"\n✅ Using model '{model_name}' (version ID: {model_version_id})\n"
            )
        except ResourceNotFoundError:
            typer.echo("❌ Could not find model version. Exiting.")
            raise typer.Exit()
    else:
        model_name = typer.prompt("Model name", default=pipeline_name)
        version_name = typer.prompt("Version name", default="v1")

        typer.echo("")

        framework_options = [f.name for f in Framework if f != Framework.NOT_CONFIGURED]
        inference_options = [
            i.name for i in InferenceType if i != InferenceType.NOT_CONFIGURED
        ]

        framework_input = typer.prompt(
            f"Select framework ({', '.join(framework_options)})", default="ONNX"
        )
        inference_type_input = typer.prompt(
            f"Select inference type ({', '.join(inference_options)})",
            default="OBJECT_DETECTION",
        )

        typer.echo("")

        try:
            model = client.get_model(name=model_name)
            typer.echo(f"Model '{model_name}' already exists. Reusing.")
        except ResourceNotFoundError:
            model = client.create_model(name=model_name)
            typer.echo(f"Created model '{model_name}'")

        try:
            _ = model.get_version(version_name)
            typer.echo(
                f"❌ Model version '{version_name}' already exists in model '{model_name}'."
            )
            raise typer.Exit()
        except ResourceNotFoundError:
            pass

        model_version = model.create_version(
            name=version_name,
            framework=Framework(framework_input),
            type=InferenceType(inference_type_input),
            base_parameters={
                "epochs": 2,
                "batch_size": 8,
                "image_size": 640,
            },
        )
        model_version_id = model_version.id
        typer.echo(
            f"\n✅ Created model '{model_name}' with version '{version_name}' (ID: {model_version_id})"
        )
        organization_id = client.connexion.organization_id
        typer.echo(
            "Model URL: "
            + typer.style(
                f"https://app.picsellia.com/{organization_id}/model/{model.id}/version/{model_version_id}",
                fg=typer.colors.BLUE,
            )
        )
        typer.echo()
        typer.echo(typer.style("Reminder:", fg=typer.colors.YELLOW, bold=True))
        typer.echo(
            "Upload a file named "
            + typer.style("'pretrained-weights'", fg=typer.colors.CYAN, bold=True)
            + " to this model version."
        )
        typer.echo("It's required for the training pipeline to find the weights.\n")

    # Register in session
    pipeline_data = {
        "pipeline_name": pipeline_name,
        "pipeline_type": "TRAINING",
        "picsellia_pipeline_script_path": f"{template_instance.pipeline_dir}/training_pipeline.py",
        "local_pipeline_script_path": f"{template_instance.pipeline_dir}/local_training_pipeline.py",
        "requirements_path": f"{template_instance.pipeline_dir}/requirements.txt",
        "image_name": None,
        "image_tag": None,
        "parameters": {},
        "model_version_id": str(model_version_id),
    }

    session_manager.add_pipeline(pipeline_name, pipeline_data)

    typer.echo("")
    typer.echo(
        typer.style(
            "✅ Pipeline initialized and registered", fg=typer.colors.GREEN, bold=True
        )
    )
    typer.echo(f"Structure: {template_instance.pipeline_dir}")
    typer.echo(f"Linked to model '{model_name}' (version ID: {model_version_id})\n")
    typer.echo("Next steps:")
    typer.echo(
        f"- Edit your training steps in the '{template_instance.utils_dir}' folder."
    )
    typer.echo(
        f"- Adjust context setup in '{template_instance.pipeline_dir}/training_pipeline.py' if needed."
    )
    typer.echo(
        "- Run locally with: "
        + typer.style("pipeline-cli training test", fg=typer.colors.GREEN)
    )
    typer.echo(
        "- Deploy when ready with: "
        + typer.style("pipeline-cli training deploy", fg=typer.colors.GREEN)
    )
    typer.echo("")


def get_template_instance(template_name: str, pipeline_name: str):
    match template_name:
        case "ultralytics":
            return UltralyticsTrainingTemplate(pipeline_name)
        case "simple" | _:
            return SimpleTrainingTemplate(pipeline_name)

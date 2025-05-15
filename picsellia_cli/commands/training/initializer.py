from typing import Dict, Any

import typer

from picsellia_cli.commands.training.templates.simple_template import (
    SimpleTrainingTemplate,
)
from picsellia_cli.commands.training.templates.ultralytics_template import (
    UltralyticsTrainingTemplate,
)
from picsellia_cli.utils.session_manager import session_manager
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

app = typer.Typer(help="Initialize and register a new training pipeline.")


def init_client() -> Client:
    session_manager.ensure_session_initialized()
    session = session_manager.get_global_session()
    if session is None:
        typer.echo("❌ No global session found. Please login first.")
        raise typer.Exit()

    return Client(
        api_token=session["api_token"],
        organization_name=session["organization_name"],
        host=session["host"],
    )


def get_template_instance(template_name: str, pipeline_name: str):
    match template_name:
        case "ultralytics":
            return UltralyticsTrainingTemplate(pipeline_name)
        case "simple" | _:
            return SimpleTrainingTemplate(pipeline_name)


def choose_model_version(client: Client) -> tuple[str, str]:
    if typer.confirm("Do you want to use an existing model version?", default=False):
        model_version_id = typer.prompt("Enter the model version ID")
        try:
            model_version = client.get_model_version_by_id(model_version_id)
            typer.echo(
                f"\n✅ Using model '{model_version.origin_name}' (version ID: {model_version_id})\n"
            )
            return model_version.origin_name, model_version_id
        except ResourceNotFoundError:
            typer.echo("❌ Could not find model version. Exiting.")
            raise typer.Exit()
    return create_model_version(client)


def create_model_version(client: Client) -> tuple[str, str]:
    model_name = typer.prompt("Model name")
    version_name = typer.prompt("Version name", default="v1")

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
        base_parameters={"epochs": 2, "batch_size": 8, "image_size": 640},
    )

    organization_id = client.connexion.organization_id
    typer.echo(
        f"\n✅ Created model '{model_name}' with version '{version_name}' (ID: {model_version.id})"
    )
    typer.echo(
        "Model URL: "
        + typer.style(
            f"https://app.picsellia.com/{organization_id}/model/{model.id}/version/{model_version.id}",
            fg=typer.colors.BLUE,
        )
    )
    typer.echo(
        "\nReminder: Upload a file named 'pretrained-weights' to this model version. It's required for training.\n"
    )

    return model_name, str(model_version.id)


def register_pipeline(pipeline_name: str, template_instance, model_version_id: str):
    pipeline_data: Dict[str, Any] = {
        "pipeline_name": pipeline_name,
        "pipeline_type": "TRAINING",
        "pipeline_dir": template_instance.pipeline_dir,
        "picsellia_pipeline_script_path": f"{template_instance.pipeline_dir}/training_pipeline.py",
        "local_pipeline_script_path": f"{template_instance.pipeline_dir}/local_training_pipeline.py",
        "requirements_path": f"{template_instance.pipeline_dir}/requirements.txt",
        "image_name": None,
        "image_tag": None,
        "parameters": {},
        "model_version_id": str(model_version_id),
    }

    return session_manager.add_pipeline(pipeline_name, pipeline_data)


def show_next_steps(pipeline_name, template_instance, model_name, model_version_id):
    typer.echo("\n✅ Pipeline initialized and registered.")
    typer.echo(f"Structure: {template_instance.pipeline_dir}")
    typer.echo(f"Linked to model '{model_name}' (version ID: {model_version_id})\n")
    typer.echo("Next steps:")
    typer.echo(
        f"- Edit your training steps in '{template_instance.pipeline_dir}/steps.py'"
    )
    typer.echo(
        "- Run locally with: "
        + typer.style(f"pipeline-cli test {pipeline_name}", fg=typer.colors.GREEN)
    )
    typer.echo(
        "- Deploy when ready with: "
        + typer.style(f"pipeline-cli deploy {pipeline_name}", fg=typer.colors.GREEN)
    )


@app.command(name="init")
def init_training(
    pipeline_name: str,
    template: str = typer.Option(
        "simple", help="Template to use: 'simple' or 'ultralytics'"
    ),
):
    client = init_client()
    template_instance = get_template_instance(
        template_name=template, pipeline_name=pipeline_name
    )
    model_name, model_version_id = choose_model_version(client=client)

    if not register_pipeline(
        pipeline_name=pipeline_name,
        template_instance=template_instance,
        model_version_id=model_version_id,
    ):
        typer.echo("❌ Pipeline registration failed. Exiting.")
        raise typer.Exit()

    template_instance.write_all_files()
    show_next_steps(
        pipeline_name=pipeline_name,
        template_instance=template_instance,
        model_name=model_name,
        model_version_id=model_version_id,
    )

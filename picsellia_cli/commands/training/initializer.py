from typing import Optional, Tuple
import typer

from picsellia_cli.commands.training.templates.ultralytics_template import (
    UltralyticsTrainingTemplate,
)
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

from picsellia_cli.utils.env_utils import (
    get_host_env_config,
    ensure_env_vars,
)
from picsellia_cli.utils.initializer import handle_pipeline_name, init_client
from picsellia_cli.utils.logging import section, kv, bullet, step, hr
from picsellia_cli.utils.pipeline_config import PipelineConfig


def init_training(
    pipeline_name: str,
    template: str,
    output_dir: Optional[str] = None,
    use_pyproject: Optional[bool] = True,
    host: str = "prod",
):
    ensure_env_vars(host=host)

    # Guaranteed env config (prompted if missing)
    env_cfg = get_host_env_config(host=host)

    output_dir = output_dir or "."
    use_pyproject = True if use_pyproject is None else use_pyproject
    pipeline_name = handle_pipeline_name(pipeline_name=pipeline_name)

    # Init client on chosen host
    client = init_client(host=env_cfg["host"])

    # HEADER
    section("👋 Welcome")
    org_name = (
        getattr(getattr(client, "connexion", None), "organization_name", None)
        or env_cfg["organization_name"]
    )
    org_id = getattr(getattr(client, "connexion", None), "organization_id", None)
    host_url = env_cfg["host"]
    kv("Workspace", f"{org_name} ({org_id})" if org_id else org_name)
    kv("Host", host_url)

    # TEMPLATE + PROJECT ENV
    template_instance = get_template_instance(
        template_name=template,
        pipeline_name=pipeline_name,
        output_dir=output_dir,
        use_pyproject=use_pyproject,
    )

    section("📦 Project setup")
    # ► ce bloc donne un résumé clair et non verbeux
    kv("Template", template)
    template_dir = template_instance.pipeline_dir
    bullet(
        typer.style("Template scaffold generated", bold=True) + f" at {template_dir}",
        accent=True,
    )
    bullet("Key files:")
    typer.echo("  • steps.py")
    typer.echo("  • pipeline.toml")
    if use_pyproject:
        typer.echo("  • pyproject.toml")
    # actions effectuées par le template
    template_instance.write_all_files()
    template_instance.post_init_environment()
    bullet(f"Virtual environment: {template_dir}/.venv")
    bullet("Dependencies installed and locked")

    # MODEL (single section: prompt + summary)
    section("🧠 Model")
    model_name, model_version_name, model_id, model_version_id, model_url = (
        choose_or_create_model_version(client=client)
    )
    kv("Name", model_name)
    kv("Version", model_version_name)
    kv("Version ID", model_version_id)
    kv("URL", model_url, color=typer.colors.BLUE)
    typer.echo("")
    bullet(
        "Upload a file named 'pretrained-weights' to this model version (required for training).",
        accent=True,
    )

    # Pipeline metadata (after we know the model)
    config = PipelineConfig(pipeline_name=pipeline_name)
    register_pipeline_metadata(
        config=config,
        model_name=model_name,
        model_version_name=model_version_name,
        model_version_id=model_version_id,
    )

    # NEXT STEPS — numérotés
    section("🧭 Next steps")
    step(
        1,
        f"Open {typer.style(model_url, fg=typer.colors.BLUE)} and upload "
        + typer.style("'pretrained-weights'", bold=True)
        + " to this model version.",
        accent=True,
    )
    step(
        2, "Edit training steps: " + typer.style(f"{template_dir}/steps.py", bold=True)
    )
    if use_pyproject:
        step(
            3,
            "Update dependencies in "
            + typer.style(f"{template_dir}/pyproject.toml", bold=True),
        )
        step(
            4,
            "Adjust pipeline config: "
            + typer.style(f"{template_dir}/config.toml", bold=True),
        )
        step(
            5,
            "Run locally: "
            + typer.style(
                f"pxl-pipeline test {pipeline_name}", fg=typer.colors.GREEN, bold=True
            ),
        )
        step(
            6,
            "Deploy: "
            + typer.style(
                f"pxl-pipeline deploy {pipeline_name}", fg=typer.colors.GREEN, bold=True
            ),
        )
    else:
        # fallback si pas de pyproject (rare ici, mais propre)
        step(
            3,
            "Adjust pipeline config: "
            + typer.style(f"{template_dir}/config.toml", bold=True),
        )
        step(
            4,
            "Run locally: "
            + typer.style(
                f"pxl-pipeline test {pipeline_name}", fg=typer.colors.GREEN, bold=True
            ),
        )
        step(
            5,
            "Deploy: "
            + typer.style(
                f"pxl-pipeline deploy {pipeline_name}", fg=typer.colors.GREEN, bold=True
            ),
        )
    hr()


def get_template_instance(
    template_name: str, pipeline_name: str, output_dir: str, use_pyproject: bool = True
):
    match template_name:
        case "ultralytics":
            return UltralyticsTrainingTemplate(
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


def choose_or_create_model_version(client: Client) -> Tuple[str, str, str, str, str]:
    """
    Prompt to reuse an existing model version or create a new one.

    Returns:
        (model_name, model_version_name, model_id, model_version_id, model_url)
    """
    if typer.confirm("Reuse an existing model version?", default=False):
        model_version_id = typer.prompt("Model version ID")
        mv = client.get_model_version_by_id(id=model_version_id)  # raises if not found
        return _pack_model_version(
            client=client,
            model_name=mv.origin_name,
            model_id=str(mv.origin_id),
            version_name=mv.name,
            version_id=str(mv.id),
        )

    # create new
    model_name = typer.prompt("Model name")
    model_version_name = typer.prompt("Version name", default="v1")

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

    try:
        model = client.get_model(name=model_name)
    except ResourceNotFoundError:
        model = client.create_model(name=model_name)

    # Ensure the version does not already exist
    try:
        _ = model.get_version(model_version_name)
        typer.echo(
            typer.style(
                f"❌ Model version '{model_version_name}' already exists in '{model_name}'.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit()
    except ResourceNotFoundError:
        pass

    mv = model.create_version(
        name=model_version_name,
        framework=Framework(framework_input),
        type=InferenceType(inference_type_input),
        base_parameters={"epochs": 2, "batch_size": 8, "image_size": 640},
    )
    return _pack_model_version(
        client=client,
        model_name=model.name,
        model_id=str(model.id),
        version_name=mv.name,
        version_id=str(mv.id),
    )


def _pack_model_version(
    client: Client, model_name: str, model_id: str, version_name: str, version_id: str
) -> Tuple[str, str, str, str, str]:
    org_id = client.connexion.organization_id
    host = client.connexion.host
    url = f"{host}/{org_id}/model/{model_id}/version/{version_id}"
    return model_name, version_name, str(model_id), str(version_id), url


def register_pipeline_metadata(
    config: PipelineConfig,
    model_name: str,
    model_version_name: str,
    model_version_id: str,
):
    config.config.setdefault("model", {})
    config.config["model"]["model_name"] = model_name
    config.config["model"]["model_version_name"] = model_version_name
    config.config["model"]["model_version_id"] = model_version_id

    with open(config.config_path, "w") as f:
        import toml

        toml.dump(config.config, f)

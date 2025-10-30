import typer
from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

from picsellia_pipelines_cli.commands.training.templates.yolov8_template import (
    YOLOV8TrainingTemplate,
)
from picsellia_pipelines_cli.utils.env_utils import get_env_config
from picsellia_pipelines_cli.utils.initializer import handle_pipeline_name, init_client
from picsellia_pipelines_cli.utils.logging import bullet, hr, kv, section, step
from picsellia_pipelines_cli.utils.pipeline_config import PipelineConfig


def init_training(
    pipeline_name: str,
    template: str,
    output_dir: str | None = None,
    use_pyproject: bool | None = True,
):
    """Initialize and scaffold a training pipeline project.

    Steps performed:
        1. Validate environment and organization inputs.
        2. Create a new pipeline project directory from the chosen template.
        3. Prompt the user to reuse or create a new model version.
        4. Store model metadata (name, version, framework, inference type, IDs) in `config.toml`.
        5. Print next steps for editing, testing, and deploying the pipeline.

    Args:
        pipeline_name: Name of the new pipeline project.
        template: Template to scaffold (e.g., "ultralytics").
        output_dir: Directory where the pipeline will be created (default: current dir).
        use_pyproject: Whether to generate a `pyproject.toml` (default: True).

    Raises:
        typer.Exit: If required arguments are missing or invalid.
    """
    output_dir = output_dir or "."
    use_pyproject = True if use_pyproject is None else use_pyproject
    pipeline_name = handle_pipeline_name(pipeline_name=pipeline_name)

    # ── Environment ─────────────────────────────────────────────────────────
    section("🌍 Environment")
    env_config = get_env_config()
    kv("Host", env_config["host"])
    kv("Organization", env_config["organization_name"])

    client = init_client(env_config=env_config)

    # Template setup
    template_instance = get_template_instance(
        template_name=template,
        pipeline_name=pipeline_name,
        output_dir=output_dir,
        use_pyproject=use_pyproject,
    )

    section("Project setup")
    kv("Template", template)
    template_dir = template_instance.pipeline_dir
    bullet(f"Template scaffold generated at {template_dir}", accent=True)
    bullet("Key files:")
    typer.echo("  • steps.py")
    typer.echo("  • pipeline.toml")
    if use_pyproject:
        typer.echo("  • pyproject.toml")
    template_instance.write_all_files()
    template_instance.post_init_environment()
    bullet(f"Virtual environment: {template_dir}/.venv")
    bullet("Dependencies installed and locked")

    # Model setup
    section("Model")
    model_name, model_version_name, model_url, framework, inference_type = (
        choose_or_create_model_version(client=client)
    )
    kv("Name", model_name)
    kv("Version", model_version_name)
    kv("URL", model_url, color=typer.colors.BLUE)
    typer.echo("")
    bullet(
        "Upload a file named 'pretrained-weights' to this model version (required for training).",
        accent=True,
    )

    # Pipeline metadata
    config = PipelineConfig(pipeline_name=pipeline_name)
    register_pipeline_metadata(
        config=config,
        model_version_name=model_version_name,
        origin_name=model_name,
        framework=framework,
        inference_type=inference_type,
    )

    # Next steps
    section("Next steps")
    step(
        1,
        f"Open {typer.style(model_url, fg=typer.colors.BLUE)} and upload "
        + typer.style("'pretrained-weights'", bold=True)
        + " to this model version.",
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
    """Return a training template instance based on the template name.

    Args:
        template_name: Name of the template (e.g., "ultralytics").
        pipeline_name: Name of the pipeline.
        output_dir: Output directory for the pipeline project.
        use_pyproject: Whether to use `pyproject.toml` for dependency management.

    Returns:
        A template instance.

    Raises:
        typer.Exit: If the template name is not recognized.
    """
    match template_name:
        case "yolov8":
            return YOLOV8TrainingTemplate(
                pipeline_name=pipeline_name,
                output_dir=output_dir,
                use_pyproject=use_pyproject,
            )
        case _:
            typer.echo(
                typer.style(
                    f"Unknown template '{template_name}'",
                    fg=typer.colors.RED,
                    bold=True,
                )
            )
            raise typer.Exit(code=1)


def choose_or_create_model_version(
    client: Client,
) -> tuple[str, str, str, str, str]:
    """Prompt the user to select or create a model version.

    Returns:
        Tuple containing:
            - model_name: Name of the Picsellia model
            - model_version_name: Version name
            - model_url: Web URL for the model version
            - framework: Framework name (e.g., "ONNX", "PYTORCH")
            - inference_type: Inference type (e.g., "OBJECT_DETECTION")
    """
    if typer.confirm("Reuse an existing model version?", default=False):
        is_public = typer.confirm("Is it a public model?", default=False)
        if is_public:
            model_name = typer.prompt("Public model name")
            model_version_name = typer.prompt("Model version name")

            try:
                model = client.get_public_model(name=model_name)
                mv = model.get_version(version=model_version_name)
            except ResourceNotFoundError as e:
                typer.echo(
                    typer.style(
                        f"❌ Could not find public model '{model_name}' with version '{model_version_name}'.",
                        fg=typer.colors.RED,
                    )
                )
                raise typer.Exit(code=1) from e
        else:
            model_version_id = typer.prompt("Private model version ID")
            mv = client.get_model_version_by_id(id=model_version_id)

        return (
            mv.origin_name,
            mv.name,
            f"{client.connexion.host}/{client.connexion.organization_id}/model/{mv.origin_id}/version/{mv.id}",
            mv.framework.name,
            mv.type.name,
        )

    # Create a new model version
    model_name = typer.prompt("Model name")
    model_version_name = typer.prompt("Version name", default="v1")

    framework_options = [f.name for f in Framework if f != Framework.NOT_CONFIGURED]
    inference_options = [
        i.name for i in InferenceType if i != InferenceType.NOT_CONFIGURED
    ]

    framework_input = typer.prompt(
        f"Select framework ({', '.join(framework_options)})", default="ONNX"
    ).upper()
    if framework_input not in framework_options:
        typer.echo(
            f"❌ Invalid framework '{framework_input}'. Must be one of {framework_options}."
        )
        raise typer.Exit(code=1)

    inference_type_input = typer.prompt(
        f"Select inference type ({', '.join(inference_options)})",
        default="OBJECT_DETECTION",
    ).upper()
    if inference_type_input not in inference_options:
        typer.echo(
            f"❌ Invalid inference type '{inference_type_input}'. Must be one of {inference_options}."
        )
        raise typer.Exit(code=1)

    # Ensure model exists
    try:
        model = client.get_model(name=model_name)
    except ResourceNotFoundError:
        model = client.create_model(name=model_name)

    # Ensure version does not exist yet
    try:
        _ = model.get_version(model_version_name)
        typer.echo(
            typer.style(
                f"Model version '{model_version_name}' already exists in '{model_name}'.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)
    except ResourceNotFoundError:
        pass

    mv = model.create_version(
        name=model_version_name,
        framework=Framework[framework_input],
        type=InferenceType[inference_type_input],
        base_parameters={"epochs": 2, "batch_size": 8, "image_size": 640},
    )

    return (
        model.name,
        mv.name,
        f"{client.connexion.host}/{client.connexion.organization_id}/model/{model.id}/version/{mv.id}",
        framework_input,
        inference_type_input,
    )


def register_pipeline_metadata(
    config: PipelineConfig,
    model_version_name: str,
    origin_name: str,
    framework: str,
    inference_type: str,
):
    """Register model metadata in the pipeline configuration file.

    Saved under `[model_version]` in `config.toml`:

    ```toml
    [model_version]
    name = "v1"
    origin_name = "MyModel"
    framework = "ONNX"
    inference_type = "OBJECT_DETECTION"
    ```

    Args:
        config: Pipeline configuration object.
        model_version_name: Name of the model version.
        origin_name: Origin model name.
        framework: Framework string (validated against `Framework` enum).
        inference_type: Inference type string (validated against `InferenceType` enum).
    """
    try:
        _ = Framework[framework.upper()]
    except KeyError as e:
        typer.echo(
            f"❌ Invalid framework '{framework}'. Must be one of {[f.name for f in Framework]}."
        )
        raise typer.Exit(code=1) from e

    try:
        _ = InferenceType[inference_type.upper()]
    except KeyError as e:
        typer.echo(
            f"❌ Invalid inference type '{inference_type}'. Must be one of {[i.name for i in InferenceType]}."
        )
        raise typer.Exit(code=1) from e

    config.config.setdefault("model_version", {})
    config.config["model_version"].update(
        {
            "name": model_version_name,
            "origin_name": origin_name,
            "framework": framework.upper(),
            "inference_type": inference_type.upper(),
        }
    )
    config.save()

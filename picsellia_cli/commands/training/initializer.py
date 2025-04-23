import os
import typer

from picsellia_cli.utils.session_manager import session_manager
from picsellia_cli.commands.training.utils.template_loader import (
    get_training_picsellia_pipeline_template,
    get_training_local_pipeline_template,
    get_training_dockerfile_template,
    get_training_requirements_template,
    get_training_dockerignore_template,
    get_training_prepare_dataset_template,
    get_training_load_model_template,
    get_training_train_model_template,
    get_training_export_model_template,
    get_training_evaluate_model_template,
    get_training_hyperparameters_template,
    get_training_augmentation_parameters_template,
    get_training_export_parameters_template,
)

app = typer.Typer(help="Initialize and register a new training pipeline.")


@app.command(name="init")
def init_training_pipeline(pipeline_name: str):
    session_manager.ensure_session_initialized()

    os.makedirs(pipeline_name, exist_ok=True)
    utils_dir = os.path.join(pipeline_name, "utils")
    os.makedirs(utils_dir, exist_ok=True)

    # Main pipeline files
    with open(os.path.join(pipeline_name, "training_pipeline.py"), "w") as f:
        f.write(get_training_picsellia_pipeline_template(pipeline_name))

    with open(os.path.join(pipeline_name, "local_training_pipeline.py"), "w") as f:
        f.write(get_training_local_pipeline_template(pipeline_name))

    with open(os.path.join(pipeline_name, "Dockerfile"), "w") as f:
        f.write(get_training_dockerfile_template(pipeline_name))

    with open(os.path.join(pipeline_name, "requirements.txt"), "w") as f:
        f.write(get_training_requirements_template())

    with open(os.path.join(pipeline_name, ".dockerignore"), "w") as f:
        f.write(get_training_dockerignore_template())

    # Utils files
    with open(os.path.join(utils_dir, "prepare_dataset.py"), "w") as f:
        f.write(get_training_prepare_dataset_template())

    with open(os.path.join(utils_dir, "load_model.py"), "w") as f:
        f.write(get_training_load_model_template())

    with open(os.path.join(utils_dir, "train_model.py"), "w") as f:
        f.write(get_training_train_model_template())

    with open(os.path.join(utils_dir, "export_model.py"), "w") as f:
        f.write(get_training_export_model_template())

    with open(os.path.join(utils_dir, "evaluate_model.py"), "w") as f:
        f.write(get_training_evaluate_model_template())

    with open(os.path.join(utils_dir, "hyperparameters.py"), "w") as f:
        f.write(get_training_hyperparameters_template())

    with open(os.path.join(utils_dir, "augmentation_parameters.py"), "w") as f:
        f.write(get_training_augmentation_parameters_template())

    with open(os.path.join(utils_dir, "export_parameters.py"), "w") as f:
        f.write(get_training_export_parameters_template())

    # Register in session
    pipeline_data = {
        "pipeline_name": pipeline_name,
        "pipeline_type": "TRAINING",
        "picsellia_pipeline_script_path": f"{pipeline_name}/training_pipeline.py",
        "local_pipeline_script_path": f"{pipeline_name}/local_training_pipeline.py",
        "requirements_path": f"{pipeline_name}/requirements.txt",
        "image_name": None,
        "image_tag": None,
        "parameters": {
            "model_name": pipeline_name,
            "weights": "pretrained-weights",
        },
    }

    session_manager.add_pipeline(pipeline_name, pipeline_data)

    # CLI feedback
    typer.echo(f"✅ Training pipeline '{pipeline_name}' initialized and registered!")
    typer.echo(f"📁 Structure created at ./{pipeline_name}/")
    typer.echo("🧠 Modify your training steps in the `utils/` folder.")
    typer.echo("⚙️  Edit the context classes in `training_pipeline.py` if needed.")
    typer.echo("🧪 Run your pipeline locally using `pipeline-cli training test`.")
    typer.echo("🚀 When ready, deploy it using `pipeline-cli training deploy`.")

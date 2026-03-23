from picsellia_pipelines_cli.utils.base_template import BaseTemplate

TRAINING_PIPELINE_TRAINING = """import argparse

from picsellia_cv_engine import pipeline
from picsellia_cv_engine.core.parameters import (
    AugmentationParameters,
    ExportParameters,
)
from picsellia_cv_engine.core.services.context.unified_context import create_training_context_from_config

from steps import list_training_datasets
from utils.parameters import TrainingHyperParameters

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["local", "picsellia"], default="picsellia")
parser.add_argument("--config-file", type=str, required=False)
args = parser.parse_args()

context = create_training_context_from_config(
    hyperparameters_cls=TrainingHyperParameters,
    augmentation_parameters_cls=AugmentationParameters,
    export_parameters_cls=ExportParameters,
    mode=args.mode,
    config_file_path=args.config_file,
)

@pipeline(context=context, log_folder_path="logs/", remove_logs_on_completion=False)
def {pipeline_name}_pipeline():
    # Define custom functions in steps.py to easily organize your code
    datasets = list_training_datasets()
    # Easily access your parameters from the context
    print(context.hyperparameters.epochs)
    
    # Your code goes here ....
    
    
if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

TRAINING_STEPS = """import os

from picsellia_cv_engine import step, Pipeline


@step()
def list_training_datasets() -> list[DatasetVersion] :
    context = Pipeline.get_active_context()
    experiment = context.experiment
    datasets = experiments.list_attached_dataset_versions()
    return datasets
"""

TRAINING_PIPELINE_PARAMETERS = """from picsellia.types.schemas import LogDataType
from picsellia_cv_engine.core.parameters import HyperParameters


class TrainingHyperParameters(HyperParameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)
        self.epochs = self.extract_parameter(["epochs"], expected_type=int, default=3)
        self.batch_size = self.extract_parameter(["batch_size"], expected_type=int, default=8)
        self.image_size = self.extract_parameter(["image_size"], expected_type=int, default=640)
"""

TRAINING_PIPELINE_REQUIREMENTS = """# Add your dependencies here

"""

TRAINING_PIPELINE_PYPROJECT = """[project]
name = "{pipeline_name}"
version = "0.1.0"
description = "Your training pipeline"
requires-python = ">=3.10"

dependencies = [
    "picsellia-pipelines-cli",
    "picsellia-cv-engine",
]
"""

TRAINING_PIPELINE_DOCKERFILE = """FROM picsellia/cuda:11.8.0-cudnn8-ubuntu20.04-python3.10

RUN apt-get update && apt-get install -y \\
    libgl1-mesa-glx \\
    git \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /experiment

RUN git clone --depth 1 https://github.com/picselliahq/picsellia-cv-base-docker.git /tmp/base-docker && \
    cp -r /tmp/base-docker/base/. /experiment
RUN sed -i '1 a source /experiment/{pipeline_dir}/.venv/bin/activate' /experiment/run.sh

COPY ./uv.lock {pipeline_dir}/uv.lock
COPY ./pyproject.toml {pipeline_dir}/pyproject.toml

# Sync from uv.lock (assumes uv lock has already been created)
RUN uv sync --python=$(which python3.10) --project {pipeline_dir}

COPY ./ {pipeline_dir}

ENV PYTHONPATH=":/experiment"

ENTRYPOINT ["run", "python3.10", "{pipeline_dir}/pipeline.py"]
"""

TRAINING_PIPELINE_DOCKERIGNORE = """.venv/
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.log
runs/
"""

TRAINING_RUN_CONFIG = """override_outputs = true

[job]
type = "TRAINING"

[input.train_dataset_version]
id = ""

[input.model_version]
id = ""

[output.experiment]
name = "{pipeline_name}_exp1"
project_name = "{pipeline_name}"

[hyperparameters]
epochs = 3
batch_size = 8
image_size = 640
"""


class SimpleTrainingTemplate(BaseTemplate):
    def __init__(self, pipeline_name: str, output_dir: str, use_pyproject: bool = True):
        super().__init__(
            pipeline_name=pipeline_name,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
        self.pipeline_type = "TRAINING"

    def get_main_files(self) -> dict[str, str]:
        files = {
            "pipeline.py": TRAINING_PIPELINE_TRAINING.format(
                pipeline_module=self.pipeline_module,
                pipeline_name=self.pipeline_name,
            ),
            "steps.py": TRAINING_STEPS.format(pipeline_module=self.pipeline_module),
            "Dockerfile": self._get_dockerfile(),
            ".dockerignore": TRAINING_PIPELINE_DOCKERIGNORE,
        }

        if self.use_pyproject:
            files["pyproject.toml"] = TRAINING_PIPELINE_PYPROJECT.format(
                pipeline_name=self.pipeline_name
            )
        else:
            files["requirements.txt"] = TRAINING_PIPELINE_REQUIREMENTS

        return files

    def get_utils_files(self) -> dict[str, str]:
        return {
            "parameters.py": TRAINING_PIPELINE_PARAMETERS,
        }

    def get_config_toml(self) -> dict:
        return {
            "metadata": {
                "name": self.pipeline_name,
                "version": "1.0",
                "description": "Training pipeline using YOLOV8.",
                "type": self.pipeline_type,
            },
            "execution": {
                "pipeline_script": "pipeline.py",
                "requirements_file": "pyproject.toml"
                if self.use_pyproject
                else "requirements.txt",
                "parameters_class": "utils/parameters.py:TrainingHyperParameters",
            },
            "docker": {
                "image_name": "",
                "image_tag": "",
            },
            "model_version": {
                "name": "",
                "origin_name": "",
                "framework": "",
                "inference_type": "",
            },
        }

    def _get_dockerfile(self) -> str:
        if self.use_pyproject:
            return TRAINING_PIPELINE_DOCKERFILE.format(pipeline_dir=self.pipeline_dir)
        else:
            return TRAINING_PIPELINE_DOCKERFILE.replace(
                "uv sync --python=$(which python3.10) --project {pipeline_dir}",
                "uv pip install --python=$(which python3.10) -r ./{pipeline_dir}/requirements.txt",
            ).format(pipeline_dir=self.pipeline_dir)

    def get_run_config_toml(self) -> str:
        return TRAINING_RUN_CONFIG.format(pipeline_name=self.pipeline_name)

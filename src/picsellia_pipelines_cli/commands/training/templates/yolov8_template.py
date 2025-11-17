from picsellia_pipelines_cli.utils.base_template import BaseTemplate

TRAINING_PIPELINE_TRAINING = """import argparse

from picsellia_cv_engine import pipeline
from picsellia_cv_engine.core.parameters import (
    AugmentationParameters,
    ExportParameters,
)
from picsellia_cv_engine.core.services.context.unified_context import create_training_context_from_config
from picsellia_cv_engine.steps.base.dataset.loader import (
    load_yolo_datasets
)
from picsellia_cv_engine.steps.base.model.builder import build_model

from steps import train
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
    picsellia_datasets = load_yolo_datasets()
    picsellia_model = build_model(pretrained_weights_name="pretrained-weights")
    train(picsellia_model=picsellia_model, picsellia_datasets=picsellia_datasets)


if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

TRAINING_STEPS = """import os

from picsellia_cv_engine import step, Pipeline
from picsellia_cv_engine.core import Model, DatasetCollection, YoloDataset
from ultralytics import YOLO

from utils.data import generate_data_yaml


@step()
def train(picsellia_model: Model, picsellia_datasets: DatasetCollection[YoloDataset]):
    context = Pipeline.get_active_context()

    data_yaml_path = generate_data_yaml(picsellia_datasets=picsellia_datasets)

    if picsellia_model.pretrained_weights_path:
        ultralytics_model = YOLO(picsellia_model.pretrained_weights_path)
    else:
        raise Exception("No 'pretrained-weights' file found in model version")

    ultralytics_model.train(
        data=data_yaml_path,
        epochs=context.hyperparameters.epochs,
        imgsz=context.hyperparameters.image_size,
        batch=context.hyperparameters.batch_size,
        project=picsellia_model.results_dir,
        name=picsellia_model.name,
        )

    picsellia_model.save_artifact_to_experiment(
        experiment=context.experiment,
        artifact_name="best-model",
        artifact_path=os.path.join(
            picsellia_model.results_dir,
            picsellia_model.name,
            "weights",
            "best.pt",
        ),
    )
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

TRAINING_PIPELINE_DATA = """import os

import yaml
from picsellia_cv_engine.core.data.dataset.dataset_collection import DatasetCollection
from picsellia_cv_engine.core.data.dataset.yolo_dataset import YoloDataset


def generate_data_yaml(
    picsellia_datasets: DatasetCollection[YoloDataset],
) -> str:
    data_yaml = {
        "train": os.path.join(picsellia_datasets.dataset_path, "images", "train"),
        "val": os.path.join(picsellia_datasets.dataset_path, "images", "val"),
        "test": os.path.join(picsellia_datasets.dataset_path, "images", "test"),
        "nc": len(picsellia_datasets["train"].labelmap.keys()),
        "names": list(picsellia_datasets["train"].labelmap.keys()),
    }

    with open(os.path.join(picsellia_datasets.dataset_path, "data.yaml"), "w") as f:
        yaml.dump(data_yaml, f, default_flow_style=False)

    return os.path.join(picsellia_datasets.dataset_path, "data.yaml")
"""

TRAINING_PIPELINE_REQUIREMENTS = """# Add your dependencies here
ultralytics
"""

TRAINING_PIPELINE_PYPROJECT = """[project]
name = "{pipeline_name}"
version = "0.1.0"
description = "YoloV8 training pipeline"
requires-python = ">=3.10"

dependencies = [
    "picsellia-pipelines-cli",
    "picsellia-cv-engine",
    "ultralytics>=8.3.145",
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

ARG REBUILD_ALL
COPY ./ {pipeline_dir}
ARG REBUILD_PICSELLIA

# Sync from uv.lock (assumes uv lock has already been created)
RUN uv sync --python=$(which python3.10) --project {pipeline_dir}

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


class YOLOV8TrainingTemplate(BaseTemplate):
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
            "data.py": TRAINING_PIPELINE_DATA,
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

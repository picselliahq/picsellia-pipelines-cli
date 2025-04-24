from picsellia_cli.utils.base_template import BaseTemplate

SIMPLE_PIPELINE_TRAINING = """from picsellia_cv_engine import pipeline
from picsellia_cv_engine.services.base.utils.picsellia_context import create_picsellia_training_context
from picsellia_cv_engine.core.parameters import (
    AugmentationParameters,
    ExportParameters,
)
from picsellia_cv_engine.steps.base.dataset.loader import (
    load_yolo_datasets
)

from {pipeline_module}.utils.parameters import SimpleHyperParameters
from {pipeline_module}.utils.pipeline_steps import run_training_step

context = create_picsellia_training_context(
    hyperparameters_cls=SimpleHyperParameters,
    augmentation_parameters_cls=AugmentationParameters,
    export_parameters_cls=ExportParameters
)

@pipeline(context=context, log_folder_path="logs/", remove_logs_on_completion=False)
def {pipeline_name}_pipeline():
    dataset_collection = load_yolo_datasets()
    run_training_step(dataset_collection=dataset_collection)


if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

SIMPLE_PIPELINE_LOCAL = """import argparse
from picsellia_cv_engine import pipeline
from picsellia_cv_engine.services.base.utils.local_context import create_local_training_context
from picsellia_cv_engine.core.parameters import (
    AugmentationParameters,
    ExportParameters,
)
from picsellia_cv_engine.steps.base.dataset.loader import (
    load_yolo_datasets
)

from {pipeline_module}.utils.parameters import SimpleHyperParameters
from {pipeline_module}.utils.pipeline_steps import run_training_step

parser = argparse.ArgumentParser()
parser.add_argument("--api_token", type=str, required=True)
parser.add_argument("--organization_id", type=str, required=True)
parser.add_argument("--experiment_id", type=str, required=True)
args = parser.parse_args()

context = create_local_training_context(
    hyperparameters_cls=SimpleHyperParameters,
    augmentation_parameters_cls=AugmentationParameters,
    export_parameters_cls=ExportParameters,
    api_token=args.api_token,
    organization_id=args.organization_id,
    experiment_id=args.experiment_id,
)

@pipeline(context=context, log_folder_path="logs/", remove_logs_on_completion=False)
def {pipeline_name}_pipeline():
    dataset_collection = load_yolo_datasets()
    run_training_step(dataset_collection=dataset_collection)


if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

SIMPLE_PIPELINE_PARAMETERS = """from typing import Optional
from picsellia.types.schemas import LogDataType
from picsellia_cv_engine.core.parameters import HyperParameters


class SimpleHyperParameters(HyperParameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)
        self.epochs = self.extract_parameter(["epochs"], expected_type=int, default=3)
        self.batch_size = self.extract_parameter(["batch_size"], expected_type=int, default=8)
        self.image_size = self.extract_parameter(["image_size"], expected_type=int, default=640)
"""

SIMPLE_PIPELINE_STEP = """from ultralytics import YOLO
from picsellia_cv_engine import Pipeline
from picsellia_cv_engine.decorators import step

from picsellia_cv_engine.core.data.dataset.dataset_collection import DatasetCollection
from picsellia_cv_engine.core.data.dataset.yolo_dataset import YoloDataset

import os
import yaml


@step()
def run_training_step(dataset_collection: DatasetCollection[YoloDataset]):
    context = Pipeline.get_active_context()
    
    data_yaml_path = generate_data_yaml(dataset_collection=dataset_collection)

    pretrained_weights_path = download_pretrained_weights(
        experiment=context.experiment,
        pretrained_weights_artifact_name="pretrained-weights",
        target_path=os.path.join(context.experiment.name, "pretrained-weights"),
    )
    model = YOLO(pretrained_weights_path)

    model.train(
        data=data_yaml_path,
        epochs=context.hyperparameters.epochs,
        imgsz=context.hyperparameters.image_size,
        batch=context.hyperparameters.batch_size,
    )

    context.experiment.store(name="trained-model", path=model.ckpt_path)


def generate_data_yaml(
    dataset_collection: DatasetCollection[YoloDataset],
) -> DatasetCollection[YoloDataset]:
    data_yaml = {
        "train": os.path.join(dataset_collection.dataset_path, "images", "train"),
        "val": os.path.join(dataset_collection.dataset_path, "images", "val"),
        "test": os.path.join(dataset_collection.dataset_path, "images", "test"),
        "nc": len(dataset_collection["train"].labelmap.keys()),
        "names": list(dataset_collection["train"].labelmap.keys()),
    }

    with open(os.path.join(dataset_collection.dataset_path, "data.yaml"), "w") as f:
        yaml.dump(data_yaml, f, default_flow_style=False)

    return os.path.join(dataset_collection.dataset_path, "data.yaml")


def download_pretrained_weights(
    experiment: Experiment,
    pretrained_weights_artifact_name: str,
    target_path: str,
) -> str:
    pretrained_weights_artifact = experiment.get_artifact(name=pretrained_weights_artifact_name)
    if pretrained_weights_artifact:
        pretrained_weights_artifact.download(target_path=target_path)
        return os.path.join(target_path, pretrained_weights_artifact.filename)
    return None
"""

SIMPLE_PIPELINE_REQUIREMENTS = """picsellia>=6.10.0, <7.0.0
ultralytics
"""

SIMPLE_PIPELINE_DOCKERFILE = """FROM picsellia/cuda:11.8.0-cudnn8-ubuntu20.04-python3.10

RUN apt-get update && apt-get install -y \\
    libgl1-mesa-glx \\
    git \\
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --python=$(which python3.10) git+https://github.com/picselliahq/picsellia-cv-engine.git@main

WORKDIR /experiment

ARG REBUILD_ALL
COPY ./{pipeline_dir} ./{pipeline_dir}
ARG REBUILD_PICSELLIA

RUN uv pip install --python=$(which python3.10) --no-cache -r ./{pipeline_dir}/requirements.txt
RUN uv pip install --python=$(which python3.10) --no-cache torch==2.2.1+cu118 torchaudio==2.2.1+cu118 torchvision==0.17.1+cu118 --find-links https://download.pytorch.org/whl/torch_stable.html

ENV PYTHONPATH=":/experiment"

ENTRYPOINT ["run", "python3.10", "{pipeline_dir}/training_pipeline.py"]
"""

SIMPLE_PIPELINE_DOCKERIGNORE = """.venv/
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.log
"""


class SimpleTrainingTemplate(BaseTemplate):
    def get_main_files(self) -> dict[str, str]:
        return {
            "training_pipeline.py": SIMPLE_PIPELINE_TRAINING.format(pipeline_module=self.pipeline_dir.replace("/", "."), pipeline_name=self.pipeline_name),
            "local_training_pipeline.py": SIMPLE_PIPELINE_LOCAL.format(pipeline_module=self.pipeline_dir.replace("/", "."), pipeline_name=self.pipeline_name),
            "requirements.txt": SIMPLE_PIPELINE_REQUIREMENTS,
            "Dockerfile": SIMPLE_PIPELINE_DOCKERFILE.format(pipeline_dir=self.pipeline_dir),
            ".dockerignore": SIMPLE_PIPELINE_DOCKERIGNORE
        }

    def get_utils_files(self) -> dict[str, str]:
        return {
            "parameters.py": SIMPLE_PIPELINE_PARAMETERS,
            "pipeline_steps.py": SIMPLE_PIPELINE_STEP,
        }

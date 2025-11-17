from picsellia_pipelines_cli.utils.base_template import BaseTemplate

PREANNOTATION_PIPELINE_PICSELLIA = """import argparse

from picsellia.types.enums import ProcessingType
from picsellia_cv_engine.core.services.context.unified_context import create_processing_context_from_config
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.steps.base.dataset.loader import load_coco_datasets
from picsellia_cv_engine.steps.base.dataset.uploader import upload_dataset_annotations
from picsellia_cv_engine.steps.base.model.builder import build_model

from steps import process
from utils.parameters import ProcessingParameters

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["local", "picsellia"], default="picsellia")
parser.add_argument("--config-file", type=str, required=False)
args = parser.parse_args()

context = create_processing_context_from_config(
    processing_type=ProcessingType.PRE_ANNOTATION,
    processing_parameters_cls=ProcessingParameters,
    mode=args.mode,
    config_file_path=args.config_file,
)

@pipeline(
    context=context,
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def {pipeline_name}_pipeline():
    picsellia_dataset = load_coco_datasets()
    picsellia_model = build_model(
        pretrained_weights_name="pretrained-weights", config_name="config"
    )
    picsellia_dataset = process(
        picsellia_model=picsellia_model, picsellia_dataset=picsellia_dataset
    )
    upload_dataset_annotations(dataset=picsellia_dataset, use_id=True)

if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

PREANNOTATION_PIPELINE_STEPS = """import json

from picsellia.types.enums import InferenceType
from picsellia_cv_engine.core import CocoDataset, Model
from picsellia_cv_engine.core.contexts import PicselliaDatasetProcessingContext
from picsellia_cv_engine.decorators.pipeline_decorator import Pipeline
from picsellia_cv_engine.decorators.step_decorator import step

from utils.processing import process_images


@step
def process(picsellia_model: Model, picsellia_dataset: CocoDataset):
    \"\"\"
    🚀 This function processes the dataset using `process_images()`.

    🔹 **What You Need to Do:**
    - Modify `process_images()` to apply custom transformations or augmentations.
    - Ensure it returns the correct processed images & COCO metadata.

    Args:
        picsellia_model (Model): The model used for processing the dataset.
        picsellia_dataset (CocoDataset): The input dataset to be processed.

    Returns:
        CocoDataset: The processed dataset, ready for local execution and Picsellia.
    \"\"\"

    # Get processing parameters from the user-defined configuration
    context: PicselliaDatasetProcessingContext = Pipeline.get_active_context()
    parameters = context.processing_parameters.to_dict()

    if picsellia_dataset.dataset_version.type == InferenceType.NOT_CONFIGURED:
        picsellia_dataset.dataset_version.set_type(picsellia_model.model_version.type)
        picsellia_dataset.download_annotations(destination_dir=picsellia_dataset.annotations_dir, use_id=True)

    if picsellia_dataset.dataset_version.type != picsellia_model.model_version.type:
        raise ValueError(
            f"❌ Dataset type '{picsellia_dataset.dataset_version.type}' "
            f"does not match model type '{picsellia_model.model_version.type}'"
        )

    # Call the helper function to process images
    output_coco = process_images(
        picsellia_model=picsellia_model,
        picsellia_dataset=picsellia_dataset,
        parameters=parameters,
    )

    # Assign processed data to output dataset
    picsellia_dataset.coco_data = output_coco

    with open(picsellia_dataset.coco_file_path, "w") as f:
        json.dump(picsellia_dataset.coco_data, f)

    print("✅ Dataset processing complete!")
    return picsellia_dataset
"""

PREANNOTATION_PIPELINE_PROCESSING = """import os
from typing import Any

import cv2
from picsellia_cv_engine.core import Model as PicselliaModel
from picsellia_cv_engine.core.data.dataset.coco_dataset import CocoDataset
from ultralytics import YOLO


def process_images(
    picsellia_model: PicselliaModel,
    picsellia_dataset: CocoDataset,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    \"\"\"
    Annotate a dataset using a YOLOv8 Ultralytics detection model.

    Args:
        picsellia_model (PicselliaModel): Contains the model paths (weights).
        picsellia_dataset (CocoDataset): Dataset object containing image dir, labelmap, coco metadata.
        parameters (dict[str, Any]): Parameters including 'threshold' and others.

    Returns:
        dict[str, Any]: COCO annotations with added bounding boxes.
    \"\"\"
    images_dir = picsellia_dataset.images_dir
    coco = picsellia_dataset.coco_data or {}
    labelmap = picsellia_dataset.labelmap or {}
    threshold = parameters.get("threshold", 0.1)

    # Build name -> Label
    label_by_name = {label.name: label for label in labelmap.values()}

    # Build name -> category_id for COCO (starting from 1)
    coco["categories"] = coco.get("categories", [])
    category_name_to_id = {
        cat["name"]: cat["id"] for cat in coco["categories"]
    }
    next_category_id = max(category_name_to_id.values(), default=0) + 1

    model = YOLO(picsellia_model.pretrained_weights_path)
    coco["annotations"] = []  # Reset annotations

    for image_info in coco["images"]:
        image_filename = image_info["file_name"]
        image_id = image_info["id"]

        input_path = os.path.join(images_dir, image_filename)
        image_bgr = cv2.imread(input_path)
        if image_bgr is None:
            print(f"⚠️ Unable to read {input_path}. Skipping.")
            continue

        results = model.predict(image_bgr, verbose=False)[0]

        for i, box in enumerate(results.boxes.xyxy.cpu().numpy()):
            score = float(results.boxes.conf[i].cpu().item())
            if score < threshold:
                continue

            class_index = int(results.boxes.cls[i].cpu().item())
            class_name = results.names[class_index]

            # Ensure Label exists in Picsellia
            if class_name not in label_by_name:
                print(f"➕ Creating missing label '{class_name}' in dataset version...")
                new_label = picsellia_dataset.dataset_version.create_label(name=class_name)
                label_by_name[class_name] = new_label
                labelmap[class_name] = new_label

            # Ensure category_id exists for COCO
            if class_name not in category_name_to_id:
                category_name_to_id[class_name] = next_category_id
                coco["categories"].append({
                    "id": next_category_id,
                    "name": class_name,
                    "supercategory": "",  # optional
                })
                next_category_id += 1

            category_id = category_name_to_id[class_name]

            x_min, y_min, x_max, y_max = box
            coco["annotations"].append(
                {
                    "id": len(coco["annotations"]),
                    "image_id": image_id,
                    "category_id": category_id,
                    "bbox": [
                        max(int(x_min), 0),
                        max(int(y_min), 0),
                        int(x_max - x_min),
                        int(y_max - y_min),
                    ],
                    "area": float((x_max - x_min) * (y_max - y_min)),
                    "iscrowd": 0,
                }
            )

    print(f"✅ Annotated {len(coco['images'])} images using YOLOv8.")
    return coco
"""

PREANNOTATION_PIPELINE_PARAMETERS = """from picsellia.types.schemas import LogDataType
from picsellia_cv_engine.core.parameters import Parameters


class ProcessingParameters(Parameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)
        self.threshold = self.extract_parameter(["threshold"], expected_type=float, default=0.1)
"""

PREANNOTATION_PIPELINE_REQUIREMENTS = """# Add your dependencies here
picsellia-pipelines-cli
picsellia-cv-engine[ultralytics]>=0.4.1
opencv-python
"""

PREANNOTATION_PIPELINE_PYPROJECT = """[project]
name = "{pipeline_name}"
version = "0.1.0"
description = "Picsellia processing pipeline"
requires-python = ">=3.10,<3.12"

dependencies = [
    "picsellia-pipelines-cli",
    "picsellia-cv-engine[ultralytics]>=0.4.1",
    "ultralytics",
    "opencv-python"
]
"""

PREANNOTATION_PIPELINE_DOCKERFILE = """FROM picsellia/cpu:python3.10

RUN apt-get update && apt-get install -y \\
    libgl1-mesa-glx \\
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

ENV PYTHONPATH="/experiment"

ENTRYPOINT ["run", "python3.10", "{pipeline_dir}/pipeline.py"]
"""

PREANNOTATION_PIPELINE_DOCKERIGNORE = """# Exclude virtual environments
.venv/
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.log
runs/
"""

PROCESSING_RUN_CONFIG = """
[job]
type = "PRE_ANNOTATION"

[input.dataset_version]
id = ""

[input.model_version]
id = ""

[parameters]
threshold = 0.1
"""


class PreAnnotationTemplate(BaseTemplate):
    def __init__(self, pipeline_name: str, output_dir: str, use_pyproject: bool = True):
        super().__init__(
            pipeline_name=pipeline_name,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
        self.pipeline_type = "PRE_ANNOTATION"

    def get_main_files(self) -> dict[str, str]:
        files = {
            "pipeline.py": PREANNOTATION_PIPELINE_PICSELLIA.format(
                pipeline_name=self.pipeline_name,
            ),
            "steps.py": PREANNOTATION_PIPELINE_STEPS,
            ".dockerignore": PREANNOTATION_PIPELINE_DOCKERIGNORE,
            "Dockerfile": self._get_dockerfile(),
        }

        if self.use_pyproject:
            files["pyproject.toml"] = PREANNOTATION_PIPELINE_PYPROJECT.format(
                pipeline_name=self.pipeline_name
            )
        else:
            files["requirements.txt"] = PREANNOTATION_PIPELINE_REQUIREMENTS

        return files

    def get_utils_files(self) -> dict[str, str]:
        return {
            "processing.py": PREANNOTATION_PIPELINE_PROCESSING,
            "parameters.py": PREANNOTATION_PIPELINE_PARAMETERS,
        }

    def get_config_toml(self) -> dict:
        return {
            "metadata": {
                "name": self.pipeline_name,
                "version": "1.0",
                "description": "This pipeline processes data for X.",
                "type": self.pipeline_type,
            },
            "execution": {
                "pipeline_script": "pipeline.py",
                "requirements_file": "pyproject.toml"
                if self.use_pyproject
                else "requirements.txt",
                "parameters_class": "utils/parameters.py:ProcessingParameters",
            },
            "docker": {"image_name": "", "image_tag": ""},
        }

    def _get_dockerfile(self) -> str:
        if self.use_pyproject:
            return PREANNOTATION_PIPELINE_DOCKERFILE.format(
                pipeline_dir=self.pipeline_dir
            )
        else:
            return PREANNOTATION_PIPELINE_DOCKERFILE.replace(
                "uv sync --python=$(which python3.10) --project {pipeline_dir}",
                "uv pip install --python=$(which python3.10) -r ./{pipeline_dir}/requirements.txt",
            ).format(pipeline_dir=self.pipeline_dir)

    def get_run_config_toml(self) -> str:
        return PROCESSING_RUN_CONFIG.format(pipeline_name=self.pipeline_name)

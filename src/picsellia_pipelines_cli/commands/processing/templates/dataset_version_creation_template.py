from picsellia_pipelines_cli.utils.base_template import BaseTemplate

PROCESSING_PIPELINE = """import argparse

from picsellia.types.enums import ProcessingType
from picsellia_cv_engine.core.services.context.unified_context import create_processing_context_from_config
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.steps.base.dataset.loader import load_coco_datasets
from picsellia_cv_engine.steps.base.dataset.uploader import upload_full_dataset

from steps import process
from utils.parameters import ProcessingParameters


parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["local", "picsellia"], default="picsellia")
parser.add_argument("--config-file", type=str, required=False)
args = parser.parse_args()

context = create_processing_context_from_config(
    processing_type=ProcessingType.DATASET_VERSION_CREATION,
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
    dataset_collection = load_coco_datasets()
    dataset_collection["output"] = process(
        dataset_collection["input"], dataset_collection["output"]
    )
    upload_full_dataset(dataset_collection["output"], use_id=False)
    return dataset_collection

if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

PROCESSING_PIPELINE_STEPS = """from copy import deepcopy

from picsellia_cv_engine.core import CocoDataset
from picsellia_cv_engine.core.contexts import PicselliaDatasetProcessingContext
from picsellia_cv_engine.decorators.pipeline_decorator import Pipeline
from picsellia_cv_engine.decorators.step_decorator import step

from utils.processing import process_images


@step
def process(
    input_dataset: CocoDataset, output_dataset: CocoDataset
):
    \"\"\"
    🚀 This function processes the dataset using `process_images()`.

    🔹 **What You Need to Do:**
    - Modify `process_images()` to apply custom transformations or augmentations.
    - Ensure it returns the correct processed images & COCO metadata.

    Args:
        input_dataset (CocoDataset): Input dataset from Picsellia.
        output_dataset (CocoDataset): Output dataset for saving processed data.

    Returns:
        CocoDataset: The processed dataset, ready for local execution and Picsellia.
    \"\"\"

    # Get processing parameters from the user-defined configuration
    context: PicselliaDatasetProcessingContext = Pipeline.get_active_context()
    parameters = context.processing_parameters.to_dict()

    # Initialize an empty COCO dataset
    output_coco = deepcopy(input_dataset.coco_data)
    output_coco["images"] = []  # Reset image metadata
    output_coco["annotations"] = []  # Reset annotation metadata

    # Call the helper function to process images
    output_coco = process_images(
        input_images_dir=input_dataset.images_dir,
        input_coco=input_dataset.coco_data,
        parameters=parameters,
        output_images_dir=output_dataset.images_dir,
        output_coco=output_coco,
    )
    # Assign processed data to output dataset
    output_dataset.coco_data = output_coco

    print(f"✅ Dataset processing complete!")
    return output_dataset
"""

PROCESSING_PIPELINE_PROCESSING = """import os
from copy import deepcopy
from glob import glob
from typing import Any

from PIL import Image


def process_images(
    input_images_dir: str,
    input_coco: dict[str, Any],
    parameters: dict[str, Any],
    output_images_dir: str,
    output_coco: dict[str, Any],
) -> dict[str, Any]:
    \"\"\"
    🚀 Modify this function to define how your dataset should be processed.

    🔹 **Your Goal:**
    - Apply transformations, augmentations, or processing to images.
    - Modify existing annotations or generate new ones.
    - Ensure processed images go inside `output_images_dir`.
    - Ensure processed annotations are stored in `output_coco`.

    🔹 **Inputs:**
    - `input_images_dir`: Path to directory with input images.
    - `input_coco`: COCO annotations for input dataset.
    - `parameters`: User-defined processing parameters.
    - `output_images_dir`: Path to directory where processed images should be stored.
    - `output_coco`: Empty COCO dictionary where you should store processed metadata.

    🔹 **Returns:**
    - `output_coco`: Updated COCO dictionary with new image & annotation metadata.
    \"\"\"

    os.makedirs(output_images_dir, exist_ok=True)  # Ensure output dir exists

    # Get all input images
    image_paths = glob(os.path.join(input_images_dir, "*"))

    for image_path in image_paths:
        image_filename = os.path.basename(image_path)

        # Open the image
        img = Image.open(image_path).convert("RGB")

        # ✨ Modify the image here (e.g., apply augmentations)
        processed_img = img  # Default behavior: Copy image unchanged

        # Save the processed image
        processed_img.save(os.path.join(output_images_dir, image_filename))

        # Register the processed image in COCO metadata
        new_image_id = len(output_coco["images"])
        output_coco["images"].append(
            {
                "id": new_image_id,
                "file_name": image_filename,
                "width": processed_img.width,
                "height": processed_img.height,
            }
        )

        # Copy & Modify Annotations (or create new ones)
        input_image_id = get_image_id_by_filename(input_coco, image_filename)
        annotations = [
            annotation
            for annotation in input_coco["annotations"]
            if annotation["image_id"] == input_image_id
        ]

        for annotation in annotations:
            new_annotation = deepcopy(annotation)
            new_annotation["image_id"] = new_image_id
            new_annotation["id"] = len(output_coco["annotations"])
            output_coco["annotations"].append(new_annotation)

    print(f"✅ Processed {len(image_paths)} images.")
    return output_coco

def get_image_id_by_filename(coco_data: dict[str, Any], filename: str) -> int:
    \"\"\"
    Retrieve the image ID for a given filename.

    Args:
        coco_data (dict): COCO dataset structure containing images.
        filename (str): Filename of the image.

    Returns:
        int: ID of the image.
    \"\"\"
    for image in coco_data["images"]:
        if image["file_name"] == filename:
            return image["id"]
    raise ValueError(f"⚠️ Image with filename '{filename}' not found.")

"""

PROCESSING_PIPELINE_PARAMETERS = """from picsellia.types.schemas import LogDataType
from picsellia_cv_engine.core.parameters import Parameters


class ProcessingParameters(Parameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)
        self.datalake = self.extract_parameter(["datalake"], expected_type=str, default="default")
        self.data_tag = self.extract_parameter(["data_tag"], expected_type=str, default="processed")
"""

PROCESSING_PIPELINE_REQUIREMENTS = """# Add your dependencies here
picsellia-pipelines-cli
picsellia-cv-engine>=0.4.1
"""

PROCESSING_PIPELINE_PYPROJECT = """[project]
name = "{pipeline_name}"
version = "0.1.0"
description = "Picsellia processing pipeline"
requires-python = ">=3.10"

dependencies = [
    "picsellia-pipelines-cli",
    "picsellia-cv-engine>=0.4.1",
]
"""


PROCESSING_PIPELINE_DOCKERFILE = """FROM picsellia/cpu:python3.10

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


PROCESSING_PIPELINE_DOCKERIGNORE = """# Exclude virtual environments
.venv/
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.log
runs/
"""

PROCESSING_RUN_CONFIG = """override_outputs = true

[job]
type = "DATASET_VERSION_CREATION"

[input.dataset_version]
id = ""

[output.dataset_version]
name = "test_{pipeline_name}"

[parameters]
datalake = "default"
data_tag = "processed"
"""


class DatasetVersionCreationProcessingTemplate(BaseTemplate):
    def __init__(self, pipeline_name: str, output_dir: str, use_pyproject: bool = True):
        super().__init__(
            pipeline_name=pipeline_name,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
        self.pipeline_type = "DATASET_VERSION_CREATION"

    def get_main_files(self) -> dict[str, str]:
        files = {
            "pipeline.py": PROCESSING_PIPELINE.format(
                pipeline_name=self.pipeline_name,
            ),
            "steps.py": PROCESSING_PIPELINE_STEPS,
            ".dockerignore": PROCESSING_PIPELINE_DOCKERIGNORE,
            "Dockerfile": self._get_dockerfile(),
        }

        if self.use_pyproject:
            files["pyproject.toml"] = PROCESSING_PIPELINE_PYPROJECT.format(
                pipeline_name=self.pipeline_name
            )
        else:
            files["requirements.txt"] = PROCESSING_PIPELINE_REQUIREMENTS

        return files

    def get_utils_files(self) -> dict[str, str]:
        return {
            "processing.py": PROCESSING_PIPELINE_PROCESSING,
            "parameters.py": PROCESSING_PIPELINE_PARAMETERS,
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
            return PROCESSING_PIPELINE_DOCKERFILE.format(pipeline_dir=self.pipeline_dir)
        else:
            return PROCESSING_PIPELINE_DOCKERFILE.replace(
                "uv sync --python=$(which python3.10) --project {pipeline_dir}",
                "uv pip install --python=$(which python3.10) -r ./{pipeline_dir}/requirements.txt",
            ).format(pipeline_dir=self.pipeline_dir)

    def get_run_config_toml(self) -> str:
        return PROCESSING_RUN_CONFIG.format(pipeline_name=self.pipeline_name)

from picsellia_cli.utils.base_template import BaseTemplate

PROCESSING_PIPELINE_PICSELLIA = """from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.core.services.utils.picsellia_context import create_picsellia_processing_context
from picsellia_cv_engine.steps.base.dataset.loader import load_coco_datasets
from picsellia_cv_engine.steps.base.dataset.uploader import upload_full_dataset

from {pipeline_module}.steps import process
from {pipeline_module}.utils.config import load_processing_parameters

processing_context = create_picsellia_processing_context(
    processing_parameters=load_processing_parameters()
)

@pipeline(
    context=processing_context,
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

PROCESSING_PIPELINE_LOCAL = """import argparse
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.core.services.utils.local_context import create_local_processing_context
from picsellia_cv_engine.steps.base.dataset.loader import load_coco_datasets
from picsellia_cv_engine.steps.base.dataset.uploader import upload_full_dataset

from {pipeline_module}.steps import process
from {pipeline_module}.utils.config import load_processing_parameters

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Run the local processing pipeline")
parser.add_argument("--api_token", required=True, type=str, help="Picsellia API token")
parser.add_argument("--organization_name", required=True, type=str, help="Picsellia Organization ID")
parser.add_argument("--job_type", required=True, type=str, choices=["DATASET_VERSION_CREATION", "TRAINING"], help="Job type")
parser.add_argument("--input_dataset_version_id", required=True, type=str, help="Input dataset version ID")
parser.add_argument("--output_dataset_version_name", required=False, type=str, help="Output dataset version name", default=None)
parser.add_argument("--working_dir", required=False, type=str, help="Working directory", default=None)
args = parser.parse_args()

# Create local processing context
processing_context = create_local_processing_context(
    api_token=args.api_token,
    organization_name=args.organization_name,
    job_type=args.job_type,
    input_dataset_version_id=args.input_dataset_version_id,
    output_dataset_version_name=args.output_dataset_version_name,
    processing_parameters=load_processing_parameters(),
    working_dir=args.working_dir,
)

@pipeline(
    context=processing_context,
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
from picsellia_cv_engine.core.contexts import PicselliaProcessingContext
from picsellia_cv_engine.decorators.pipeline_decorator import Pipeline
from picsellia_cv_engine.decorators.step_decorator import step

from {pipeline_module}.utils.processing import process_images


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
    context: PicselliaProcessingContext = Pipeline.get_active_context()
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
from typing import Dict, Any

from PIL import Image


def process_images(
    input_images_dir: str,
    input_coco: Dict[str, Any],
    parameters: Dict[str, Any],
    output_images_dir: str,
    output_coco: Dict[str, Any],
) -> Dict[str, Any]:
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

def get_image_id_by_filename(coco_data: Dict[str, Any], filename: str) -> int:
    \"\"\"
    Retrieve the image ID for a given filename.

    Args:
        coco_data (Dict): COCO dataset structure containing images.
        filename (str): Filename of the image.

    Returns:
        int: ID of the image.
    \"\"\"
    for image in coco_data["images"]:
        if image["file_name"] == filename:
            return image["id"]
    raise ValueError(f"⚠️ Image with filename '{filename}' not found.")

"""

PROCESSING_PIPELINE_DOCKERFILE = """FROM picsellia/cpu:python3.10

RUN apt-get update && apt-get install -y \\
    libgl1-mesa-glx \\
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --python=$(which python3.10) git+https://github.com/picselliahq/picsellia-cv-engine.git@main

WORKDIR /experiment

ARG REBUILD_ALL
COPY ./ ./{pipeline_dir}
ARG REBUILD_PICSELLIA

RUN uv pip install --python=$(which python3.10) --no-cache -r ./{pipeline_dir}/requirements.txt

ENV PYTHONPATH=\"/experiment\"

ENTRYPOINT ["run", "python3.10", "{pipeline_dir}/picsellia_pipeline.py"]
"""


PROCESSING_PIPELINE_REQUIREMENTS = """# Add your dependencies here
"""

PROCESSING_PIPELINE_DOCKERIGNORE = """# Exclude virtual environments
.venv/
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.log
tests/
"""


class SimpleProcessingTemplate(BaseTemplate):
    def __init__(self, pipeline_name: str):
        super().__init__(pipeline_name=pipeline_name)
        self.pipeline_type = "DATASET_VERSION_CREATION"
        self.default_parameters = {
            "datalake": "default",
            "data_tag": "processed",
        }

    def get_main_files(self) -> dict[str, str]:
        return {
            "picsellia_pipeline.py": PROCESSING_PIPELINE_PICSELLIA.format(
                pipeline_module=self.pipeline_module,
                pipeline_name=self.pipeline_name,
                processing_parameters=self.default_parameters,
            ),
            "local_pipeline.py": PROCESSING_PIPELINE_LOCAL.format(
                pipeline_module=self.pipeline_module,
                pipeline_name=self.pipeline_name,
                processing_parameters=self.default_parameters,
            ),
            "steps.py": PROCESSING_PIPELINE_STEPS.format(
                pipeline_module=self.pipeline_module,
            ),
            "requirements.txt": PROCESSING_PIPELINE_REQUIREMENTS,
            "Dockerfile": PROCESSING_PIPELINE_DOCKERFILE.format(
                pipeline_dir=self.pipeline_dir
            ),
            ".dockerignore": PROCESSING_PIPELINE_DOCKERIGNORE,
        }

    def get_utils_files(self) -> dict[str, str]:
        return {
            "processing.py": PROCESSING_PIPELINE_PROCESSING,
        }

    def get_config_toml(self) -> dict:
        """Define the pipeline-specific configuration."""
        config_data = {
            "metadata": {
                "name": self.pipeline_name,
                "version": "1.0",
                "description": "This pipeline processes data for X.",
                "type": self.pipeline_type,
            },
            "execution": {
                "picsellia_pipeline_script": "picsellia_pipeline.py",
                "local_pipeline_script": "local_pipeline.py",
                "requirements_file": "requirements.txt",
            },
            "docker": {"image_name": "", "image_tag": ""},
            "default_parameters": self.default_parameters,
        }
        return config_data

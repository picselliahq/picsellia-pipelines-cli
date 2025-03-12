TEMPLATE_PICSELLIA_PIPELINE = """from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.models.utils.picsellia_context import (
    create_picsellia_processing_context,
)
from picsellia_cv_engine.steps.dataset.loader import load_coco_datasets
from picsellia_cv_engine.steps.dataset.uploader import upload_full_dataset

from {pipeline_name}.process_dataset import process_dataset

processing_context = create_picsellia_processing_context(
    processing_parameters={{
        "datalake": "default",
        "data_tag": "processed",
    }}
)

@pipeline(
    context=processing_context,
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def {pipeline_name}_pipeline():
    dataset_collection = load_coco_datasets()
    dataset_collection["output"] = process_dataset(
        dataset_collection["input"], dataset_collection["output"]
    )
    upload_full_dataset(dataset_collection["output"], use_id=False)
    return dataset_collection

if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

TEMPLATE_LOCAL_PIPELINE = """import argparse
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.models.utils.local_context import create_local_processing_context
from picsellia_cv_engine.steps.dataset.loader import load_coco_datasets
from picsellia_cv_engine.steps.dataset.uploader import upload_full_dataset

from {pipeline_name}.process_dataset import process_dataset

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Run the local processing pipeline")
parser.add_argument("--api_token", required=True, type=str, help="Picsellia API token")
parser.add_argument("--organization_id", required=True, type=str, help="Picsellia Organization ID")
parser.add_argument("--results_dir", required=True, type=str, help="Results directory")
parser.add_argument("--job_type", required=True, type=str, choices=["DATASET_VERSION_CREATION", "TRAINING"], help="Job type")
parser.add_argument("--input_dataset_version_id", required=True, type=str, help="Input dataset version ID")
parser.add_argument("--output_dataset_version_name", required=False, type=str, help="Output dataset version name", default=None)
parser.add_argument("--datalake", required=False, type=str, help="Datalake name", default="default")
parser.add_argument("--data_tag", required=False, type=str, help="Data tag", default="processed")
args = parser.parse_args()

# Create local processing context
processing_context = create_local_processing_context(
    api_token=args.api_token,
    organization_id=args.organization_id,
    job_id=args.results_dir,
    job_type=args.job_type,
    input_dataset_version_id=args.input_dataset_version_id,
    output_dataset_version_name=args.output_dataset_version_name,
    processing_parameters={{
        "datalake": args.datalake,
        "data_tag": args.data_tag,
    }},
)

@pipeline(
    context=processing_context,
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def {pipeline_name}_pipeline():
    dataset_collection = load_coco_datasets()
    dataset_collection["output"] = process_dataset(
        dataset_collection["input"], dataset_collection["output"]
    )
    upload_full_dataset(dataset_collection["output"], use_id=False)
    return dataset_collection

if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

TEMPLATE_PROCESS_DATASET = """import os
from copy import deepcopy
from glob import glob
from typing import Dict, Any, Tuple

from PIL import Image
from picsellia_cv_engine.decorators.pipeline_decorator import Pipeline
from picsellia_cv_engine.decorators.step_decorator import step
from picsellia_cv_engine.models.contexts.processing.dataset.picsellia_processing_context import (
    PicselliaProcessingContext,
)
from picsellia_cv_engine.models.data.dataset.coco_dataset_context import CocoDatasetContext

@step
def process_dataset(
    input_dataset: CocoDatasetContext, output_dataset: CocoDatasetContext
):
    \"\"\"
    🚀 This function processes the dataset using `process_images()`.

    🔹 **What You Need to Do:**
    - Modify `process_images()` to apply custom transformations or augmentations.
    - Ensure it returns the correct processed images & COCO metadata.

    Args:
        input_dataset (CocoDatasetContext): Input dataset from Picsellia.
        output_dataset (CocoDatasetContext): Output dataset for saving processed data.

    Returns:
        CocoDatasetContext: The processed dataset, ready for local execution and Picsellia.
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

TEMPLATE_DOCKERFILE = """FROM picsellia/cpu:python3.10

RUN apt-get update && apt-get install -y \\
    libgl1-mesa-glx \\
    && rm -rf /var/lib/apt/lists/*

RUN git clone -b feat/add-mkdocs https://github.com/picselliahq/picsellia-cv-engine.git /picsellia-cv-engine
RUN pip install -e /picsellia-cv-engine

WORKDIR /experiment

ARG REBUILD_ALL
COPY ./{pipeline_name} ./{pipeline_name}
ARG REBUILD_PICSELLIA

RUN uv pip install --python=$(which python3.10) --no-cache -r ./{pipeline_name}/requirements.txt

ENV PYTHONPATH=":/experiment"

ENTRYPOINT ["run", "python3.10", "{pipeline_name}/picsellia_pipeline.py"]
"""

TEMPLATE_REQUIREMENTS = """# Add your dependencies here
git+https://github.com/picselliahq/picsellia-cv-engine.git@feat/add-mkdocs#egg=picsellia-cv-engine
"""


def get_picsellia_pipeline_template(pipeline_name: str) -> str:
    return TEMPLATE_PICSELLIA_PIPELINE.format(pipeline_name=pipeline_name)


def get_local_pipeline_template(pipeline_name: str) -> str:
    return TEMPLATE_LOCAL_PIPELINE.format(pipeline_name=pipeline_name)


def get_process_dataset_template() -> str:
    return TEMPLATE_PROCESS_DATASET


def get_dockerfile_template(pipeline_name: str) -> str:
    return TEMPLATE_DOCKERFILE.format(pipeline_name=pipeline_name)


def get_requirements_template() -> str:
    return TEMPLATE_REQUIREMENTS


def get_dockerignore_template() -> str:
    """
    Returns a .dockerignore template to exclude unnecessary files from the Docker build.
    """
    return """# Exclude virtual environments
            .venv/
            venv/

            # Ignore Python cache files
            __pycache__/
            *.pyc
            *.pyo

            # Ignore macOS system files
            .DS_Store

            # Ignore any temporary or log files
            *.log
            """

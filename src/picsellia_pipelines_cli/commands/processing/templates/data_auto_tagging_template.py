from picsellia_pipelines_cli.utils.base_template import BaseTemplate

PROCESSING_PIPELINE = """import argparse

from picsellia.types.enums import ProcessingType
from picsellia_cv_engine.core.services.context.unified_context import create_processing_context_from_config
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.steps.base.datalake.loader import load_datalake

from steps import get_hugging_face_model, load_clip_model, autotag_datalake_with_clip
from utils.parameters import ProcessingParameters


parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["local", "picsellia"], default="picsellia")
parser.add_argument("--config-file", type=str, required=False)
args = parser.parse_args()

context = create_processing_context_from_config(
    processing_type=ProcessingType.DATA_AUTO_TAGGING,
    processing_parameters_cls=ProcessingParameters,
    mode=args.mode,
    config_file_path=args.config_file,
)

@pipeline(
    context=context,
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def {pipeline_name}_processing_pipeline() -> None:
    datalake = load_datalake()
    model = get_hugging_face_model(hugging_face_model_name="openai/clip-vit-large-patch14-336")
    model = load_clip_model(model=model, device="cuda:0")
    autotag_datalake_with_clip(datalake=datalake, model=model, device="cuda:0")

if __name__ == "__main__":
    import os

    import torch

    cpu_count = os.cpu_count()
    if cpu_count is not None and cpu_count > 1:
        torch.set_num_threads(cpu_count - 1)

    {pipeline_name}_processing_pipeline()
"""

PROCESSING_PIPELINE_STEPS = """import logging

from picsellia_cv_engine.core import (
    Datalake,
    DatalakeCollection,
)

from picsellia_cv_engine.decorators.pipeline_decorator import Pipeline
from picsellia_cv_engine.decorators.step_decorator import step
from picsellia_cv_engine.core.contexts.processing.datalake.picsellia_context import PicselliaDatalakeProcessingContext
from utils.model_loader import (
    clip_load_model,
)
from utils.predictor import (
    CLIPModelPredictor,
)

from utils.model import (
    HuggingFaceModel,
)

logger = logging.getLogger(__name__)

@step
def get_hugging_face_model(
    hugging_face_model_name: str | None = None,
) -> HuggingFaceModel:
    context = Pipeline.get_active_context()
    model_version = context.model_version
    if not hugging_face_model_name:
        model_parameters = model_version.sync()["parameters"]
        hugging_face_model_name = model_parameters.get("hugging_face_model_name")
        if not hugging_face_model_name:
            raise ValueError(
                "Hugging Face model name not provided. Please provide it as an argument or set the 'hugging_face_model_name' parameter in the model version."
            )
    print(f"Loading Hugging Face model {hugging_face_model_name}")
    model = HuggingFaceModel(
        hugging_face_model_name=hugging_face_model_name,
        model_name=model_version.name,
        model_version=model_version,
        pretrained_weights_name=None,
        trained_weights_name=None,
        config_name=None,
        exported_weights_name=None,
    )
    return model

@step
def load_clip_model(
    model: HuggingFaceModel,
    device: str = "cuda:0",
) -> HuggingFaceModel:
    loaded_model, loaded_processor = clip_load_model(
        model_name=model.hugging_face_model_name,
        device=device,
    )
    model.set_loaded_model(loaded_model)
    model.set_loaded_processor(loaded_processor)
    return model

@step
def autotag_datalake_with_clip(
    datalake: Datalake | DatalakeCollection,
    model: HuggingFaceModel,
    device: str = "cuda:0",
):
    context: PicselliaDatalakeProcessingContext = Pipeline.get_active_context()

    model_predictor = CLIPModelPredictor(
        model=model,
        tags_list=context.processing_parameters.tags_list,
        device=device,
    )
    if isinstance(datalake, Datalake):
        datalake = datalake
    elif isinstance(datalake, DatalakeCollection):
        datalake = datalake["input"]
    else:
        raise ValueError("Datalake should be either a Datalake or a DatalakeCollection")

    image_inputs, image_paths = model_predictor.pre_process_datalake(
        datalake=datalake,
    )
    image_input_batches = model_predictor.prepare_batches(
        images=image_inputs,
        batch_size=context.processing_parameters.batch_size,
    )
    image_path_batches = model_predictor.prepare_batches(
        images=image_paths,
        batch_size=context.processing_parameters.batch_size,
    )
    batch_results = model_predictor.run_inference_on_batches(
        image_batches=image_input_batches
    )
    picsellia_datalake_autotagging_predictions = model_predictor.post_process_batches(
        image_batches=image_path_batches,
        batch_results=batch_results,
        datalake=datalake,
    )
    logging.info(f"Predictions for datalake {datalake.datalake.id} done.")

    for (
        picsellia_datalake_autotagging_prediction
    ) in picsellia_datalake_autotagging_predictions:
        if not picsellia_datalake_autotagging_prediction["tag"]:
            continue
        picsellia_datalake_autotagging_prediction["data"].add_tags(
            tags=picsellia_datalake_autotagging_prediction["tag"]
        )

    logging.info(f"Tags added to datalake {datalake.datalake.id}.")

"""

PROCESSING_PIPELINE_MODEL = """from typing import Any

from picsellia import Label, ModelVersion
from picsellia_cv_engine.core.models import Model


class HuggingFaceModel(Model):
    \"\"\"
    A context class specifically designed for managing HuggingFace models in the Picsellia platform.

    This class extends the general `Model` and adds additional functionalities
    to support HuggingFace models, including the ability to set and retrieve
    a processor object (such as a model or tokenizer) associated with the HuggingFace model.
    \"\"\"

    def __init__(
        self,
        hugging_face_model_name: str,
        model_name: str,
        model_version: ModelVersion,
        pretrained_weights_name: str | None = None,
        trained_weights_name: str | None = None,
        config_name: str | None = None,
        exported_weights_name: str | None = None,
        labelmap: dict[str, Label] | None = None,
    ):
        \"\"\"
        Initializes the `HuggingFaceModel` with model-related details.

        Args:
            hugging_face_model_name (str): The identifier of the HuggingFace model (e.g., 'bert-base-uncased').
            model_name (str): The name of the model as defined in Picsellia.
            model_version (ModelVersion): The specific version of the model within Picsellia.
            pretrained_weights_name (Optional[str]): The name of the pretrained weights file, if any.
            trained_weights_name (Optional[str]): The name of the trained weights file, if any.
            config_name (Optional[str]): The name of the configuration file for the model, if any.
            exported_weights_name (Optional[str]): The name of the exported weights file, if any.
            labelmap (Optional[Dict[str, Label]]): A dictionary mapping label names to `Label` objects in Picsellia.

        \"\"\"
        super().__init__(
            name=model_name,
            model_version=model_version,
            pretrained_weights_name=pretrained_weights_name,
            trained_weights_name=trained_weights_name,
            config_name=config_name,
            exported_weights_name=exported_weights_name,
            labelmap=labelmap,
        )
        self.hugging_face_model_name = hugging_face_model_name
        self._loaded_processor: Any | None = None

    @property
    def loaded_processor(self) -> Any:
        \"\"\"
        Retrieves the processor currently loaded into the context.

        The processor can be a model, tokenizer, or any other relevant object needed
        for running inferences or processing tasks in HuggingFace models.

        Returns:
            Any: The processor object, typically a HuggingFace model or tokenizer.

        Raises:
            ValueError: If no processor has been set, raises an error indicating that the processor
            must be loaded before accessing it.
        \"\"\"
        if self._loaded_processor is None:
            raise ValueError(
                "Processor is not loaded. Please set the model processor before accessing it."
            )
        return self._loaded_processor

    def set_loaded_processor(self, model: Any) -> None:
        \"\"\"
        Assigns a processor to the context.

        The processor can be any model, tokenizer, or related object required for HuggingFace model
        operations. This method allows the user to specify which processor to use in the context.

        Args:
            model (Any): The processor to assign to the context, typically a HuggingFace model or tokenizer.
        \"\"\"
        self._loaded_processor = model
"""

PROCESSING_PIPELINE_LOADER = """import logging

import torch
from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger(__name__)


def get_device(device: str):
    if device.startswith("cuda") and torch.cuda.is_available():
        print(f"Using GPU: {torch.cuda.get_device_name(0)}")
        device = torch.device("cuda")
    elif device.startswith("cuda") and not torch.cuda.is_available():
        print("Using CPU")
        device = torch.device("cpu")
    else:
        print("Using CPU")
        device = torch.device("cpu")
    return device


def clip_load_model(model_name: str, device: str):
    model = CLIPModel.from_pretrained(model_name)
    model.eval()
    model.to(get_device(device=device))
    processor = CLIPProcessor.from_pretrained(model_name)
    return model, processor
"""

PROCESSING_PIPELINE_PREDICTOR = """import os
from typing import Any
from uuid import UUID

from picsellia import Tag
from picsellia import Datalake as PicselliaDatalake
from picsellia_cv_engine.core import Datalake
from picsellia_cv_engine.core.services.model.predictor.model_predictor import (
    ModelPredictor,
)
from PIL import Image

from utils.model import (
    HuggingFaceModel,
)
from utils.model_loader import (
    get_device,
)


def create_tags(datalake: PicselliaDatalake, list_tags: list):
    \"\"\"
    Creates or retrieves tags from the Datalake.
    Args:
        datalake (Datalake): The datalake object to interact with.
        list_tags (list): List of tags to create or retrieve.
    Returns:
        dict: A dictionary of tag names and Tag objects.
    \"\"\"
    if list_tags:
        for tag_name in list_tags:
            datalake.get_or_create_data_tag(name=tag_name)
    return {k.name: k for k in datalake.list_data_tags()}


def get_picsellia_tag(
        prediction: str, picsellia_tags_name: dict[str, Tag]
) -> Tag:
    \"\"\"
    Retrieves the Picsellia tag corresponding to the prediction.
    Args:
        prediction (str): The predicted tag name.
        picsellia_tags_name (Dict[str, Tag]): A dictionary mapping tag names to Tag objects.
    Returns:
        Tag: The corresponding Picsellia Tag object.
    Raises:
        ValueError: If the predicted tag is not found in Picsellia tags.
    \"\"\"
    if prediction not in picsellia_tags_name:
        raise ValueError(f"Tag {prediction} not found in Picsellia tags.")
    return picsellia_tags_name[prediction]


class CLIPModelPredictor(ModelPredictor[HuggingFaceModel]):
    \"\"\"
    A class to handle the prediction process for CLIP model within a given model.
    Args:
        model (HuggingFaceModel): The model containing the HuggingFace model and processor.
        tags_list (List[str]): A list of tags used for image classification.
        device (str): The device ('cpu' or 'gpu') on which to run the model.
    \"\"\"

    def __init__(
        self,
        model: HuggingFaceModel,
        tags_list: list[str],
        device: str = "cuda:0",
    ):
        \"\"\"
        Initializes the CLIPModelPredictor.
        Args:
            model (HuggingFaceModel): The context of the model to be used.
            tags_list (List[str]): List of tags for inference.
            device (str): The device ('cpu' or 'gpu') on which to run the model.
        \"\"\"
        super().__init__(model)
        if not hasattr(self.model, "loaded_processor"):
            raise ValueError("The model does not have a processor attribute.")
        self.tags_list = tags_list
        self.device = get_device(device)

    def pre_process_datalake(self, datalake: Datalake) -> tuple[list, list[str]]:
        \"\"\"
        Pre-processes images from the datalake by converting them into inputs for the model.
        Args:
            datalake (Datalake): The context containing the directory of images.
        Returns:
            Tuple[List, List[str]]: A tuple containing the list of preprocessed inputs and image paths.
        \"\"\"
        inputs = []
        image_paths = []
        for image_name in os.listdir(datalake.images_dir):
            image_path = os.path.join(datalake.images_dir, image_name)
            image_paths.append(image_path)
            image = Image.open(image_path)

            input = self.model.loaded_processor(
                images=image,
                text=self.tags_list,
                return_tensors="pt",
                padding=True,
            ).to(self.device)
            inputs.append(input)

        return inputs, image_paths

    def prepare_batches(self, images: list[Any], batch_size: int) -> list[list[str]]:
        \"\"\"
        Splits the given images into batches of specified size.
        Args:
            images (List[Any]): A list of images to split into batches.
            batch_size (int): The size of each batch.
        Returns:
            List[List[str]]: A list of image batches.
        \"\"\"
        return [images[i : i + batch_size] for i in range(0, len(images), batch_size)]

    def run_inference_on_batches(
        self, image_batches: list[list[str]]
    ) -> list[list[str]]:
        \"\"\"
        Runs inference on each batch of images.
        Args:
            image_batches (List[List[str]]): List of image batches for inference.
        Returns:
            List[List[str]]: A list of predicted labels for each batch.
        \"\"\"
        all_batch_results = []

        for batch_paths in image_batches:
            batch_results = self._run_inference(batch_inputs=batch_paths)
            all_batch_results.append(batch_results)
        return all_batch_results

    def _run_inference(self, batch_inputs: list) -> list[str]:
        \"\"\"
        Runs the model inference on a batch of inputs.
        Args:
            batch_inputs (List): A batch of pre-processed image inputs.
        Returns:
            List[str]: A list of predicted labels for the batch.
        \"\"\"
        answers = []
        for input in batch_inputs:
            outputs = self.model.loaded_model(**input)
            probs = outputs.logits_per_image.softmax(dim=1)
            predicted_label = self.tags_list[probs.argmax().item()]
            answers.append(predicted_label)
        return answers

    def post_process_batches(
        self,
        image_batches: list[list[str]],
        batch_results: list[list[str]],
        datalake: Datalake,
    ) -> list[dict]:
        \"\"\"
        Post-processes the batch predictions by mapping them to Picsellia tags and generating a final output.
        Args:
            image_batches (List[List[str]]): List of image batches.
            batch_results (List[List[str]]): List of batch prediction results.
            datalake (Datalake): The datalake for processing.
        Returns:
            List[Dict]: A list of dictionaries containing processed predictions.
        \"\"\"
        all_predictions = []

        picsellia_tags_name = create_tags(
            datalake=datalake.datalake, list_tags=self.tags_list
        )

        for batch_result, batch_paths in zip(
            batch_results, image_batches, strict=False
        ):
            all_predictions.extend(
                self._post_process(
                    image_paths=batch_paths,
                    batch_prediction=batch_result,
                    datalake=datalake,
                    picsellia_tags_name=picsellia_tags_name,
                )
            )
        return all_predictions

    def _post_process(
        self,
        image_paths: list[str],
        batch_prediction: list[str],
        datalake: Datalake,
        picsellia_tags_name: dict[str, Tag],
    ) -> list[dict]:
        \"\"\"
        Maps the predictions to Picsellia tags and returns processed predictions.
        Args:
            image_paths (List[str]): List of image paths.
            batch_prediction (List[str]): List of predictions for each image.
            datalake (Datalake): The datalake for retrieving data.
            picsellia_tags_name (Dict[str, Tag]): A dictionary of Picsellia tags.
        Returns:
            List[Dict]: A list of dictionaries containing data and their corresponding Picsellia tags.
        \"\"\"
        processed_predictions = []

        for image_path, prediction in zip(image_paths, batch_prediction, strict=False):
            data_id = os.path.basename(image_path).split(".")[0]
            data = datalake.datalake.list_data(ids=[UUID(data_id)])[0]
            picsellia_tag = get_picsellia_tag(
                prediction=prediction, picsellia_tags_name=picsellia_tags_name
            )
            processed_prediction = {"data": data, "tag": picsellia_tag}
            processed_predictions.append(processed_prediction)

        return processed_predictions
"""

PROCESSING_PIPELINE_PARAMETERS = """from picsellia_cv_engine.core.parameters.base_parameters import Parameters


class ProcessingParameters(Parameters):
    def __init__(self, log_data):
        super().__init__(log_data)

        self.tags_list = [
            tag.strip()
            for tag in self.extract_parameter(["tags_list"], expected_type=str, default="women, men").split(",")
            if tag.strip()
        ]

        self.batch_size = self.extract_parameter(
            keys=["batch_size"], expected_type=int, default=8
        )
"""

PROCESSING_PIPELINE_REQUIREMENTS = """
transformers[torch]
picsellia-cv-engine>=0.4.1
"""

PROCESSING_PIPELINE_PYPROJECT = """[project]
name = "autotag"
version = "0.1.0"
description = "Picsellia processing pipeline"
requires-python = ">=3.10"

dependencies = [
    "picsellia-pipelines-cli",
    "transformers[torch]",
    picsellia-cv-engine>=0.4.1"
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
type = "DATA_AUTO_TAGGING"

[input.datalake]
id = ""

[input.model_version]
id = ""
visibility = "private"

[output.datalake]
id = ""

[run_parameters]
offset = 0
limit = 10

[parameters]
batch_size = 8
tags_list = "women, men"
"""


class DataAutoTaggingProcessingTemplate(BaseTemplate):
    def __init__(self, pipeline_name: str, output_dir: str, use_pyproject: bool = True):
        super().__init__(
            pipeline_name=pipeline_name,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
        self.pipeline_type = "DATA_AUTO_TAGGING"

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
            "parameters.py": PROCESSING_PIPELINE_PARAMETERS,
            "model.py": PROCESSING_PIPELINE_MODEL,
            "model_loader.py": PROCESSING_PIPELINE_LOADER,
            "predictor.py": PROCESSING_PIPELINE_PREDICTOR,
        }

    def get_config_toml(self) -> dict:
        return {
            "metadata": {
                "name": self.pipeline_name,
                "version": "1.0",
                "description": "Autotags data using CLIP model",
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
        return PROCESSING_RUN_CONFIG

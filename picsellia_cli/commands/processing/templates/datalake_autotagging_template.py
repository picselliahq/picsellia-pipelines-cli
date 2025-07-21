from picsellia_cli.utils.base_template import BaseTemplate


PROCESSING_PIPELINE_PICSELLIA = """
from picsellia_cv_engine.core.contexts.processing.datalake.picsellia_datalake_processing_context import (
    PicselliaDatalakeProcessingContext,
)
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.steps.base.datalake.loader import load_datalake

from pipelines.datalake_autotagging.pipeline_utils.parameters.processing_datalake_autotagging_parameters import (
    ProcessingDatalakeAutotaggingParameters,
)
from pipelines.datalake_autotagging.pipeline_utils.steps.model_loading.clip_model_context_loader import (
    load_clip_model,
)
from pipelines.datalake_autotagging.pipeline_utils.steps.processing.clip_datalake_autotagging import (
    autotag_datalake_with_clip,
)
from pipelines.datalake_autotagging.pipeline_utils.steps.weights_extraction.hugging_face_weights_extractor import (
    get_hugging_face_model,
)


def get_context() -> PicselliaDatalakeProcessingContext[
    ProcessingDatalakeAutotaggingParameters
]:
    return PicselliaDatalakeProcessingContext(
        processing_parameters_cls=ProcessingDatalakeAutotaggingParameters
    )


@pipeline(
    context=get_context(),
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def datalake_autotagging_processing_pipeline() -> None:
    datalake = load_datalake()
    model = get_hugging_face_model()
    model = load_clip_model(model=model, device="cuda:0")
    autotag_datalake_with_clip(datalake=datalake, model=model, device="cuda:0")


if __name__ == "__main__":
    import os

    import torch

    cpu_count = os.cpu_count()
    if cpu_count is not None and cpu_count > 1:
        torch.set_num_threads(cpu_count - 1)

    datalake_autotagging_processing_pipeline()
"""

PROCESSING_PIPELINE_LOCAL = """
import dataclasses
from argparse import ArgumentParser

from picsellia_cv_engine.core.contexts.processing.datalake.local_datalake_processing_context import (
    LocalDatalakeProcessingContext,
)
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline
from picsellia_cv_engine.steps.base.datalake.loader import load_datalake

from pipelines.datalake_autotagging.pipeline_utils.steps.model_loading.clip_model_context_loader import (
    load_clip_model,
)
from pipelines.datalake_autotagging.pipeline_utils.steps.processing.clip_datalake_autotagging import (
    autotag_datalake_with_clip,
)
from pipelines.datalake_autotagging.pipeline_utils.steps.weights_extraction.hugging_face_weights_extractor import (
    get_hugging_face_model,
)


@dataclasses.dataclass
class ProcessingDatalakeAutotaggingParameters:
    tags_list: list[str]
    device: str
    batch_size: int


parser = ArgumentParser()
parser.add_argument("--api_token", type=str)
parser.add_argument("--organization_id", type=str)
parser.add_argument("--job_id", type=str)
parser.add_argument("--input_datalake_id", type=str)
parser.add_argument("--output_datalake_id", type=str, required=False)
parser.add_argument("--model_version_id", type=str)
parser.add_argument("--tags_list", nargs="+", type=str)
parser.add_argument("--offset", type=int, default=0)
parser.add_argument("--limit", type=int, default=100)
parser.add_argument("--device", type=str, default="cuda:0")
parser.add_argument("--batch_size", type=int, default=8)
args = parser.parse_args()


def get_context() -> LocalDatalakeProcessingContext:
    return LocalDatalakeProcessingContext(
        api_token=args.api_token,
        organization_id=args.organization_id,
        job_id=args.job_id,
        job_type=None,
        input_datalake_id=args.input_datalake_id,
        output_datalake_id=args.output_datalake_id,
        model_version_id=args.model_version_id,
        offset=args.offset,
        limit=args.limit,
        use_id=True,
        processing_parameters=ProcessingDatalakeAutotaggingParameters(
            tags_list=args.tags_list, device=args.device, batch_size=args.batch_size
        ),
    )


@pipeline(
    context=get_context(),
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def datalake_autotagging_processing_pipeline() -> None:
    datalake = load_datalake()
    model = get_hugging_face_model()
    model = load_clip_model(model=model, device="cuda:0")
    autotag_datalake_with_clip(datalake=datalake, model=model, device="cuda:0")


if __name__ == "__main__":
    import os

    import torch

    cpu_count = os.cpu_count()
    if cpu_count is not None and cpu_count > 1:
        torch.set_num_threads(cpu_count - 1)

    datalake_autotagging_processing_pipeline()
"""

PROCESSING_PIPELINE_STEPS = """import logging

from picsellia_cv_engine.core import (
    Datalake,
    DatalakeCollection,
)
from picsellia_cv_engine.core.contexts.processing.dataset.picsellia_processing_context import (
    PicselliaProcessingContext,
)
from picsellia_cv_engine.decorators.pipeline_decorator import Pipeline
from picsellia_cv_engine.decorators.step_decorator import step

from pipelines.datalake_autotagging.pipeline_utils.model.hugging_face_model import (
    HuggingFaceModel,
)
from pipelines.datalake_autotagging.pipeline_utils.steps_utils.model_prediction.clip_model_predictor import (
    CLIPModelPredictor,
)


@step
def autotag_datalake_with_clip(
    datalake: Datalake | DatalakeCollection,
    model: HuggingFaceModel,
    device: str = "cuda:0",
):
    context: PicselliaProcessingContext = Pipeline.get_active_context()

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

    logging.info(f"Tags added to datalake {datalake.datalake.id}.")"""

PROCESSING_PIPELINE_PARAMETERS = """import re

from picsellia_cv_engine.core.parameters.base_parameters import Parameters


class ProcessingDatalakeAutotaggingParameters(Parameters):
    def __init__(self, log_data):
        super().__init__(log_data)

        self.tags_list: list[str] = re.findall(
            r"'(.*?)'", self.extract_parameter(keys=["tags_list"], expected_type=str)
        )
        self.batch_size = self.extract_parameter(
            keys=["batch_size"], expected_type=int, default=8
        )"""

PROCESSING_PIPELINE_REQUIREMENTS = """torch>=2.0.0
opencv-python
transformers
picsellia-cv-engine
"""

PROCESSING_PIPELINE_PYPROJECT = """[project]
name = "{pipeline_name}"
version = "0.1.0"
description = "Picsellia processing pipeline"
requires-python = ">=3.10"

dependencies = [
    "picsellia-pipelines-cli",
    "transformers",
]

[dependency-groups]
dev = [
    "picsellia-cv-engine",
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

ENTRYPOINT ["run", "python3.10", "{pipeline_dir}/picsellia_pipeline.py"]
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


class DatalakeAutotaggingProcessingTemplate(BaseTemplate):
    def __init__(self, pipeline_name: str, output_dir: str, use_pyproject: bool = True):
        super().__init__(
            pipeline_name=pipeline_name,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
        self.pipeline_type = "DATALAKE_AUTOTAGGING"

    def get_main_files(self) -> dict[str, str]:
        files = {
            "picsellia_pipeline.py": PROCESSING_PIPELINE_PICSELLIA.format(
                pipeline_name=self.pipeline_name,
            ),
            "local_pipeline.py": PROCESSING_PIPELINE_LOCAL.format(
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
        }

    def get_config_toml(self) -> dict:
        return {
            "metadata": {
                "name": self.pipeline_name,
                "version": "1.0",
                "description": "Autotags datalakes using CLIP model",
                "type": self.pipeline_type,
            },
            "execution": {
                "picsellia_pipeline_script": "datalake_pipeline.py",
                "local_pipeline_script": "datalake_pipeline.py",
                "requirements_file": "pyproject.toml"
                if self.use_pyproject
                else "requirements.txt",
                "parameters_class": "utils/parameters.py:ProcessingDatalakeAutotaggingParameters",
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

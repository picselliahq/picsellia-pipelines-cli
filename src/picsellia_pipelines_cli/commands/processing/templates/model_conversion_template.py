from picsellia_pipelines_cli.utils.base_template import BaseTemplate

PROCESSING_PIPELINE = """import argparse

from picsellia.types.enums import ProcessingType
from picsellia_cv_engine.core.services.context.unified_context import create_processing_context_from_config
from picsellia_cv_engine.decorators.pipeline_decorator import pipeline

from steps import convert_model
from utils.parameters import ProcessingParameters

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["local", "picsellia"], default="picsellia")
parser.add_argument("--config-file", type=str, required=False)
args = parser.parse_args()

context = create_processing_context_from_config(
    processing_type=ProcessingType.MODEL_CONVERSION,
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
    convert_model()
    print("✅ Model conversion pipeline completed!")

if __name__ == "__main__":
    {pipeline_name}_pipeline()
"""

PROCESSING_PIPELINE_STEPS = """import os

from picsellia_cv_engine.core.contexts import PicselliaModelProcessingContext
from picsellia_cv_engine.decorators.pipeline_decorator import Pipeline
from picsellia_cv_engine.decorators.step_decorator import step

from utils.processing import convert_model_file


@step
def convert_model():
    \"\"\"
    🚀 Converts a model file (e.g. .pt → .onnx).

    🔹 What it does:
    - Fetch the model version from context.
    - Download the model file locally.
    - Run conversion (defined in utils/processing.py).
    - Optionally re-upload the converted file.
    \"\"\"
    context: PicselliaModelProcessingContext = Pipeline.get_active_context()
    parameters = context.processing_parameters.to_dict()

    # Get model version and download file
    model_version = context.model_version
    model_file = model_version.get_file(parameters.get("input_model_file_name"))
    model_file.download(target_path=os.path.join(context.working_dir, "model"))

    model_file_path = os.path.join(context.working_dir, "model", model_file.filename)

    # Process conversion
    output_path = convert_model_file(model_file_path, parameters)

    # Optionally, re-upload converted file back to Picsellia
    model_version.store(name=parameters.get("output_model_file_name"), path=output_path)

    print(f"✅ Model converted and uploaded: {output_path}")
"""

PROCESSING_PIPELINE_PROCESSING = """from ultralytics import YOLO

def convert_model_file(input_path: str, parameters: dict) -> str:
    \"\"\"
    Converts an Ultralytics YOLO model (.pt) to a specified export format.

    Args:
        input_path (str): Path to the YOLO .pt model file.
        parameters (dict): Export configuration.

    Returns:
        str: Path to the exported model file or directory.
    \"\"\"
    fmt = parameters.get("output_format", "onnx")
    imgsz = parameters.get("imgsz", 640)
    opset = parameters.get("opset_version", 12)
    half = parameters.get("half", False)
    int8 = parameters.get("int8", False)
    dynamic = parameters.get("dynamic", False)

    print(f"🚀 Loading YOLO model from {input_path}")
    model = YOLO(model=input_path, task="classify")

    print(
        f"🔧 Exporting model with format={fmt}, imgsz={imgsz}, opset={opset}, "
        f"half={half}, int8={int8}, dynamic={dynamic}"
    )

    # Run Ultralytics export
    exported_model_path = model.export(
        format=fmt,
        imgsz=imgsz,
        opset=opset,
        half=half,
        int8=int8,
        dynamic=dynamic,
    )

    return exported_model_path
"""

PROCESSING_PIPELINE_PARAMETERS = """from picsellia.types.schemas import LogDataType
from picsellia_cv_engine.core.parameters import Parameters

class ProcessingParameters(Parameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)
        self.input_model_file_name = self.extract_parameter(
            ["input_model_file_name"], expected_type=str, default="best-model"
        )
        self.output_model_file_name = self.extract_parameter(
            ["output_model_file_name"], expected_type=str, default="onnx-model"
        )
        self.output_format = self.extract_parameter(
            ["output_format"], expected_type=str, default="onnx"
        )
        self.imgsz = self.extract_parameter(
            ["imgsz"], expected_type=int, default=640
        )
        self.half = self.extract_parameter(
            ["half"], expected_type=bool, default=False
        )
        self.int8 = self.extract_parameter(
            ["int8"], expected_type=bool, default=False
        )
        self.dynamic = self.extract_parameter(
            ["dynamic"], expected_type=bool, default=False
        )
        self.opset_version = self.extract_parameter(
            ["opset_version"], expected_type=int, default=12
        )
"""

PROCESSING_PIPELINE_REQUIREMENTS = """# Add your dependencies here
picsellia-pipelines-cli
picsellia-cv-engine[ultralytics]>=0.4.1
onnx>=1.12
onnxslim>=0.1.67
onnxruntime
"""

PROCESSING_PIPELINE_PYPROJECT = """[project]
name = "{pipeline_name}"
version = "0.1.0"
description = "Picsellia processing pipeline"
requires-python = ">=3.10"

dependencies = [
    "picsellia-pipelines-cli",
    "picsellia-cv-engine[ultralytics]>=0.4.1",
    "onnx>=1.12",
    "onnxslim>=0.1.67",
    "onnxruntime",
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
type = "MODEL_CONVERSION"

[input.model_version]
id = ""
visibility = "private"

[parameters]
input_model_file_name = "pretrained-weights"
output_model_file_name = "onnx-model"
opset_version = 12
"""


class ModelConversionProcessingTemplate(BaseTemplate):
    def __init__(self, pipeline_name: str, output_dir: str, use_pyproject: bool = True):
        super().__init__(
            pipeline_name=pipeline_name,
            output_dir=output_dir,
            use_pyproject=use_pyproject,
        )
        self.pipeline_type = "MODEL_CONVERSION"

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
                "description": "This pipeline processes model for X.",
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

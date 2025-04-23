# ======================
# TEMPLATES - PIPELINES
# ======================

TRAINING_TEMPLATE_PICSELLIA_PIPELINE = """from picsellia_cv_engine import pipeline
from picsellia_cv_engine.services.base.utils.picsellia_context import (
    create_picsellia_training_context,
)

from {pipeline_name}.utils.augmentation_parameters import (
    DefaultUltralyticsAugmentationParameters,
)
from {pipeline_name}.utils.export_parameters import DefaultExportParameters
from {pipeline_name}.utils.hyperparameters import DefaultUltralyticsHyperParameters
from utils.prepare_dataset import prepare_dataset
from utils.load_model import load_model
from utils.train_model import train_model
from utils.export_model import export_model
from utils.evaluate_model import evaluate_model

context = create_picsellia_training_context(
    hyperparameters_cls=DefaultUltralyticsHyperParameters,
    augmentation_parameters_cls=DefaultUltralyticsAugmentationParameters,
    export_parameters_cls=DefaultExportParameters,
)


@pipeline(
    context=context,
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def {pipeline_name}_pipeline():
    dataset_collection = prepare_dataset()
    model = load_model(pretrained_weights_name="pretrained-weights")
    train_model(model=model, dataset_collection=dataset_collection)
    export_model(model=model)
    evaluate_model(model=model, dataset=dataset_collection["test"])


if __name__ == "__main__":
    {pipeline_name}_pipeline()

"""

TRAINING_TEMPLATE_LOCAL_PIPELINE = """import argparse

from picsellia_cv_engine import pipeline
from picsellia_cv_engine.services.base.utils.local_context import (
    create_local_training_context,
)

from {pipeline_name}.utils.augmentation_parameters import (
    DefaultUltralyticsAugmentationParameters,
)
from {pipeline_name}.utils.export_parameters import DefaultExportParameters
from {pipeline_name}.utils.hyperparameters import DefaultUltralyticsHyperParameters
from utils.prepare_dataset import prepare_dataset
from utils.load_model import load_model
from utils.train_model import train_model
from utils.export_model import export_model
from utils.evaluate_model import evaluate_model

parser = argparse.ArgumentParser()
parser.add_argument("--api_token", type=str, required=True)
parser.add_argument("--organization_id", type=str, required=True)
parser.add_argument("--experiment_id", type=str, required=True)
args = parser.parse_args()

context = create_local_training_context(
    api_token=args.api_token,
    organization_id=args.organization_id,
    experiment_id=args.experiment_id,
    hyperparameters_cls=DefaultUltralyticsHyperParameters,
    augmentation_parameters_cls=DefaultUltralyticsAugmentationParameters,
    export_parameters_cls=DefaultExportParameters,
)


@pipeline(
    context=context,
    log_folder_path="logs/",
    remove_logs_on_completion=False,
)
def {pipeline_name}_pipeline():
    dataset_collection = prepare_dataset()
    model = load_model(pretrained_weights_name="pretrained-weights")
    train_model(model=model, dataset_collection=dataset_collection)
    export_model(model=model)
    evaluate_model(model=model, dataset=dataset_collection["test"])


if __name__ == "__main__":
    import gc
    import torch

    gc.collect()
    torch.cuda.empty_cache()
    {pipeline_name}_pipeline()
"""

# ======================
# TEMPLATES - UTILS
# ======================

TEMPLATE_PREPARE_DATASET = """from picsellia.types.enums import InferenceType
from picsellia_cv_engine import Pipeline
from picsellia_cv_engine.steps.base.dataset.loader import (
    load_coco_datasets_impl,
    load_yolo_datasets_impl,
)
from picsellia_cv_engine.steps.base.dataset.validator import validate_dataset_impl
from picsellia_cv_engine.steps.ultralytics.dataset.preparator import (
    detect_inference_type_from_experiment,
    prepare_classification_data,
    generate_data_yaml,
)


def prepare_dataset():
    context = Pipeline.get_active_context()
    task_type: InferenceType = detect_inference_type_from_experiment(context.experiment)

    if task_type == InferenceType.CLASSIFICATION:
        dataset_collection = load_coco_datasets_impl(
            context=context, skip_asset_listing=False
        )
        dataset_collection = prepare_classification_data(
            dataset_collection=dataset_collection
        )
    elif task_type in (InferenceType.OBJECT_DETECTION, InferenceType.SEGMENTATION):
        dataset_collection = load_yolo_datasets_impl(
            context=context, skip_asset_listing=False
        )
        dataset_collection = generate_data_yaml(dataset_collection=dataset_collection)
    else:
        raise ValueError(f"Unsupported task type detected: {task_type}")
    validate_dataset_impl(dataset=dataset_collection, fix_annotation=True)
    return dataset_collection

"""


TEMPLATE_LOAD_MODEL = """from picsellia_cv_engine import Pipeline
from picsellia_cv_engine.core.contexts import PicselliaTrainingContext
from picsellia_cv_engine.core.models.ultralytics.model import UltralyticsModel
from picsellia_cv_engine.core.parameters import ExportParameters
from picsellia_cv_engine.core.parameters.ultralytics.augmentation_parameters import (
    UltralyticsAugmentationParameters,
)
from picsellia_cv_engine.core.parameters.ultralytics.hyper_parameters import (
    UltralyticsHyperParameters,
)
from picsellia_cv_engine.steps.base.model.builder import build_model_impl
from picsellia_cv_engine.steps.ultralytics.model.loader import load_yolo_weights


def load_model(
    pretrained_weights_name: str = "pretrained-weights",
    trained_weights_name: str | None = None,
    config_name: str | None = None,
    exported_weights_name: str | None = None,
) -> UltralyticsModel:
    context: PicselliaTrainingContext[
        UltralyticsHyperParameters, UltralyticsAugmentationParameters, ExportParameters
    ] = Pipeline.get_active_context()

    model = build_model_impl(
        context=context,
        model_cls=UltralyticsModel,
        pretrained_weights_name=pretrained_weights_name,
        trained_weights_name=trained_weights_name,
        config_name=config_name,
        exported_weights_name=exported_weights_name,
    )

    if not model.pretrained_weights_path:
        raise FileNotFoundError("No pretrained weights path found in model.")

    loaded_model = load_yolo_weights(
        weights_path_to_load=model.pretrained_weights_path,
        device=context.hyperparameters.device,
    )
    model.set_loaded_model(loaded_model)
    return model
"""


TEMPLATE_TRAIN_MODEL = """import os

from picsellia_cv_engine import Pipeline
from picsellia_cv_engine.core.contexts import PicselliaTrainingContext
from picsellia_cv_engine.core.parameters import ExportParameters
from picsellia_cv_engine.core.parameters.ultralytics.augmentation_parameters import (
    UltralyticsAugmentationParameters,
)
from picsellia_cv_engine.core.parameters.ultralytics.hyper_parameters import (
    UltralyticsHyperParameters,
)
from picsellia_cv_engine.services.ultralytics.model.trainer import (
    UltralyticsModelTrainer,
)


def train_model(model, dataset_collection):
    context: PicselliaTrainingContext[
        UltralyticsHyperParameters, UltralyticsAugmentationParameters, ExportParameters
    ] = Pipeline.get_active_context()

    model_trainer = UltralyticsModelTrainer(
        model=model,
        experiment=context.experiment,
    )

    model = model_trainer.train_model(
        dataset_collection=dataset_collection,
        hyperparameters=context.hyperparameters,
        augmentation_parameters=context.augmentation_parameters,
    )

    model.set_latest_run_dir()
    model.set_trained_weights_path()
    if not model.trained_weights_path or not os.path.exists(model.trained_weights_path):
        raise FileNotFoundError(
            f"Trained weights not found at {model.trained_weights_path}"
        )
    model.save_artifact_to_experiment(
        experiment=context.experiment,
        artifact_name="best-model",
        artifact_path=model.trained_weights_path,
    )

    return model

"""


TEMPLATE_EXPORT_MODEL = """from picsellia_cv_engine import Pipeline
from picsellia_cv_engine.core.contexts import PicselliaTrainingContext
from picsellia_cv_engine.core.parameters import ExportParameters
from picsellia_cv_engine.core.parameters.ultralytics.augmentation_parameters import (
    UltralyticsAugmentationParameters,
)
from picsellia_cv_engine.core.parameters.ultralytics.hyper_parameters import (
    UltralyticsHyperParameters,
)
from picsellia_cv_engine.services.ultralytics.model.exporter import (
    UltralyticsModelExporter,
)


def export_model(model):
    context: PicselliaTrainingContext[
        UltralyticsHyperParameters, UltralyticsAugmentationParameters, ExportParameters
    ] = Pipeline.get_active_context()

    model_exporter = UltralyticsModelExporter(model=model)

    if model.exported_weights_dir:
        model_exporter.export_model(
            exported_model_destination_path=model.exported_weights_dir,
            export_format=context.export_parameters.export_format,
            hyperparameters=context.hyperparameters,
        )
        model_exporter.save_model_to_experiment(
            experiment=context.experiment,
            exported_weights_path=model.exported_weights_dir,
            exported_weights_name="model-latest",
        )
    else:
        print("No exported weights directory found in model. Skipping export.")

"""


TEMPLATE_EVALUATE_MODEL = """import os

from picsellia_cv_engine import Pipeline
from picsellia_cv_engine.core.contexts import PicselliaTrainingContext
from picsellia_cv_engine.core.parameters import ExportParameters
from picsellia_cv_engine.core.parameters.ultralytics.augmentation_parameters import (
    UltralyticsAugmentationParameters,
)
from picsellia_cv_engine.core.parameters.ultralytics.hyper_parameters import (
    UltralyticsHyperParameters,
)
from picsellia_cv_engine.services.ultralytics.model.predictor.classification import (
    UltralyticsClassificationModelPredictor,
)
from picsellia_cv_engine.services.ultralytics.model.predictor.object_detection import (
    UltralyticsDetectionModelPredictor,
)
from picsellia_cv_engine.services.ultralytics.model.predictor.segmentation import (
    UltralyticsSegmentationModelPredictor,
)
from picsellia_cv_engine.steps.base.model.evaluator import evaluate_model_impl


def evaluate_model(model, dataset):
    context: PicselliaTrainingContext[
        UltralyticsHyperParameters, UltralyticsAugmentationParameters, ExportParameters
    ] = Pipeline.get_active_context()

    if model.loaded_model.task == "classify":
        model_predictor = UltralyticsClassificationModelPredictor(model=model)
    elif model.loaded_model.task == "detect":
        model_predictor = UltralyticsDetectionModelPredictor(model=model)
    elif model.loaded_model.task == "segment":
        model_predictor = UltralyticsSegmentationModelPredictor(model=model)
    else:
        raise ValueError(f"Model task {model.loaded_model.task} not supported")

    image_paths = model_predictor.pre_process_dataset(dataset=dataset)
    image_batches = model_predictor.prepare_batches(
        image_paths=image_paths, batch_size=context.hyperparameters.batch_size
    )
    batch_results = model_predictor.run_inference_on_batches(
        image_batches=image_batches
    )
    picsellia_predictions = model_predictor.post_process_batches(
        image_batches=image_batches,
        batch_results=batch_results,
        dataset=dataset,
    )

    evaluate_model_impl(
        context=context,
        picsellia_predictions=picsellia_predictions,
        inference_type=model.model_version.type,
        assets=dataset.assets,
        output_dir=os.path.join(context.experiment.name, "evaluation"),
    )

"""

TEMPLATE_HYPERPARAMETERS = """from typing import Optional

from picsellia.types.schemas import LogDataType

from picsellia_cv_engine.core.parameters import HyperParameters


class DefaultUltralyticsHyperParameters(HyperParameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)
        self.time = self.extract_parameter(
            keys=["time"], expected_type=Optional[float], default=None
        )
        self.patience = self.extract_parameter(
            keys=["patience"], expected_type=int, default=100
        )
        self.save_period = self.extract_parameter(
            keys=["save_period"],
            expected_type=int,
            default=-1,
        )
        self.cache = self.extract_parameter(
            keys=["cache", "use_cache"],
            expected_type=bool,
            default=False,
        )
        self.workers = self.extract_parameter(
            keys=["workers"], expected_type=int, default=8
        )
        self.optimizer = self.extract_parameter(
            keys=["optimizer"], expected_type=str, default="auto"
        )
        self.deterministic = self.extract_parameter(
            keys=["deterministic"], expected_type=bool, default=True
        )
        self.single_cls = self.extract_parameter(
            keys=["single_cls"], expected_type=bool, default=False
        )
        self.rect = self.extract_parameter(
            keys=["rect"], expected_type=bool, default=False
        )
        self.cos_lr = self.extract_parameter(
            keys=["cos_lr"], expected_type=bool, default=False
        )
        self.close_mosaic = self.extract_parameter(
            keys=["close_mosaic"], expected_type=int, default=10
        )
        self.amp = self.extract_parameter(
            keys=["amp"], expected_type=bool, default=True
        )
        self.fraction = self.extract_parameter(
            keys=["fraction"], expected_type=float, default=1.0
        )
        self.profile = self.extract_parameter(
            keys=["profile"], expected_type=bool, default=False
        )
        self.freeze = self.extract_parameter(
            keys=["freeze"], expected_type=Optional[int], default=None
        )
        self.lr0 = self.extract_parameter(
            keys=["lr0"], expected_type=float, default=0.01
        )
        self.lrf = self.extract_parameter(
            keys=["lrf"], expected_type=float, default=0.1
        )
        self.momentum = self.extract_parameter(
            keys=["momentum"], expected_type=float, default=0.937
        )
        self.weight_decay = self.extract_parameter(
            keys=["weight_decay"], expected_type=float, default=0.0005
        )
        self.warmup_epochs = self.extract_parameter(
            keys=["warmup_epochs"], expected_type=float, default=3.0
        )
        self.warmup_momentum = self.extract_parameter(
            keys=["warmup_momentum"], expected_type=float, default=0.8
        )
        self.warmup_bias_lr = self.extract_parameter(
            keys=["warmup_bias_lr"], expected_type=float, default=0.1
        )
        self.box = self.extract_parameter(
            keys=["box"], expected_type=float, default=7.5
        )
        self.cls = self.extract_parameter(
            keys=["cls"], expected_type=float, default=0.5
        )
        self.dfl = self.extract_parameter(
            keys=["dfl"], expected_type=float, default=1.5
        )
        self.pose = self.extract_parameter(
            keys=["pose"], expected_type=float, default=12.0
        )
        self.kobj = self.extract_parameter(
            keys=["kobj"], expected_type=float, default=2.0
        )
        self.label_smoothing = self.extract_parameter(
            keys=["label_smoothing"], expected_type=float, default=0.0
        )
        self.nbs = self.extract_parameter(keys=["nbs"], expected_type=int, default=64)
        self.overlap_mask = self.extract_parameter(
            keys=["overlap_mask"], expected_type=bool, default=True
        )
        self.mask_ratio = self.extract_parameter(
            keys=["mask_ratio"], expected_type=int, default=4
        )
        self.dropout = self.extract_parameter(
            keys=["dropout"], expected_type=float, default=0.0
        )
        self.plots = self.extract_parameter(
            keys=["plots"], expected_type=bool, default=True
        )

"""

TEMPLATE_AUGMENTATION_PARAMETERS = """from picsellia.types.schemas import LogDataType

from picsellia_cv_engine.core.parameters import AugmentationParameters


class DefaultUltralyticsAugmentationParameters(AugmentationParameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)

        self.hsv_h = self.extract_parameter(
            keys=["hsv_h"], expected_type=float, default=0.015, range_value=(0.0, 1.0)
        )
        self.hsv_s = self.extract_parameter(
            keys=["hsv_s"], expected_type=float, default=0.7, range_value=(0.0, 1.0)
        )
        self.hsv_v = self.extract_parameter(
            keys=["hsv_v"], expected_type=float, default=0.4, range_value=(0.0, 1.0)
        )
        self.degrees = self.extract_parameter(
            keys=["degrees"],
            expected_type=float,
            default=0.0,
            range_value=(-180.0, 180.0),
        )
        self.translate = self.extract_parameter(
            keys=["translate"], expected_type=float, default=0.1, range_value=(0.0, 1.0)
        )
        self.scale = self.extract_parameter(
            keys=["scale"],
            expected_type=float,
            default=0.5,
            range_value=(
                0.0,
                float("inf"),
            ),
        )
        self.shear = self.extract_parameter(
            keys=["shear"],
            expected_type=float,
            default=0.0,
            range_value=(-180.0, 180.0),
        )
        self.perspective = self.extract_parameter(
            keys=["perspective"],
            expected_type=float,
            default=0.0,
            range_value=(0.0, 0.001),
        )
        self.flipud = self.extract_parameter(
            keys=["flipud"], expected_type=float, default=0.0, range_value=(0.0, 1.0)
        )
        self.fliplr = self.extract_parameter(
            keys=["fliplr"], expected_type=float, default=0.5, range_value=(0.0, 1.0)
        )
        self.bgr = self.extract_parameter(
            keys=["bgr"], expected_type=float, default=0.0, range_value=(0.0, 1.0)
        )
        self.mosaic = self.extract_parameter(
            keys=["mosaic"], expected_type=float, default=1.0, range_value=(0.0, 1.0)
        )
        self.mixup = self.extract_parameter(
            keys=["mixup"], expected_type=float, default=0.0, range_value=(0.0, 1.0)
        )
        self.copy_paste = self.extract_parameter(
            keys=["copy_paste"],
            expected_type=float,
            default=0.0,
            range_value=(0.0, 1.0),
        )
        self.auto_augment = self.extract_parameter(
            keys=["auto_augment"], expected_type=str, default="randaugment"
        )
        self.erasing = self.extract_parameter(
            keys=["erasing"], expected_type=float, default=0.4, range_value=(0.0, 1.0)
        )
        self.crop_fraction = self.extract_parameter(
            keys=["crop_fraction"],
            expected_type=float,
            default=1.0,
            range_value=(0.1, 1.0),
        )

"""


TEMPLATE_EXPORT_PARAMETERS = """from picsellia.types.schemas import LogDataType
from picsellia_cv_engine.core.parameters import ExportParameters


class DefaultExportParameters(ExportParameters):
    def __init__(self, log_data: LogDataType):
        super().__init__(log_data=log_data)

        self.export_format = self.extract_parameter(
            keys=["export_format"], expected_type=str, default="onnx"
        )
"""


# ======================
# TEMPLATES - ENV SETUP
# ======================

TRAINING_TEMPLATE_DOCKERFILE = """FROM picsellia/cuda:11.8.0-cudnn8-ubuntu20.04-python3.10

RUN apt-get update && apt-get install -y \\
    libgl1-mesa-glx \\
    git \\
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/picselliahq/picsellia-cv-engine.git /picsellia-cv-engine
RUN git clone https://github.com/picselliahq/picsellia-pipelines-cli.git /picsellia-pipelines-cli
RUN uv pip install --python=$(which python3.10) -e /picsellia-cv-engine

WORKDIR /experiment

ARG REBUILD_ALL
COPY ./{pipeline_path} ./{pipeline_path}
ARG REBUILD_PICSELLIA

RUN uv pip install --python=$(which python3.10) --no-cache -r ./{pipeline_path}/requirements.txt
RUN uv pip install --python=$(which python3.10) --no-cache torch==2.2.1+cu118 torchaudio==2.2.1+cu118 torchvision==0.17.1+cu118 --find-links https://download.pytorch.org/whl/torch_stable.html

ENV PYTHONPATH=":/experiment"

ENTRYPOINT ["run", "python3.10", "{pipeline_path}/training_pipeline.py"]
"""

TRAINING_TEMPLATE_REQUIREMENTS = """# Add your dependencies here
-e ../picsellia-cv-engine
picsellia>=6.10.0, <7.0.0
numpy<2.0
scikit-learn>=1.2.2, <2.0.0
pycocotools
ultralytics
onnx
onnxruntime
onnxruntime-gpu
onnxslim

"""

TRAINING_TEMPLATE_DOCKERIGNORE = """.venv/
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.log
"""

# ======================
# ACCESSORS
# ======================


def get_training_picsellia_pipeline_template(pipeline_name: str) -> str:
    return TRAINING_TEMPLATE_PICSELLIA_PIPELINE.format(pipeline_name=pipeline_name)


def get_training_local_pipeline_template(pipeline_name: str) -> str:
    return TRAINING_TEMPLATE_LOCAL_PIPELINE.format(pipeline_name=pipeline_name)


def get_training_prepare_dataset_template() -> str:
    return TEMPLATE_PREPARE_DATASET


def get_training_load_model_template() -> str:
    return TEMPLATE_LOAD_MODEL


def get_training_train_model_template() -> str:
    return TEMPLATE_TRAIN_MODEL


def get_training_export_model_template() -> str:
    return TEMPLATE_EXPORT_MODEL


def get_training_evaluate_model_template() -> str:
    return TEMPLATE_EVALUATE_MODEL


def get_training_hyperparameters_template() -> str:
    return TEMPLATE_HYPERPARAMETERS


def get_training_augmentation_parameters_template() -> str:
    return TEMPLATE_AUGMENTATION_PARAMETERS


def get_training_export_parameters_template() -> str:
    return TEMPLATE_EXPORT_PARAMETERS


def get_training_dockerfile_template(pipeline_path: str) -> str:
    return TRAINING_TEMPLATE_DOCKERFILE.format(pipeline_path=pipeline_path)


def get_training_requirements_template() -> str:
    return TRAINING_TEMPLATE_REQUIREMENTS


def get_training_dockerignore_template() -> str:
    return TRAINING_TEMPLATE_DOCKERIGNORE

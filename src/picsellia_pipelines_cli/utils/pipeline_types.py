from enum import Enum

from picsellia.types.enums import ProcessingType

# Default metadata.type written by each init template (template name -> ProcessingType value).
TEMPLATE_DEFAULT_PROCESSING_TYPES: dict[str, str] = {
    "dataset_version_creation": ProcessingType.DATASET_VERSION_CREATION.value,
    "dataset_version": ProcessingType.DATASET_VERSION_CREATION.value,
    "pre_annotation": ProcessingType.PRE_ANNOTATION.value,
    "data_auto_tagging": ProcessingType.DATA_AUTO_TAGGING.value,
    "datalake": ProcessingType.DATA_AUTO_TAGGING.value,
    "model_conversion": ProcessingType.MODEL_CONVERSION.value,
    "model_version": ProcessingType.MODEL_CONVERSION.value,
    "model_compression": ProcessingType.MODEL_COMPRESSION.value,
}

TRAINING_PIPELINE_TYPE = "TRAINING"


class ProcessingLaunchTarget(str, Enum):
    """Platform resource used as the path parameter for processing launch endpoints."""

    DATASET_VERSION = "dataset_version"
    DATALAKE = "datalake"
    MODEL_VERSION = "model_version"


# ProcessingType -> API launch endpoint family (dataset / datalake / model version).
PROCESSING_LAUNCH_TARGETS: dict[ProcessingType, ProcessingLaunchTarget] = {
    ProcessingType.PRE_ANNOTATION: ProcessingLaunchTarget.DATASET_VERSION,
    ProcessingType.DATASET_VERSION_CREATION: ProcessingLaunchTarget.DATASET_VERSION,
    ProcessingType.DATA_AUGMENTATION: ProcessingLaunchTarget.DATASET_VERSION,
    ProcessingType.AUTO_ANNOTATION: ProcessingLaunchTarget.DATASET_VERSION,
    ProcessingType.DATA_AUTO_TAGGING: ProcessingLaunchTarget.DATALAKE,
    ProcessingType.AUTO_TAGGING: ProcessingLaunchTarget.DATALAKE,
    ProcessingType.MODEL_CONVERSION: ProcessingLaunchTarget.MODEL_VERSION,
    ProcessingType.MODEL_COMPRESSION: ProcessingLaunchTarget.MODEL_VERSION,
}

_LAUNCH_TARGET_PROMPT_LABELS: dict[ProcessingLaunchTarget, str] = {
    ProcessingLaunchTarget.DATASET_VERSION: "Dataset version ID (target)",
    ProcessingLaunchTarget.DATALAKE: "Datalake ID (target)",
    ProcessingLaunchTarget.MODEL_VERSION: "Model version ID (target)",
}


def valid_processing_type_values() -> tuple[str, ...]:
    return tuple(pt.value for pt in ProcessingType)


def is_training_pipeline_type(pipeline_type: str) -> bool:
    return pipeline_type == TRAINING_PIPELINE_TYPE


def is_processing_pipeline_type(pipeline_type: str) -> bool:
    try:
        ProcessingType(pipeline_type)
        return True
    except ValueError:
        return False


def parse_processing_type(pipeline_type: str) -> ProcessingType:
    """Return the ProcessingType enum member or raise ValueError."""
    return ProcessingType(pipeline_type)


def get_processing_launch_target(processing_type: ProcessingType) -> ProcessingLaunchTarget:
    """Return which launch endpoint family applies to this processing type."""
    try:
        return PROCESSING_LAUNCH_TARGETS[processing_type]
    except KeyError as exc:
        mapped = ", ".join(t.value for t in PROCESSING_LAUNCH_TARGETS)
        raise ValueError(
            f"No launch endpoint mapping for processing type '{processing_type.value}'. "
            f"CLI supports: {mapped}"
        ) from exc


def processing_types_with_launch_support() -> tuple[str, ...]:
    return tuple(pt.value for pt in PROCESSING_LAUNCH_TARGETS)


def processing_target_id_prompt_label(pipeline_type: str) -> str | None:
    """Human-readable label for the target_id prompt, when applicable."""
    try:
        ptype = parse_processing_type(pipeline_type)
        launch_target = get_processing_launch_target(ptype)
    except ValueError:
        return None
    return _LAUNCH_TARGET_PROMPT_LABELS.get(
        launch_target, f"Target resource ID ({ptype.value})"
    )

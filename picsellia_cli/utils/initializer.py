import os

from picsellia import Client
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType


def write_pipeline_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def create_or_get_model_version(
    client: Client,
    model_name: str,
    version_name: str,
    framework: str,
    inference_type: str,
):
    try:
        model = client.get_model(name=model_name)
    except ResourceNotFoundError:
        model = client.create_model(name=model_name)

    try:
        model.get_version(version_name)
        raise ValueError("Version already exists.")
    except ResourceNotFoundError:
        return model.create_version(
            name=version_name,
            framework=Framework(framework),
            type=InferenceType(inference_type),
            base_parameters={
                "epochs": 2,
                "batch_size": 8,
                "image_size": 640,
            },
        )

"""Unit tests for the training deployer (no network: the Picsellia client is mocked)."""

from unittest.mock import MagicMock

import pytest
from picsellia.exceptions import ResourceNotFoundError
from picsellia.types.enums import Framework, InferenceType

from picsellia_pipelines_cli.commands.training.deployer import (
    _ensure_model_versions_on_host,
)

TARGET = {
    "origin_name": "MyModel",
    "name": "v1",
    "framework": "ONNX",
    "inference_type": "OBJECT_DETECTION",
}
DESCRIPTION = "# My pipeline\n\nRequirements, parameters, outputs..."


def _make_client(*, version_exists: bool):
    """Fake client whose model.get_version raises ResourceNotFoundError when missing."""
    mv = MagicMock(name="model_version")
    mv.framework = Framework.ONNX
    mv.type = InferenceType.OBJECT_DETECTION

    model = MagicMock(name="model")
    if version_exists:
        model.get_version.return_value = mv
    else:
        model.get_version.side_effect = ResourceNotFoundError("missing")
    model.create_version.return_value = mv

    client = MagicMock(name="client")
    client.get_model.return_value = model
    return client, model, mv


def _run(client, *, description, apply_deployment):
    return _ensure_model_versions_on_host(
        client=client,
        model_targets=[TARGET],
        default_parameters={"epochs": 3},
        image_name="registry/image" if apply_deployment else None,
        image_tag="1.0.0" if apply_deployment else None,
        description=description,
        apply_deployment=apply_deployment,
    )


def test_precheck_creates_missing_version_without_description():
    client, model, mv = _make_client(version_exists=False)

    results = _run(client, description=DESCRIPTION, apply_deployment=False)

    model.create_version.assert_called_once()
    assert model.create_version.call_args.kwargs["description"] is None
    mv.update.assert_not_called()
    assert results[0][1] == "Created"


def test_precheck_existing_version_writes_nothing():
    client, model, mv = _make_client(version_exists=True)

    results = _run(client, description=DESCRIPTION, apply_deployment=False)

    model.create_version.assert_not_called()
    mv.update.assert_not_called()
    assert results[0][1] == "Verified"


def test_deploy_missing_version_creates_it_with_description():
    client, model, mv = _make_client(version_exists=False)

    results = _run(client, description=DESCRIPTION, apply_deployment=True)

    model.create_version.assert_called_once()
    assert model.create_version.call_args.kwargs["description"] == DESCRIPTION
    mv.update.assert_not_called()
    assert results[0][1] == "Created"


def test_deploy_existing_version_updates_description():
    client, model, mv = _make_client(version_exists=True)

    results = _run(client, description=DESCRIPTION, apply_deployment=True)

    model.create_version.assert_not_called()
    mv.update.assert_called_once()
    kwargs = mv.update.call_args.kwargs
    assert kwargs["description"] == DESCRIPTION
    # Unchanged framework / type are still not sent (SDK rejects e.g. MASK on update).
    assert kwargs["framework"] is None
    assert kwargs["type"] is None
    assert kwargs["docker_image_name"] == "registry/image"
    assert kwargs["docker_tag"] == "1.0.0"
    assert results[0][1] == "Updated"


@pytest.mark.parametrize("description", [None, ""])
def test_deploy_existing_version_missing_description_is_not_wiped(description):
    client, _model, mv = _make_client(version_exists=True)

    _run(client, description=description, apply_deployment=True)

    assert mv.update.call_args.kwargs["description"] is None


@pytest.mark.parametrize("description", [None, ""])
def test_deploy_missing_version_empty_description_sends_none(description):
    client, model, _mv = _make_client(version_exists=False)

    _run(client, description=description, apply_deployment=True)

    assert model.create_version.call_args.kwargs["description"] is None

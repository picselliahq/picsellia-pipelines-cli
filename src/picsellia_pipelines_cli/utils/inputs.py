from typing import Any

from picsellia.types.enums import (
    Framework,
    InferenceType,
    ProcessingInputType,
)


class InputDefinition:
    """A single input declaration for a Processing pipeline.

    Attributes:
        name: Unique name used to reference this input in the run config.
        input_type: The kind of resource or value expected (from SDK enum).
        required: Whether the input must be provided before launch.
        inference_type_constraint: Optional constraint on the inference type.
        framework_constraint: Optional constraint on the framework.
    """

    def __init__(
        self,
        name: str,
        input_type: ProcessingInputType,
        required: bool = True,
        inference_type_constraint: InferenceType | None = None,
        framework_constraint: Framework | None = None,
    ):
        self.name = name
        self.input_type = input_type
        self.required = required
        self.inference_type_constraint = inference_type_constraint
        self.framework_constraint = framework_constraint

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "input_type": self.input_type.value,
            "required": self.required,
            "inference_type_constraint": self.inference_type_constraint.value
            if self.inference_type_constraint
            else None,
            "framework_constraint": self.framework_constraint.value
            if self.framework_constraint
            else None,
        }

    def __repr__(self) -> str:
        return (
            f"InputDefinition(name={self.name!r}, input_type={self.input_type.value!r}, "
            f"required={self.required})"
        )


class PipelineInputs:
    """Base class for declaring the inputs a Processing pipeline expects.

    Subclass this and call :meth:`define_input` in ``__init__`` for each
    input your processing needs.  The CLI uses :meth:`to_list` to extract
    the definitions when deploying.

    Example::

        class ProcessingInputs(PipelineInputs):
            def __init__(self):
                super().__init__()
                self.define_input(
                    name="dataset",
                    input_type=ProcessingInputType.DATASET_VERSION,
                )
                self.define_input(
                    name="model",
                    input_type=ProcessingInputType.MODEL_VERSION,
                    required=False,
                )
    """

    def __init__(self) -> None:
        self._inputs: list[InputDefinition] = []

    def define_input(
        self,
        name: str,
        input_type: ProcessingInputType,
        required: bool = True,
        inference_type_constraint: InferenceType | None = None,
        framework_constraint: Framework | None = None,
    ) -> None:
        """Register an input that this processing expects."""
        self._inputs.append(
            InputDefinition(
                name=name,
                input_type=input_type,
                required=required,
                inference_type_constraint=inference_type_constraint,
                framework_constraint=framework_constraint,
            )
        )

    @property
    def inputs(self) -> list[InputDefinition]:
        return list(self._inputs)

    def to_list(self) -> list[dict[str, Any]]:
        """Serialise every declared input to a list of dicts (for the API)."""
        return [inp.to_dict() for inp in self._inputs]

    def __repr__(self) -> str:
        return f"PipelineInputs({self._inputs!r})"

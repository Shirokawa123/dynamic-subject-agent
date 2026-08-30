from __future__ import annotations

import pytest

from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ModelGatewayFailure,
    ModelResult,
    ModelTask,
    ModelTaskKind,
    ProviderAdapter,
    ProviderCapabilities,
    StructuredOutputMode,
)


CAPABILITIES = ProviderCapabilities(
    provider_id="test-provider",
    model_id="test-model",
    local=True,
    structured_output_modes=(StructuredOutputMode.STRICT_SCHEMA,),
)


class _Adapter(ProviderAdapter):
    capabilities = CAPABILITIES

    def __init__(self, *, wrong_kind: bool = False) -> None:
        self.tasks = []
        self.wrong_kind = wrong_kind

    def invoke(self, task: ModelTask) -> ModelResult:
        self.tasks.append(task)
        kind = (
            ModelTaskKind.PARTICIPANT_GOAL_REPLY
            if self.wrong_kind
            else task.kind
        )
        return ModelResult(kind=kind, value={"provider-neutral": True})


def test_gateway_exposes_one_provider_neutral_execute_interface() -> None:
    adapter = _Adapter()
    gateway = ModelGateway(adapter)
    task = ModelTask(
        kind=ModelTaskKind.PARTICIPANT_GOAL_CLASSIFICATION,
        payload={"bounded": "task"},
    )

    result = gateway.execute(task)

    assert result == ModelResult(kind=task.kind, value={"provider-neutral": True})
    assert adapter.tasks == [task]
    assert gateway.capabilities == CAPABILITIES


def test_gateway_rejects_wrong_result_kind_and_untyped_adapter_failure() -> None:
    with pytest.raises(ModelGatewayFailure) as mismatch:
        ModelGateway(_Adapter(wrong_kind=True)).execute(
            ModelTask(
                kind=ModelTaskKind.PARTICIPANT_GOAL_CLASSIFICATION,
                payload={},
            )
        )
    assert mismatch.value.code == "provider-result-kind-mismatch"

    class _Broken(ProviderAdapter):
        capabilities = CAPABILITIES

        def invoke(self, task: ModelTask) -> ModelResult:
            raise RuntimeError("provider-specific detail")

    with pytest.raises(ModelGatewayFailure) as failure:
        ModelGateway(_Broken()).execute(
            ModelTask(kind=ModelTaskKind.PARTICIPANT_GOAL_REPLY, payload={})
        )
    assert failure.value.code == "provider-task-failed"

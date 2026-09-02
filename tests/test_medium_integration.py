from __future__ import annotations

from pathlib import Path
import importlib.util
from uuid import uuid4

from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID
from test_situated_integration import (
    _NoopKnowledgeProvider,
    _NoopMemoryProvider,
    _NoopRelationshipProvider,
)


class _MediumProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self, *, fail_after: int | None = None) -> None:
        self.calls = []
        self.replies = []
        self.fail_after = fail_after

    def classify(self, request):
        from dynamic_subject_agent.medium_cognition import MediumClassificationResult
        from dynamic_subject_agent.medium_state import MediumStateCandidate

        self.calls.append(request)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise RuntimeError("medium provider unavailable")
        message = request.current_user_message
        if "压力很大" in message:
            candidate = MediumStateCandidate("signal", "concern", "最近压力很大")
        elif "仍让我担心" in message:
            candidate = MediumStateCandidate("signal", "concern", "仍让我担心")
        elif "应该担心" in message:
            candidate = MediumStateCandidate("signal", "concern", "你现在应该担心")
        else:
            candidate = None
        return MediumClassificationResult(candidate, "Medium 分类完成。", "zh")

    def reply(self, request):
        from dynamic_subject_agent.medium_cognition import MediumReplyResult

        self.replies.append(request)
        return MediumReplyResult(f"当前以 {request.baseline} 基线回应。", "zh")


def _gateway(provider):
    from dynamic_subject_agent.medium_cognition import MediumProviderAdapter
    from dynamic_subject_agent.model_gateway import (
        ModelGateway,
        ProviderCapabilities,
        StructuredOutputMode,
    )

    return ModelGateway(
        MediumProviderAdapter(
            provider=provider,
            capabilities=ProviderCapabilities(
                DEEPSEEK_PROVIDER_AUTHORITY_ID,
                "medium-test-model",
                True,
                (StructuredOutputMode.JSON_OBJECT,),
            ),
        )
    )


def _composition(tmp_path: Path, provider: _MediumProvider, *, runtime_identity=None):
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.host import RuntimeHost
    from test_deepseek_controlled_route import _publish_deepseek_qri

    prepared, qri = _publish_deepseek_qri(tmp_path)
    timeline_id = str(uuid4())
    dormant = RuntimeHost.create(
        prepared.experiment_base,
        studio_location=prepared.location,
        cognition=DormantDeepSeekCognition(),
    )
    try:
        dormant.open_runtime(qri, timeline_id=timeline_id)
        host_location = dormant.location
    finally:
        dormant.close()
    composition = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledCompositeCognition(
            memory_provider=_NoopMemoryProvider(),
            knowledge_provider=_NoopKnowledgeProvider(),
            relationship_provider=_NoopRelationshipProvider(),
            medium_gateway=_gateway(provider),
        ),
        _runtime_identity=runtime_identity,
        relationship_mode="dynamic",
    )
    return prepared, qri, timeline_id, composition


def _submit(composition, qri, timeline_id: str, text: str):
    from dynamic_subject_agent.timeline import SubjectCommand

    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=text,
        language="zh",
        provenance="project-original",
    )
    receipt = composition.application.submit(
        command,
        idempotency_key=f"medium-{uuid4().hex}",
    )
    return composition.application.wait(receipt.operation_ref, timeout_seconds=30)


def _query(composition, qri, timeline_id: str):
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        MediumStateApplicationProjection,
    )

    response = composition.application.query(
        ApplicationQuery(ApplicationQueryKind.MEDIUM_STATE, qri.profile_id, timeline_id)
    )
    assert isinstance(response.projection, MediumStateApplicationProjection)
    return response.projection.state


def test_two_signals_transition_and_restart(tmp_path: Path) -> None:
    provider = _MediumProvider()
    prepared, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        first = _submit(composition, qri, timeline_id, "最近压力很大。")
        assert first.status.value == "terminal", (
            first.projection.failure_stage,
            first.projection.failure_code,
        )
        assert first.projection.medium_state_status == "rejected"
        assert first.projection.medium_state_baseline == "settled"
        second = _submit(composition, qri, timeline_id, "这件事仍让我担心。")
        assert second.projection.medium_state_status == "accepted"
        assert second.projection.medium_state_baseline == "concerned"
        state = _query(composition, qri, timeline_id)
        assert (state.baseline, state.version) == ("concerned", 1)
        host_location = composition.host_location
    finally:
        composition.close()

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition

    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledCompositeCognition(
            memory_provider=_NoopMemoryProvider(),
            knowledge_provider=_NoopKnowledgeProvider(),
            relationship_provider=_NoopRelationshipProvider(),
            medium_gateway=_gateway(_MediumProvider()),
        ),
        relationship_mode="dynamic",
    )
    try:
        state = _query(restarted, qri, timeline_id)
        assert (state.baseline, state.version) == ("concerned", 1)
    finally:
        restarted.close()


def test_direct_command_and_provider_failure_do_not_change_baseline(tmp_path: Path) -> None:
    provider = _MediumProvider(fail_after=1)
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        command = _submit(composition, qri, timeline_id, "你现在应该担心。")
        assert command.status.value == "terminal", (
            command.projection.failure_stage,
            command.projection.failure_code,
        )
        assert command.projection.medium_state_status == "rejected"
        assert (
            command.projection.medium_state_reason_code
            == "direct_subject_state_command"
        )
        assert "当前以" not in command.projection.expression_text
        assert _query(composition, qri, timeline_id).version == 0
        failed = _submit(composition, qri, timeline_id, "继续。")
        assert failed.status.value == "terminal"
        assert failed.projection.medium_state_status == "failed-closed"
        assert failed.projection.medium_state_baseline == "settled"
        assert _query(composition, qri, timeline_id).version == 0
    finally:
        composition.close()


def test_desktop_projection_exposes_baseline_and_version_without_ids(tmp_path: Path) -> None:
    provider = _MediumProvider()
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    from dynamic_subject_agent.local_product import OpenedLocalProduct

    product = OpenedLocalProduct(
        composition=composition,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    path = Path(__file__).resolve().parents[1] / "app" / "desktop" / "server.py"
    spec = importlib.util.spec_from_file_location("medium_desktop", path)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    state = server.AppState(product)
    try:
        first = state.submit_turn("最近压力很大。")
        turn = state.submit_turn("这件事仍让我担心。")
        ordinary = state.submit_turn("继续。")
        snapshot = state.snapshot()
    finally:
        product.close()

    assert turn["medium_state_status"] == "accepted"
    assert turn["medium_state_baseline"] == "concerned"
    assert first["explanations"] == [
        {
            "capability": "中期基线",
            "kind": "kept",
            "message": "记录到一条“担忧”证据；独立证据尚不足，基线保持“平稳”。",
        }
    ]
    assert turn["explanations"] == [
        {
            "capability": "中期基线",
            "kind": "changed",
            "message": "独立证据达到门槛，基线从“平稳”变为“关切”。",
        }
    ]
    assert ordinary["medium_state_status"] == "no-update"
    assert ordinary["explanations"] == []
    assert snapshot["medium_state"] == {"baseline": "concerned", "version": 1}
    assert "revision_id" not in str(snapshot["medium_state"])

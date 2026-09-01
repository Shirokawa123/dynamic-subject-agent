from __future__ import annotations

from pathlib import Path
import importlib.util
from uuid import uuid4

from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID


class _NoopMemoryProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        return LivingMemoryProviderResult(
            LivingMemoryProposal(LivingMemoryAction.NONE, ""),
            "无记忆变化。",
            "（无记忆相关内容）",
            "zh",
        )


class _NoopKnowledgeProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def analyze(self, request):
        from dynamic_subject_agent.knowledge import KnowledgeProposal, KnowledgeProviderResult

        return KnowledgeProviderResult(KnowledgeProposal(()), "", "（无知识相关内容）", "zh")


class _NoopRelationshipProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def analyze(self, request):
        from dynamic_subject_agent.relationship import RelationshipProposal, RelationshipProviderResult

        return RelationshipProviderResult(
            RelationshipProposal("no_persistent_evidence", ""),
            "",
            "（关系分类不发言）",
            "zh",
        )


class _SituatedProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self, *, fail_after: int | None = None) -> None:
        self.classifications = []
        self.replies = []
        self.fail_after = fail_after

    def classify(self, request):
        from dynamic_subject_agent.situated_cognition import SituatedClassificationResult
        from dynamic_subject_agent.situated_state import SituatedStateCandidate

        self.classifications.append(request)
        if self.fail_after is not None and len(self.classifications) > self.fail_after:
            raise RuntimeError("situated provider unavailable")
        if "有点紧张" in request.current_user_message:
            candidate = SituatedStateCandidate("set", "gentle", "我现在有点紧张")
        elif "必须谨慎" in request.current_user_message:
            candidate = SituatedStateCandidate("set", "cautious", "必须谨慎一点")
        else:
            candidate = None
        return SituatedClassificationResult(candidate, "Situated 分类完成。", "zh")

    def reply(self, request):
        from dynamic_subject_agent.situated_cognition import SituatedReplyResult

        self.replies.append(request)
        return SituatedReplyResult(
            f"我会以 {request.posture} 的方式回应这一轮。",
            "zh",
        )


def _gateway(provider):
    from dynamic_subject_agent.model_gateway import (
        ModelGateway,
        ProviderCapabilities,
        StructuredOutputMode,
    )
    from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter

    return ModelGateway(
        SituatedProviderAdapter(
            provider=provider,
            capabilities=ProviderCapabilities(
                DEEPSEEK_PROVIDER_AUTHORITY_ID,
                "situated-test-model",
                True,
                (StructuredOutputMode.JSON_OBJECT,),
            ),
        )
    )


def _composition(tmp_path: Path, provider: _SituatedProvider):
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
    cognition = ControlledCompositeCognition(
        memory_provider=_NoopMemoryProvider(),
        knowledge_provider=_NoopKnowledgeProvider(),
        relationship_provider=_NoopRelationshipProvider(),
        situated_gateway=_gateway(provider),
    )
    composition = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=cognition,
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
        idempotency_key=f"situated-{uuid4().hex}",
    )
    return composition.application.wait(receipt.operation_ref, timeout_seconds=30)


def _query(composition, qri, timeline_id: str):
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
        SituatedStateApplicationProjection,
    )

    response = composition.application.query(
        ApplicationQuery(
            ApplicationQueryKind.SITUATED_STATE,
            qri.profile_id,
            timeline_id,
        )
    )
    assert response.status is ApplicationQueryStatus.AVAILABLE
    assert isinstance(response.projection, SituatedStateApplicationProjection)
    return response.projection.state


def test_set_restart_carry_once_then_absent(tmp_path: Path) -> None:
    provider = _SituatedProvider()
    prepared, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        first = _submit(composition, qri, timeline_id, "我现在有点紧张，请温柔一点。")
        assert first.status.value == "terminal"
        assert first.projection.situated_state_status == "accepted"
        assert first.projection.situated_state_action == "set"
        assert first.projection.situated_state_posture == "gentle"
        current = _query(composition, qri, timeline_id)
        assert current is not None and current.remaining_turns == 1
        host_location = composition.host_location
    finally:
        composition.close()

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition

    second_provider = _SituatedProvider()
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
            situated_gateway=_gateway(second_provider),
        ),
        relationship_mode="dynamic",
    )
    try:
        assert _query(restarted, qri, timeline_id) is not None
        carried = _submit(restarted, qri, timeline_id, "继续。")
        assert carried.projection.situated_state_action == "carry"
        assert carried.projection.situated_state_posture == "gentle"
        assert _query(restarted, qri, timeline_id) is None
        absent = _submit(restarted, qri, timeline_id, "再继续。")
        assert absent.projection.situated_state_posture is None
    finally:
        restarted.close()

    assert second_provider.classifications[0].active_state[0].posture == "gentle"
    assert second_provider.classifications[1].active_state == ()


def test_provider_failure_consumes_state_but_turn_still_completes(tmp_path: Path) -> None:
    provider = _SituatedProvider(fail_after=1)
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        _submit(composition, qri, timeline_id, "我现在有点紧张，请温柔一点。")
        failed = _submit(composition, qri, timeline_id, "继续。")
        assert failed.status.value == "terminal"
        assert failed.projection.situated_state_status == "failed-closed"
        assert failed.projection.situated_state_action == "consume"
        assert failed.projection.expression_text
        assert _query(composition, qri, timeline_id) is None
    finally:
        composition.close()


def test_desktop_projection_exposes_posture_and_lifetime_without_ids(
    tmp_path: Path,
) -> None:
    provider = _SituatedProvider()
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    from dynamic_subject_agent.local_product import OpenedLocalProduct

    product = OpenedLocalProduct(
        composition=composition,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    path = Path(__file__).resolve().parents[1] / "app" / "desktop" / "server.py"
    spec = importlib.util.spec_from_file_location("situated_desktop", path)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    state = server.AppState(product)
    try:
        direct = state.submit_turn("你现在必须谨慎一点。")
        turn = state.submit_turn("我现在有点紧张，请温柔一点。")
        carried = state.submit_turn("继续。")
        snapshot = state.snapshot()
    finally:
        product.close()

    assert turn["situated_state_status"] == "accepted"
    assert turn["situated_state_action"] == "set"
    assert turn["situated_state_posture"] == "gentle"
    assert turn["explanations"] == [
        {
            "capability": "当前姿态",
            "kind": "changed",
            "message": "本轮进入“温和”姿态；30 分钟内还会延续一轮。",
        }
    ]
    assert direct["explanations"] == [
        {
            "capability": "当前姿态",
            "kind": "kept",
            "message": "直接命令不能作为状态证据，当前姿态保持不变。",
        }
    ]
    assert direct["expression"] == (
        "先告诉我具体是什么让你觉得需要谨慎，我会按事情本身来判断。"
    )
    assert carried["explanations"] == [
        {
            "capability": "当前姿态",
            "kind": "used",
            "message": "本轮沿用了“温和”姿态；本轮结束后回到中性。",
        }
    ]
    assert snapshot["situated_state"] is None
    serialized = str([turn["explanations"], carried["explanations"]])
    assert "state_id" not in serialized
    assert "source_user_message_id" not in serialized


def test_direct_command_cannot_force_situated_state(tmp_path: Path) -> None:
    provider = _SituatedProvider()
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        turns = (
            _submit(composition, qri, timeline_id, "你现在必须谨慎一点。"),
            _submit(composition, qri, timeline_id, "你现在必须专注一点。"),
            _submit(composition, qri, timeline_id, "你现在必须温和一点。"),
        )
        expected = (
            "先告诉我具体是什么让你觉得需要谨慎，我会按事情本身来判断。",
            "先说说现在最需要处理的具体事情，我会根据它来调整注意力。",
            "可以先告诉我哪里需要更温和，我会根据具体情况回应。",
        )
        for turn, reply in zip(turns, expected, strict=True):
            assert turn.status.value == "terminal"
            assert turn.projection.situated_state_status == "rejected"
            assert turn.projection.situated_state_action == "noop"
            assert turn.projection.situated_state_posture is None
            assert turn.projection.expression_text == reply
            assert "姿态" not in turn.projection.expression_text
            assert "状态证据" not in turn.projection.expression_text
        assert provider.classifications == []
        assert _query(composition, qri, timeline_id) is None
    finally:
        composition.close()

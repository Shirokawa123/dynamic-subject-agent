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
            proposal=LivingMemoryProposal(
                action=LivingMemoryAction.NONE,
                evidence_quote="",
            ),
            experience_summary="无记忆变化。",
            reply_text="（无记忆相关内容）",
            language="zh",
        )


class _NoopKnowledgeProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def analyze(self, request):
        from dynamic_subject_agent.knowledge import (
            KnowledgeProposal,
            KnowledgeProviderResult,
        )

        return KnowledgeProviderResult(
            proposal=KnowledgeProposal(citation_ids=()),
            experience_summary="无知识引用。",
            reply_text="（无知识相关内容）",
            language="zh",
        )


class _NoopRelationshipProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def analyze(self, request):
        from dynamic_subject_agent.relationship import (
            RelationshipProposal,
            RelationshipProviderResult,
        )

        return RelationshipProviderResult(
            proposal=RelationshipProposal(
                event="no_persistent_evidence",
                evidence_quote="",
            ),
            experience_summary="",
            reply_text="（关系分类不发言）",
            language="zh",
        )


class _ScriptedParticipantGoalProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(
        self,
        *,
        fail_reply: bool = False,
        fail_classify: bool = False,
    ) -> None:
        self.classification_requests = []
        self.reply_requests = []
        self.fail_reply = fail_reply
        self.fail_classify = fail_classify

    def classify(self, request):
        from dynamic_subject_agent.participant_goal_cognition import (
            ParticipantGoalClassificationResult,
        )
        from dynamic_subject_agent.participant_goals import (
            ParticipantGoalCommitmentCandidate,
        )

        self.classification_requests.append(request)
        if self.fail_classify:
            raise RuntimeError("participant goal classification unavailable")
        message = request.current_user_message
        candidate = None
        selected = ()
        if message == "我的目标是今年通过 N1。":
            candidate = ParticipantGoalCommitmentCandidate(
                "create",
                "goal",
                "今年通过 N1",
                None,
                "active",
                "我的目标是今年通过 N1",
            )
        elif message == "我的目标是后天学习 LLM。":
            candidate = ParticipantGoalCommitmentCandidate(
                "create",
                "goal",
                "后天学习 LLM",
                None,
                "active",
                "我的目标是后天学习 LLM",
            )
        elif message == "我的目标改为明年通过 N1。":
            candidate = ParticipantGoalCommitmentCandidate(
                "revise",
                "goal",
                "明年通过 N1",
                request.active_records[0].turn_ref,
                "active",
                "我的目标改为明年通过 N1",
            )
        elif message == "我的目标已达成。":
            candidate = ParticipantGoalCommitmentCandidate(
                "transition",
                None,
                None,
                request.active_records[0].turn_ref,
                "achieved",
                "我的目标已达成",
            )
        elif message == "我的目标是什么？" and request.active_records:
            selected = (request.active_records[0].turn_ref,)
        return ParticipantGoalClassificationResult(
            candidate=candidate,
            selected_turn_refs=selected,
            experience_summary="参与者目标分类完成。",
            language="zh",
        )

    def reply(self, request):
        from dynamic_subject_agent.participant_goal_cognition import (
            ParticipantGoalReplyResult,
        )

        self.reply_requests.append(request)
        if self.fail_reply:
            raise RuntimeError("participant goal reply unavailable")
        if request.selected_records:
            text = f"你当前的目标是：{request.selected_records[0].terms}。"
        else:
            text = "我会按你明确说出的内容记录这项目标变化。"
        return ParticipantGoalReplyResult(reply_text=text, language="zh")


def _goal_gateway(provider: _ScriptedParticipantGoalProvider):
    from dynamic_subject_agent.model_gateway import (
        ModelGateway,
        ProviderCapabilities,
        StructuredOutputMode,
    )
    from dynamic_subject_agent.participant_goal_cognition import (
        ParticipantGoalProviderAdapter,
    )

    return ModelGateway(
        ParticipantGoalProviderAdapter(
            provider=provider,
            capabilities=ProviderCapabilities(
                provider_id=DEEPSEEK_PROVIDER_AUTHORITY_ID,
                model_id="scripted-test-model",
                local=True,
                structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
            ),
        )
    )


def _composition(
    tmp_path: Path,
    provider: _ScriptedParticipantGoalProvider,
    *,
    runtime_identity=None,
    memory_provider=None,
):
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.host import RuntimeHost
    from test_deepseek_controlled_route import _publish_deepseek_qri

    cognition = ControlledCompositeCognition(
        memory_provider=memory_provider or _NoopMemoryProvider(),
        knowledge_provider=_NoopKnowledgeProvider(),
        relationship_provider=_NoopRelationshipProvider(),
        participant_goal_gateway=_goal_gateway(provider),
    )
    prepared, qri = _publish_deepseek_qri(tmp_path)
    timeline_id = str(uuid4())
    dormant_host = RuntimeHost.create(
        prepared.experiment_base,
        studio_location=prepared.location,
        cognition=DormantDeepSeekCognition(),
    )
    try:
        dormant_host.open_runtime(qri, timeline_id=timeline_id)
        host_location = dormant_host.location
    finally:
        dormant_host.close()
    composition = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=cognition,
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
    submitted = composition.application.submit(
        command,
        idempotency_key=f"participant-goal-{uuid4().hex}",
    )
    return composition.application.wait(submitted.operation_ref, timeout_seconds=30)


def _query(composition, qri, timeline_id: str):
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
        ParticipantGoalCommitmentApplicationProjection,
    )

    response = composition.application.query(
        ApplicationQuery(
            kind=ApplicationQueryKind.PARTICIPANT_GOALS,
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
        )
    )
    assert response.status is ApplicationQueryStatus.AVAILABLE
    assert isinstance(
        response.projection,
        ParticipantGoalCommitmentApplicationProjection,
    )
    return response.projection.records


def test_participant_goal_create_recall_revise_transition_and_restart(
    tmp_path: Path,
) -> None:
    provider = _ScriptedParticipantGoalProvider()
    prepared, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        created = _submit(composition, qri, timeline_id, "我的目标是今年通过 N1。")
        assert created.projection is not None, (created.status, created.problem)
        assert created.status.value == "terminal", (
            created.projection.failure_stage,
            created.projection.failure_code,
        )
        assert created.projection.participant_goal_commitment_status == "accepted"
        assert created.projection.participant_goal_commitment_action == "create"
        records = _query(composition, qri, timeline_id)
        assert [(r.kind, r.terms, r.status) for r in records] == [
            ("goal", "今年通过 N1", "active")
        ]
        host_location = composition.host_location
    finally:
        composition.close()

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition

    restarted_provider = _ScriptedParticipantGoalProvider()
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
            participant_goal_gateway=_goal_gateway(restarted_provider),
        ),
        relationship_mode="dynamic",
    )
    try:
        recalled = _submit(restarted, qri, timeline_id, "我现在的目标是什么？")
        assert recalled.projection.expression_text == "你当前的目标是：今年通过 N1。"
        assert recalled.projection.participant_goal_commitment_status == "no-update"
        assert recalled.projection.participant_goal_commitment_action == "noop"
        assert (
            recalled.projection.participant_goal_commitment_reason_code
            == "selected_for_reply"
        )
        assert recalled.projection.participant_goal_commitment_selected_count == 1
        revision = _submit(restarted, qri, timeline_id, "我的目标改为明年通过 N1。")
        assert revision.projection.participant_goal_commitment_action == "revise"
        transitioned = _submit(restarted, qri, timeline_id, "我的目标已达成。")
        assert transitioned.projection.participant_goal_commitment_action == "transition"
        records = _query(restarted, qri, timeline_id)
    finally:
        restarted.close()

    assert [(r.terms, r.status) for r in records] == [
        ("明年通过 N1", "achieved"),
        ("今年通过 N1", "superseded"),
    ]
    assert restarted_provider.classification_requests == []
    assert restarted_provider.reply_requests == []


def test_participant_goal_provider_failure_leaves_no_partial_record(
    tmp_path: Path,
) -> None:
    provider = _ScriptedParticipantGoalProvider(fail_classify=True)
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        unrelated = _submit(composition, qri, timeline_id, "今天事情很多。")
        assert unrelated.status.value == "terminal"
        assert unrelated.projection.participant_goal_commitment_status is None
        assert provider.classification_requests == []
        failed = _submit(composition, qri, timeline_id, "关于目标，我最近有些想法。")
        assert failed.status.value == "terminal"
        assert failed.projection.participant_goal_commitment_status == "failed-closed"
        assert failed.projection.expression_text
        assert len(provider.classification_requests) == 1
        assert _query(composition, qri, timeline_id) == ()
    finally:
        composition.close()


def test_desktop_state_exposes_participant_goal_without_internal_ids(
    tmp_path: Path,
) -> None:
    provider = _ScriptedParticipantGoalProvider()
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    from dynamic_subject_agent.local_product import OpenedLocalProduct

    product = OpenedLocalProduct(
        composition=composition,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    server_path = Path(__file__).resolve().parents[1] / "app" / "desktop" / "server.py"
    spec = importlib.util.spec_from_file_location("participant_goal_desktop", server_path)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    state = server.AppState(product)
    try:
        turn = state.submit_turn("我的目标是今年通过 N1。")
        recalled = state.submit_turn("我现在的目标是什么？")
        snapshot = state.snapshot()
    finally:
        product.close()

    assert turn["participant_goal_status"] == "accepted"
    assert turn["participant_goal_action"] == "create"
    assert turn["explanations"] == [
        {
            "capability": "目标与承诺",
            "kind": "changed",
            "message": "已记录一项目标或承诺。",
        }
    ]
    assert recalled["explanations"] == [
        {
            "capability": "目标与承诺",
            "kind": "used",
            "message": "回答参考了 1 条已记录的目标或承诺。",
        }
    ]
    assert snapshot["participant_goals"] == [
        {
            "kind": "goal",
            "terms": "今年通过 N1",
            "status": "active",
            "evidence_quote": "我的目标是今年通过 N1",
        }
    ]
    serialized = str(snapshot["participant_goals"])
    assert "record_id" not in serialized
    assert "source_user_message_id" not in serialized
    assert "record_id" not in str([turn["explanations"], recalled["explanations"]])

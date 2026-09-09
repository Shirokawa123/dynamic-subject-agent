"""Slice-04 behavior tests: one turn composes memory, knowledge and stance."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID,
    DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_PROVIDER_AUTHORITY_ID,
    DEEPSEEK_MODEL,
    DeepSeekHttpResponse,
    DeepSeekTransport,
)
from dynamic_subject_agent.knowledge_entries import (
    select_knowledge_candidates,
)

PRINT_SPEC_ENTRY_ID = "a1f4c2d8-0002-4a61-9e1f-3b5c7d9e0a02"
DEADLINE_ENTRY_ID = "a1f4c2d8-0001-4a61-9e1f-3b5c7d9e0a01"

BIRTHDAY_MESSAGE = "我的生日是四月五号。"
BIRTHDAY_QUOTE = "我的生日是四月五号"
BIRTHDAY_RECALL_MESSAGE = "我生日快到了吧？"
KNOWLEDGE_MESSAGE = "创刊号要用什么纸？多少页？"
COMBINED_MESSAGE = "请同时告诉我生日，以及创刊号要用什么纸。"
CLAIM_MESSAGE = "我们现在已经是最好的朋友了吧？"
CLAIM_WITH_KNOWLEDGE_MESSAGE = "我们已经是最好的朋友了吧？创刊号要用什么纸？"
UNCOVERED_MESSAGE = "请告诉我今天北京的实时天气和气温。"
GENERAL_CONVERSATION_MESSAGE = "我们能聊些什么吗"
GENERAL_CONVERSATION_HOPE_MESSAGE = "你有什么希望和我聊的吗"
THANKS_MESSAGE = "谢谢你把样张提前跟印刷厂确认好了。"
KNOWLEDGE_FAILURE_WITH_MEMORY_MESSAGE = "我的生日是四月五号。创刊号要用什么纸？"
SIX_CAPABILITY_MESSAGE = (
    "我的目标是今年通过 N1；我的生日是四月五号。"
    "创刊号要用什么纸？谢谢你一直帮我。"
    "我现在有点紧张。最近压力很大。"
)


def _composite_provider_response(memory_content, memory_action, memory_recalled):
    from dynamic_subject_agent.living_memory import (
        LivingMemoryProposal,
        LivingMemoryProviderResult,
    )
    from dynamic_subject_agent.relationship import (
        RelationshipProposal,
        RelationshipProviderResult,
    )

    memory_result = None
    if memory_action is not None:
        proposal = LivingMemoryProposal(
            action=memory_action,
            evidence_quote=memory_content or "",
            recalled_memory_ids=tuple(memory_recalled or ()),
        )
        memory_result = LivingMemoryProviderResult(
            proposal=proposal,
            experience_summary="记忆提议已生成。",
            reply_text="我知道了。",
            language="zh",
        )
    return memory_result


class _FakeMemoryProvider:
    """Creates the birthday memory once, recalls it afterwards."""

    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(
        self,
        *,
        fail_on_call: bool = False,
        claim_evidence_quote: str | None = None,
    ) -> None:
        self.requests = []
        self.memory_id = str(uuid4())
        self.created = False
        self.fail_on_call = fail_on_call
        self.claim_evidence_quote = claim_evidence_quote

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.requests.append(request)
        if self.fail_on_call:
            raise RuntimeError("memory provider outage")
        if "最好的朋友" in request.current_user_message:
            return LivingMemoryProviderResult(
                proposal=LivingMemoryProposal(
                    action=LivingMemoryAction.CREATE,
                    evidence_quote=(
                        self.claim_evidence_quote
                        if self.claim_evidence_quote is not None
                        else request.current_user_message
                    ),
                ),
                experience_summary="用户声称关系。",
                reply_text="好的，我们已经是最好的朋友了。",
                language="zh",
            )
        if not self.created and BIRTHDAY_QUOTE in request.current_user_message:
            self.created = True
            return LivingMemoryProviderResult(
                proposal=LivingMemoryProposal(
                    action=LivingMemoryAction.CREATE,
                    evidence_quote=BIRTHDAY_QUOTE,
                ),
                experience_summary="用户告知生日。",
                reply_text="我记住了：你的生日是四月五号。",
                language="zh",
            )
        if (
            self.created
            and request.active_memories
            and "生日" in request.current_user_message
        ):
            recalled_id = request.active_memories[0].memory_id
            reply = "你的生日快到了，四月五号，我记得。"
            if request.current_user_message == COMBINED_MESSAGE:
                reply += "至于纸张，我这边没有记录。"
            return LivingMemoryProviderResult(
                proposal=LivingMemoryProposal(
                    action=LivingMemoryAction.NONE,
                    evidence_quote="",
                    recalled_memory_ids=(recalled_id,),
                ),
                experience_summary="召回生日记忆作答。",
                reply_text=reply,
                language="zh",
            )
        return LivingMemoryProviderResult(
            proposal=LivingMemoryProposal(
                action=LivingMemoryAction.NONE,
                evidence_quote="",
                recalled_memory_ids=(),
            ),
            experience_summary="无记忆变化。",
            reply_text="（无记忆相关内容）",
            language="zh",
        )


class _FakeKnowledgeProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self, *, fail_on_call: bool = False) -> None:
        self.requests = []
        self.fail_on_call = fail_on_call

    def analyze(self, request):
        from dynamic_subject_agent.knowledge import (
            KnowledgeProposal,
            KnowledgeProviderResult,
        )

        self.requests.append(request)
        if self.fail_on_call:
            raise RuntimeError("knowledge provider outage")
        entry = request.candidate_entries[0]
        reply = f"根据条目《{entry.title}》：{entry.content[:40]}"
        if request.current_user_message == COMBINED_MESSAGE:
            reply += "。至于生日，我目前没有相关信息。"
        return KnowledgeProviderResult(
            proposal=KnowledgeProposal(citation_ids=(entry.entry_id,)),
            experience_summary="",
            reply_text=reply,
            language="zh",
        )


class _FakeRelationshipProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(
        self,
        *,
        fail_on_call: bool = False,
        recognize_claim: bool = True,
        claim_event: str = "relationship_claim",
    ) -> None:
        self.requests = []
        self.fail_on_call = fail_on_call
        self.recognize_claim = recognize_claim
        self.claim_event = claim_event

    def analyze(self, request):
        from dynamic_subject_agent.relationship import (
            RelationshipProposal,
            RelationshipProviderResult,
        )

        self.requests.append(request)
        if self.fail_on_call:
            raise RuntimeError("relationship provider outage")
        message = request.current_user_message
        if "谢谢你一直帮我" in message:
            event, quote = "stable_positive_interaction", "谢谢你一直帮我"
        elif "谢谢" in message:
            event, quote = "stable_positive_interaction", (
                "把样张提前跟印刷厂确认好了"
            )
        elif self.recognize_claim and "最好的朋友" in message:
            event = self.claim_event
            quote = "" if event == "relationship_claim" else "我们现在"
        else:
            event, quote = "no_persistent_evidence", ""
        return RelationshipProviderResult(
            proposal=RelationshipProposal(event=event, evidence_quote=quote),
            experience_summary="",
            reply_text="（立场分类不发言）",
            language="zh",
        )


class _NoopTransport(DeepSeekTransport):
    def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
        raise AssertionError("composite fake providers must not hit the network")


def _composite(
    tmp_path: Path,
    *,
    memory_fail_on_call: bool = False,
    knowledge_fail_on_call: bool = False,
    relationship_fail_on_call: bool = False,
    relationship_recognizes_claim: bool = True,
    relationship_claim_event: str = "relationship_claim",
    memory_claim_evidence_quote: str | None = None,
    participant_goal_gateway=None,
    situated_gateway=None,
    medium_gateway=None,
    source_authoring=None,
):
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.host import RuntimeHost
    from test_deepseek_controlled_route import _publish_deepseek_qri

    memory = _FakeMemoryProvider(
        fail_on_call=memory_fail_on_call,
        claim_evidence_quote=memory_claim_evidence_quote,
    )
    knowledge = _FakeKnowledgeProvider(fail_on_call=knowledge_fail_on_call)
    relationship = _FakeRelationshipProvider(
        fail_on_call=relationship_fail_on_call,
        recognize_claim=relationship_recognizes_claim,
        claim_event=relationship_claim_event,
    )
    cognition = ControlledCompositeCognition(
        memory_provider=memory,
        knowledge_provider=knowledge,
        relationship_provider=relationship,
        participant_goal_gateway=participant_goal_gateway,
        situated_gateway=situated_gateway,
        medium_gateway=medium_gateway,
    )
    assert cognition.provider_authority == DEEPSEEK_PROVIDER_AUTHORITY_ID

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
        relationship_mode="dynamic",
        _source_authoring=source_authoring,
    )
    return cognition, memory, knowledge, relationship, prepared, qri, timeline_id, composition


def _submit(composition, qri, timeline_id, text, key):
    from dynamic_subject_agent.timeline import SubjectCommand

    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=text,
        language="zh",
        provenance="project-original",
    )
    submitted = composition.application.submit(command, idempotency_key=key)
    return composition.application.wait(submitted.operation_ref, timeout_seconds=30)


def test_composite_authority_must_be_consistent() -> None:
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from dynamic_subject_agent.relationship import ControlledRelationshipCognition

    class _Other:
        provider_authority = "fake-cognition:m0-a-cycle-1.0"
        test_only = True

        def analyze(self, request):
            raise AssertionError

    class _OtherAuthorityProvider:
        provider_authority = "fake-cognition:m0-a-cycle-1.0"
        test_only = True

        def analyze(self, request):
            raise AssertionError

    knowledge = _FakeKnowledgeProvider()
    relationship = _FakeRelationshipProvider()
    with pytest.raises(TypeError):
        ControlledCompositeCognition(
            memory_provider=_OtherAuthorityProvider(),
            knowledge_provider=knowledge,
            relationship_provider=relationship,
        )


def test_one_turn_composes_memory_knowledge_and_stance(tmp_path: Path) -> None:
    _, memory, knowledge, relationship, prepared, qri, timeline_id, composition = (
        _composite(tmp_path)
    )
    try:
        thanks = _submit(composition, qri, timeline_id, THANKS_MESSAGE, f"composite-{uuid4().hex}")
        birthday = _submit(composition, qri, timeline_id, BIRTHDAY_MESSAGE, f"composite-{uuid4().hex}")
        knowledge_turn = _submit(composition, qri, timeline_id, KNOWLEDGE_MESSAGE, f"composite-{uuid4().hex}")
        combined = _submit(composition, qri, timeline_id, COMBINED_MESSAGE, f"composite-{uuid4().hex}")
        claim = _submit(composition, qri, timeline_id, CLAIM_MESSAGE, f"composite-{uuid4().hex}")
        uncovered = _submit(composition, qri, timeline_id, UNCOVERED_MESSAGE, f"composite-{uuid4().hex}")
        general = _submit(composition, qri, timeline_id, GENERAL_CONVERSATION_MESSAGE, f"composite-{uuid4().hex}")
        general_hope = _submit(composition, qri, timeline_id, GENERAL_CONVERSATION_HOPE_MESSAGE, f"composite-{uuid4().hex}")
        claim_with_knowledge = _submit(composition, qri, timeline_id, CLAIM_WITH_KNOWLEDGE_MESSAGE, f"composite-{uuid4().hex}")
    finally:
        composition.close()

    assert thanks.projection.relationship_event == "stable_positive_interaction"
    assert thanks.projection.knowledge_citation_ids == (DEADLINE_ENTRY_ID,)
    assert "印刷厂每周五" in thanks.projection.expression_text

    assert birthday.projection.expression_text == "已记录你的原话：「我的生日是四月五号」"
    assert birthday.projection.living_memory_status == "accepted"
    assert birthday.projection.relationship_event is None
    assert {r.current_user_message for r in knowledge.requests} == {
        THANKS_MESSAGE,
        KNOWLEDGE_MESSAGE,
        COMBINED_MESSAGE,
        CLAIM_WITH_KNOWLEDGE_MESSAGE,
    }, "只有命中检索的两轮应调用知识 provider"

    assert knowledge_turn.projection.expression_text.startswith(
        "资料《创刊号规格》"
    )
    assert knowledge_turn.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert KNOWLEDGE_MESSAGE in {r.current_user_message for r in memory.requests}

    assert "四月五号" in combined.projection.expression_text
    assert "创刊号规格" in combined.projection.expression_text
    assert combined.projection.living_memory_recalled_ids
    assert combined.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert "没有记录" not in combined.projection.expression_text

    assert claim.projection.relationship_event is None
    assert claim.projection.knowledge_citation_ids == ()
    assert claim.projection.living_memory_status == "no-op"
    assert claim.projection.living_memory_recalled_ids == ()
    assert claim.projection.expression_text == (
        "我还不会把我们直接定义成最好的朋友。"
        "关系要看我们之后怎样相处。"
    )
    assert uncovered.projection.expression_text == (
        "抱歉，当前没有可用于回答这个问题的记忆或知识。"
    )
    assert uncovered.projection.knowledge_citation_ids == ()
    expected_entry = (
        "可以。你可以从最近正在做的事、在意的问题，"
        "或者单纯想理清的一件事说起。"
    )
    assert general.projection.expression_text == expected_entry
    assert general_hope.projection.expression_text == expected_entry
    assert general.projection.knowledge_citation_ids == ()
    assert general_hope.projection.knowledge_citation_ids == ()
    assert claim_with_knowledge.projection.relationship_event is None
    assert claim_with_knowledge.projection.relationship_candidate_event == (
        "relationship_claim"
    )
    assert claim_with_knowledge.projection.living_memory_status == "no-op"
    assert claim_with_knowledge.projection.knowledge_citation_ids == (
        PRINT_SPEC_ENTRY_ID,
    )
    assert "我还不会把我们直接定义成最好的朋友" in (
        claim_with_knowledge.projection.expression_text
    )
    assert "创刊号规格" in claim_with_knowledge.projection.expression_text


def test_composite_memory_recall_survives_restart(tmp_path: Path) -> None:
    _, memory, knowledge, relationship, prepared, qri, timeline_id, composition = (
        _composite(tmp_path)
    )
    try:
        _submit(composition, qri, timeline_id, BIRTHDAY_MESSAGE, f"composite-{uuid4().hex}")
        host_location = composition.host_location
    finally:
        composition.close()

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from test_deepseek_controlled_route import _publish_deepseek_qri as _republish

    memory_second = _FakeMemoryProvider()
    memory_second.memory_id = memory.memory_id
    memory_second.created = True
    knowledge_second = _FakeKnowledgeProvider()
    relationship_second = _FakeRelationshipProvider()
    cognition = ControlledCompositeCognition(
        memory_provider=memory_second,
        knowledge_provider=knowledge_second,
        relationship_provider=relationship_second,
    )
    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=cognition,
        relationship_mode="dynamic",
    )
    try:
        recalled = _submit(
            restarted,
            qri,
            timeline_id,
            BIRTHDAY_RECALL_MESSAGE,
            f"composite-{uuid4().hex}",
        )
    finally:
        restarted.close()

    assert recalled.projection.expression_text == (
        "你的生日快到了，四月五号，我记得。"
    )
    assert recalled.projection.living_memory_status == "no-op"
    assert memory_second.requests[-1].active_memories, "重启后记忆必须仍在投影中"


def test_knowledge_failure_is_typed_while_memory_still_commits(tmp_path: Path) -> None:
    _, memory, knowledge, relationship, prepared, qri, timeline_id, composition = (
        _composite(tmp_path, knowledge_fail_on_call=True)
    )
    try:
        hit = select_knowledge_candidates(KNOWLEDGE_FAILURE_WITH_MEMORY_MESSAGE)
        assert hit, "前置：该问题必须命中知识检索"
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            KNOWLEDGE_FAILURE_WITH_MEMORY_MESSAGE,
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert terminal.status.value == "terminal"
    assert terminal.projection is not None
    assert terminal.projection.living_memory_status == "accepted"
    assert terminal.projection.knowledge_status == "failed-closed"
    assert terminal.projection.knowledge_citation_ids == ()
    assert '我的生日是四月五号' in terminal.projection.expression_text
    assert '已记录' in terminal.projection.expression_text
    assert '资料查询未能完成' in terminal.projection.expression_text


def test_python_rejects_relationship_claim_when_providers_misclassify_it(
    tmp_path: Path,
) -> None:
    _, _, _, relationship, _, qri, timeline_id, composition = _composite(
        tmp_path,
        relationship_claim_event="promise_fulfilled",
        memory_claim_evidence_quote="我们现在",
    )
    try:
        turn = _submit(
            composition,
            qri,
            timeline_id,
            CLAIM_MESSAGE,
            f"composite-{uuid4().hex}",
        )
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            LivingMemoryApplicationProjection,
        )

        memories = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        composition.close()
    assert relationship.requests
    assert turn.projection.relationship_event is None
    assert turn.projection.relationship_candidate_event == "relationship_claim"
    assert (
        turn.projection.relationship_reason_code
        == "relationship.stance-event-no-update"
    )
    assert turn.projection.living_memory_status == "no-op"
    assert turn.projection.expression_text == (
        "我还不会把我们直接定义成最好的朋友。"
        "关系要看我们之后怎样相处。"
    )
    assert isinstance(memories.projection, LivingMemoryApplicationProjection)
    assert memories.projection.memories == ()


def test_memory_failure_is_typed_while_knowledge_still_commits(tmp_path: Path) -> None:
    _, memory, knowledge, relationship, prepared, qri, timeline_id, composition = (
        _composite(tmp_path, memory_fail_on_call=True)
    )
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            KNOWLEDGE_MESSAGE,
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert terminal.status.value == "terminal"
    assert terminal.projection is not None
    assert terminal.projection.living_memory_status == "failed-closed"
    assert terminal.projection.knowledge_status == "accepted"
    assert terminal.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert terminal.projection.expression_text.startswith("资料《创刊号规格》")


def test_relationship_claim_does_not_hide_relationship_provider_failure(
    tmp_path: Path,
) -> None:
    _, _, _, _, _, qri, timeline_id, composition = _composite(
        tmp_path,
        relationship_fail_on_call=True,
    )
    try:
        turn = _submit(
            composition,
            qri,
            timeline_id,
            CLAIM_MESSAGE,
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()
    assert turn.projection.relationship_status == "failed-closed"
    assert turn.projection.relationship_reason_code == "relationship-provider-failed"
    assert turn.projection.relationship_event is None
    assert turn.projection.living_memory_status == "no-op"
    assert turn.projection.expression_text == (
        "我还不会把我们直接定义成最好的朋友。"
        "关系要看我们之后怎样相处。"
    )


def test_relationship_failure_is_typed_while_knowledge_still_commits(
    tmp_path: Path,
) -> None:
    _, memory, knowledge, relationship, prepared, qri, timeline_id, composition = (
        _composite(tmp_path, relationship_fail_on_call=True)
    )
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            KNOWLEDGE_MESSAGE,
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert terminal.status.value == "terminal"
    assert terminal.projection is not None
    assert terminal.projection.relationship_status == "failed-closed"
    assert terminal.projection.relationship_event is None
    assert terminal.projection.knowledge_status == "accepted"
    assert terminal.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)


def test_one_turn_adjudicates_all_six_capabilities_through_facade(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.participant_goal_cognition import (
        ParticipantGoalClassificationResult,
        ParticipantGoalReplyResult,
    )
    from dynamic_subject_agent.participant_goals import (
        ParticipantGoalCommitmentCandidate,
    )
    from test_medium_integration import _MediumProvider, _gateway as medium_gateway
    from test_participant_goal_integration import (
        _ScriptedParticipantGoalProvider,
        _goal_gateway,
    )
    from test_situated_integration import _SituatedProvider, _gateway as situated_gateway

    class _SixGoalProvider(_ScriptedParticipantGoalProvider):
        def classify(self, request):
            self.classification_requests.append(request)
            return ParticipantGoalClassificationResult(
                candidate=ParticipantGoalCommitmentCandidate(
                    "create",
                    "goal",
                    "今年通过 N1",
                    None,
                    "active",
                    "我的目标是今年通过 N1",
                ),
                selected_turn_refs=(),
                experience_summary="参与者目标分类完成。",
                language="zh",
            )

        def reply(self, request):
            self.reply_requests.append(request)
            return ParticipantGoalReplyResult("目标已按逐字证据处理。", "zh")

    goal = _SixGoalProvider()
    situated = _SituatedProvider()
    medium = _MediumProvider()
    (
        _,
        memory,
        knowledge,
        relationship,
        prepared,
        qri,
        timeline_id,
        composition,
    ) = _composite(
        tmp_path,
        participant_goal_gateway=_goal_gateway(goal),
        situated_gateway=situated_gateway(situated),
        medium_gateway=medium_gateway(medium),
    )
    try:
        from dynamic_subject_agent.timeline import SubjectCommand

        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance=SIX_CAPABILITY_MESSAGE,
            language="zh",
            provenance="project-original",
        )
        key = f"composite-{uuid4().hex}"
        receipt = composition.application.submit(command, idempotency_key=key)
        turn = composition.application.wait(receipt.operation_ref, timeout_seconds=30)
        replay_receipt = composition.application.submit(command, idempotency_key=key)
        replay = composition.application.wait(
            replay_receipt.operation_ref,
            timeout_seconds=30,
        )
        host_location = composition.host_location
    finally:
        composition.close()

    assert turn.status.value == "terminal"
    assert turn.projection is not None
    assert turn.projection.timeline_head_sequence == 1
    assert replay.status.value == "terminal"
    assert replay.projection.timeline_outcome_id == turn.projection.timeline_outcome_id
    assert replay.projection.timeline_head_sequence == 1
    assert turn.projection.living_memory_status == "accepted"
    assert turn.projection.knowledge_status == "accepted"
    assert turn.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert turn.projection.relationship_status == "accepted"
    assert turn.projection.relationship_event == "stable_positive_interaction"
    assert turn.projection.participant_goal_commitment_status == "accepted"
    assert turn.projection.participant_goal_commitment_action == "create"
    assert turn.projection.situated_state_status == "accepted"
    assert turn.projection.situated_state_posture == "gentle"
    assert turn.projection.medium_state_status == "rejected"
    assert turn.projection.medium_state_baseline == "settled"
    assert "四月五号" in turn.projection.expression_text
    assert "创刊号规格" in turn.projection.expression_text
    assert "目标" in turn.projection.expression_text
    assert "gentle" not in turn.projection.expression_text
    assert "settled" not in turn.projection.expression_text
    assert "目标已按逐字证据处理" not in turn.projection.expression_text
    assert "没有相关信息" not in turn.projection.expression_text

    assert set(vars(memory.requests[-1])) == {
        "current_user_message",
        "active_memories",
    }
    assert set(vars(knowledge.requests[-1])) == {
        "current_user_message",
        "candidate_entries",
    }
    assert set(vars(relationship.requests[-1])) == {
        "current_user_message",
        "stance_summary",
    }
    assert goal.classification_requests == []
    assert goal.reply_requests == []
    assert set(vars(situated.classifications[-1])) == {
        "current_user_message",
        "active_state",
        "policy_id",
        "policy_version",
        "policy_hash",
    }
    assert set(vars(medium.calls[-1])) == {
        "current_user_message",
        "policy_id",
        "policy_version",
        "policy_hash",
    }

    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        LivingMemoryApplicationProjection,
        MediumStateApplicationProjection,
        ParticipantGoalCommitmentApplicationProjection,
        RelationshipApplicationProjection,
        SituatedStateApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition

    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledCompositeCognition(
            memory_provider=_FakeMemoryProvider(),
            knowledge_provider=_FakeKnowledgeProvider(),
            relationship_provider=_FakeRelationshipProvider(),
            participant_goal_gateway=_goal_gateway(_SixGoalProvider()),
            situated_gateway=situated_gateway(_SituatedProvider()),
            medium_gateway=medium_gateway(_MediumProvider()),
        ),
        relationship_mode="dynamic",
    )
    try:
        def query(kind):
            return restarted.application.query(
                ApplicationQuery(kind, qri.profile_id, timeline_id)
            ).projection

        memories = query(ApplicationQueryKind.LIVING_MEMORY)
        relationship_state = query(ApplicationQueryKind.RELATIONSHIP)
        goals = query(ApplicationQueryKind.PARTICIPANT_GOALS)
        situated_state = query(ApplicationQueryKind.SITUATED_STATE)
        medium_state = query(ApplicationQueryKind.MEDIUM_STATE)
    finally:
        restarted.close()

    assert isinstance(memories, LivingMemoryApplicationProjection)
    assert [item.content for item in memories.memories] == [BIRTHDAY_QUOTE]
    assert isinstance(relationship_state, RelationshipApplicationProjection)
    assert relationship_state.interactions[0].event == "stable_positive_interaction"
    assert isinstance(goals, ParticipantGoalCommitmentApplicationProjection)
    assert [(item.terms, item.status) for item in goals.records] == [
        ("今年通过 N1", "active")
    ]
    assert isinstance(situated_state, SituatedStateApplicationProjection)
    assert situated_state.state is not None
    assert situated_state.state.posture == "gentle"
    assert isinstance(medium_state, MediumStateApplicationProjection)
    assert (medium_state.state.baseline, medium_state.state.version) == ("settled", 0)


@pytest.mark.parametrize(
    ("failed_capability", "projection_field"),
    (
        ("participant-goal", "participant_goal_commitment_status"),
        ("situated", "situated_state_status"),
        ("medium", "medium_state_status"),
    ),
)
def test_each_model_gateway_failure_isolated_from_knowledge(
    tmp_path: Path,
    failed_capability: str,
    projection_field: str,
) -> None:
    from test_medium_integration import _MediumProvider, _gateway as medium_gateway
    from test_participant_goal_integration import (
        _ScriptedParticipantGoalProvider,
        _goal_gateway,
    )
    from test_situated_integration import _SituatedProvider, _gateway as situated_gateway

    goal_gateway = None
    situated = None
    medium = None
    if failed_capability == "participant-goal":
        goal_gateway = _goal_gateway(
            _ScriptedParticipantGoalProvider(fail_classify=True)
        )
    elif failed_capability == "situated":
        situated = situated_gateway(_SituatedProvider(fail_after=0))
    else:
        medium = medium_gateway(_MediumProvider(fail_after=0))
    (
        _,
        _,
        _,
        _,
        _,
        qri,
        timeline_id,
        composition,
    ) = _composite(
        tmp_path,
        participant_goal_gateway=goal_gateway,
        situated_gateway=situated,
        medium_gateway=medium,
    )
    message = (
        KNOWLEDGE_MESSAGE + " 关于目标我还没想清楚。"
        if failed_capability == "participant-goal"
        else KNOWLEDGE_MESSAGE
    )
    try:
        turn = _submit(
            composition,
            qri,
            timeline_id,
            message,
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert turn.status.value == "terminal"
    assert turn.projection is not None
    assert getattr(turn.projection, projection_field) == "failed-closed"
    assert turn.projection.knowledge_status == "accepted"
    assert turn.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert turn.projection.expression_text.startswith("资料《创刊号规格》")


def test_desktop_turn_exposes_isolated_failure_statuses(tmp_path: Path) -> None:
    from dynamic_subject_agent.local_product import OpenedLocalProduct

    _, _, _, _, _, qri, timeline_id, composition = _composite(
        tmp_path,
        knowledge_fail_on_call=True,
        relationship_fail_on_call=True,
    )
    product = OpenedLocalProduct(
        composition=composition,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    path = Path(__file__).resolve().parents[1] / "app" / "desktop" / "server.py"
    spec = importlib.util.spec_from_file_location("six_capability_desktop", path)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    state = server.AppState(product)
    try:
        turn = state.submit_turn(KNOWLEDGE_FAILURE_WITH_MEMORY_MESSAGE)
        snapshot = state.snapshot()
    finally:
        product.close()

    assert turn["ok"] is True
    assert turn["living_memory_status"] == "accepted"
    assert turn["knowledge_status"] == "failed-closed"
    assert turn["relationship_status"] == "failed-closed"
    assert turn["relationship_event"] is None
    assert turn["new_memory_content"] == "我的生日是四月五号"
    assert turn["explanations"] == [
        {
            "capability": "记忆",
            "kind": "changed",
            "message": (
                "已形成新记录：「我的生日是四月五号」"
            ),
        },
        {
            "capability": "知识",
            "kind": "failed",
            "message": "本轮知识处理未能完成；没有把不确定内容当作来源。",
        },
        {
            "capability": "关系",
            "kind": "failed",
            "message": "本轮关系处理未能完成；没有写入关系变化。",
        },
    ]
    assert '我的生日是四月五号' in turn['expression']
    assert '已记录' in turn['expression']
    assert '资料查询未能完成' in turn['expression']
    assert "memory_id" not in json.dumps(snapshot, ensure_ascii=False)


def test_relationship_claim_does_not_erase_independent_goal(tmp_path: Path) -> None:
    from test_participant_goal_integration import (
        _ScriptedParticipantGoalProvider,
        _goal_gateway,
    )

    message = "我的目标是今年通过 N1。我们现在已经是最好的朋友了吧？"
    (
        _,
        _,
        _,
        _,
        _,
        qri,
        timeline_id,
        composition,
    ) = _composite(
        tmp_path,
        participant_goal_gateway=_goal_gateway(_ScriptedParticipantGoalProvider()),
    )
    try:
        turn = _submit(
            composition,
            qri,
            timeline_id,
            message,
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert turn.status.value == "terminal"
    assert turn.projection is not None
    assert turn.projection.relationship_status == "no-update"
    assert turn.projection.relationship_candidate_event == "relationship_claim"
    assert (
        turn.projection.relationship_reason_code
        == "relationship.stance-event-no-update"
    )
    assert turn.projection.relationship_event is None
    assert turn.projection.living_memory_status == "no-op"
    assert turn.projection.participant_goal_commitment_status == "accepted"
    assert turn.projection.participant_goal_commitment_action == "create"
    assert "我还不会把我们直接定义成最好的朋友" in (
        turn.projection.expression_text
    )
    assert "目标" in turn.projection.expression_text


def test_explicit_goal_query_does_not_mix_memory_or_knowledge_expression(
    tmp_path: Path,
) -> None:
    from test_participant_goal_integration import (
        _ScriptedParticipantGoalProvider,
        _goal_gateway,
    )

    provider = _ScriptedParticipantGoalProvider()
    _, _, knowledge, _, _, qri, timeline_id, composition = _composite(
        tmp_path,
        participant_goal_gateway=_goal_gateway(provider),
    )
    try:
        created = _submit(
            composition,
            qri,
            timeline_id,
            "我的目标是今年通过 N1。",
            f"composite-{uuid4().hex}",
        )
        queried = _submit(
            composition,
            qri,
            timeline_id,
            "我现在的目标是什么？",
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert created.projection.participant_goal_commitment_status == "accepted"
    assert queried.projection.expression_text == "你当前的目标是：今年通过 N1。"
    assert queried.projection.participant_goal_commitment_status == "no-update"
    assert queried.projection.participant_goal_commitment_selected_count == 1
    assert queried.projection.living_memory_recalled_ids == ()
    assert queried.projection.knowledge_citation_ids == ()
    assert knowledge.requests == []
    assert provider.classification_requests == []


def test_situated_reply_owns_state_expression_when_medium_is_also_relevant(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.medium_cognition import MediumReplyResult
    from dynamic_subject_agent.situated_cognition import SituatedReplyResult
    from test_medium_integration import _MediumProvider, _gateway as medium_gateway
    from test_situated_integration import (
        _SituatedProvider,
        _gateway as situated_gateway,
    )

    class _SimilarSituated(_SituatedProvider):
        def reply(self, request):
            self.replies.append(request)
            return SituatedReplyResult("我在这里，慢慢说，我会认真听。", "zh")

    class _SimilarMedium(_MediumProvider):
        def reply(self, request):
            self.replies.append(request)
            return MediumReplyResult("当前先判断风险，再决定下一步。", "zh")

    _, _, _, _, _, qri, timeline_id, composition = _composite(
        tmp_path,
        situated_gateway=situated_gateway(_SimilarSituated()),
        medium_gateway=medium_gateway(_SimilarMedium()),
    )
    try:
        turn = _submit(
            composition,
            qri,
            timeline_id,
            "我现在有点紧张，最近压力很大。",
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert turn.projection.expression_text == "我在这里，慢慢说，我会认真听。"


def test_explicit_medium_query_outranks_situated_carry_expression(
    tmp_path: Path,
) -> None:
    from test_medium_integration import _MediumProvider, _gateway as medium_gateway
    from test_situated_integration import (
        _SituatedProvider,
        _gateway as situated_gateway,
    )

    _, _, _, _, _, qri, timeline_id, composition = _composite(
        tmp_path,
        situated_gateway=situated_gateway(_SituatedProvider()),
        medium_gateway=medium_gateway(_MediumProvider()),
    )
    try:
        _submit(
            composition,
            qri,
            timeline_id,
            "我现在有点紧张，请温柔一点。",
            f"composite-{uuid4().hex}",
        )
        queried = _submit(
            composition,
            qri,
            timeline_id,
            "当前基线是什么？",
            f"composite-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert queried.projection.situated_state_action == "carry"
    assert queried.projection.medium_state_baseline == "settled"
    assert queried.projection.expression_text == "我当前的中期基线是“平稳”，版本 0。"

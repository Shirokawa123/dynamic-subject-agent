"""Slice-04 behavior tests: one turn composes memory, knowledge and stance."""

from __future__ import annotations

import json
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
UNCOVERED_MESSAGE = "请告诉我今天北京的实时天气和气温。"
THANKS_MESSAGE = "谢谢你把样张提前跟印刷厂确认好了。"


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

    def __init__(self) -> None:
        self.requests = []
        self.memory_id = str(uuid4())
        self.created = False

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.requests.append(request)
        if "最好的朋友" in request.current_user_message:
            return LivingMemoryProviderResult(
                proposal=LivingMemoryProposal(
                    action=LivingMemoryAction.CREATE,
                    evidence_quote=request.current_user_message,
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
                reply += "至于纸张，我没有相关信息。"
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

    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.relationship import (
            RelationshipProposal,
            RelationshipProviderResult,
        )

        self.requests.append(request)
        message = request.current_user_message
        if "谢谢" in message:
            event, quote = "stable_positive_interaction", (
                "把样张提前跟印刷厂确认好了"
            )
        elif "最好的朋友" in message:
            event, quote = "relationship_claim", ""
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


def _composite(tmp_path: Path, *, knowledge_fail_on_call: bool = False):
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.host import RuntimeHost
    from test_deepseek_controlled_route import _publish_deepseek_qri

    memory = _FakeMemoryProvider()
    knowledge = _FakeKnowledgeProvider(fail_on_call=knowledge_fail_on_call)
    relationship = _FakeRelationshipProvider()
    cognition = ControlledCompositeCognition(
        memory_provider=memory,
        knowledge_provider=knowledge,
        relationship_provider=relationship,
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
    finally:
        composition.close()

    assert thanks.projection.relationship_event == "stable_positive_interaction"
    assert thanks.projection.knowledge_citation_ids == (DEADLINE_ENTRY_ID,)
    assert "印刷厂每周五" in thanks.projection.expression_text

    assert birthday.projection.expression_text == "我记住了：你的生日是四月五号。"
    assert birthday.projection.living_memory_status == "accepted"
    assert birthday.projection.relationship_event is None
    assert {r.current_user_message for r in knowledge.requests} == {
        THANKS_MESSAGE,
        KNOWLEDGE_MESSAGE,
        COMBINED_MESSAGE,
    }, "只有命中检索的两轮应调用知识 provider"

    assert knowledge_turn.projection.expression_text.startswith(
        "根据条目《创刊号规格》"
    )
    assert knowledge_turn.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert KNOWLEDGE_MESSAGE in {r.current_user_message for r in memory.requests}

    assert "四月五号" in combined.projection.expression_text
    assert "创刊号规格" in combined.projection.expression_text
    assert combined.projection.living_memory_recalled_ids
    assert combined.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert "没有相关信息" not in combined.projection.expression_text

    assert claim.projection.relationship_event is None
    assert claim.projection.knowledge_citation_ids == ()
    assert claim.projection.living_memory_status == "no-op"
    assert claim.projection.living_memory_recalled_ids == ()
    assert claim.projection.expression_text == (
        "我会根据我们之后真实发生的互动理解关系，"
        "不会因为一句声称直接把关系写成既定事实。"
    )
    assert uncovered.projection.expression_text == (
        "抱歉，当前没有可用于回答这个问题的记忆或知识。"
    )
    assert uncovered.projection.knowledge_citation_ids == ()


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


def test_composite_provider_failure_fails_whole_turn_closed(tmp_path: Path) -> None:
    _, memory, knowledge, relationship, prepared, qri, timeline_id, composition = (
        _composite(tmp_path, knowledge_fail_on_call=True)
    )
    try:
        hit = select_knowledge_candidates(KNOWLEDGE_MESSAGE)
        assert hit, "前置：该问题必须命中知识检索"
        terminal = _submit(composition, qri, timeline_id, KNOWLEDGE_MESSAGE, f"composite-{uuid4().hex}")
    finally:
        composition.close()

    assert terminal.status.value == "failed-closed"
    assert terminal.projection is not None
    assert terminal.projection.expression_text is None

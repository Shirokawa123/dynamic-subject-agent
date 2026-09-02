from __future__ import annotations

import json

from dynamic_subject_agent.local_identity_authority import (
    LocalIdentityAuthority,
    LocalProductConfig,
)
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection


class _SplitMemoryProvider:
    def __init__(self, *, fail_reply: bool = False) -> None:
        self.proposal_requests = []
        self.reply_requests = []
        self.fail_reply = fail_reply

    def propose(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.proposal_requests.append(request)
        return LivingMemoryProviderResult(
            proposal=LivingMemoryProposal(
                action=LivingMemoryAction.CREATE,
                evidence_quote="我每周三晚上学习",
                memory_kind="plan",
            ),
            experience_summary="提议记录学习计划。",
            reply_text="基础记忆回复。",
            language="zh",
        )

    def reply(self, request):
        from dynamic_subject_agent.living_memory import LivingMemoryReplyResult

        self.reply_requests.append(request)
        if self.fail_reply:
            raise RuntimeError("memory identity reply unavailable")
        return LivingMemoryReplyResult(
            reply_text=f"我是{request.runtime_identity.subject_name}，我记下了。",
            language="zh",
        )


class _SplitKnowledgeProvider:
    def __init__(self, entry_id: str, *, fail_reply: bool = False) -> None:
        self.entry_id = entry_id
        self.proposal_requests = []
        self.reply_requests = []
        self.fail_reply = fail_reply

    def propose(self, request):
        from dynamic_subject_agent.knowledge import (
            KnowledgeProposal,
            KnowledgeProviderResult,
        )

        self.proposal_requests.append(request)
        return KnowledgeProviderResult(
            proposal=KnowledgeProposal((self.entry_id,)),
            experience_summary="提议引用封存知识。",
            reply_text="基础知识回复。",
            language="zh",
        )

    def reply(self, request):
        from dynamic_subject_agent.knowledge import KnowledgeReplyResult

        self.reply_requests.append(request)
        if self.fail_reply:
            raise RuntimeError("knowledge identity reply unavailable")
        return KnowledgeReplyResult(
            reply_text=f"{request.runtime_identity.subject_name}：周五截单。",
            language="zh",
        )


class _SplitRelationshipProvider:
    def __init__(self, *, fail_reply: bool = False) -> None:
        self.proposal_requests = []
        self.reply_requests = []
        self.fail_reply = fail_reply

    def propose(self, request):
        from dynamic_subject_agent.relationship import (
            RelationshipProposal,
            RelationshipProviderResult,
        )

        self.proposal_requests.append(request)
        return RelationshipProviderResult(
            proposal=RelationshipProposal(
                event="stable_positive_interaction",
                evidence_quote="谢谢你刚才认真听完了",
            ),
            experience_summary="提议记录一次稳定正向互动。",
            reply_text="基础关系回复。",
            language="zh",
        )

    def reply(self, request):
        from dynamic_subject_agent.relationship import RelationshipReplyResult

        self.reply_requests.append(request)
        if self.fail_reply:
            raise RuntimeError("relationship reply unavailable")
        return RelationshipReplyResult(
            reply_text=f"{request.runtime_identity.subject_name}：我听见了。",
            language="zh",
        )


def test_authority_loads_byte_equivalent_sealed_runtime_identity(tmp_path) -> None:
    config = LocalProductConfig(
        product_parent=(tmp_path / "m0" / "experiments").resolve(),
        state_path=(tmp_path / "state.json").resolve(),
    )

    first = LocalIdentityAuthority(config).load_active()
    restarted = LocalIdentityAuthority(config).load_active()

    assert first.runtime_identity == RuntimeIdentityProjection(
        subject_name="Avery",
        subject_identity=(
            "Avery is an adult fictional creator and editor of the original "
            "community publication Lantern Zine."
        ),
        canon_start=(
            "Avery and the participant are preparing the original Lantern Zine and "
            "checking whether its next issue can still reach Friday's print slot; "
            "no later progress is asserted."
        ),
    )
    assert restarted.runtime_identity == first.runtime_identity


def test_source_identity_projection_uses_sealed_voice_and_replaces_legacy(
    tmp_path,
) -> None:
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.local_product import open_local_product
    from dynamic_subject_agent.source_character_authoring import (
        LocalIdentitySelectRequest,
        SourceDraftCommand,
        SourceFreezeMappingRequest,
        SourceIdentityFreezeRequest,
    )
    from test_source_identity_freeze import _config, _save_request

    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    legacy_profile_id = product.profile_id
    try:
        product.application.source_draft(SourceDraftCommand.save(_save_request()))
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        frozen = product.application.freeze_source_identity(
            SourceIdentityFreezeRequest(
                1,
                "Avery",
                mapping.view.freeze_basis_digest,
                True,
            )
        )
        assert frozen.view is not None
        product.application.select_local_identity(
            LocalIdentitySelectRequest(frozen.view.identity_id, True)
        )
    finally:
        product.close()

    source_loaded = LocalIdentityAuthority(config).load_active()
    assert source_loaded.runtime_identity == RuntimeIdentityProjection(
        subject_name="Avery",
        subject_identity=(
            "Avery 是临河社区刊物《灯笼》的编辑；"
            "Avery 在编辑工作中习惯先核对来源再回答"
        ),
        canon_start=(
            "表达方式：Avery 说话简洁，不确定时会直接说‘资料里没有写，我不知道’\n"
            "此身份尚无运行时经历。"
        ),
    )
    assert source_loaded.qri.profile_id != legacy_profile_id


def test_memory_proposal_is_identity_free_and_reply_receives_exact_projection(
    tmp_path,
) -> None:
    from uuid import uuid4

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    runtime_identity = RuntimeIdentityProjection(
        subject_name="Mira",
        subject_identity="Mira 是一名谨慎的地图修复师。",
        canon_start="表达方式：使用简短、克制的句子。\n此身份尚无运行时经历。",
    )
    provider = _SplitMemoryProvider()
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _runtime_identity=runtime_identity,
        _cognition=ControlledLivingMemoryCognition(
            provider=provider,
        ),
    )
    try:
        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance="我每周三晚上学习。",
            language="zh",
            provenance="project-original",
        )
        submitted = composition.application.submit(
            command,
            idempotency_key="runtime-identity-memory-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.expression_text == "我是Mira，我记下了。"
    assert len(provider.proposal_requests) == 1
    assert not hasattr(provider.proposal_requests[0], "runtime_identity")
    assert len(provider.reply_requests) == 1
    assert provider.reply_requests[0].runtime_identity == runtime_identity
    assert provider.reply_requests[0].selected_memories == ()


def test_deepseek_memory_reply_outbound_is_exact_identity_projection() -> None:
    from dynamic_subject_agent.deepseek import DeepSeekLivingMemoryProvider
    from dynamic_subject_agent.living_memory import (
        LivingMemoryReplyMemory,
        LivingMemoryReplyRequest,
    )

    request = LivingMemoryReplyRequest(
        current_user_message="我之前的计划是什么？",
        selected_memories=(LivingMemoryReplyMemory("我明天学习 LLM"),),
        runtime_identity=RuntimeIdentityProjection(
            subject_name="Mira",
            subject_identity="Mira 是一名谨慎的地图修复师。",
            canon_start="表达方式：使用简短、克制的句子。",
        ),
    )

    body = json.loads(
        DeepSeekLivingMemoryProvider.reply_outbound_bytes(request).decode("utf-8")
    )
    projection = json.loads(body["messages"][1]["content"])
    assert "canon_start 只是不可续写的故事起点" in body["messages"][0]["content"]
    assert "不得复制、引用或反复当作口头禅" in body["messages"][0]["content"]

    assert projection == {
        "current_user_message": "我之前的计划是什么？",
        "selected_memories": [{"content": "我明天学习 LLM"}],
        "runtime_identity": {
            "subject_name": "Mira",
            "subject_identity": "Mira 是一名谨慎的地图修复师。",
            "canon_start": "表达方式：使用简短、克制的句子。",
        },
    }
    serialized = json.dumps(body, ensure_ascii=False)
    for forbidden in (
        "identity_core",
        "initial_relationship_premise",
        "profile_id",
        "timeline_id",
        "freeze_basis",
    ):
        assert forbidden not in serialized


def test_knowledge_proposal_is_identity_free_and_reply_gets_selected_content(
    tmp_path,
) -> None:
    from uuid import uuid4

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
    from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    runtime_identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )
    entry = KnowledgeEntry(
        entry_id="a1f4c2d8-0001-4a61-9e1f-3b5c7d9e0a01",
        title="截单时间",
        content="社区刊物每周五 17:00 截单。",
        source_ref="project-original:test",
    )
    provider = _SplitKnowledgeProvider(entry.entry_id)
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _runtime_identity=runtime_identity,
        _cognition=ControlledKnowledgeCognition(
            provider=provider,
            entries=(entry,),
        ),
    )
    try:
        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance="社区刊物什么时候截单？",
            language="zh",
            provenance="project-original",
        )
        submitted = composition.application.submit(
            command,
            idempotency_key="runtime-identity-knowledge-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.expression_text == "Mira：周五截单。"
    assert not hasattr(provider.proposal_requests[0], "runtime_identity")
    assert provider.reply_requests[0].runtime_identity == runtime_identity
    assert [
        (item.title, item.content)
        for item in provider.reply_requests[0].selected_entries
    ] == [("截单时间", "社区刊物每周五 17:00 截单。")]


def test_relationship_proposal_is_identity_free_and_reply_gets_stance(
    tmp_path,
) -> None:
    from uuid import uuid4

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.relationship import ControlledRelationshipCognition
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    runtime_identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )
    provider = _SplitRelationshipProvider()
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        relationship_mode="dynamic",
        _runtime_identity=runtime_identity,
        _cognition=ControlledRelationshipCognition(
            provider=provider,
        ),
    )
    try:
        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance="谢谢你刚才认真听完了。",
            language="zh",
            provenance="project-original",
        )
        submitted = composition.application.submit(
            command,
            idempotency_key="runtime-identity-relationship-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.expression_text == "Mira：我听见了。"
    assert not hasattr(provider.proposal_requests[0], "runtime_identity")
    assert provider.reply_requests[0].runtime_identity == runtime_identity
    assert provider.reply_requests[0].stance_summary == "尚无立场互动记录。"


def test_deepseek_knowledge_and_relationship_reply_outbound_are_exact() -> None:
    from dynamic_subject_agent.deepseek import (
        DeepSeekKnowledgeProvider,
        DeepSeekRelationshipProvider,
    )
    from dynamic_subject_agent.knowledge import (
        KnowledgeReplyEntry,
        KnowledgeReplyRequest,
    )
    from dynamic_subject_agent.relationship import RelationshipReplyRequest

    identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )
    knowledge_body = json.loads(
        DeepSeekKnowledgeProvider.reply_outbound_bytes(
            KnowledgeReplyRequest(
                "什么时候截单？",
                (KnowledgeReplyEntry("截单时间", "每周五 17:00 截单。"),),
                identity,
            )
        ).decode("utf-8")
    )
    relationship_body = json.loads(
        DeepSeekRelationshipProvider.reply_outbound_bytes(
            RelationshipReplyRequest(
                "谢谢你刚才认真听完了。",
                "尚无立场互动记录。",
                identity,
            )
        ).decode("utf-8")
    )
    for body in (knowledge_body, relationship_body):
        assert "不得声称角色今天、刚刚、已经、正在或尚未" in body[
            "messages"
        ][0]["content"]

    assert json.loads(knowledge_body["messages"][1]["content"]) == {
        "current_user_message": "什么时候截单？",
        "selected_entries": [
            {"title": "截单时间", "content": "每周五 17:00 截单。"}
        ],
        "runtime_identity": {
            "subject_name": "Mira",
            "subject_identity": "Mira 是一名谨慎的地图修复师。",
            "canon_start": "表达方式：使用简短、克制的句子。",
        },
    }
    assert json.loads(relationship_body["messages"][1]["content"]) == {
        "current_user_message": "谢谢你刚才认真听完了。",
        "stance_summary": "尚无立场互动记录。",
        "runtime_identity": {
            "subject_name": "Mira",
            "subject_identity": "Mira 是一名谨慎的地图修复师。",
            "canon_start": "表达方式：使用简短、克制的句子。",
        },
    }


def test_participant_goal_reply_adds_identity_without_changing_classification() -> None:
    from dynamic_subject_agent.deepseek import DeepSeekParticipantGoalProvider
    from dynamic_subject_agent.participant_goal_cognition import (
        ParticipantGoalReplyRecord,
        ParticipantGoalReplyRequest,
    )

    identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )
    body = json.loads(
        DeepSeekParticipantGoalProvider.reply_outbound_bytes(
            ParticipantGoalReplyRequest(
                "我的目标是什么？",
                (ParticipantGoalReplyRecord("goal", "通过 N1", "active"),),
                identity,
            )
        ).decode("utf-8")
    )
    assert "不得复制、引用或反复当作口头禅" in body["messages"][0]["content"]

    assert json.loads(body["messages"][1]["content"]) == {
        "current_user_message": "我的目标是什么？",
        "selected_records": [
            {"kind": "goal", "terms": "通过 N1", "status": "active"}
        ],
        "runtime_identity": {
            "subject_name": "Mira",
            "subject_identity": "Mira 是一名谨慎的地图修复师。",
            "canon_start": "表达方式：使用简短、克制的句子。",
        },
    }


def test_situated_reply_adds_identity_without_changing_classification() -> None:
    from dynamic_subject_agent.deepseek import DeepSeekSituatedProvider
    from dynamic_subject_agent.situated_cognition import SituatedReplyRequest

    identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )
    body = json.loads(
        DeepSeekSituatedProvider.reply_outbound_bytes(
            SituatedReplyRequest("我现在有点乱。", "gentle", identity)
        ).decode("utf-8")
    )
    assert "canon_start 只是不可续写的故事起点" in body["messages"][0]["content"]

    assert json.loads(body["messages"][1]["content"]) == {
        "current_user_message": "我现在有点乱。",
        "selected_state": {"posture": "gentle"},
        "runtime_identity": {
            "subject_name": "Mira",
            "subject_identity": "Mira 是一名谨慎的地图修复师。",
            "canon_start": "表达方式：使用简短、克制的句子。",
        },
    }


def test_medium_reply_adds_identity_without_changing_classification() -> None:
    from dynamic_subject_agent.deepseek import DeepSeekMediumProvider
    from dynamic_subject_agent.medium_cognition import MediumReplyRequest

    identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )
    body = json.loads(
        DeepSeekMediumProvider.reply_outbound_bytes(
            MediumReplyRequest("继续。", "concerned", identity)
        ).decode("utf-8")
    )
    assert "canon_start 只是不可续写的故事起点" in body["messages"][0]["content"]

    assert json.loads(body["messages"][1]["content"]) == {
        "current_user_message": "继续。",
        "selected_state": {"baseline": "concerned"},
        "runtime_identity": {
            "subject_name": "Mira",
            "subject_identity": "Mira 是一名谨慎的地图修复师。",
            "canon_start": "表达方式：使用简短、克制的句子。",
        },
    }


def test_identity_projection_removes_only_invented_current_activity_sentences() -> None:
    from dynamic_subject_agent.runtime_identity_reply import (
        guard_runtime_identity_reply,
    )

    identity = RuntimeIdentityProjection(
        "Avery",
        "Avery 是社区刊物编辑。",
        "此身份尚无运行时经历。",
    )

    assert guard_runtime_identity_reply(
        "忙完一天确实该放松。想聊点什么？我正好也歇口气。"
    ) == "忙完一天确实该放松。想聊点什么？"
    assert guard_runtime_identity_reply(
        "忙完了就好。今天有人送来稿子，我还没核对完。你想聊什么？"
    ) == "忙完了就好。你想聊什么？"
    assert guard_runtime_identity_reply("我正在整理今天收到的稿件。") is None


def test_split_reply_failure_preserves_grounded_candidate_and_base_reply(tmp_path) -> None:
    from uuid import uuid4

    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.relationship import ControlledRelationshipCognition
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        relationship_mode="dynamic",
        _runtime_identity=RuntimeIdentityProjection(
            "Mira",
            "Mira 是一名谨慎的地图修复师。",
            "表达方式：使用简短、克制的句子。",
        ),
        _cognition=ControlledRelationshipCognition(
            provider=_SplitRelationshipProvider(fail_reply=True),
        ),
    )
    try:
        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance="谢谢你刚才认真听完了。",
            language="zh",
            provenance="project-original",
        )
        submitted = composition.application.submit(
            command,
            idempotency_key="runtime-identity-reply-failure-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert terminal.status.value == "terminal"
    assert terminal.projection is not None
    assert terminal.projection.relationship_status == "accepted"
    assert terminal.projection.expression_text == "基础关系回复。"


def test_memory_and_knowledge_identity_reply_failure_preserves_canonical_state(
    tmp_path,
) -> None:
    from uuid import uuid4

    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        LivingMemoryApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
    from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )

    memory_studio, memory_qri = _publish_qri(tmp_path / "memory-fallback")
    memory_timeline = str(uuid4())
    memory_app = compose_application(
        m0_root=tmp_path / "memory-fallback",
        studio_location=memory_studio,
        qualified_runtime_input=memory_qri,
        timeline_id=memory_timeline,
        _runtime_identity=identity,
        _cognition=ControlledLivingMemoryCognition(
            provider=_SplitMemoryProvider(fail_reply=True),
        ),
    )
    try:
        command = SubjectCommand.contribute_utterance(
            target_profile_id=memory_qri.profile_id,
            target_timeline_id=memory_timeline,
            declared_intent="ask-collaborator-status",
            utterance="我每周三晚上学习。",
            language="zh",
            provenance="project-original",
        )
        submitted = memory_app.application.submit(
            command,
            idempotency_key="identity-memory-fallback-0001",
        )
        memory_terminal = memory_app.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        memory_query = memory_app.application.query(
            ApplicationQuery(
                ApplicationQueryKind.LIVING_MEMORY,
                memory_qri.profile_id,
                memory_timeline,
            )
        )
        assert isinstance(
            memory_query.projection,
            LivingMemoryApplicationProjection,
        )
        memories = memory_query.projection.memories
    finally:
        memory_app.close()

    entry = KnowledgeEntry(
        "a1f4c2d8-0001-4a61-9e1f-3b5c7d9e0a01",
        "截单时间",
        "社区刊物每周五 17:00 截单。",
        "project-original:test",
    )
    knowledge_studio, knowledge_qri = _publish_qri(tmp_path / "knowledge-fallback")
    knowledge_timeline = str(uuid4())
    knowledge_app = compose_application(
        m0_root=tmp_path / "knowledge-fallback",
        studio_location=knowledge_studio,
        qualified_runtime_input=knowledge_qri,
        timeline_id=knowledge_timeline,
        _runtime_identity=identity,
        _cognition=ControlledKnowledgeCognition(
            provider=_SplitKnowledgeProvider(entry.entry_id, fail_reply=True),
            entries=(entry,),
        ),
    )
    try:
        command = SubjectCommand.contribute_utterance(
            target_profile_id=knowledge_qri.profile_id,
            target_timeline_id=knowledge_timeline,
            declared_intent="ask-collaborator-status",
            utterance="社区刊物什么时候截单？",
            language="zh",
            provenance="project-original",
        )
        submitted = knowledge_app.application.submit(
            command,
            idempotency_key="identity-knowledge-fallback-0001",
        )
        knowledge_terminal = knowledge_app.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        knowledge_app.close()

    assert memory_terminal.projection is not None
    assert memory_terminal.projection.living_memory_status == "accepted"
    assert memory_terminal.projection.expression_text == "基础记忆回复。"
    assert memories[0].content == "我每周三晚上学习"
    assert knowledge_terminal.projection is not None
    assert knowledge_terminal.projection.knowledge_status == "accepted"
    assert knowledge_terminal.projection.expression_text == "基础知识回复。"


def test_runtime_forwards_identity_to_goal_situated_and_medium_reply_seams(
    tmp_path,
) -> None:
    from dynamic_subject_agent.participant_goal_cognition import (
        ParticipantGoalClassificationResult,
    )
    from test_medium_integration import (
        _MediumProvider,
        _composition as medium_composition,
        _submit as medium_submit,
    )
    from test_participant_goal_integration import (
        _ScriptedParticipantGoalProvider,
        _composition as goal_composition,
        _submit as goal_submit,
    )
    from test_situated_integration import (
        _SituatedProvider,
        _composition as situated_composition,
        _submit as situated_submit,
    )

    class _SelectingGoalProvider(_ScriptedParticipantGoalProvider):
        def classify(self, request):
            if request.current_user_message == "关于目标，你怎么看？":
                self.classification_requests.append(request)
                return ParticipantGoalClassificationResult(
                    candidate=None,
                    selected_turn_refs=(request.active_records[0].turn_ref,),
                    experience_summary="选中目标用于回复。",
                    language="zh",
                )
            return super().classify(request)

    identity = RuntimeIdentityProjection(
        "Mira",
        "Mira 是一名谨慎的地图修复师。",
        "表达方式：使用简短、克制的句子。",
    )

    goal_provider = _SelectingGoalProvider()
    _, goal_qri, goal_timeline, goal_app = goal_composition(
        tmp_path / "goal",
        goal_provider,
        runtime_identity=identity,
    )
    try:
        goal_submit(goal_app, goal_qri, goal_timeline, "我的目标是今年通过 N1。")
        goal_submit(goal_app, goal_qri, goal_timeline, "关于目标，你怎么看？")
    finally:
        goal_app.close()

    situated_provider = _SituatedProvider()
    _, situated_qri, situated_timeline, situated_app = situated_composition(
        tmp_path / "situated",
        situated_provider,
        runtime_identity=identity,
    )
    try:
        situated_submit(
            situated_app,
            situated_qri,
            situated_timeline,
            "我现在有点紧张，希望你说慢一点。",
        )
    finally:
        situated_app.close()

    medium_provider = _MediumProvider()
    _, medium_qri, medium_timeline, medium_app = medium_composition(
        tmp_path / "medium",
        medium_provider,
        runtime_identity=identity,
    )
    try:
        medium_submit(
            medium_app,
            medium_qri,
            medium_timeline,
            "最近压力很大。",
        )
    finally:
        medium_app.close()

    assert goal_provider.reply_requests[-1].runtime_identity == identity
    assert situated_provider.replies[-1].runtime_identity == identity
    assert medium_provider.replies[-1].runtime_identity == identity

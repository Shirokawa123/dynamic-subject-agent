from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID
from dynamic_subject_agent.runtime import CognitionEngine


def _us(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(
        datetime(
            year,
            month,
            day,
            hour,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ).timestamp()
        * 1_000_000
    )


def _utc_us(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
) -> int:
    return int(
        datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            tzinfo=UTC,
        ).timestamp()
        * 1_000_000
    )


class _CountingMemoryProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self) -> None:
        self.calls = []

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.calls.append(request)
        return LivingMemoryProviderResult(
            LivingMemoryProposal(LivingMemoryAction.NONE, ""),
            "无记忆变化。",
            "普通 Provider 回复。",
            "zh",
        )


class _CountingKnowledgeProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self) -> None:
        self.calls = []

    def analyze(self, request):
        from dynamic_subject_agent.knowledge import (
            KnowledgeProposal,
            KnowledgeProviderResult,
        )

        self.calls.append(request)
        return KnowledgeProviderResult(
            KnowledgeProposal(()),
            "无知识引用。",
            "普通 Knowledge 回复。",
            "zh",
        )


class _CountingRelationshipProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self) -> None:
        self.calls = []

    def analyze(self, request):
        from dynamic_subject_agent.relationship import (
            RelationshipProposal,
            RelationshipProviderResult,
        )

        self.calls.append(request)
        return RelationshipProviderResult(
            RelationshipProposal("no_persistent_evidence", ""),
            "无关系变化。",
            "普通 Relationship 回复。",
            "zh",
        )


class _FailingDeepSeekCognition(CognitionEngine):
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False
    experimental = True

    def preflight(self, *, context, command) -> None:
        del context, command

    def reserved_operation_id(self, *, context, command):
        del context, command
        return None

    def propose(self, **kwargs):
        from dynamic_subject_agent.runtime import CognitionFailedClosed

        del kwargs
        raise CognitionFailedClosed(
            "cognition",
            "forced-pre-publication-failure",
            "test-only failure before Publication",
        )


def _composition(tmp_path: Path):
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.host import RuntimeHost
    from test_deepseek_controlled_route import _publish_deepseek_qri
    from test_medium_integration import _MediumProvider, _gateway as medium_gateway
    from test_participant_goal_integration import (
        _ScriptedParticipantGoalProvider,
        _goal_gateway,
    )
    from test_situated_integration import (
        _SituatedProvider,
        _gateway as situated_gateway,
    )

    memory = _CountingMemoryProvider()
    knowledge = _CountingKnowledgeProvider()
    relationship = _CountingRelationshipProvider()
    participant_goal = _ScriptedParticipantGoalProvider()
    situated = _SituatedProvider()
    medium = _MediumProvider()
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
            memory_provider=memory,
            knowledge_provider=knowledge,
            relationship_provider=relationship,
            participant_goal_gateway=_goal_gateway(participant_goal),
            situated_gateway=situated_gateway(situated),
            medium_gateway=medium_gateway(medium),
        ),
        relationship_mode="dynamic",
    )
    return prepared, qri, timeline_id, composition, (
        memory,
        knowledge,
        relationship,
        participant_goal,
        situated,
        medium,
    )


def _provider_call_counts(providers) -> tuple[int, ...]:
    memory, knowledge, relationship, goal, situated, medium = providers
    return (
        len(memory.calls),
        len(knowledge.calls),
        len(relationship.calls),
        len(goal.classification_requests) + len(goal.reply_requests),
        len(situated.classifications) + len(situated.replies),
        len(medium.calls) + len(medium.replies),
    )


def _submit(composition, qri, timeline_id: str, text: str, key: str):
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
    return composition.application.wait(submitted.operation_ref, timeout_seconds=5)


def _submit_product(product, text: str, key: str):
    from dynamic_subject_agent.timeline import SubjectCommand

    command = SubjectCommand.contribute_utterance(
        target_profile_id=product.profile_id,
        target_timeline_id=product.timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=text,
        language="zh",
        provenance="project-original",
    )
    submitted = product.application.submit(command, idempotency_key=key)
    return product.application.wait(submitted.operation_ref, timeout_seconds=5)


def test_first_subject_time_query_is_local_and_has_no_earlier_committed_turn(
    tmp_path: Path,
) -> None:
    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            "我们上次什么时候聊的？",
            "subject-time-first-query-0001",
        )
    finally:
        composition.close()

    assert terminal.status.value == "terminal"
    assert terminal.projection is not None
    assert terminal.projection.expression_text == (
        "在这条身份时间线上，还没有更早的已提交对话。"
    )
    assert _provider_call_counts(providers) == (0, 0, 0, 0, 0, 0)


def test_subject_time_reports_yesterday_without_additional_provider_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module

    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 4),
        )
        first = _submit(
            composition,
            qri,
            timeline_id,
            "今天记录一轮普通对话。",
            "subject-time-yesterday-base-0001",
        )
        assert first.status.value == "terminal"
        calls_after_first = _provider_call_counts(providers)

        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 5),
        )
        query = _submit(
            composition,
            qri,
            timeline_id,
            "我们多久没聊了？",
            "subject-time-yesterday-query-0001",
        )
    finally:
        composition.close()

    assert query.status.value == "terminal", (query.problem, query.projection)
    assert query.projection is not None
    assert query.projection.expression_text == "我们上次聊天是昨天。"
    assert _provider_call_counts(providers) == calls_after_first


def test_committed_time_query_becomes_last_turn_after_restart(tmp_path: Path) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition

    prepared, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        first = _submit(
            composition,
            qri,
            timeline_id,
            "我们上次是什么时候聊的？",
            "subject-time-restart-first-0001",
        )
        assert first.projection is not None
        assert first.projection.expression_text == (
            "在这条身份时间线上，还没有更早的已提交对话。"
        )
        host_location = composition.host_location
    finally:
        composition.close()

    memory = _CountingMemoryProvider()
    knowledge = _CountingKnowledgeProvider()
    relationship = _CountingRelationshipProvider()
    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledCompositeCognition(
            memory_provider=memory,
            knowledge_provider=knowledge,
            relationship_provider=relationship,
        ),
        relationship_mode="dynamic",
    )
    try:
        second = _submit(
            restarted,
            qri,
            timeline_id,
            "我们多久没聊了？",
            "subject-time-restart-second-0001",
        )
    finally:
        restarted.close()

    assert second.status.value == "terminal"
    assert second.projection is not None
    assert second.projection.expression_text == "我们上次聊天是今天。"
    assert _provider_call_counts(providers) == (0, 0, 0, 0, 0, 0)
    assert [len(memory.calls), len(knowledge.calls), len(relationship.calls)] == [
        0,
        0,
        0,
    ]


@pytest.mark.parametrize(
    ("last_date", "expected"),
    [
        ((2026, 9, 5), "我们上次聊天是今天。"),
        ((2026, 9, 3), "我们上次聊天是前天。"),
        ((2026, 9, 1), "我们上次聊天是4 天前。"),
        (
            (2026, 8, 20),
            "我们上次聊天是2026年8月20日（距今 16 天）。",
        ),
    ],
)
def test_subject_time_day_precision_rendering_through_application(
    tmp_path: Path,
    monkeypatch,
    last_date: tuple[int, int, int],
    expected: str,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module

    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(*last_date),
        )
        first = _submit(
            composition,
            qri,
            timeline_id,
            "先完成一轮普通对话。",
            f"subject-time-render-base-{last_date[1]:02d}{last_date[2]:02d}",
        )
        assert first.status.value == "terminal"
        calls_after_first = _provider_call_counts(providers)
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 5),
        )
        query = _submit(
            composition,
            qri,
            timeline_id,
            "距离我们上次聊天多久了？",
            f"subject-time-render-query-{last_date[1]:02d}{last_date[2]:02d}",
        )
    finally:
        composition.close()

    assert query.status.value == "terminal"
    assert query.projection is not None
    assert query.projection.expression_text == expected
    assert _provider_call_counts(providers) == calls_after_first


@pytest.mark.parametrize(
    "message",
    [
        "你还记得我们上次聊了什么吗？",
        "我们上次什么时候聊的？顺便提醒我明天学习。",
    ],
)
def test_near_or_compound_time_language_keeps_existing_provider_route(
    tmp_path: Path,
    message: str,
) -> None:
    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            message,
            f"subject-time-nonmatch-{uuid4().hex}",
        )
    finally:
        composition.close()

    assert terminal.status.value == "terminal"
    assert terminal.projection is not None
    assert terminal.projection.expression_text == "普通 Provider 回复。"
    counts = _provider_call_counts(providers)
    assert counts[0] == 1
    assert sum(counts) >= 1


def test_subject_time_clock_regression_fails_closed_before_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module

    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 5),
        )
        first = _submit(
            composition,
            qri,
            timeline_id,
            "先完成一轮普通对话。",
            "subject-time-regression-base-0001",
        )
        assert first.status.value == "terminal"
        calls_after_first = _provider_call_counts(providers)
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 4),
        )
        query = _submit(
            composition,
            qri,
            timeline_id,
            "我们上次什么时候聊的？",
            "subject-time-regression-query-0001",
        )
    finally:
        composition.close()

    assert query.status.value == "failed-closed"
    assert query.projection is not None
    assert query.projection.expression_text is None
    assert query.projection.failure_stage == "subject-time"
    assert _provider_call_counts(providers) == calls_after_first


def test_interaction_recency_is_isolated_between_local_identities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    from dynamic_subject_agent.local_product import open_local_product
    from dynamic_subject_agent.source_character_authoring import (
        LocalIdentitySelectRequest,
        SourceDraftCommand,
        SourceFreezeMappingRequest,
        SourceIdentityFreezeRequest,
    )
    from test_source_identity_freeze import _config, _save_request

    def cognition_and_providers():
        memory = _CountingMemoryProvider()
        knowledge = _CountingKnowledgeProvider()
        relationship = _CountingRelationshipProvider()
        return (
            ControlledCompositeCognition(
                memory_provider=memory,
                knowledge_provider=knowledge,
                relationship_provider=relationship,
            ),
            (memory, knowledge, relationship),
        )

    config = _config(tmp_path)
    seed = open_local_product(config, cognition=DormantDeepSeekCognition())
    legacy_id = seed.profile_id
    try:
        seed.application.source_draft(SourceDraftCommand.save(_save_request()))
        mapping = seed.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        frozen = seed.application.freeze_source_identity(
            SourceIdentityFreezeRequest(
                1,
                "Avery",
                mapping.view.freeze_basis_digest,
                True,
            )
        )
        assert frozen.view is not None
        source_id = frozen.view.identity_id
        selected = seed.application.select_local_identity(
            LocalIdentitySelectRequest(source_id, True)
        )
        assert selected.identity is not None
    finally:
        seed.close()

    source_cognition, _ = cognition_and_providers()
    source_product = open_local_product(config, cognition=source_cognition)
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 1),
        )
        source_first = _submit_product(
            source_product,
            "来源身份完成一轮普通对话。",
            "subject-time-source-base-0001",
        )
        assert source_first.status.value == "terminal"
    finally:
        source_product.close()

    authority = LocalIdentityAuthority(config)
    source_loaded = authority.load_active()
    switched = authority.select(
        LocalIdentitySelectRequest(legacy_id, True),
        current=source_loaded,
    )
    assert switched.identity is not None

    legacy_cognition, legacy_providers = cognition_and_providers()
    legacy_product = open_local_product(config, cognition=legacy_cognition)
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 5),
        )
        legacy_query = _submit_product(
            legacy_product,
            "我们上次什么时候聊的？",
            "subject-time-legacy-query-0001",
        )
    finally:
        legacy_product.close()

    legacy_loaded = authority.load_active()
    switched = authority.select(
        LocalIdentitySelectRequest(source_id, True),
        current=legacy_loaded,
    )
    assert switched.identity is not None
    source_cognition, source_query_providers = cognition_and_providers()
    source_product = open_local_product(config, cognition=source_cognition)
    try:
        source_query = _submit_product(
            source_product,
            "我们上次什么时候聊的？",
            "subject-time-source-query-0001",
        )
    finally:
        source_product.close()

    assert legacy_query.projection is not None
    assert legacy_query.projection.expression_text == (
        "在这条身份时间线上，还没有更早的已提交对话。"
    )
    assert source_query.projection is not None
    assert source_query.projection.expression_text == "我们上次聊天是4 天前。"
    assert [len(provider.calls) for provider in legacy_providers] == [0, 0, 0]
    assert [len(provider.calls) for provider in source_query_providers] == [0, 0, 0]


def test_subject_time_history_integrity_failure_is_terminal_failed_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module

    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    monkeypatch.setattr(
        timeline_module,
        "_utc_microseconds",
        lambda: _us(2026, 9, 1),
    )
    first = _submit(
        composition,
        qri,
        timeline_id,
        "先完成一轮普通对话。",
        "subject-time-integrity-base-0001",
    )
    assert first.status.value == "terminal"
    calls_after_first = _provider_call_counts(providers)
    database = next(composition.host_location.root.rglob("timeline.sqlite3"))
    connection = sqlite3.connect(database, autocommit=True)
    try:
        connection.execute(
            "UPDATE expression_record SET expression_text = 'tampered history'"
        )
    finally:
        connection.close()
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 2),
        )
        query = _submit(
            composition,
            qri,
            timeline_id,
            "我们上次什么时候聊的？",
            "subject-time-integrity-query-0001",
        )
    finally:
        composition.close()

    assert query.status.value == "failed-closed"
    assert query.projection is not None
    assert query.projection.failure_stage == "subject-time"
    assert _provider_call_counts(providers) == calls_after_first


def test_subject_time_typed_interface_is_lazy_and_rejects_extreme_clock() -> None:
    from dynamic_subject_agent.subject_time_continuity import (
        SubjectTimeContinuity,
        SubjectTimeResult,
        SubjectTimeStatus,
    )

    module = SubjectTimeContinuity()
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return None

    no_op = module.evaluate(
        query_text="你还记得上次聊了什么吗？",
        current_admitted_at_us=_us(2026, 9, 5),
        load_last_committed_at_us=loader,
    )
    extreme = module.evaluate(
        query_text="我们多久没聊了？",
        current_admitted_at_us=10**40,
        load_last_committed_at_us=loader,
    )

    assert no_op.status is SubjectTimeStatus.NO_OP
    assert calls == 0
    assert extreme.status is SubjectTimeStatus.FAILED_CLOSED
    assert extreme.problem_code == "subject-time-civil-time-invalid"
    with pytest.raises(ValueError):
        SubjectTimeResult(SubjectTimeStatus.ANSWER)


def test_subject_time_uses_shanghai_midnight_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module

    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _utc_us(2026, 9, 1, 15, 59, 59),
        )
        first = _submit(
            composition,
            qri,
            timeline_id,
            "午夜前完成一轮普通对话。",
            "subject-time-midnight-base-0001",
        )
        assert first.status.value == "terminal"
        calls_after_first = _provider_call_counts(providers)
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _utc_us(2026, 9, 1, 16, 0, 0),
        )
        query = _submit(
            composition,
            qri,
            timeline_id,
            "我们多久没聊了？",
            "subject-time-midnight-query-0001",
        )
    finally:
        composition.close()

    assert query.projection is not None
    assert query.projection.expression_text == "我们上次聊天是昨天。"
    assert _provider_call_counts(providers) == calls_after_first


def test_subject_time_uses_canonical_last_turn_beyond_ui_twenty_turn_window(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        ConversationHistoryApplicationProjection,
    )

    _, qri, timeline_id, composition, providers = _composition(tmp_path)
    try:
        for ordinal in range(1, 22):
            day = 4 if ordinal == 21 else 1
            monkeypatch.setattr(
                timeline_module,
                "_utc_microseconds",
                lambda day=day: _us(2026, 9, day),
            )
            terminal = _submit(
                composition,
                qri,
                timeline_id,
                f"普通对话第 {ordinal} 轮。",
                f"subject-time-window-{ordinal:04d}",
            )
            assert terminal.status.value == "terminal"
        history = composition.application.query(
            ApplicationQuery(
                ApplicationQueryKind.CONVERSATION_HISTORY,
                qri.profile_id,
                timeline_id,
            )
        )
        assert isinstance(
            history.projection,
            ConversationHistoryApplicationProjection,
        )
        assert len(history.projection.turns) == 20
        calls_after_history = _provider_call_counts(providers)
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 5),
        )
        query = _submit(
            composition,
            qri,
            timeline_id,
            "我们多久没聊了？",
            "subject-time-window-query-0001",
        )
    finally:
        composition.close()

    assert query.projection is not None
    assert query.projection.expression_text == "我们上次聊天是昨天。"
    assert _provider_call_counts(providers) == calls_after_history


def test_nonmatch_provider_outbound_matches_authorized_baselines() -> None:
    from dynamic_subject_agent.deepseek import (
        DeepSeekKnowledgeProvider,
        DeepSeekLivingMemoryProvider,
        DeepSeekMediumProvider,
        DeepSeekParticipantGoalProvider,
        DeepSeekRelationshipProvider,
        DeepSeekSituatedProvider,
    )
    from dynamic_subject_agent.knowledge import KnowledgeProviderRequest
    from dynamic_subject_agent.knowledge import KnowledgeReplyEntry, KnowledgeReplyRequest
    from dynamic_subject_agent.living_memory import (
        LivingMemoryProviderRequest,
        LivingMemoryReplyMemory,
        LivingMemoryReplyRequest,
    )
    from dynamic_subject_agent.medium_cognition import (
        MediumClassificationRequest,
        MediumReplyRequest,
    )
    from dynamic_subject_agent.participant_goal_cognition import (
        ParticipantGoalClassificationRequest,
        ParticipantGoalReplyRecord,
        ParticipantGoalReplyRequest,
    )
    from dynamic_subject_agent.relationship import (
        RelationshipProviderRequest,
        RelationshipReplyRequest,
    )
    from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
    from dynamic_subject_agent.situated_cognition import (
        SituatedClassificationRequest,
        SituatedReplyRequest,
    )

    message = "你还记得我们上次聊了什么吗？"
    identity = RuntimeIdentityProjection(
        "Avery",
        "Avery 是社区刊物编辑。",
        "此身份尚无运行时经历。",
    )
    outbound = {
        "living": DeepSeekLivingMemoryProvider.outbound_bytes(
            LivingMemoryProviderRequest(message, ())
        ),
        "knowledge": DeepSeekKnowledgeProvider.outbound_bytes(
            KnowledgeProviderRequest(message, ())
        ),
        "relationship": DeepSeekRelationshipProvider.outbound_bytes(
            RelationshipProviderRequest(message, "尚无立场互动记录。")
        ),
        "goal": DeepSeekParticipantGoalProvider.classification_outbound_bytes(
            ParticipantGoalClassificationRequest(message, ())
        ),
        "situated": DeepSeekSituatedProvider.classification_outbound_bytes(
            SituatedClassificationRequest(message, ())
        ),
        "medium": DeepSeekMediumProvider.classification_outbound_bytes(
            MediumClassificationRequest(message)
        ),
        "living-reply": DeepSeekLivingMemoryProvider.reply_outbound_bytes(
            LivingMemoryReplyRequest(
                message,
                (LivingMemoryReplyMemory("我每周三学习"),),
                identity,
            )
        ),
        "knowledge-reply": DeepSeekKnowledgeProvider.reply_outbound_bytes(
            KnowledgeReplyRequest(
                message,
                (KnowledgeReplyEntry("标题", "封存内容。"),),
                identity,
            )
        ),
        "relationship-reply": DeepSeekRelationshipProvider.reply_outbound_bytes(
            RelationshipReplyRequest(message, "尚无立场互动记录。", identity)
        ),
        "goal-reply": DeepSeekParticipantGoalProvider.reply_outbound_bytes(
            ParticipantGoalReplyRequest(
                message,
                (ParticipantGoalReplyRecord("goal", "通过 N1", "active"),),
                identity,
            )
        ),
        "situated-reply": DeepSeekSituatedProvider.reply_outbound_bytes(
            SituatedReplyRequest(message, "gentle", identity)
        ),
        "medium-reply": DeepSeekMediumProvider.reply_outbound_bytes(
            MediumReplyRequest(message, "settled", identity)
        ),
    }
    expected = {
        "living": "77989ff3c6b6aacd6c50564a203db11017768f896f085662b874226132b945f1",
        "knowledge": "bde02f404c978ff8970f7c1967efa472473f691e846d5840197b876c067574e2",
        "relationship": "0019aec13f38ca89874e1c0f188f8ff531e5f27ef00a7c2fbe41f02552dcad84",
        "goal": "4c037a29bb43a5f5c0fc3e70813b5f27704ad4dac6333730dfc6c394c8b6b44c",
        "situated": "04f167a465671bd452a8dbd4593dc98b7db0f6c3082e4a0455f5da5314e6803e",
        "medium": "5d3bcb4c0dcb73396bd2c49744ee7424da9b691c26c461d242511e1a71af25fa",
        # Slice-32 separates write receipts from LM continuation; other 11 hashes remain.
        "living-reply": "995182a1b91e6ef6557af0f51b8c9559aff04651d46fd6710f77c161980af73f",
        "knowledge-reply": "85cd4778e1b18b432e02d7cd59f68e238fb7fc95c9c56ed31f1e8381f40950a1",
        "relationship-reply": "30e65c081d2bbc2c6c0096381577366a983d7cceb6597cd3f3d9537465be7c20",
        "goal-reply": "d544b15ca979461e93f91ee3d07409d72479e1f25174db1eec2edfb751123d62",
        "situated-reply": "b329332347fc77f1a90b24e29fed529629478d7fb849043b2651362974304826",
        "medium-reply": "18df22292cc427404a3120100be7b74db758d47ad90bfeb5a0b9e71f34953d20",
    }

    assert {name: sha256(body).hexdigest() for name, body in outbound.items()} == (
        expected
    )


@pytest.mark.parametrize("non_committed", ["failed-closed", "interrupted"])
def test_non_committed_operation_does_not_replace_last_committed_turn(
    tmp_path: Path,
    monkeypatch,
    non_committed: str,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import RuntimeFaultPoint

    prepared, qri, timeline_id, composition, _ = _composition(tmp_path)
    monkeypatch.setattr(
        timeline_module,
        "_utc_microseconds",
        lambda: _us(2026, 9, 1),
    )
    base = _submit(
        composition,
        qri,
        timeline_id,
        "先完成一轮普通对话。",
        f"subject-time-{non_committed}-base-0001",
    )
    assert base.status.value == "terminal"
    host_location = composition.host_location
    composition.close()

    monkeypatch.setattr(
        timeline_module,
        "_utc_microseconds",
        lambda: _us(2026, 9, 4),
    )
    if non_committed == "failed-closed":
        interrupted_or_failed = compose_application(
            m0_root=prepared.experiment_base,
            studio_location=prepared.location,
            qualified_runtime_input=qri,
            timeline_id=timeline_id,
            host_location=host_location,
            _cognition=_FailingDeepSeekCognition(),
            relationship_mode="dynamic",
        )
    else:
        memory = _CountingMemoryProvider()
        knowledge = _CountingKnowledgeProvider()
        relationship = _CountingRelationshipProvider()
        interrupted_or_failed = compose_application(
            m0_root=prepared.experiment_base,
            studio_location=prepared.location,
            qualified_runtime_input=qri,
            timeline_id=timeline_id,
            host_location=host_location,
            _cognition=ControlledCompositeCognition(
                memory_provider=memory,
                knowledge_provider=knowledge,
                relationship_provider=relationship,
            ),
            relationship_mode="dynamic",
            _runtime_interrupt_at=RuntimeFaultPoint.AFTER_COGNITION,
        )
    try:
        failed = _submit(
            interrupted_or_failed,
            qri,
            timeline_id,
            "这一轮不应成为 committed history。",
            f"subject-time-{non_committed}-operation-0001",
        )
        assert failed.status.value in {"failed-closed", "interrupted"}
    finally:
        interrupted_or_failed.close()

    memory = _CountingMemoryProvider()
    knowledge = _CountingKnowledgeProvider()
    relationship = _CountingRelationshipProvider()
    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledCompositeCognition(
            memory_provider=memory,
            knowledge_provider=knowledge,
            relationship_provider=relationship,
        ),
        relationship_mode="dynamic",
    )
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 5),
        )
        query = _submit(
            restarted,
            qri,
            timeline_id,
            "我们多久没聊了？",
            f"subject-time-{non_committed}-query-0001",
        )
    finally:
        restarted.close()

    assert query.projection is not None
    assert query.projection.expression_text == "我们上次聊天是4 天前。"
    assert [len(memory.calls), len(knowledge.calls), len(relationship.calls)] == [
        0,
        0,
        0,
    ]


def test_pending_admission_does_not_replace_last_committed_turn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.timeline as timeline_module
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.host import RuntimeHost
    from dynamic_subject_agent.timeline import OperationState, SubjectCommand

    prepared, qri, timeline_id, composition, _ = _composition(tmp_path)
    monkeypatch.setattr(
        timeline_module,
        "_utc_microseconds",
        lambda: _us(2026, 9, 1),
    )
    base = _submit(
        composition,
        qri,
        timeline_id,
        "先完成一轮普通对话。",
        "subject-time-pending-base-0001",
    )
    assert base.status.value == "terminal"
    host_location = composition.host_location
    composition.close()

    pending_host = RuntimeHost.open(
        host_location,
        studio_location=prepared.location,
        cognition=ControlledCompositeCognition(
            memory_provider=_CountingMemoryProvider(),
            knowledge_provider=_CountingKnowledgeProvider(),
            relationship_provider=_CountingRelationshipProvider(),
        ),
        relationship_enabled=True,
    )
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 4),
        )
        with pending_host.lease(
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
        ) as lease:
            admitted = lease.admit(
                SubjectCommand.contribute_utterance(
                    target_profile_id=qri.profile_id,
                    target_timeline_id=timeline_id,
                    declared_intent="ask-collaborator-status",
                    utterance="这轮只 Admission，不完成 Publication。",
                    language="zh",
                    provenance="project-original",
                ),
                idempotency_key="subject-time-pending-operation-0001",
            )
            assert admitted.snapshot.operation_state is OperationState.ADMITTED_PENDING
    finally:
        pending_host.close()

    memory = _CountingMemoryProvider()
    knowledge = _CountingKnowledgeProvider()
    relationship = _CountingRelationshipProvider()
    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledCompositeCognition(
            memory_provider=memory,
            knowledge_provider=knowledge,
            relationship_provider=relationship,
        ),
        relationship_mode="dynamic",
    )
    try:
        monkeypatch.setattr(
            timeline_module,
            "_utc_microseconds",
            lambda: _us(2026, 9, 5),
        )
        query = _submit(
            restarted,
            qri,
            timeline_id,
            "我们多久没聊了？",
            "subject-time-pending-query-0001",
        )
    finally:
        restarted.close()

    assert query.projection is not None
    assert query.projection.expression_text == "我们上次聊天是4 天前。"
    assert [len(memory.calls), len(knowledge.calls), len(relationship.calls)] == [
        0,
        0,
        0,
    ]

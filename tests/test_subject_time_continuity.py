from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID


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
    assert counts[2] == 1
    assert sum(counts) >= 2


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

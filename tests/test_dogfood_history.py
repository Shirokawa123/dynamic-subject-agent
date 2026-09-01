from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace

import pytest

from dynamic_subject_agent.application import (
    ApplicationQuery,
    ApplicationQueryKind,
    ApplicationQueryStatus,
    ConversationHistoryApplicationProjection,
)
from dynamic_subject_agent.bootstrap import compose_application
from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID
from dynamic_subject_agent.host import RuntimeHost
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
from dynamic_subject_agent.runtime import (
    FakeCognition,
    FakeCognitionMode,
    RuntimeFaultPoint,
)
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.source_character_authoring import (
    LocalIdentitySelectRequest,
    SourceDraftCommand,
    SourceFreezeMappingRequest,
    SourceIdentityFreezeRequest,
)
from test_runtime_host_binding import _publish_qri
from test_source_identity_freeze import _save_request


class _DeepSeekAuthorityFake(FakeCognition):
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self) -> None:
        super().__init__()
        self.proposal_count = 0

    def propose(self, **kwargs):
        self.proposal_count += 1
        return super().propose(**kwargs)


def _command(profile_id: str, timeline_id: str, ordinal: int) -> SubjectCommand:
    return SubjectCommand.contribute_utterance(
        target_profile_id=profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=f"Dogfood canonical turn {ordinal:02d}.",
        language="en",
        provenance="project-original",
    )


def _history(application, profile_id: str, timeline_id: str):
    return application.query(
        ApplicationQuery(
            kind=ApplicationQueryKind.CONVERSATION_HISTORY,
            target_profile_id=profile_id,
            target_timeline_id=timeline_id,
        )
    )


def test_recent_twenty_completed_turns_restore_byte_equivalent_after_restart(
    tmp_path: Path,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=FakeCognition(),
    )
    terminal_text: dict[int, str] = {}
    for ordinal in range(1, 22):
        submitted = first.application.submit(
            _command(qri.profile_id, timeline_id, ordinal),
            idempotency_key=f"dogfood-history-{ordinal:04d}",
        )
        terminal = first.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        assert terminal.projection is not None
        assert terminal.projection.expression_text is not None
        terminal_text[ordinal] = terminal.projection.expression_text
    before = _history(first.application, qri.profile_id, timeline_id)
    host_location = first.host_location
    first.close()

    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=FakeCognition(),
    )
    try:
        after = _history(restarted.application, qri.profile_id, timeline_id)
    finally:
        restarted.close()

    assert before.status is after.status is ApplicationQueryStatus.AVAILABLE
    assert isinstance(before.projection, ConversationHistoryApplicationProjection)
    assert after.projection == before.projection
    assert [turn.head_sequence for turn in before.projection.turns] == list(
        range(2, 22)
    )
    assert [turn.user_text for turn in before.projection.turns] == [
        f"Dogfood canonical turn {ordinal:02d}." for ordinal in range(2, 22)
    ]
    assert [turn.assistant_text for turn in before.projection.turns] == [
        terminal_text[ordinal] for ordinal in range(2, 22)
    ]


def test_pending_operation_is_absent_until_atomic_outcome_commits(
    tmp_path: Path,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    host.open_runtime(qri, timeline_id=timeline_id)
    try:
        with host.lease(profile_id=qri.profile_id, timeline_id=timeline_id) as lease:
            admitted = lease.admit(
                _command(qri.profile_id, timeline_id, 1),
                idempotency_key="dogfood-pending-history-0001",
            )
            pending = lease.list_conversation_turns()
            lease.resume(admitted.operation_ref)
            completed = lease.list_conversation_turns()
    finally:
        host.close()
    assert pending == ()
    assert len(completed) == 1


def test_failed_closed_and_interrupted_operations_are_not_completed_history(
    tmp_path: Path,
) -> None:
    failed_root = tmp_path / "failed"
    failed_root.mkdir()
    studio_location, qri = _publish_qri(failed_root)
    failed_timeline = str(uuid4())
    failed_composition = compose_application(
        m0_root=failed_root,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=failed_timeline,
        _cognition=FakeCognition(mode=FakeCognitionMode.EPISTEMIC_FAILURE),
    )
    submitted = failed_composition.application.submit(
        _command(qri.profile_id, failed_timeline, 1),
        idempotency_key="dogfood-failed-history-0001",
    )
    failed_composition.application.wait(submitted.operation_ref, timeout_seconds=5)
    failed_history = _history(
        failed_composition.application,
        qri.profile_id,
        failed_timeline,
    )
    failed_composition.close()

    interrupted_root = tmp_path / "interrupted"
    interrupted_root.mkdir()
    studio_location, qri = _publish_qri(interrupted_root)
    interrupted_timeline = str(uuid4())
    first = compose_application(
        m0_root=interrupted_root,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=interrupted_timeline,
        _runtime_interrupt_at=RuntimeFaultPoint.AFTER_COGNITION,
    )
    submitted = first.application.submit(
        _command(qri.profile_id, interrupted_timeline, 1),
        idempotency_key="dogfood-interrupted-history-0001",
    )
    first.application.wait(submitted.operation_ref, timeout_seconds=5)
    interrupted_history = _history(
        first.application,
        qri.profile_id,
        interrupted_timeline,
    )
    host_location = first.host_location
    first.close()
    restarted = compose_application(
        m0_root=interrupted_root,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=interrupted_timeline,
        host_location=host_location,
    )
    try:
        restarted.application.wait(submitted.operation_ref, timeout_seconds=5)
        resumed_history = _history(
            restarted.application,
            qri.profile_id,
            interrupted_timeline,
        )
    finally:
        restarted.close()
    assert isinstance(
        failed_history.projection,
        ConversationHistoryApplicationProjection,
    )
    assert failed_history.projection.turns == ()
    assert isinstance(
        interrupted_history.projection,
        ConversationHistoryApplicationProjection,
    )
    assert interrupted_history.projection.turns == ()
    assert isinstance(
        resumed_history.projection,
        ConversationHistoryApplicationProjection,
    )
    assert len(resumed_history.projection.turns) == 1


@pytest.mark.parametrize(
    "tamper",
    ["command", "expression", "head", "outcome-digest", "previous-digest"],
)
def test_canonical_tamper_makes_history_query_fail_closed(
    tmp_path: Path,
    tamper: str,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=FakeCognition(),
    )
    submitted = composition.application.submit(
        _command(qri.profile_id, timeline_id, 1),
        idempotency_key="dogfood-history-tamper-0001",
    )
    composition.application.wait(submitted.operation_ref, timeout_seconds=5)
    timeline_database = next(
        composition.host_location.root.rglob("timeline.sqlite3")
    )
    connection = sqlite3.connect(timeline_database, autocommit=True)
    try:
        if tamper == "command":
            connection.execute(
                "UPDATE subject_command SET utterance = 'tampered history'"
            )
        elif tamper == "expression":
            connection.execute(
                "UPDATE expression_record SET expression_text = 'tampered history'"
            )
        elif tamper == "head":
            connection.execute("UPDATE timeline_outcome SET head_sequence = 2")
        elif tamper == "outcome-digest":
            connection.execute(
                "UPDATE timeline_outcome SET outcome_digest = zeroblob(32)"
            )
        else:
            connection.execute(
                "UPDATE timeline_outcome SET previous_outcome_digest = zeroblob(32)"
            )
    finally:
        connection.close()
    try:
        response = _history(composition.application, qri.profile_id, timeline_id)
        from app.desktop.server import AppState

        snapshot = AppState(
            SimpleNamespace(
                application=composition.application,
                profile_id=qri.profile_id,
                timeline_id=timeline_id,
            )
        ).snapshot()
    finally:
        composition.close()
    assert response.status is ApplicationQueryStatus.FAILED_CLOSED
    assert response.projection is None
    assert response.problem is not None
    assert response.problem.code == "query-failed-closed"
    assert snapshot["conversation_history_status"] == "failed-closed"
    assert snapshot["conversation_history"] == []


def test_desktop_snapshot_projects_build_and_canonical_history(tmp_path: Path) -> None:
    from app.desktop.server import AppState, _turn_failure_message
    from dynamic_subject_agent.local_product import DOGFOOD_BUILD_ID

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=FakeCognition(),
    )
    submitted = composition.application.submit(
        _command(qri.profile_id, timeline_id, 1),
        idempotency_key="dogfood-desktop-history-0001",
    )
    composition.application.wait(submitted.operation_ref, timeout_seconds=5)
    product = SimpleNamespace(
        application=composition.application,
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
    )
    try:
        snapshot = AppState(product).snapshot()
    finally:
        composition.close()
    assert snapshot["build_id"] == DOGFOOD_BUILD_ID
    assert snapshot["conversation_history_status"] == "available"
    assert snapshot["conversation_history"][0]["head_sequence"] == 1
    assert snapshot["conversation_history"][0]["user_text"] == (
        "Dogfood canonical turn 01."
    )
    assert snapshot["conversation_history"][0]["assistant_text"]
    message = _turn_failure_message("cognition", "secret-provider-code")
    assert "secret-provider-code" not in message
    assert "没有形成可见提交" in message
    unknown = _turn_failure_message("unknown-stage", "contains-provider-text")
    assert "模型处理未完成" not in unknown
    assert "失败关闭" in unknown
    html = (Path(__file__).parents[1] / "app" / "desktop" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert '"连接失败: " + error' not in html
    assert "if (!await refreshState(true))" in html


def test_desktop_turn_response_carries_canonical_twenty_turn_window(
    tmp_path: Path,
) -> None:
    from app.desktop.server import AppState

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=FakeCognition(),
    )
    state = AppState(
        SimpleNamespace(
            application=composition.application,
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
        )
    )
    try:
        for ordinal in range(1, 22):
            result = state.submit_turn(f"Desktop dogfood turn {ordinal:02d}.")
            assert result["ok"]
    finally:
        composition.close()
    assert result["head_sequence"] == 21
    assert result["conversation_history_status"] == "available"
    assert len(result["conversation_history"]) == 20
    assert result["conversation_history"][0]["head_sequence"] == 2
    assert result["conversation_history"][-1]["head_sequence"] == 21


def test_two_local_identities_never_project_each_others_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "DynamicSubjectAgent"
    config = LocalProductConfig(
        product_parent=root / "m0" / "experiments",
        state_path=root / "state.json",
        relationship_mode="dynamic",
    )
    legacy_cognition = _DeepSeekAuthorityFake()
    legacy = open_local_product(config, cognition=legacy_cognition)
    legacy_profile_id = legacy.profile_id
    first = legacy.application.submit(
        _command(legacy.profile_id, legacy.timeline_id, 1),
        idempotency_key="dogfood-legacy-history-0001",
    )
    legacy.application.wait(first.operation_ref, timeout_seconds=5)
    legacy.application.source_draft(SourceDraftCommand.save(_save_request()))
    mapping = legacy.application.preview_source_freeze_mapping(
        SourceFreezeMappingRequest(1, "Avery")
    )
    assert mapping.view is not None
    frozen = legacy.application.freeze_source_identity(
        SourceIdentityFreezeRequest(
            1,
            "Avery",
            mapping.view.freeze_basis_digest,
            True,
        )
    )
    assert frozen.view is not None
    legacy.application.select_local_identity(
        LocalIdentitySelectRequest(frozen.view.identity_id, True)
    )
    legacy.close()

    source_cognition = _DeepSeekAuthorityFake()
    source = open_local_product(config, cognition=source_cognition)
    second = source.application.submit(
        _command(source.profile_id, source.timeline_id, 2),
        idempotency_key="dogfood-source-history-0001",
    )
    source.application.wait(second.operation_ref, timeout_seconds=5)
    source_history = _history(
        source.application,
        source.profile_id,
        source.timeline_id,
    )
    source.application.select_local_identity(
        LocalIdentitySelectRequest(legacy_profile_id, True)
    )
    source.close()

    restored_cognition = _DeepSeekAuthorityFake()
    restored_legacy = open_local_product(
        config,
        cognition=restored_cognition,
    )
    try:
        legacy_history = _history(
            restored_legacy.application,
            restored_legacy.profile_id,
            restored_legacy.timeline_id,
        )
    finally:
        restored_legacy.close()
    assert isinstance(
        source_history.projection,
        ConversationHistoryApplicationProjection,
    )
    assert [turn.user_text for turn in source_history.projection.turns] == [
        "Dogfood canonical turn 02."
    ]
    assert isinstance(
        legacy_history.projection,
        ConversationHistoryApplicationProjection,
    )
    assert [turn.user_text for turn in legacy_history.projection.turns] == [
        "Dogfood canonical turn 01."
    ]
    assert legacy_cognition.proposal_count == 1
    assert source_cognition.proposal_count == 1
    assert restored_cognition.proposal_count == 0

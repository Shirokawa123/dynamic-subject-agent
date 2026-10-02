from threading import Event
from time import monotonic
from uuid import uuid4
import sqlite3

import pytest

from dynamic_subject_agent.application import SubjectRequestLookupRequest
from dynamic_subject_agent.timeline import SubjectCommand, TimelineEngine, PublicationInterrupted
from test_original_whole_chat import whole_fixture, approved, personality_fixture, model_fixture, WholeTransport, send, history


def lookup(product, message, key, **changed):
    command = SubjectCommand.contribute_utterance(target_profile_id=changed.get("profile", product.profile_id),
        target_timeline_id=changed.get("timeline", product.timeline_id), declared_intent=changed.get("intent", "ask-collaborator-status"),
        utterance=message, language=changed.get("language", "zh"), provenance=changed.get("provenance", "project-original"))
    return product.application.lookup_subject_request(SubjectRequestLookupRequest(command, "original-whole-test-" + key))


def canonical_path(config):
    # Read only the synthetic fixture's registry and existing Timeline path.
    import json
    from dynamic_subject_agent.host import RuntimeHostRootRef
    from dynamic_subject_agent.studio import StudioRootRef
    from dynamic_subject_agent.host import RuntimeHost
    from dynamic_subject_agent.original_whole_chat_cognition import OriginalWholeChatCognition
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    record = next(row for row in state["identities"] if row["identity_id"] == state["active_identity_id"])
    # Existing tests may call this only while product is closed; avoid a second
    # Host owner by obtaining the path before opening the serving fixture.
    host = RuntimeHost.open(RuntimeHostRootRef.from_dict(record["host_location"]),
        studio_location=StudioRootRef.from_dict(record["studio_location"]), cognition=OriginalWholeChatCognition())
    try:
        return host.query_binding(profile_id=record["identity_id"], timeline_id=record["timeline_id"]).timeline_root.timeline_database
    finally:
        host.close()


def counts(path):
    db = sqlite3.connect(path)
    try:
        return tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in ("subject_operation", "idempotency_claim", "timeline_outcome", "operation_failure", "commit_plan_identity_claim"))
    finally:
        db.close()


def test_pure_lookup_missing_completed_and_restarted_never_admits_or_executes(whole_fixture, monkeypatch):
    opening, _, config, _ = whole_fixture
    initial = opening(); initial.close()
    path = canonical_path(config)
    transport = WholeTransport()
    product = opening(transport)
    before = counts(path)
    assert lookup(product, "尚未提交的合成草稿。", "missing").query_status == "not-found"
    assert counts(path) == before and not transport.calls
    completed = send(product, "当前合成问题。", "complete")
    assert completed.status == "terminal"
    saved_counts, used = counts(path), product.application.reviewed_character_chat_status().budget_used
    def forbidden(*a, **kw):
        pytest.fail("lookup entered a write/execution path")
    from dynamic_subject_agent.application import _ApplicationRouter
    from dynamic_subject_agent.runtime import SubjectRuntime
    from dynamic_subject_agent.host import RuntimeHost
    with monkeypatch.context() as no_execution:
        no_execution.setattr(_ApplicationRouter, "submit", forbidden)
        no_execution.setattr(_ApplicationRouter, "follow", forbidden)
        no_execution.setattr(_ApplicationRouter, "wait", forbidden)
        no_execution.setattr(_ApplicationRouter, "_start_resume", forbidden)
        no_execution.setattr(RuntimeHost, "lease", forbidden)
        no_execution.setattr(TimelineEngine, "admit", forbidden)
        no_execution.setattr(SubjectRuntime, "resume", forbidden)
        result = lookup(product, "当前合成问题。", "complete")
        assert result.query_status == "found" and result.operation.status == "terminal"
        assert result.operation.projection.expression_text == completed.projection.expression_text
        assert counts(path) == saved_counts and len(transport.calls) == 1
    # Restore lease for normal lifecycle startup, then independently prohibit
    # recovery during the lookup itself after the restart has completed.
    product.close()
    transport2 = WholeTransport()
    restarted = opening(transport2)
    monkeypatch.setattr(SubjectRuntime, "recover_original_whole_pending", forbidden)
    result = lookup(restarted, "当前合成问题。", "complete")
    assert result.query_status == "found" and result.operation.projection.expression_text == completed.projection.expression_text
    assert counts(path) == saved_counts and not transport2.calls
    assert restarted.application.reviewed_character_chat_status().budget_used == used


def test_lookup_reads_inflight_snapshot_without_waiting_for_model_or_resuming(whole_fixture):
    opening, _, _, _ = whole_fixture
    entered, release = Event(), Event()
    def blocking():
        entered.set()
        assert release.wait(10)
    transport = WholeTransport(callback=blocking)
    product = opening(transport)
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent="ask-collaborator-status", utterance="在途合成问题。", language="zh", provenance="project-original")
    admitted = product.application.submit(command, idempotency_key="original-whole-test-inflight")
    assert admitted.status == "pending" and entered.wait(5)
    try:
        started = monotonic()
        result = lookup(product, "在途合成问题。", "inflight")
        assert monotonic() - started < 3
        assert result.query_status == "found" and result.operation.status == "pending"
        assert result.operation.projection is None and len(transport.calls) == 1
    finally:
        release.set()
    assert product.application.wait(admitted.operation_ref, timeout_seconds=30).status == "terminal"


def test_lookup_foreign_mismatch_and_invalid_chat_never_return_original_body(whole_fixture):
    opening, _, _, _ = whole_fixture
    product = opening()
    assert send(product, "原合成文字。", "private").status == "terminal"
    mismatch = lookup(product, "后来修改的合成草稿。", "private")
    assert mismatch.query_status == "unavailable" and mismatch.problem.code == "subject-request-payload-mismatch"
    assert mismatch.operation is None
    for changed in ({"profile": str(uuid4())}, {"timeline": str(uuid4())}):
        foreign = lookup(product, "原合成文字。", "private", **changed)
        assert foreign.query_status == "not-found" and foreign.operation is None
    for changed in ({"intent": "first-life-system"}, {"language": "en"}, {"provenance": "foreign-origin"}):
        rejected = lookup(product, "原合成文字。", "private", **changed)
        assert rejected.query_status == "unavailable" and rejected.operation is None


@pytest.mark.parametrize("fault,status", [("schema", "failed-closed"), ("timeout", "unknown")])
def test_query_success_is_distinct_from_canonical_terminal_failure_or_unknown(whole_fixture, fault, status):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport(fault=fault)
    product = opening(transport)
    sent = send(product, "失败合成问题。", "failure")
    assert sent.status == status
    for _ in range(2):
        result = lookup(product, "失败合成问题。", "failure")
        assert result.query_status == "found" and result.operation.status == status
        assert result.operation.projection.expression_text is None and len(transport.calls) == 1


def test_lookup_integrity_failure_does_not_become_not_found_or_operation_unknown(whole_fixture):
    opening, _, config, _ = whole_fixture
    opening().close()
    path = canonical_path(config)
    product = opening()
    assert send(product, "原合成文字。", "corrupt").status == "terminal"
    db = sqlite3.connect(path, autocommit=True)
    try:
        db.execute("UPDATE expression_record SET expression_text='TAMPERED_SYNTHETIC_TEXT'")
    finally:
        db.close()
    result = lookup(product, "原合成文字。", "corrupt")
    assert result.query_status == "failed-closed" and result.operation is None


def test_lookup_cold_pending_only_observes_without_recovery_or_model(whole_fixture, monkeypatch):
    opening, _, config, _ = whole_fixture
    opening().close()
    path = canonical_path(config)
    product = opening(WholeTransport())
    interrupted = Event()
    def stop_before_publication(*a, **kw):
        interrupted.set()
        raise PublicationInterrupted("synthetic-interruption", "Synthetic uncommitted delivery.")
    monkeypatch.setattr(TimelineEngine, "publish", stop_before_publication)
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent="ask-collaborator-status", utterance="未提交的合成问题。", language="zh", provenance="project-original")
    pending = product.application.submit(command, idempotency_key="original-whole-test-cold")
    assert pending.status == "pending"
    assert interrupted.wait(5)
    before = counts(path)
    result = lookup(product, "未提交的合成问题。", "cold")
    assert result.query_status == "found" and result.operation.status == "pending"
    assert counts(path) == before


def test_lost_claim_index_never_turns_existing_work_into_not_found(whole_fixture):
    opening, _, config, _ = whole_fixture
    opening().close()
    path = canonical_path(config)
    product = opening()
    assert send(product, "原合成文字。", "lost-index").status == "terminal"
    db = sqlite3.connect(path, autocommit=True)
    try:
        db.execute("DELETE FROM idempotency_claim")
    finally:
        db.close()
    result = lookup(product, "原合成文字。", "lost-index")
    assert result.query_status == "failed-closed" and result.operation is None


def test_whole_lookup_accepts_canonical_opaque_key_from_other_adapter_without_any_new_work(whole_fixture):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport()
    product = opening(transport)
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent="ask-collaborator-status", utterance="已有开发分支的合成消息。", language="zh", provenance="project-original")
    opaque_key = "whole-development-s130-grounded-proposal-1"
    submitted = product.application.submit(command, idempotency_key=opaque_key)
    if submitted.status == "pending":
        submitted = product.application.wait(submitted.operation_ref, timeout_seconds=30)
    assert submitted.status == "terminal" and len(transport.calls) == 1
    before = product.application.reviewed_character_chat_status().budget_used
    for _ in range(2):
        found = product.application.lookup_subject_request(SubjectRequestLookupRequest(command, opaque_key))
        assert found.query_status == "found" and found.operation.projection.expression_text == submitted.projection.expression_text
    assert len(transport.calls) == 1 and product.application.reviewed_character_chat_status().budget_used == before
    for invalid in ("short", "x" * 257, "opaque token with spaces"):
        rejected = product.application.lookup_subject_request(SubjectRequestLookupRequest(command, invalid))
        assert rejected.query_status == "unavailable" and rejected.problem.code == "malformed-idempotency-key"
        assert rejected.operation is None
    assert len(transport.calls) == 1

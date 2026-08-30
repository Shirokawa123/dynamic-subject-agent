from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest

from dynamic_subject_agent.timeline import (
    AdmissionFailedClosed,
    AttemptState,
    CanonicalRootRef,
    FaultPoint,
    FixtureAuthority,
    OperationState,
    PayloadConflict,
    PreAdmissionRejected,
    SubjectCommand,
    TimelineEngine,
)


PROFILE_ID = "c627e693-68f0-43f7-b3db-e55490b47b32"
TIMELINE_ID = "471f4fd1-69fd-49df-aa14-3af405d301cf"
AUTHORITY_SCOPE_ID = "91f6a5fc-22dc-482b-b482-5ca9089d1e69"
IDEMPOTENCY_KEY = "lantern-zine-operation-0001"


def _authority() -> FixtureAuthority:
    return FixtureAuthority(
        authority_scope_id=AUTHORITY_SCOPE_ID,
        profile_id=PROFILE_ID,
        timeline_id=TIMELINE_ID,
        allowed_intents=("ask-collaborator-status",),
        allowed_provenance=("project-original",),
    )


def _command(
    *,
    utterance: str = (
        "Could you check whether the lantern issue can still make Friday's print slot?"
    ),
    timeline_id: str = TIMELINE_ID,
) -> SubjectCommand:
    return SubjectCommand.contribute_utterance(
        target_profile_id=PROFILE_ID,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=utterance,
        language="en",
        provenance="project-original",
    )


def _open_read_only(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, autocommit=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _canonical_counts(location: CanonicalRootRef) -> dict[str, int]:
    connection = _open_read_only(location.timeline_database)
    try:
        names = (
            "idempotency_claim",
            "subject_operation",
            "subject_command",
            "subject_event",
            "experience_attempt",
            "operation_transition",
        )
        counts = {
            name: int(connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0])
            for name in names
        }
        counts["timeline_head"] = int(
            connection.execute(
                "SELECT head_sequence FROM timeline_head WHERE singleton = 1"
            ).fetchone()[0]
        )
        return counts
    finally:
        connection.close()


def _assert_empty_admission(location: CanonicalRootRef) -> None:
    assert _canonical_counts(location) == {
        "idempotency_claim": 0,
        "subject_operation": 0,
        "subject_command": 0,
        "subject_event": 0,
        "experience_attempt": 0,
        "operation_transition": 0,
        "timeline_head": 0,
    }
    assert (
        IDEMPOTENCY_KEY.encode("utf-8") not in location.timeline_database.read_bytes()
    )


def test_first_submit_retry_conflict_and_restart_recovery(tmp_path: Path) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    location = engine.location
    command = _command()

    first = engine.admit(command, idempotency_key=IDEMPOTENCY_KEY)
    repeated = engine.admit(command, idempotency_key=IDEMPOTENCY_KEY)

    assert first.replayed is False
    assert repeated.replayed is True
    assert repeated.operation_ref == first.operation_ref
    assert UUID(first.operation_ref.operation_id)
    assert UUID(first.attempt_id)
    assert _canonical_counts(location) == {
        "idempotency_claim": 1,
        "subject_operation": 1,
        "subject_command": 1,
        "subject_event": 1,
        "experience_attempt": 1,
        "operation_transition": 1,
        "timeline_head": 0,
    }

    with pytest.raises(PayloadConflict) as captured:
        engine.admit(
            _command(utterance="Please reserve the slot without checking first."),
            idempotency_key=IDEMPOTENCY_KEY,
        )
    assert captured.value.code == "payload-conflict"
    assert captured.value.existing_operation_ref == first.operation_ref
    assert _canonical_counts(location)["experience_attempt"] == 1

    engine.close()
    restarted = TimelineEngine.open(location)
    recovered = restarted.query(first.operation_ref)
    restarted.close()

    assert recovered.operation_state is OperationState.ADMITTED_PENDING
    assert recovered.attempt_state is AttemptState.PENDING
    assert recovered.operation_ref == first.operation_ref
    assert recovered.attempt_id == first.attempt_id
    assert recovered.timeline_head_sequence == 0


def test_concurrent_same_key_submissions_converge_on_one_operation(
    tmp_path: Path,
) -> None:
    bootstrap = TimelineEngine.create_test(tmp_path, _authority())
    location = bootstrap.location
    bootstrap.close()
    start = Barrier(2)

    def submit() -> tuple[str, bool]:
        engine = TimelineEngine.open(location)
        start.wait(timeout=5)
        admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
        engine.close()
        return admitted.operation_ref.operation_id, admitted.replayed

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: submit(), range(2)))

    assert len({operation_id for operation_id, _ in results}) == 1
    assert sorted(replayed for _, replayed in results) == [False, True]
    assert _canonical_counts(location) == {
        "idempotency_claim": 1,
        "subject_operation": 1,
        "subject_command": 1,
        "subject_event": 1,
        "experience_attempt": 1,
        "operation_transition": 1,
        "timeline_head": 0,
    }


def test_invalid_command_or_fixture_authority_is_rejected_before_admission(
    tmp_path: Path,
) -> None:
    with pytest.raises(PreAdmissionRejected) as malformed:
        SubjectCommand.contribute_utterance(
            target_profile_id=PROFILE_ID,
            target_timeline_id=TIMELINE_ID,
            declared_intent="ask-collaborator-status",
            utterance="   ",
            language="en",
            provenance="project-original",
        )
    assert malformed.value.code == "malformed-command"

    engine = TimelineEngine.create_test(tmp_path, _authority())
    with pytest.raises(PreAdmissionRejected) as unauthorized:
        engine.admit(
            _command(timeline_id="1bdd554b-fecc-4d37-a4bc-ca7c6476cc28"),
            idempotency_key=IDEMPOTENCY_KEY,
        )
    assert unauthorized.value.code == "authority-mismatch"
    _assert_empty_admission(engine.location)
    engine.close()


@pytest.mark.parametrize(
    "fault_point",
    (
        FaultPoint.BEFORE_TRANSACTION,
        FaultPoint.AFTER_IDEMPOTENCY_CLAIM,
        FaultPoint.AFTER_OPERATION,
        FaultPoint.BEFORE_COMMIT,
    ),
)
def test_definite_precommit_faults_leave_no_partial_state(
    tmp_path: Path,
    fault_point: FaultPoint,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    location = engine.location
    engine.close()

    def fail_at(point: FaultPoint) -> None:
        if point is fault_point:
            raise RuntimeError(f"fault at {point.value}")

    failing = TimelineEngine.open(location, _fault_hook=fail_at)
    with pytest.raises(AdmissionFailedClosed) as captured:
        failing.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    assert captured.value.code == "admission-transaction-failed"
    failing.close()

    _assert_empty_admission(location)
    recovered = TimelineEngine.open(location)
    admitted = recovered.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    assert admitted.replayed is False
    recovered.close()


def test_lost_commit_response_is_resolved_from_canonical_state(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    location = engine.location
    engine.close()

    def lose_response(point: FaultPoint) -> None:
        if point is FaultPoint.AFTER_COMMIT:
            raise RuntimeError("simulated response loss")

    uncertain = TimelineEngine.open(location, _fault_hook=lose_response)
    admitted = uncertain.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    uncertain.close()

    assert admitted.replayed is True
    assert admitted.recovered_after_commit is True
    assert _canonical_counts(location)["experience_attempt"] == 1


@pytest.mark.parametrize(
    ("fault_point", "committed"),
    (
        (FaultPoint.BEFORE_TRANSACTION, False),
        (FaultPoint.AFTER_IDEMPOTENCY_CLAIM, False),
        (FaultPoint.AFTER_OPERATION, False),
        (FaultPoint.BEFORE_COMMIT, False),
        (FaultPoint.AFTER_COMMIT, True),
    ),
)
def test_process_termination_recovers_as_atomic_or_committed(
    tmp_path: Path,
    fault_point: FaultPoint,
    committed: bool,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    location = engine.location
    engine.close()

    worker = Path(__file__).parent / "support" / "admission_crash_worker.py"
    result = subprocess.run(
        [
            sys.executable,
            str(worker),
            json.dumps(location.to_dict(), sort_keys=True),
            json.dumps(_authority().to_dict(), sort_keys=True),
            json.dumps(_command().to_dict(), sort_keys=True),
            IDEMPOTENCY_KEY,
            fault_point.value,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert result.returncode == 86, result.stderr

    restarted = TimelineEngine.open(location)
    if not committed:
        _assert_empty_admission(location)
    admitted = restarted.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    restarted.close()

    assert admitted.replayed is committed
    assert _canonical_counts(location)["experience_attempt"] == 1
    assert _canonical_counts(location)["timeline_head"] == 0


def test_wrong_database_identity_and_schema_version_fail_closed(
    tmp_path: Path,
) -> None:
    identity_engine = TimelineEngine.create_test(tmp_path / "identity", _authority())
    identity_location = identity_engine.location
    identity_engine.close()

    db = sqlite3.connect(identity_location.timeline_database, autocommit=True)
    try:
        db.execute(
            "UPDATE store_manifest SET store_id = ?",
            ("32821b54-2677-4b04-885a-b29247061290",),
        )
    finally:
        db.close()
    with pytest.raises(AdmissionFailedClosed) as identity_error:
        TimelineEngine.open(identity_location)
    assert identity_error.value.code == "store-identity-mismatch"

    schema_engine = TimelineEngine.create_test(tmp_path / "schema", _authority())
    schema_location = schema_engine.location
    schema_engine.close()
    db = sqlite3.connect(schema_location.timeline_database, autocommit=True)
    try:
        db.execute("PRAGMA user_version = 2")
    finally:
        db.close()
    with pytest.raises(AdmissionFailedClosed) as schema_error:
        TimelineEngine.open(schema_location)
    assert schema_error.value.code == "unsupported-schema-version"


def test_missing_schema_object_and_hard_linked_store_fail_closed(
    tmp_path: Path,
) -> None:
    shape_engine = TimelineEngine.create_test(tmp_path / "shape", _authority())
    shape_location = shape_engine.location
    shape_engine.close()
    db = sqlite3.connect(shape_location.timeline_database, autocommit=True)
    try:
        db.execute("DROP TABLE subject_event")
    finally:
        db.close()
    with pytest.raises(AdmissionFailedClosed) as shape_error:
        TimelineEngine.open(shape_location)
    assert shape_error.value.code == "store-schema-mismatch"

    link_engine = TimelineEngine.create_test(tmp_path / "link", _authority())
    link_location = link_engine.location
    link_engine.close()
    linked_copy = link_location.timeline_database.with_name("linked.sqlite3")
    os.link(link_location.timeline_database, linked_copy)
    with pytest.raises(AdmissionFailedClosed) as link_error:
        TimelineEngine.open(link_location)
    assert link_error.value.code == "store-missing"


@pytest.mark.parametrize("reserved_segment", ("legacy", "private", "retired"))
def test_protected_target_shapes_fail_before_store_creation(
    tmp_path: Path,
    reserved_segment: str,
) -> None:
    protected = tmp_path / reserved_segment
    protected.mkdir()

    with pytest.raises(AdmissionFailedClosed) as captured:
        TimelineEngine.create_test(protected, _authority())
    assert captured.value.code == "canonical-root-not-allowed"
    assert list(protected.iterdir()) == []


def test_relative_target_is_not_resolved_from_process_context() -> None:
    with pytest.raises(AdmissionFailedClosed) as captured:
        TimelineEngine.create_test(Path("implicit-root"), _authority())
    assert captured.value.code == "canonical-root-not-allowed"

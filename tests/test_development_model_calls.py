"""Development audit behavior with synthetic metadata and no provider/key use."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import sqlite3

import pytest

from dynamic_subject_agent.development_model_calls import AUTHORIZATION, DevelopmentCallAudit


PURPOSE = "reply-protocol-comparison"


def digest(value):
    return sha256(str(value).encode()).hexdigest()


def claim(audit, index):
    attempt = digest(("attempt", index))
    audit.claim(attempt, digest(("request", index)), purpose=PURPOSE, run_digest=digest("run"))
    return attempt


@pytest.fixture
def audit(tmp_path):
    return DevelopmentCallAudit(tmp_path / "development-calls", initialize=True)


def test_unlimited_config_and_query_contain_only_audit_metadata(audit):
    assert audit.counts() == (None, 0, None) and audit.config["limit"] is None
    assert audit.config["authorization"] == AUTHORIZATION == "user-unlimited-model-development-2026-10-01"
    assert audit.query(digest("not-attempted")) is None
    attempt = claim(audit, 0)
    assert audit.query(attempt) == dict(ordinal=0, attempt_id=attempt, request_digest=digest(("request", 0)),
        purpose=PURPOSE, run_digest=digest("run"), status="claimed", output_digest=None)
    audit.record(attempt, status="complete", output_digest=digest("output"))
    row = audit.query(attempt)
    assert row["status"] == "complete" and row["output_digest"] == digest("output")
    assert set(row) == {"ordinal", "attempt_id", "request_digest", "purpose", "run_digest", "status", "output_digest"}
    assert audit.counts() == (None, 1, None)


def test_unknown_and_pending_attempts_are_not_refunded_or_reclaimed_on_reopen(audit):
    unknown = claim(audit, "unknown")
    audit.record(unknown, status="unknown")
    pending = claim(audit, "crashed")
    reopened = DevelopmentCallAudit(audit.path, initialize=True)
    assert reopened.counts() == (None, 2, None)
    assert reopened.query(unknown)["status"] == "unknown" and reopened.query(pending)["status"] == "claimed"
    for index in ("unknown", "crashed"):
        with pytest.raises(ValueError, match="already claimed"):
            claim(reopened, index)
    with pytest.raises(ValueError, match="uncompleted claim"):
        reopened.record(unknown, status="complete", output_digest=digest("late"))
    reopened.record(pending, status="failed-closed")
    assert reopened.counts() == (None, 2, None)


def test_over_previous_200_is_still_an_unlimited_audit(audit):
    for index in range(205):
        attempt = claim(audit, index)
        audit.record(attempt, status="unknown" if index % 2 else "complete",
            output_digest=None if index % 2 else digest(("output", index)))
    assert audit.counts() == (None, 205, None)
    reopened = DevelopmentCallAudit(audit.path)
    assert reopened.counts() == (None, 205, None) and reopened.query(digest(("attempt", 204)))["ordinal"] == 204
    with sqlite3.connect(audit.path / "calls.sqlite3") as db:
        assert json.loads(db.execute("SELECT body FROM audit_config").fetchone()[0])["limit"] is None


def test_concurrent_claims_are_unique_and_atomic(audit):
    def attempt(index):
        separate = DevelopmentCallAudit(audit.path)
        try:
            claim(separate, index % 6)
            return True
        except ValueError as error:
            assert "already claimed" in str(error)
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(attempt, range(36))) == 6
    assert audit.counts() == (None, 6, None)
    assert all(audit.query(digest(("attempt", index)))["status"] == "claimed" for index in range(6))


def test_terminal_transition_is_once_even_across_connections(audit):
    attempt = claim(audit, "one-result")
    def record(index):
        separate = DevelopmentCallAudit(audit.path)
        try:
            separate.record(attempt, status="unknown" if index % 2 else "complete", output_digest=digest(index))
            return True
        except ValueError as error:
            assert "uncompleted claim" in str(error)
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(record, range(12))) == 1
    assert audit.counts() == (None, 1, None) and audit.query(attempt)["status"] in ("complete", "unknown")


@pytest.mark.parametrize("damage", ["tail", "row", "head", "config", "head-table"])
def test_integrity_damage_never_reopens_or_accepts_new_calls(audit, damage):
    claim(audit, 0)
    claim(audit, 1)
    with sqlite3.connect(audit.path / "calls.sqlite3") as db:
        if damage == "tail":
            db.execute("DELETE FROM call_attempt WHERE ordinal=1")
        elif damage == "row":
            db.execute("UPDATE call_attempt SET status='unknown' WHERE ordinal=0")
        elif damage == "head":
            db.execute("UPDATE audit_head SET claim_count=1")
        elif damage == "config":
            body = json.loads(db.execute("SELECT body FROM audit_config").fetchone()[0])
            body["limit"] = 1000000000
            db.execute("UPDATE audit_config SET body=?", (json.dumps(body),))
        else:
            db.execute("DROP TABLE audit_head")
    for action in (audit.counts, lambda: audit.query(digest(("attempt", 0))), lambda: claim(audit, 2),
        lambda: DevelopmentCallAudit(audit.path, initialize=True)):
        with pytest.raises(ValueError, match="integrity"):
            action()


@pytest.mark.parametrize("missing", ["database", "marker"])
def test_missing_initialization_witness_or_database_is_not_repaired(audit, missing):
    claim(audit, 0)
    if missing == "database":
        (audit.path / "calls.sqlite3").unlink()  # Only this synthetic tmp_path file.
    else:
        (audit.path / "initialized").rmdir()  # Only this synthetic empty marker.
    for action in (audit.counts, lambda: DevelopmentCallAudit(audit.path),
        lambda: DevelopmentCallAudit(audit.path, initialize=True)):
        with pytest.raises(ValueError, match="missing"):
            action()


def test_new_directory_requires_explicit_initialization_and_partial_open_is_not_repaired(tmp_path, monkeypatch):
    path = tmp_path / "explicit-new-audit"
    with pytest.raises(ValueError, match="existing"):
        DevelopmentCallAudit(path)
    assert not path.exists()
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("synthetic interrupted initialization")))
        with pytest.raises(sqlite3.OperationalError):
            DevelopmentCallAudit(path, initialize=True)
    assert (path / "initialized").is_dir()
    with pytest.raises(ValueError, match="missing"):
        DevelopmentCallAudit(path, initialize=True)


def test_head_write_failure_rolls_back_the_unique_claim(audit):
    with sqlite3.connect(audit.path / "calls.sqlite3") as db:
        db.execute("CREATE TRIGGER reject_audit_head BEFORE UPDATE ON audit_head BEGIN SELECT RAISE(ABORT,'synthetic interruption'); END")
    with pytest.raises(sqlite3.DatabaseError):
        claim(audit, "atomic")
    assert audit.counts() == (None, 0, None) and audit.query(digest(("attempt", "atomic"))) is None


def test_invalid_or_unapproved_metadata_is_rejected_before_writes(audit):
    cases = [dict(attempt_id="raw request text", request_digest=digest("request"), purpose=PURPOSE, run_digest=digest("run")),
        dict(attempt_id=digest("attempt"), request_digest="not-a-digest", purpose=PURPOSE, run_digest=digest("run")),
        dict(attempt_id=digest("attempt"), request_digest=digest("request"), purpose="", run_digest=digest("run")),
        dict(attempt_id=digest("attempt"), request_digest=digest("request"), purpose="new-private-data-use", run_digest=digest("run")),
        dict(attempt_id=digest("attempt"), request_digest=digest("request"), purpose=PURPOSE, run_digest="other raw material")]
    for case in cases:
        with pytest.raises(ValueError):
            audit.claim(**case)
    assert audit.counts() == (None, 0, None)
    attempt = claim(audit, "valid")
    for arguments in (dict(status="claimed"), dict(status="complete", output_digest="raw final content")):
        with pytest.raises(ValueError):
            audit.record(attempt, **arguments)
    assert audit.query(attempt)["status"] == "claimed" and audit.counts() == (None, 1, None)

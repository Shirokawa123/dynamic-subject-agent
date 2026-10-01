"""Synthetic S112 22/42 prefix and S114 18 sublimit; never open real ledgers."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
import json
import sqlite3

import pytest

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.first_life_candidate_budget import CandidateTrialBudget, approve_candidate_allowance


GRANT = "a" * 64
MARKER = "s114-candidate-allowance"
TABLES = ("s114_candidate_grant", "s114_candidate_claim", "s114_candidate_head")


def digest(value):
    return sha256(str(value).encode()).hexdigest()


def claim(budget, index, *, identity="candidate"):
    ids = (digest(identity), digest(index), "expression")
    budget.claim(*ids, digest((identity, index, "request")))
    return ids


@pytest.fixture
def parent(tmp_path):
    # The baseline is explicitly 22 actual terminal synthetic stage records,
    # not initial_used=22 and not a fresh 18- or 42-slot replacement allowance.
    budget = CharacterChatBudget(tmp_path / "s112-parent", total=42, initial_used=0, initialize=True)
    for index in range(22):
        ids = claim(budget, index, identity="s112")
        budget.record(*ids, status="unknown" if index in (4, 21) else "complete",
            output_digest=None if index in (4, 21) else digest(("output", index)))
    assert budget.counts() == (42, 22, 20)
    return budget


def snapshot(parent):
    with sqlite3.connect(parent.path / "attempts.sqlite3") as db:
        return dict(stages=db.execute("SELECT * FROM stage_attempt ORDER BY ordinal").fetchall(),
            config=db.execute("SELECT * FROM config").fetchall(),
            head=db.execute("SELECT * FROM ledger_head").fetchall(),
            schema=db.execute("SELECT name,sql FROM sqlite_schema WHERE name IN ('config','stage_attempt','ledger_head') ORDER BY name").fetchall(),
            user_version=db.execute("PRAGMA user_version").fetchone()[0])


def test_approval_is_one_exact_prefix_bound_sublimit_and_old_reader_is_unchanged(parent):
    before = snapshot(parent)
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    assert type(budget) is CandidateTrialBudget and budget.config == parent.config
    assert budget.counts() == (18, 0, 18) and budget.parent_counts() == parent.counts() == (42, 22, 20)
    assert snapshot(parent) == before
    repeated = approve_candidate_allowance(parent, grant_digest=GRANT)
    assert repeated.counts() == (18, 0, 18) and snapshot(parent) == before
    with sqlite3.connect(parent.path / "attempts.sqlite3") as db:
        body, body_digest = db.execute("SELECT body,body_digest FROM s114_candidate_grant").fetchone()
        value = json.loads(body)
        assert value["parent_prefix_count"] == 22 and value["parent_prefix_digest"] == parent._chain(before["stages"])
        assert value["grant_digest"] == GRANT and value["limit"] == 18 and body_digest == parent._hash(value)
    ids = claim(budget, "first")
    budget.record(*ids, status="complete", output_digest=digest("final"))
    after = snapshot(parent)
    assert after["stages"][:22] == before["stages"]
    assert all(after[key] == before[key] for key in ("config", "schema", "user_version"))
    assert CharacterChatBudget(parent.path, total=42, initial_used=0).counts() == (42, 23, 19)
    assert approve_candidate_allowance(parent, grant_digest=GRANT).counts() == (18, 1, 17)


def test_approval_cannot_change_digest_reset_count_or_reuse_nonparent_budget(parent):
    before = snapshot(parent)
    with pytest.raises(ValueError):
        approve_candidate_allowance(parent, grant_digest=GRANT, confirmed=False)
    assert snapshot(parent) == before and not (parent.path / MARKER).exists()
    with pytest.raises(ValueError):
        CandidateTrialBudget(parent.path, grant_digest=GRANT)
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    ids = claim(budget, "unknown")
    budget.record(*ids, status="unknown")
    for action in (lambda: approve_candidate_allowance(parent, grant_digest="b" * 64),
        lambda: CandidateTrialBudget(parent.path, grant_digest="b" * 64),
        lambda: approve_candidate_allowance(budget, grant_digest=GRANT)):
        with pytest.raises(ValueError):
            action()
    assert CandidateTrialBudget(parent.path, grant_digest=GRANT).counts() == (18, 1, 17)
    assert parent.counts() == (42, 23, 19)


def test_unknown_and_unfinished_claims_remain_spent_after_restart(parent):
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    unknown = claim(budget, "unknown")
    budget.record(*unknown, status="unknown")
    unfinished = claim(budget, "crashed-before-result")
    reopened = CandidateTrialBudget(parent.path, grant_digest=GRANT)
    assert reopened.counts() == (18, 2, 16) and reopened.parent_counts() == (42, 24, 18)
    for index in ("unknown", "crashed-before-result"):
        with pytest.raises(ValueError, match="already attempted"):
            claim(reopened, index)
    with pytest.raises(ValueError):
        reopened.record(*unknown, status="complete", output_digest=digest("replacement"))
    reopened.record(*unfinished, status="failed-closed")
    assert reopened.counts() == (18, 2, 16)


def test_candidate_cannot_finalize_other_parent_claim(parent):
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    ids = claim(parent, "other-parent-work", identity="other")
    with pytest.raises(ValueError, match="without its uncompleted claim"):
        budget.record(*ids, status="complete", output_digest=digest("wrong"))
    parent.record(*ids, status="unknown")
    assert budget.counts() == (18, 0, 18) and budget.parent_counts() == (42, 23, 19)


def test_initialization_requires_the_exact_22_closed_records_not_just_balance(parent, tmp_path):
    for used in (0, 21, 23, 25):
        fake = CharacterChatBudget(tmp_path / f"other-{used}", total=42, initial_used=0, initialize=True)
        for index in range(used):
            fake.record(*claim(fake, index, identity="baseline"), status="complete", output_digest=digest(index))
        with pytest.raises(ValueError, match="exact closed 22"):
            approve_candidate_allowance(fake, grant_digest=GRANT)
        assert not (fake.path / MARKER).exists()
    pending = CharacterChatBudget(tmp_path / "pending", total=42, initial_used=0, initialize=True)
    for index in range(22):
        ids = claim(pending, index, identity="baseline")
        if index != 21:
            pending.record(*ids, status="complete", output_digest=digest(index))
    with pytest.raises(ValueError, match="exact closed 22"):
        approve_candidate_allowance(pending, grant_digest=GRANT)
    wrong = CharacterChatBudget(tmp_path / "wrong-config", total=42, initial_used=22, initialize=True)
    with pytest.raises(ValueError):
        approve_candidate_allowance(wrong, grant_digest=GRANT)


def test_parent_and_child_claim_are_atomic_on_sql_failure(parent):
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    before = snapshot(parent)
    with sqlite3.connect(parent.path / "attempts.sqlite3") as db:
        db.execute("CREATE TRIGGER reject_candidate BEFORE INSERT ON s114_candidate_claim BEGIN SELECT RAISE(ABORT,'synthetic write interruption'); END")
    with pytest.raises(sqlite3.DatabaseError):
        claim(budget, "interrupted")
    assert snapshot(parent) == before and budget.counts() == (18, 0, 18)
    with sqlite3.connect(parent.path / "attempts.sqlite3") as db:
        db.execute("DROP TRIGGER reject_candidate")
    claim(budget, "interrupted")
    assert budget.counts() == (18, 1, 17) and parent.counts() == (42, 23, 19)


def test_interrupted_grant_initialization_never_silently_recreates_grant(parent, monkeypatch):
    transaction = parent._transaction
    @contextmanager
    def fail_before_head():
        with transaction() as db:
            db.set_authorizer(lambda action, first, second, database, trigger:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and first == "s114_candidate_head" else sqlite3.SQLITE_OK)
            yield db
    with monkeypatch.context() as patch:
        patch.setattr(parent, "_transaction", fail_before_head)
        with pytest.raises(sqlite3.DatabaseError):
            approve_candidate_allowance(parent, grant_digest=GRANT)
    assert (parent.path / MARKER).is_dir() and parent.counts() == (42, 22, 20)
    for action in (lambda: approve_candidate_allowance(parent, grant_digest=GRANT),
        lambda: CandidateTrialBudget(parent.path, grant_digest=GRANT)):
        with pytest.raises(ValueError):
            action()


@pytest.mark.parametrize("damage", ["marker", "grant-table", "grant-row", "head-row", "mapping", "all-metadata"])
def test_lost_grant_metadata_cannot_reopen_18(parent, damage):
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    budget.record(*claim(budget, "spent"), status="unknown")
    if damage in ("marker", "all-metadata"):
        (parent.path / MARKER).rmdir()  # Empty directory inside this test's own tmp_path.
    with sqlite3.connect(parent.path / "attempts.sqlite3") as db:
        if damage == "grant-table":
            db.execute("DROP TABLE s114_candidate_grant")
        elif damage == "grant-row":
            db.execute("DELETE FROM s114_candidate_grant")
        elif damage == "head-row":
            db.execute("DELETE FROM s114_candidate_head")
        elif damage == "mapping":
            db.execute("DELETE FROM s114_candidate_claim")
        elif damage == "all-metadata":
            for table in TABLES:
                db.execute(f"DROP TABLE {table}")
    assert parent.counts() == (42, 23, 19)
    for action in (lambda: CandidateTrialBudget(parent.path, grant_digest=GRANT),
        lambda: approve_candidate_allowance(parent, grant_digest=GRANT), budget.counts,
        lambda: claim(budget, "forbidden")):
        with pytest.raises(ValueError):
            action()


def test_grant_binding_checks_parent_prefix_and_claim_mapping(parent):
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    claim(budget, "claimed")
    with sqlite3.connect(parent.path / "attempts.sqlite3") as db:
        db.execute("UPDATE s114_candidate_claim SET stage_ordinal=0")
    with pytest.raises(ValueError):
        budget.counts()
    assert parent.counts() == (42, 23, 19)


def test_grant_rejects_changed_opening_prefix_even_if_parent_chain_is_recomputed(parent):
    budget = approve_candidate_allowance(parent, grant_digest=GRANT)
    with parent._transaction() as db:
        row = db.execute("SELECT * FROM stage_attempt WHERE ordinal=0").fetchone()
        changed = [*row[:5], "unknown", None]
        db.execute("UPDATE stage_attempt SET status=?,output_digest=?,record_digest=? WHERE ordinal=0",
            ("unknown", None, parent._hash(changed)))
        parent._update_head(db)
    assert parent.counts() == (42, 22, 20)
    for action in (budget.counts, lambda: approve_candidate_allowance(parent, grant_digest=GRANT),
        lambda: CandidateTrialBudget(parent.path, grant_digest=GRANT)):
        with pytest.raises(ValueError, match="integrity"):
            action()


def test_candidate_and_parent_limits_hold_for_concurrent_connections(parent):
    approve_candidate_allowance(parent, grant_digest=GRANT)
    def attempt(index):
        budget = CandidateTrialBudget(parent.path, grant_digest=GRANT)
        try:
            claim(budget, index)
            return True
        except ValueError as error:
            assert "exhausted" in str(error)
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(attempt, range(26))) == 18
    budget = CandidateTrialBudget(parent.path, grant_digest=GRANT)
    assert budget.counts() == (18, 18, 0) and budget.parent_counts() == (42, 40, 2)
    for index in range(2):
        claim(parent, index, identity="separate-parent")
    assert budget.parent_counts() == (42, 42, 0)
    with pytest.raises(ValueError):
        claim(parent, "over-parent", identity="separate-parent")


def test_concurrent_parent_work_can_reduce_available_below_18_minus_child_used(parent):
    approve_candidate_allowance(parent, grant_digest=GRANT)
    def attempt(index):
        candidate = index % 2 == 0
        budget = (CandidateTrialBudget(parent.path, grant_digest=GRANT) if candidate
            else CharacterChatBudget(parent.path, total=42, initial_used=0))
        try:
            claim(budget, index, identity="candidate" if candidate else "other-parent")
            return candidate, True
        except ValueError as error:
            assert "exhausted" in str(error)
            return candidate, False
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(40)))
    child_used = sum(candidate and success for candidate, success in results)
    assert sum(success for _, success in results) == 20 and child_used <= 18
    budget = CandidateTrialBudget(parent.path, grant_digest=GRANT)
    assert budget.counts() == (18, child_used, 0) and budget.parent_counts() == (42, 42, 0)

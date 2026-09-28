"""S108 followup grant behavior on disposable synthetic attempt ledgers."""
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import sqlite3

import pytest

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.first_life import DEVELOPMENT_SCOPE
from dynamic_subject_agent.first_life_budget import (
    DEVELOPMENT_EXTENSION_ID, FOLLOWUP_DEVELOPMENT_EXTENSION_ID, FirstLifeBudget,
)
from dynamic_subject_agent.frozen_attempt import canonical_json


DAY = "2026-09-28"


def digest(value):
    return sha256(str(value).encode()).hexdigest()


def claim(budget, index, *, purpose="chat-planning", development_run=True):
    budget.claim_life(digest("identity"), digest(index),
        "planning" if purpose in ("chat-planning", "life-decision") else "expression",
        digest(("request", index)), purpose=purpose, civil_day=DAY,
        development_run=development_run)


def first_grant(budget):
    return budget.approve_development_extension(
        authorization_id=DEVELOPMENT_EXTENSION_ID, limit=36, confirmed=True)


def followup_grant(budget):
    return budget.approve_development_followup_extension(
        authorization_id=FOLLOWUP_DEVELOPMENT_EXTENSION_ID, limit=44, confirmed=True)


def budget_at(path, *, used=36, initial_used=61):
    CharacterChatBudget(path, initial_used=initial_used, initialize=True)
    budget = FirstLifeBudget(path, initial_used=initial_used, civil_day=lambda: DAY)
    for index in range(min(used, 24)):
        claim(budget, index)
    if used > 24:
        first_grant(budget)
        for index in range(24, used):
            claim(budget, index)
    return budget


def snapshot(path):
    with sqlite3.connect(path / "attempts.sqlite3") as db:
        return {name: db.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            for name in ("config", "stage_attempt", "ledger_head", "life_limit_claim",
                         "life_limit_head", "life_development_grant")}


def test_followup_grant_preserves_original_and_allows_exactly_eight_claims(tmp_path):
    path = tmp_path / "budget"
    budget = budget_at(path)
    before = snapshot(path)
    with pytest.raises(ValueError, match="development quota"):
        claim(budget, "unapproved")
    assert followup_grant(budget) == followup_grant(budget) == 44
    assert first_grant(budget) == 36
    assert snapshot(path) == before
    assert budget.life_counts(DAY, development_run=True) == (0, 0, 8)
    reopened = FirstLifeBudget(path, civil_day=lambda: DAY)
    for index in range(36, 44):
        claim(reopened, index)
    assert reopened.life_counts(DAY, development_run=True) == (0, 0, 0)
    assert reopened.counts() == CharacterChatBudget(path).counts() == (200, 105, 95)
    with pytest.raises(ValueError, match="development quota"):
        claim(reopened, "over-44")
    assert snapshot(path)["stage_attempt"][:36] == before["stage_attempt"]
    assert snapshot(path)["life_limit_claim"][:36] == before["life_limit_claim"]
    with sqlite3.connect(path / "attempts.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM life_development_followup_grant").fetchone()[0] == 1


@pytest.mark.parametrize("changes", [dict(confirmed=False), dict(confirmed=1), dict(limit=45),
    dict(limit=44.0), dict(authorization_id="unapproved"),
    dict(authorization_id=DEVELOPMENT_EXTENSION_ID)])
def test_exact_followup_approval_required(tmp_path, changes):
    path = tmp_path / "budget"
    budget = budget_at(path)
    before = snapshot(path)
    options = dict(authorization_id=FOLLOWUP_DEVELOPMENT_EXTENSION_ID, limit=44, confirmed=True)
    options.update(changes)
    with pytest.raises(ValueError, match="exact development followup"):
        budget.approve_development_followup_extension(**options)
    assert snapshot(path) == before
    assert budget.life_counts(DAY, development_run=True)[2] == 0
    with sqlite3.connect(path / "attempts.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_schema WHERE name='life_development_followup_grant'").fetchall()


def test_previous_grant_is_required_and_schema_v2_fails_older_reader(tmp_path):
    path = tmp_path / "budget"
    budget = budget_at(path, used=24)
    with pytest.raises(ValueError, match="previous development grant"):
        followup_grant(budget)
    first_grant(budget)
    followup_grant(budget)
    # The deployed S107 reader requires user_version=1. It stops at grant time,
    # even before the first claim above 36; reload it before writing the grant.
    with sqlite3.connect(path / "attempts.sqlite3") as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2
    assert version != 1
    assert CharacterChatBudget(path).counts() == (200, 85, 115)


@pytest.mark.parametrize("corruption", ["old-row", "old-table", "new-row", "new-table",
    "new-digest", "new-body", "new-prefix", "new-version", "extra-row"])
def test_damaged_grant_fails_closed_for_all_life_actions(tmp_path, corruption):
    path = tmp_path / "budget"
    budget = budget_at(path)
    followup_grant(budget)
    with sqlite3.connect(path / "attempts.sqlite3") as db:
        if corruption == "old-row":
            db.execute("DELETE FROM life_development_grant")
        elif corruption == "old-table":
            db.execute("DROP TABLE life_development_grant")
        elif corruption == "new-row":
            db.execute("DELETE FROM life_development_followup_grant")
        elif corruption == "new-table":
            db.execute("DROP TABLE life_development_followup_grant")
        elif corruption == "new-digest":
            db.execute("UPDATE life_development_followup_grant SET grant_digest='invalid'")
        elif corruption == "new-body":
            db.execute("UPDATE life_development_followup_grant SET body='{}'")
        elif corruption == "new-version":
            db.execute("PRAGMA user_version=1")
        elif corruption == "extra-row":
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute("INSERT INTO life_development_followup_grant SELECT 2,body,grant_digest FROM life_development_followup_grant")
        else:
            body = json.loads(db.execute("SELECT body FROM life_development_followup_grant").fetchone()[0])
            body["life_prefix_count"] = 35
            db.execute("UPDATE life_development_followup_grant SET body=?,grant_digest=?",
                (canonical_json(body), budget._hash(body)))
    for action in (budget.counts, lambda: budget.life_counts(DAY, development_run=True),
                   lambda: claim(budget, "corrupt-new"), lambda: followup_grant(budget),
                   lambda: FirstLifeBudget(path)):
        with pytest.raises(ValueError, match="grant"):
            action()


def test_interrupted_grant_rolls_back_second_table_and_version(tmp_path, monkeypatch):
    path = tmp_path / "budget"
    budget = budget_at(path)
    before = snapshot(path)
    original = budget._transaction

    @contextmanager
    def interrupted():
        with original() as db:
            yield db
            raise RuntimeError("synthetic interruption before commit")

    monkeypatch.setattr(budget, "_transaction", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        followup_grant(budget)
    monkeypatch.setattr(budget, "_transaction", original)
    assert snapshot(path) == before
    with sqlite3.connect(path / "attempts.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_schema WHERE name='life_development_followup_grant'").fetchall()
    assert FirstLifeBudget(path, civil_day=lambda: DAY).life_counts(DAY, development_run=True)[2] == 0


def _parallel_followup_claim(path, index):
    budget = FirstLifeBudget(Path(path), civil_day=lambda: DAY)
    try:
        followup_grant(budget)
        claim(budget, f"parallel-{index}")
        return "claimed"
    except ValueError as error:
        return str(error)


def test_parallel_grant_and_last_eight_claims_are_atomic(tmp_path):
    path = tmp_path / "parallel"
    budget = budget_at(path)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as workers:
        results = list(workers.map(_parallel_followup_claim, [str(path)] * 12, range(12)))
    assert results.count("claimed") == 8
    assert results.count("development quota exhausted") == 4
    assert budget.life_counts(DAY, development_run=True)[2] == 0
    assert budget.counts() == (200, 105, 95)


def test_total_and_daily_limits_still_apply_after_followup_grant(tmp_path):
    budget = budget_at(tmp_path / "daily")
    followup_grant(budget)
    for index in range(6):
        claim(budget, f"decision-{index}", purpose="life-decision", development_run=False)
    for index in range(2):
        claim(budget, f"share-{index}", purpose="life-share", development_run=False)
    for purpose in ("life-decision", "life-share"):
        with pytest.raises(ValueError, match="daily life quota"):
            claim(budget, f"over-{purpose}", purpose=purpose, development_run=False)
    assert budget.life_counts(DAY, development_run=True) == (6, 2, 8)
    capped = budget_at(tmp_path / "global", initial_used=164)
    followup_grant(capped)
    assert capped.counts() == (200, 200, 0)
    with pytest.raises(ValueError, match="global budget"):
        claim(capped, "over-global")

"""Exact development grant in the existing ledger; no Provider or real budget."""
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import sqlite3

import pytest

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.first_life import DEVELOPMENT_SCOPE
from dynamic_subject_agent.first_life_budget import FirstLifeBudget, DEVELOPMENT_EXTENSION_ID
from dynamic_subject_agent.frozen_attempt import canonical_json


DAY = '2026-09-27'


class S105BudgetReader(CharacterChatBudget):
    """Frozen S105 verification/counting algorithm (before extension support).

    The ledger already exists in these tests, so creation and claim code are
    intentionally omitted. This reader has no dependency on new grant logic.
    """
    def _life_chain(self, rows):
        head = self._hash(dict(version="first-life-limits-1", daily_decisions=6, daily_share_calls=2, development_calls=24))
        for row in rows: head = sha256((head + ":" + row[-1]).encode()).hexdigest()
        return head

    def _life_verified(self, db):
        _, stages = self._verified(db)
        rows = db.execute("SELECT stage_ordinal,purpose,civil_day,development_scope,stage_binding,claim_digest FROM life_limit_claim ORDER BY stage_ordinal").fetchall()
        for row in rows:
            if (type(row[0]) is not int or not 0 <= row[0] < len(stages) or row[1] not in ('life-decision', 'life-share', 'chat-planning', 'chat-expression')
                or date.fromisoformat(row[2]).isoformat() != row[2] or row[3] not in (None, DEVELOPMENT_SCOPE)
                or row[4] != self._hash(list(stages[row[0]][:5])) or row[5] != self._hash(list(row[:-1]))
                or stages[row[0]][3] != ("planning" if row[1] in ("life-decision", "chat-planning") else "expression")):
                raise ValueError("life limit claim invalid")
        if db.execute("SELECT count,chain_head FROM life_limit_head WHERE singleton=1").fetchone() != (len(rows), self._life_chain(rows)):
            raise ValueError("life limit cumulative head invalid")
        for day in {row[2] for row in rows}:
            if sum(row[2] == day and row[1] == "life-decision" for row in rows) > 6 or sum(row[2] == day and row[1] == "life-share" for row in rows) > 2:
                raise ValueError("life daily quota exceeded")
        if sum(row[3] == DEVELOPMENT_SCOPE for row in rows) > 24: raise ValueError("development quota exceeded")
        return rows

    def life_counts(self, civil_day, *, development_run):
        with self._transaction() as db: rows = self._life_verified(db)
        return (sum(row[2] == civil_day and row[1] == "life-decision" for row in rows),
            sum(row[2] == civil_day and row[1] == "life-share" for row in rows),
            24 - sum(row[3] == DEVELOPMENT_SCOPE for row in rows) if development_run else None)


def digest(value):
    return sha256(str(value).encode()).hexdigest()


def claim(budget, index, *, purpose='chat-planning', development_run=True):
    budget.claim_life(digest('identity'), digest(index),
        'planning' if purpose in ('chat-planning', 'life-decision') else 'expression', digest(('request', index)),
        purpose=purpose, civil_day=DAY, development_run=development_run)


def grant(budget):
    return budget.approve_development_extension(
        authorization_id=DEVELOPMENT_EXTENSION_ID, limit=36, confirmed=True)


def budget_at(path, *, used=24, initial_used=61):
    CharacterChatBudget(path, initial_used=initial_used, initialize=True)
    budget = FirstLifeBudget(path, initial_used=initial_used, civil_day=lambda: DAY)
    for index in range(used): claim(budget, index)
    return budget


def snapshot(path):
    with sqlite3.connect(path / 'attempts.sqlite3') as db:
        return {name: db.execute(f'SELECT * FROM {name} ORDER BY 1').fetchall()
            for name in ('config', 'stage_attempt', 'ledger_head', 'life_limit_claim', 'life_limit_head')}


def test_grant_is_idempotent_preserves_old_rows_and_requires_reload_after_24(tmp_path):
    path = tmp_path / 'budget'
    budget = budget_at(path)
    before = snapshot(path)
    legacy = S105BudgetReader(path)
    assert budget.life_counts(DAY, development_run=True) == (0, 0, 0)
    with pytest.raises(ValueError, match='development quota'): claim(budget, 'unapproved-25')
    assert grant(budget) == 36 and grant(budget) == 36
    assert snapshot(path) == before
    assert legacy.life_counts(DAY, development_run=True) == (0, 0, 0)
    assert budget.counts() == (200, 85, 115)
    reopened = FirstLifeBudget(path, civil_day=lambda: DAY)
    assert reopened.life_counts(DAY, development_run=True) == (0, 0, 12)
    claim(reopened, 'approved-25')
    with pytest.raises(ValueError, match='development quota exceeded'):
        legacy.life_counts(DAY, development_run=False)
    assert CharacterChatBudget(path).counts() == (200, 86, 114)
    assert snapshot(path)['life_limit_claim'][-1][3] == DEVELOPMENT_SCOPE
    assert snapshot(path)['stage_attempt'][:24] == before['stage_attempt']
    assert snapshot(path)['life_limit_claim'][:24] == before['life_limit_claim']
    # Original status audit can finish after approval; immutable life binding
    # covers stage identity, not mutable completion status.
    reopened.record(digest('identity'), digest(0), 'planning', status='complete', output_digest=digest('output'))
    assert reopened.life_counts(DAY, development_run=True) == (0, 0, 11)
    for index in range(26, 37): claim(reopened, index)
    assert reopened.life_counts(DAY, development_run=True) == (0, 0, 0)
    assert grant(reopened) == 36
    with pytest.raises(ValueError, match='development quota'): claim(reopened, '37')


@pytest.mark.parametrize('changes', [dict(confirmed=False), dict(confirmed=1), dict(limit=48),
    dict(limit=36.0), dict(authorization_id='unapproved')])
def test_wrong_approval_never_changes_ledger(tmp_path, changes):
    path = tmp_path / 'budget'
    budget = budget_at(path)
    before = snapshot(path)
    options = dict(authorization_id=DEVELOPMENT_EXTENSION_ID, limit=36, confirmed=True)
    options.update(changes)
    with pytest.raises(ValueError, match='exact development extension'):
        budget.approve_development_extension(**options)
    assert snapshot(path) == before
    assert budget.life_counts(DAY, development_run=True)[2] == 0
    with sqlite3.connect(path / 'attempts.sqlite3') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0
        assert not db.execute("SELECT name FROM sqlite_schema WHERE name='life_development_grant'").fetchall()


@pytest.mark.parametrize('corruption', ['row', 'table', 'digest', 'body', 'prefix', 'version', 'extra-row'])
def test_damaged_grant_is_closed_for_counts_claim_and_reapproval(tmp_path, corruption):
    path = tmp_path / 'budget'
    budget = budget_at(path)
    grant(budget)
    with sqlite3.connect(path / 'attempts.sqlite3') as db:
        if corruption == 'row': db.execute('DELETE FROM life_development_grant')
        elif corruption == 'table': db.execute('DROP TABLE life_development_grant')
        elif corruption == 'digest': db.execute("UPDATE life_development_grant SET grant_digest='invalid'")
        elif corruption == 'body': db.execute("UPDATE life_development_grant SET body='{}'")
        elif corruption == 'version': db.execute('PRAGMA user_version=0')
        elif corruption == 'extra-row':
            db.execute('PRAGMA ignore_check_constraints=ON')
            db.execute('INSERT INTO life_development_grant SELECT 2,body,grant_digest FROM life_development_grant')
        else:
            body = json.loads(db.execute('SELECT body FROM life_development_grant').fetchone()[0])
            body['life_prefix_count'] = 25
            db.execute('UPDATE life_development_grant SET body=?,grant_digest=?', (canonical_json(body), budget._hash(body)))
    before = snapshot(path)
    for action in (budget.counts, lambda: budget.life_counts(DAY, development_run=True),
                   lambda: claim(budget, 'corrupt-new'), lambda: grant(budget), lambda: FirstLifeBudget(path)):
        with pytest.raises(ValueError, match='grant'): action()
    assert snapshot(path) == before


def test_grant_keeps_global_and_daily_limits(tmp_path):
    budget = budget_at(tmp_path / 'daily')
    grant(budget)
    for index in range(6): claim(budget, f'decision-{index}', purpose='life-decision')
    for index in range(2): claim(budget, f'share-{index}', purpose='life-share')
    for purpose in ('life-decision', 'life-share'):
        with pytest.raises(ValueError, match='daily life quota'):
            claim(budget, f'extra-{purpose}', purpose=purpose)
    assert budget.life_counts(DAY, development_run=True) == (6, 2, 4)
    capped = budget_at(tmp_path / 'global', initial_used=175)
    grant(capped)
    claim(capped, 'last-global-call')
    assert capped.counts() == (200, 200, 0)
    with pytest.raises(ValueError, match='global budget'): claim(capped, 'over-global')
    assert capped.life_counts(DAY, development_run=True)[2] == 11


def test_interrupted_grant_rolls_back_schema_marker_and_rows_together(tmp_path, monkeypatch):
    path = tmp_path / 'interrupted'
    budget = budget_at(path)
    before = snapshot(path)
    original = budget._transaction
    @contextmanager
    def interrupted():
        with original() as db:
            yield db
            raise RuntimeError('synthetic interruption before commit')
    monkeypatch.setattr(budget, '_transaction', interrupted)
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        grant(budget)
    monkeypatch.setattr(budget, '_transaction', original)
    assert snapshot(path) == before
    restored = FirstLifeBudget(path, civil_day=lambda: DAY)
    assert restored.life_counts(DAY, development_run=True)[2] == 0
    with sqlite3.connect(path / 'attempts.sqlite3') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0
        assert not db.execute("SELECT name FROM sqlite_schema WHERE name='life_development_grant'").fetchall()
    assert grant(restored) == 36


def _parallel_claim(path, index):
    budget = FirstLifeBudget(Path(path), civil_day=lambda: DAY)
    grant(budget)
    try:
        claim(budget, f'parallel-{index}')
        return 'claimed'
    except ValueError as error:
        return str(error)


def test_multi_process_grant_and_last_claim_are_atomic(tmp_path):
    path = tmp_path / 'parallel'
    budget = budget_at(path)
    # Separate processes race the same first approval as well as usage claims.
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as workers:
        results = list(workers.map(_parallel_claim, [str(path)] * 16, range(16)))
    assert results.count('claimed') == 12
    assert results.count('development quota exhausted') == 4
    assert budget.counts() == (200, 97, 103)
    assert budget.life_counts(DAY, development_run=True)[2] == 0
    with sqlite3.connect(path / 'attempts.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM life_development_grant').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM life_limit_claim WHERE development_scope=?', (DEVELOPMENT_SCOPE,)).fetchone()[0] == 36

"""S114: one approved 18-attempt sublimit inside S112's existing 42/0 ledger.

Opening evidence: experiments/s113/CONTRACT.md and continuous-proposal.json
approve at most 18 of the original 20 remaining attempts, not a new allowance.
CharacterChatBudget already owns SQLite BEGIN IMMEDIATE/FULL transactions and
the one canonical stage chain. Reuse that writer and add only a grant, ordinal
mapping and head in the same database; retain the original tables/user_version
and old-reader behavior. No new dependency, request data or credential purpose.

Acceptance: exact terminal 22-row opening prefix, one immutable approval digest,
atomic parent/subclaim, both caps under contention, unknown attempts retained,
and missing metadata rejected. A directory witness plus the fixed S114 prefix
prevents recreating 18 after consumed grant metadata is lost. It does not defend
against restoring the entire filesystem/database to a previous valid snapshot.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.frozen_attempt import canonical_json


CANDIDATE_LIMIT = 18
_PARENT_TOTAL = 42
_S114_OPENING_COUNT = 22  # This approval is explicitly tied to S112's closed run.
_MARKER = "s114-candidate-allowance"
_GRANT = "s114_candidate_grant"
_CLAIM = "s114_candidate_claim"
_HEAD = "s114_candidate_head"
_TABLES = frozenset((_GRANT, _CLAIM, _HEAD))


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _body(budget, prefix, grant_digest):
    return dict(version="s114-candidate-allowance-1", grant_digest=grant_digest,
        limit=CANDIDATE_LIMIT, parent_config_digest=budget._hash(budget.config),
        parent_prefix_count=_S114_OPENING_COUNT, parent_prefix_digest=budget._chain(prefix))


def _claim_chain(grant_hash, claims):
    head = grant_hash
    for row in claims:
        head = sha256((head + ":" + row[-1]).encode()).hexdigest()
    return head


def _tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}.intersection(_TABLES)


class CandidateTrialBudget(CharacterChatBudget):
    """One grant's count, bounded additionally by its unchanged parent ledger.

    counts() returns (18, grant_used, currently_available). Available is the
    minimum of the grant's unused slots and parent remaining, so total-used
    need not equal available. parent_counts() returns the original 42-wide facts.
    Construction only verifies an existing grant; it never grants or repairs.
    """

    def __init__(self, path: Path, *, grant_digest):
        if not _digest(grant_digest):
            raise ValueError("exact S114 grant digest required")
        self.grant_digest = grant_digest
        super().__init__(path, total=_PARENT_TOTAL, initial_used=0)
        with self._transaction() as db:
            self._candidate_verified(db)

    def _candidate_verified(self, db):
        used, stages = CharacterChatBudget._verified(self, db)
        if not (self.path / _MARKER).is_dir() or _tables(db) != _TABLES:
            raise ValueError("candidate grant witness or tables missing")
        try:
            grants = db.execute("SELECT singleton,body,body_digest FROM s114_candidate_grant").fetchall()
            prefix = stages[:_S114_OPENING_COUNT]
            if (len(prefix) != _S114_OPENING_COUNT or any(row[5] == "claimed" for row in prefix)
                or len(grants) != 1 or grants[0][0] != 1):
                raise ValueError("candidate opening prefix or grant invalid")
            expected = _body(self, prefix, self.grant_digest)
            body = json.loads(grants[0][1])
            grant_hash = self._hash(expected)
            if body != expected or grants[0][1] != canonical_json(expected) or grants[0][2] != grant_hash:
                raise ValueError("candidate grant binding invalid")
            claims = db.execute("SELECT ordinal,stage_ordinal,stage_binding,claim_digest FROM s114_candidate_claim ORDER BY ordinal").fetchall()
            previous = _S114_OPENING_COUNT - 1
            for index, row in enumerate(claims):
                if (row[0] != index or type(row[1]) is not int or not previous < row[1] < len(stages)
                    or row[2] != self._hash(list(stages[row[1]][:5]))
                    or row[3] != self._hash([grant_hash, *row[:-1]])):
                    raise ValueError("candidate stage mapping invalid")
                previous = row[1]
            heads = db.execute("SELECT singleton,claim_count,chain_head FROM s114_candidate_head").fetchall()
            if heads != [(1, len(claims), _claim_chain(grant_hash, claims))] or len(claims) > CANDIDATE_LIMIT:
                raise ValueError("candidate cumulative head invalid")
        except (ValueError, TypeError, KeyError, IndexError, sqlite3.DatabaseError):
            raise ValueError("candidate grant integrity failed") from None
        return used, stages, claims, grant_hash

    def counts(self):
        with self._transaction() as db:
            used, _, claims, _ = self._candidate_verified(db)
            return CANDIDATE_LIMIT, len(claims), min(CANDIDATE_LIMIT - len(claims), _PARENT_TOTAL - used)

    def parent_counts(self):
        with self._transaction() as db:
            used, _, _, _ = self._candidate_verified(db)
            return _PARENT_TOTAL, used, _PARENT_TOTAL - used

    def claim(self, identity_digest, operation_digest, stage, request_digest):
        if stage not in ("planning", "expression") or not all(_digest(value) for value in (identity_digest, operation_digest, request_digest)):
            raise ValueError("exact candidate stage claim required")
        with self._transaction() as db:
            used, stages, claims, grant_hash = self._candidate_verified(db)
            if len(claims) >= CANDIDATE_LIMIT or used >= _PARENT_TOTAL:
                raise ValueError("candidate or parent budget exhausted")
            if any(row[1:4] == (identity_digest, operation_digest, stage) for row in stages):
                raise ValueError("candidate stage already attempted")
            record = [len(stages), identity_digest, operation_digest, stage, request_digest, "claimed", None]
            db.execute("INSERT INTO stage_attempt VALUES(?,?,?,?,?,?,?,?)", (*record, self._hash(record)))
            self._update_head(db)
            mapping = [len(claims), len(stages), self._hash(record[:5])]
            claim_row = (*mapping, self._hash([grant_hash, *mapping]))
            db.execute("INSERT INTO s114_candidate_claim VALUES(?,?,?,?)", claim_row)
            db.execute("UPDATE s114_candidate_head SET claim_count=?,chain_head=? WHERE singleton=1",
                (len(claims) + 1, _claim_chain(grant_hash, [*claims, claim_row])))

    def record(self, identity_digest, operation_digest, stage, *, status, output_digest=None):
        if (status not in ("complete", "unavailable", "unknown", "failed-closed")
            or output_digest is not None and not _digest(output_digest)):
            raise ValueError("closed candidate status and bounded output digest required")
        with self._transaction() as db:
            _, stages, claims, _ = self._candidate_verified(db)
            row = next((row for row in stages if row[1:4] == (identity_digest, operation_digest, stage)), None)
            if row is None or row[5] != "claimed" or row[0] not in {claim[1] for claim in claims}:
                raise ValueError("candidate result without its uncompleted claim")
            record = [*row[:5], status, output_digest]
            db.execute("UPDATE stage_attempt SET status=?,output_digest=?,record_digest=? WHERE ordinal=?",
                (status, output_digest, self._hash(record), row[0]))
            self._update_head(db)


def approve_candidate_allowance(parent_budget, *, grant_digest, confirmed=True):
    """Persist the already-approved exact S114 sublimit and return its reader.

    This is not a standalone user authorization: composition validates the
    approved manifest. Only its digest and closed parent prefix are stored here.
    Same-digest replay is idempotent; missing/partial metadata is never repaired.
    """
    if (type(parent_budget) is not CharacterChatBudget or confirmed is not True or not _digest(grant_digest)
        or parent_budget.config["total"] != _PARENT_TOTAL or parent_budget.config["initial_used"] != 0):
        raise ValueError("exact confirmed candidate grant on the S112 parent required")
    marker = parent_budget.path / _MARKER
    with parent_budget._transaction() as db:
        used, stages = parent_budget._verified(db)
        present = _tables(db)
        if marker.exists() or present:
            if not marker.is_dir() or present != _TABLES:
                raise ValueError("candidate grant witness or tables missing")
            # Verify within this same lock using a reader that cannot initialize.
            reader = object.__new__(CandidateTrialBudget)
            reader.path, reader.config, reader.grant_digest = parent_budget.path, parent_budget.config, grant_digest
            reader._candidate_verified(db)
        else:
            if (used != _S114_OPENING_COUNT or len(stages) != _S114_OPENING_COUNT
                or _PARENT_TOTAL - used < CANDIDATE_LIMIT or any(row[5] == "claimed" for row in stages)):
                raise ValueError("S114 requires its exact closed 22-attempt opening prefix")
            # Claim the initialization once. A crash before SQL COMMIT leaves
            # this marker, causing future opens/approvals to fail closed.
            marker.mkdir(exist_ok=False)
            db.execute("CREATE TABLE s114_candidate_grant (singleton INTEGER PRIMARY KEY CHECK(singleton=1),body TEXT NOT NULL,body_digest TEXT NOT NULL)")
            db.execute("CREATE TABLE s114_candidate_claim (ordinal INTEGER PRIMARY KEY,stage_ordinal INTEGER NOT NULL UNIQUE REFERENCES stage_attempt(ordinal),stage_binding TEXT NOT NULL,claim_digest TEXT NOT NULL)")
            db.execute("CREATE TABLE s114_candidate_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1),claim_count INTEGER NOT NULL,chain_head TEXT NOT NULL)")
            body = _body(parent_budget, stages, grant_digest)
            grant_hash = parent_budget._hash(body)
            db.execute("INSERT INTO s114_candidate_grant VALUES(1,?,?)", (canonical_json(body), grant_hash))
            db.execute("INSERT INTO s114_candidate_head VALUES(1,0,?)", (_claim_chain(grant_hash, []),))
    return CandidateTrialBudget(parent_budget.path, grant_digest=grant_digest)

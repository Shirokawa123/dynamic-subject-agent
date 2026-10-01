"""Metadata-only development call audit under the 2026-10-01 unlimited grant.

S116 supersedes quantity limits for already-authorized DeepSeek development,
including S115's protocol comparison. The eight planned cases are experimental
design, not a resource cap. This module never opens or upgrades finite ledgers.

Reuse CharacterChatBudget's proven SQLite FULL/BEGIN IMMEDIATE transaction and
verified chain/head mechanism, without its count limit or parent allocation.
One claim is durably unique before delivery; terminal/unknown attempts stay
counted. No request/response text, credentials, network or chat state belongs
here. The controller still verifies each approved material/provider purpose.

An existing directory and initialization marker cannot be repaired into a fresh
audit. As with the existing ledger, restoring an entire older valid filesystem
snapshot is outside this local integrity guarantee. No new dependencies.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import re
import sqlite3

from dynamic_subject_agent.frozen_attempt import canonical_json


AUTHORIZATION = "user-unlimited-model-development-2026-10-01"
PURPOSES = frozenset(("reply-protocol-comparison", "continuous-reply-development"))
_TERMINAL = frozenset(("complete", "unavailable", "unknown", "failed-closed"))
_DATABASE = "calls.sqlite3"
_MARKER = "initialized"
_TABLES = frozenset(("audit_config", "call_attempt", "audit_head"))
_FIELDS = ("ordinal", "attempt_id", "request_digest", "purpose", "run_digest", "status", "output_digest")


def _configuration():
    return dict(version="development-model-call-audit-1", authorization=AUTHORIZATION,
        provider="deepseek", purpose="authorized-model-development", limit=None)


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


class DevelopmentCallAudit:
    """No quantity limit: counts() is always (None, attempted_count, None)."""

    def __init__(self, path: Path, *, initialize=False):
        if not isinstance(path, Path) or not path.is_absolute() or type(initialize) is not bool:
            raise ValueError("absolute development audit directory and exact initialization flag required")
        self.path = path
        self.config = _configuration()
        created = False
        if not path.exists():
            if not initialize:
                raise ValueError("existing development call audit required")
            path.mkdir(parents=True, exist_ok=False)
            (path / _MARKER).mkdir(exist_ok=False)
            created = True
        elif (not path.is_dir() or not (path / _MARKER).is_dir()
            or not (path / _DATABASE).is_file()):
            raise ValueError("development audit initialization witness or database missing")
        self._allow_create = created
        with self._transaction() as db:
            if created:
                db.execute("CREATE TABLE audit_config (singleton INTEGER PRIMARY KEY CHECK(singleton=1), body TEXT NOT NULL)")
                db.execute("CREATE TABLE call_attempt (ordinal INTEGER PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL, purpose TEXT NOT NULL, run_digest TEXT NOT NULL, status TEXT NOT NULL, output_digest TEXT, record_digest TEXT NOT NULL)")
                db.execute("CREATE TABLE audit_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), claim_count INTEGER NOT NULL, chain_head TEXT NOT NULL)")
                db.execute("INSERT INTO audit_config VALUES(1,?)", (canonical_json(self.config),))
                db.execute("INSERT INTO audit_head VALUES(1,0,?)", (self._chain([]),))
            self._verified(db)
        self._allow_create = False

    @contextmanager
    def _transaction(self):
        if (not (self.path / _MARKER).is_dir()
            or not self._allow_create and not (self.path / _DATABASE).is_file()):
            raise ValueError("development audit initialization witness or database missing")
        db = sqlite3.connect(self.path / _DATABASE, timeout=5, autocommit=True)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _hash(value):
        return sha256(canonical_json(value).encode()).hexdigest()

    def _chain(self, rows):
        head = self._hash(_configuration())
        for row in rows:
            head = sha256((head + ":" + row[-1]).encode()).hexdigest()
        return head

    def _verified(self, db):
        try:
            if (self.config != _configuration()
                or {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")} != _TABLES
                or db.execute("SELECT singleton,body FROM audit_config").fetchall() != [(1, canonical_json(_configuration()))]):
                raise ValueError("development audit configuration invalid")
            rows = db.execute("SELECT ordinal,attempt_id,request_digest,purpose,run_digest,status,output_digest,record_digest FROM call_attempt ORDER BY ordinal").fetchall()
            seen = set()
            for index, row in enumerate(rows):
                if (row[0] != index or row[1] in seen or not all(_digest(row[column]) for column in (1, 2, 4))
                    or row[3] not in PURPOSES or row[5] not in _TERMINAL | {"claimed"}
                    or row[6] is not None and not _digest(row[6])
                    or row[5] == "claimed" and row[6] is not None
                    or row[7] != self._hash(list(row[:-1]))):
                    raise ValueError("development attempt integrity failed")
                seen.add(row[1])
            if db.execute("SELECT singleton,claim_count,chain_head FROM audit_head").fetchall() != [(1, len(rows), self._chain(rows))]:
                raise ValueError("development audit cumulative head invalid")
        except (sqlite3.DatabaseError, ValueError, TypeError, IndexError):
            raise ValueError("development call audit integrity failed") from None
        return rows

    def _update_head(self, db):
        rows = db.execute("SELECT ordinal,attempt_id,request_digest,purpose,run_digest,status,output_digest,record_digest FROM call_attempt ORDER BY ordinal").fetchall()
        db.execute("UPDATE audit_head SET claim_count=?,chain_head=? WHERE singleton=1", (len(rows), self._chain(rows)))

    def counts(self):
        with self._transaction() as db:
            return None, len(self._verified(db)), None

    def query(self, attempt_id):
        if not _digest(attempt_id):
            raise ValueError("exact attempt digest required")
        with self._transaction() as db:
            row = next((row for row in self._verified(db) if row[1] == attempt_id), None)
            return None if row is None else dict(zip(_FIELDS, row[:-1], strict=True))

    def claim(self, attempt_id, request_digest, *, purpose, run_digest):
        if not all(_digest(value) for value in (attempt_id, request_digest, run_digest)) or purpose not in PURPOSES:
            raise ValueError("exact development attempt metadata and approved purpose required")
        with self._transaction() as db:
            rows = self._verified(db)
            if any(row[1] == attempt_id for row in rows):
                raise ValueError("development attempt already claimed")
            record = [len(rows), attempt_id, request_digest, purpose, run_digest, "claimed", None]
            db.execute("INSERT INTO call_attempt VALUES(?,?,?,?,?,?,?,?)", (*record, self._hash(record)))
            self._update_head(db)

    def record(self, attempt_id, *, status, output_digest=None):
        if (not _digest(attempt_id) or status not in _TERMINAL
            or output_digest is not None and not _digest(output_digest)):
            raise ValueError("exact terminal development attempt metadata required")
        with self._transaction() as db:
            rows = self._verified(db)
            row = next((row for row in rows if row[1] == attempt_id), None)
            if row is None or row[5] != "claimed":
                raise ValueError("development result requires an uncompleted claim")
            record = [*row[:5], status, output_digest]
            db.execute("UPDATE call_attempt SET status=?,output_digest=?,record_digest=? WHERE ordinal=?",
                (status, output_digest, self._hash(record), row[0]))
            self._update_head(db)

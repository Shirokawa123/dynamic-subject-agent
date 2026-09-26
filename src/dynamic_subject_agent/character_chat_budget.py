"""One metadata-only, cross-process SQLite attempt budget; no chat text."""
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from dynamic_subject_agent.frozen_attempt import canonical_json


class CharacterChatBudget:
    def __init__(self, path: Path, *, total=200, initial_used=61, initialize=False):
        if (not isinstance(path, Path) or not path.is_absolute() or type(total) is not int or type(initial_used) is not int
            or not 0 <= initial_used <= total <= 200): raise ValueError("exact bounded budget required")
        self.path = path
        if type(initialize) is not bool:
            raise ValueError("existing budget ledger required")
        self.config = dict(version="character-chat-budget-1", provider="deepseek", purpose="character-continuity-use-1", total=total, initial_used=initial_used)
        created = False
        if not path.exists():
            if not initialize: raise ValueError("existing budget ledger required")
            # The dedicated directory is the durable initialization claim.
            # An interrupted or lost existing ledger is never guessed fresh.
            path.mkdir(parents=True, exist_ok=False)
            created = True
        elif not path.is_dir() or not (path / "attempts.sqlite3").is_file():
            raise ValueError("existing budget ledger required")
        self._allow_create = created
        with self._transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS config (singleton INTEGER PRIMARY KEY CHECK(singleton=1), body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS stage_attempt (ordinal INTEGER PRIMARY KEY, identity_digest TEXT NOT NULL, operation_digest TEXT NOT NULL, stage TEXT NOT NULL, request_digest TEXT NOT NULL, status TEXT NOT NULL, output_digest TEXT, record_digest TEXT NOT NULL, UNIQUE(identity_digest, operation_digest, stage))")
            db.execute("CREATE TABLE IF NOT EXISTS ledger_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), claim_count INTEGER NOT NULL, chain_head TEXT NOT NULL)")
            row = db.execute("SELECT body FROM config WHERE singleton=1").fetchone()
            if row is None:
                if not created: raise ValueError("budget configuration missing")
                if db.execute("SELECT COUNT(*) FROM stage_attempt").fetchone()[0]: raise ValueError("budget configuration missing")
                if db.execute("SELECT COUNT(*) FROM ledger_head").fetchone()[0]: raise ValueError("budget head without configuration")
                db.execute("INSERT INTO config VALUES (1,?)", (canonical_json(self.config),))
                db.execute("INSERT INTO ledger_head VALUES (1,0,?)", (self._chain([]),))
            elif row[0] != canonical_json(self.config): raise ValueError("budget initialization conflict")
            self._verified(db)
        self._allow_create = False

    @contextmanager
    def _transaction(self):
        if not self._allow_create and not (self.path / "attempts.sqlite3").is_file(): raise ValueError("budget ledger missing")
        db = sqlite3.connect(self.path / "attempts.sqlite3", timeout=5, autocommit=True)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction: db.execute("ROLLBACK")
            raise
        finally: db.close()

    @staticmethod
    def _hash(row): return sha256(canonical_json(row).encode()).hexdigest()

    def _chain(self, rows):
        head = self._hash(self.config)
        for row in rows:
            head = sha256((head + ":" + row[-1]).encode()).hexdigest()
        return head

    def _update_head(self, db):
        rows = db.execute("SELECT ordinal, identity_digest, operation_digest, stage, request_digest, status, output_digest, record_digest FROM stage_attempt ORDER BY ordinal").fetchall()
        db.execute("UPDATE ledger_head SET claim_count=?, chain_head=? WHERE singleton=1", (len(rows), self._chain(rows)))

    def _verified(self, db):
        if db.execute("SELECT body FROM config WHERE singleton=1").fetchone()[0] != canonical_json(self.config):
            raise ValueError("budget configuration changed")
        rows = db.execute("SELECT ordinal, identity_digest, operation_digest, stage, request_digest, status, output_digest, record_digest FROM stage_attempt ORDER BY ordinal").fetchall()
        for index, row in enumerate(rows):
            if (row[0] != index or row[3] not in ("planning", "expression")
                or row[5] not in ("claimed", "complete", "unavailable", "unknown", "failed-closed")
                or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in (row[1], row[2], row[4]))
                or (row[6] is not None and re.fullmatch(r"[0-9a-f]{64}", row[6]) is None)
                or self._hash(list(row[:-1])) != row[7]): raise ValueError("budget attempt integrity failed")
        head = db.execute("SELECT claim_count, chain_head FROM ledger_head WHERE singleton=1").fetchone()
        if head is None or head != (len(rows), self._chain(rows)):
            raise ValueError("budget cumulative head integrity failed")
        used = self.config["initial_used"] + len(rows)
        if used > self.config["total"]: raise ValueError("budget exceeded")
        return used, rows

    def counts(self):
        with self._transaction() as db: used, _ = self._verified(db)
        return self.config["total"], used, self.config["total"] - used

    def claim(self, identity_digest, operation_digest, stage, request_digest):
        with self._transaction() as db:
            used, rows = self._verified(db)
            if any(row[1:4] == (identity_digest, operation_digest, stage) for row in rows):
                raise ValueError("chat-stage-already-attempted")
            if used >= self.config["total"]: raise ValueError("chat-budget-exhausted")
            record = [len(rows), identity_digest, operation_digest, stage, request_digest, "claimed", None]
            if stage not in ("planning", "expression") or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in (identity_digest, operation_digest, request_digest)):
                raise ValueError("chat claim invalid")
            db.execute("INSERT INTO stage_attempt VALUES (?,?,?,?,?,?,?,?)", (*record, self._hash(record)))
            self._update_head(db)

    def record(self, identity_digest, operation_digest, stage, *, status, output_digest=None):
        if status not in ("complete", "unavailable", "unknown", "failed-closed"): raise ValueError("closed chat status required")
        with self._transaction() as db:
            _, rows = self._verified(db)
            row = next((row for row in rows if row[1:4] == (identity_digest, operation_digest, stage)), None)
            if row is None or row[5] != "claimed": raise ValueError("chat result without uncompleted claim")
            record = [*row[:5], status, output_digest]
            db.execute("UPDATE stage_attempt SET status=?, output_digest=?, record_digest=? WHERE ordinal=?", (status, output_digest, self._hash(record), row[0]))
            self._update_head(db)

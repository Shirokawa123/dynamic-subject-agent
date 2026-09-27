"""Life/day/development usage metadata in the existing shared attempt ledger."""
from datetime import date
from hashlib import sha256
import re

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.first_life import DEVELOPMENT_SCOPE, current_civil_day

PURPOSES = ("life-decision", "life-share", "chat-planning", "chat-expression")


class FirstLifeBudget(CharacterChatBudget):
    def __init__(self, path, *, total=200, initial_used=61, civil_day=None):
        self._civil_day = current_civil_day if civil_day is None else civil_day
        super().__init__(path, total=total, initial_used=initial_used)
        marker = path / "first-life-limits"
        created = False
        if not marker.exists():
            marker.mkdir(exist_ok=False)
            created = True
        with self._transaction() as db:
            present = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            required = {"life_limit_claim", "life_limit_head"}
            if not created and not required.issubset(present): raise ValueError("life limits missing")
            db.execute("CREATE TABLE IF NOT EXISTS life_limit_claim (stage_ordinal INTEGER PRIMARY KEY REFERENCES stage_attempt(ordinal), purpose TEXT NOT NULL, civil_day TEXT NOT NULL, development_scope TEXT, stage_binding TEXT NOT NULL, claim_digest TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS life_limit_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), count INTEGER NOT NULL, chain_head TEXT NOT NULL)")
            head = db.execute("SELECT count,chain_head FROM life_limit_head WHERE singleton=1").fetchone()
            if head is None:
                if not created or required.intersection(present) or db.execute("SELECT COUNT(*) FROM life_limit_claim").fetchone()[0]: raise ValueError("life limit head missing")
                db.execute("INSERT INTO life_limit_head VALUES(1,0,?)", (self._life_chain([]),))
            self._life_verified(db)

    def _life_chain(self, rows):
        head = self._hash(dict(version="first-life-limits-1", daily_decisions=6, daily_share_calls=2, development_calls=24))
        for row in rows: head = sha256((head + ":" + row[-1]).encode()).hexdigest()
        return head

    def _life_verified(self, db):
        _, stages = self._verified(db)
        rows = db.execute("SELECT stage_ordinal,purpose,civil_day,development_scope,stage_binding,claim_digest FROM life_limit_claim ORDER BY stage_ordinal").fetchall()
        for row in rows:
            if (type(row[0]) is not int or not 0 <= row[0] < len(stages) or row[1] not in PURPOSES
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

    def claim_life(self, identity_digest, operation_digest, stage, request_digest, *, purpose, civil_day, development_run):
        if purpose not in PURPOSES or type(development_run) is not bool: raise ValueError("exact life purpose required")
        if stage != ("planning" if purpose in ("life-decision", "chat-planning") else "expression"): raise ValueError("stage purpose mismatch")
        if date.fromisoformat(civil_day).isoformat() != civil_day: raise ValueError("real civil day required")
        with self._transaction() as db:
            trusted_day = self._civil_day()
            if civil_day != trusted_day: raise ValueError("first-life-call-day-expired")
            used, stages = self._verified(db); life = self._life_verified(db)
            if used >= self.config["total"]: raise ValueError("global budget exhausted")
            if development_run and sum(row[3] == DEVELOPMENT_SCOPE for row in life) >= 24: raise ValueError("development quota exhausted")
            if purpose in ("life-decision", "life-share") and sum(row[1] == purpose and row[2] == civil_day for row in life) >= (6 if purpose == "life-decision" else 2):
                raise ValueError("daily life quota exhausted")
            if any(row[1:4] == (identity_digest, operation_digest, stage) for row in stages): raise ValueError("life stage already attempted")
            if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in (identity_digest, operation_digest, request_digest)): raise ValueError("life claim digest invalid")
            record = [len(stages), identity_digest, operation_digest, stage, request_digest, "claimed", None]
            db.execute("INSERT INTO stage_attempt VALUES(?,?,?,?,?,?,?,?)", (*record, self._hash(record)))
            claim = [len(stages), purpose, civil_day, DEVELOPMENT_SCOPE if development_run else None, self._hash(record[:5])]
            db.execute("INSERT INTO life_limit_claim VALUES(?,?,?,?,?,?)", (*claim, self._hash(claim)))
            self._update_head(db)
            rows = db.execute("SELECT stage_ordinal,purpose,civil_day,development_scope,stage_binding,claim_digest FROM life_limit_claim ORDER BY stage_ordinal").fetchall()
            db.execute("UPDATE life_limit_head SET count=?,chain_head=? WHERE singleton=1", (len(rows), self._life_chain(rows)))

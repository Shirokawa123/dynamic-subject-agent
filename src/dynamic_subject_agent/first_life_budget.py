"""Life/day/development usage metadata in the existing shared attempt ledger."""
from datetime import date
from hashlib import sha256
import json
import re

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.first_life import DEVELOPMENT_SCOPE, current_civil_day

PURPOSES = ("life-decision", "life-share", "chat-planning", "chat-expression")
DEVELOPMENT_EXTENSION_ID = "s107-development-24-to-36-2026-09-27"
FOLLOWUP_DEVELOPMENT_EXTENSION_ID = "s108-development-36-to-44-2026-09-28"
_DEVELOPMENT_GRANT_TABLE = "life_development_grant"
_FOLLOWUP_GRANT_TABLE = "life_development_followup_grant"


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
        if sum(row[3] == DEVELOPMENT_SCOPE for row in rows) > self._development_limit(db, rows):
            raise ValueError("development quota exceeded")
        return rows

    def _development_limit(self, db, life):
        """Verify the optional grant against the unchanged pre-grant life chain.

        user_version is an atomic schema-presence witness, not a new usage
        ledger. Original stage/life rows and both original hash seeds stay intact.
        """
        version = db.execute("PRAGMA user_version").fetchone()[0]
        present = db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name IN (?,?)",
            (_DEVELOPMENT_GRANT_TABLE, _FOLLOWUP_GRANT_TABLE)).fetchall()
        tables = {row[0] for row in present}
        if version == 0 and not tables:
            return 24
        if (version not in (1, 2) or _DEVELOPMENT_GRANT_TABLE not in tables
            or (_FOLLOWUP_GRANT_TABLE in tables) != (version == 2)):
            raise ValueError("development grant schema invalid")
        rows = db.execute("SELECT singleton,body,grant_digest FROM life_development_grant").fetchall()
        if len(rows) != 1 or rows[0][0] != 1:
            raise ValueError("development grant missing or ambiguous")
        try:
            body = json.loads(rows[0][1])
            prefix_count = body["life_prefix_count"]
            if (type(prefix_count) is not int or not 0 <= prefix_count <= len(life)
                or type(body["development_used_at_grant"]) is not int):
                raise ValueError("grant prefix invalid")
            prefix = life[:prefix_count]
            used = sum(row[3] == DEVELOPMENT_SCOPE for row in prefix)
            expected = self._grant_body(prefix)
            if (used > 24 or body != expected or canonical_json(expected) != rows[0][1]
                or rows[0][2] != self._hash(expected)):
                raise ValueError("grant binding invalid")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("development grant integrity failed") from error
        if version == 1:
            return 36
        followup_rows = db.execute("SELECT singleton,body,grant_digest FROM life_development_followup_grant").fetchall()
        if len(followup_rows) != 1 or followup_rows[0][0] != 1:
            raise ValueError("development followup grant missing or ambiguous")
        try:
            followup = json.loads(followup_rows[0][1])
            followup_count = followup["life_prefix_count"]
            if (type(followup_count) is not int or not prefix_count <= followup_count <= len(life)
                or type(followup["development_used_at_grant"]) is not int):
                raise ValueError("followup grant prefix invalid")
            followup_prefix = life[:followup_count]
            expected_followup = self._followup_grant_body(followup_prefix, rows[0][2])
            if (sum(row[3] == DEVELOPMENT_SCOPE for row in followup_prefix) > 36
                or followup != expected_followup or canonical_json(expected_followup) != followup_rows[0][1]
                or followup_rows[0][2] != self._hash(expected_followup)):
                raise ValueError("followup grant binding invalid")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("development followup grant integrity failed") from error
        return 44

    def _grant_body(self, life):
        return dict(version="first-life-development-grant-1", authorization_id=DEVELOPMENT_EXTENSION_ID,
            development_scope=DEVELOPMENT_SCOPE, previous_limit=24, cumulative_limit=36,
            budget_config_digest=self._hash(self.config), life_prefix_count=len(life),
            life_prefix_digest=self._life_chain(life),
            development_used_at_grant=sum(row[3] == DEVELOPMENT_SCOPE for row in life))

    def _followup_grant_body(self, life, previous_grant_digest):
        return dict(version="first-life-development-grant-2",
            authorization_id=FOLLOWUP_DEVELOPMENT_EXTENSION_ID,
            development_scope=DEVELOPMENT_SCOPE, previous_limit=36, cumulative_limit=44,
            previous_grant_digest=previous_grant_digest,
            budget_config_digest=self._hash(self.config), life_prefix_count=len(life),
            life_prefix_digest=self._life_chain(life),
            development_used_at_grant=sum(row[3] == DEVELOPMENT_SCOPE for row in life))

    def approve_development_extension(self, *, authorization_id, limit, confirmed):
        """Append the one explicitly approved 24→36 grant; never allocate calls.

        Old FirstLifeBudget readers tolerate the grant while usage is ≤24, but
        reject the first 25th development row. Reload them before extended use.
        """
        if (authorization_id != DEVELOPMENT_EXTENSION_ID or type(limit) is not int or limit != 36
            or confirmed is not True):
            raise ValueError("exact development extension approval required")
        with self._transaction() as db:
            life = self._life_verified(db)
            if self._development_limit(db, life) >= 36:
                return 36
            body = self._grant_body(life)
            db.execute("CREATE TABLE life_development_grant (singleton INTEGER PRIMARY KEY CHECK(singleton=1), body TEXT NOT NULL, grant_digest TEXT NOT NULL)")
            db.execute("INSERT INTO life_development_grant VALUES(1,?,?)", (canonical_json(body), self._hash(body)))
            db.execute("PRAGMA user_version=1")
            return self._development_limit(db, life)

    def approve_development_followup_extension(self, *, authorization_id, limit, confirmed):
        """Append the approved 36→44 grant without changing the original grant or ledger."""
        if (authorization_id != FOLLOWUP_DEVELOPMENT_EXTENSION_ID or type(limit) is not int
            or limit != 44 or confirmed is not True):
            raise ValueError("exact development followup extension approval required")
        with self._transaction() as db:
            life = self._life_verified(db)
            current_limit = self._development_limit(db, life)
            if current_limit == 44:
                return 44
            if current_limit != 36:
                raise ValueError("previous development grant required")
            previous_digest = db.execute("SELECT grant_digest FROM life_development_grant WHERE singleton=1").fetchone()[0]
            body = self._followup_grant_body(life, previous_digest)
            db.execute("CREATE TABLE life_development_followup_grant (singleton INTEGER PRIMARY KEY CHECK(singleton=1), body TEXT NOT NULL, grant_digest TEXT NOT NULL)")
            db.execute("INSERT INTO life_development_followup_grant VALUES(1,?,?)", (canonical_json(body), self._hash(body)))
            db.execute("PRAGMA user_version=2")
            return self._development_limit(db, life)

    def counts(self):
        with self._transaction() as db:
            self._life_verified(db)
            used, _ = self._verified(db)
            return self.config["total"], used, self.config["total"] - used

    def life_counts(self, civil_day, *, development_run):
        with self._transaction() as db:
            rows = self._life_verified(db)
            limit = self._development_limit(db, rows)
        return (sum(row[2] == civil_day and row[1] == "life-decision" for row in rows),
            sum(row[2] == civil_day and row[1] == "life-share" for row in rows),
            limit - sum(row[3] == DEVELOPMENT_SCOPE for row in rows) if development_run else None)

    def claim_life(self, identity_digest, operation_digest, stage, request_digest, *, purpose, civil_day, development_run):
        if purpose not in PURPOSES or type(development_run) is not bool: raise ValueError("exact life purpose required")
        if stage != ("planning" if purpose in ("life-decision", "chat-planning") else "expression"): raise ValueError("stage purpose mismatch")
        if date.fromisoformat(civil_day).isoformat() != civil_day: raise ValueError("real civil day required")
        with self._transaction() as db:
            trusted_day = self._civil_day()
            if civil_day != trusted_day: raise ValueError("first-life-call-day-expired")
            used, stages = self._verified(db); life = self._life_verified(db)
            if used >= self.config["total"]: raise ValueError("global budget exhausted")
            if development_run and sum(row[3] == DEVELOPMENT_SCOPE for row in life) >= self._development_limit(db, life):
                raise ValueError("development quota exhausted")
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

"""Reusable developer-owned, new-root Facade trials; never open a user's entry."""
from dataclasses import asdict
from hashlib import sha256
import json

from dynamic_subject_agent.first_life_free_input_trial import (
    open_free_input_reply_trial, MetadataOnlyObservations,
)
from dynamic_subject_agent.local_product import open_first_life_free_input_trial
from dynamic_subject_agent.model_gateway import ModelGateway
from dynamic_subject_agent.frozen_attempt import canonical_json
from run_s112_reply_comparison import (
    SCENARIOS_PATH, prepare_branch, SeedAdapter, seed_branch, read_history, send, Journal,
)


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


class OwnedObservations(MetadataOnlyObservations):
    """Retain structural wire facts for declared owned text, never private bodies."""
    def __init__(self, owned_users):
        super().__init__()
        self.owned_users = frozenset(owned_users)
        self.envelopes = []

    def append(self, row):
        super().append(row)
        body = row.get("request_body")
        data = json.loads(body["messages"][1]["content"]) if type(body) is dict else None
        if data is None:
            self.envelopes.append(dict(available=False))
            return
        exchange = data["exchange"]
        sources = exchange["dialogue_sources"]
        owned = (data["turn"]["current_message"] in self.owned_users and all(
            item["speaker"] != "user" or item["text"] in self.owned_users for item in sources))
        if not owned:
            self.envelopes.append(dict(available=False, foreign_content=True))
            return
        self.envelopes.append(dict(available=True, background_digest=digest(data["background"]),
            evidence_digest=digest(data["evidence"]), current_message_digest=digest(data["turn"]["current_message"]),
            history_enabled=exchange["history_enabled"], sources=[dict(
                label=item["label"], speaker=item["speaker"], kind=item["kind"],
                chars=len(item["text"]), text_digest=digest(item["text"])) for item in sources],
            source_chars=sum(len(item["text"]) for item in sources),
            system_digest=digest(body["messages"][0]["content"])))


class OwnedDialogueBranch:
    """One owner, canonical root and fixed authored messages for an entire chain."""
    def __init__(self, root, scenario_id, *, live, messages, variant="current-topic", transport=None):
        if root.exists():
            raise FileExistsError("owned trial requires a fresh root, never a retry")
        self.trial = open_free_input_reply_trial(root, SCENARIOS_PATH, live=live, confirmed=True,
            expression_variant=variant)
        scenario = next(row for row in self.trial.scenarios["scenarios"] if row["id"] == scenario_id)
        self.branch_id = scenario_id + "-A"
        self.branch = prepare_branch(root / self.branch_id, self.trial.scenarios)
        self.transport = transport
        self.messages = tuple(messages)
        if any(type(text) is not str or not text.strip() or len(text) > 1000 for text in self.messages):
            raise ValueError("bounded developer-authored messages required")
        self.trial.observations = OwnedObservations(self.messages + (self.trial.scenarios["shared_intro"]["user"],))
        seed_adapter = SeedAdapter(self.trial.scenarios, scenario)
        with self._open(ModelGateway(seed_adapter)) as seeded:
            seed = seed_branch(seeded, seed_adapter)
        self.product = self._open()
        self.initial_project = asdict(self.product.application.query_first_life().project)
        self.initial_identity = self.product.profile_id, self.product.timeline_id
        self.journal = Journal(root / "owned-dialogue.jsonl")
        self.summary = dict(version="owned-dialogue-trial-1", root=str(root), scenario_id=scenario_id,
            variant=variant, live=live, run_digest=self.trial.manifest_digest,
            seed_source_digest=seed["source_digest"], steps=[], actions=[],
            automatic_retries=0, private_user_content_exported=False)
        self.journal.append(dict(event="started", **{k:v for k,v in self.summary.items() if k not in ("steps", "actions")}))

    def _open(self, seed_gateway=None):
        return open_first_life_free_input_trial(self.branch.config, approval=self.trial,
            branch_id=self.branch_id, definition_basis=self.branch.definition_basis,
            life_scope_digest=self.branch.life_scope_digest, seed_gateway=seed_gateway,
            _transport=None if seed_gateway else self.transport)

    def contribute(self, index):
        text = self.messages[index]
        before = len(self.trial.observations)
        self.journal.append(dict(event="step-started", number=index + 1, user_text=text))
        response = send(self.product, text, f"owned-dialogue-step-{index + 1}")
        row = dict(number=index + 1, user_text=text, status=response.status.value,
            failure_code=getattr(response.projection, "failure_code", None),
            assistant_text=getattr(response.projection, "expression_text", None),
            observations=self.trial.observations[before:],
            envelopes=self.trial.observations.envelopes[before:],
            canonical_history=[asdict(turn) for turn in read_history(self.product)])
        if any(envelope.get("foreign_content") for envelope in row["envelopes"]):
            raise ValueError("foreign content; owned export stopped")
        if asdict(self.product.application.query_first_life().project) != self.initial_project:
            raise ValueError("a chat changed the saved project")
        self.summary["steps"].append(row)
        self.journal.append(dict(event="step-finished", **row))
        return response.status.value

    def reopen(self):
        saved = read_history(self.product)
        before = len(self.trial.observations)
        self.product.close()
        self.product = self._open()
        if (read_history(self.product) != saved or len(self.trial.observations) != before
            or (self.product.profile_id, self.product.timeline_id) != self.initial_identity):
            raise ValueError("cold reopen changed history/identity or generated")
        self.action("reopened", canonical_history_equal=True, additional_model_calls=0)

    def action(self, kind, **facts):
        value = dict(kind=kind, **facts)
        self.summary["actions"].append(value)
        self.journal.append(dict(event="action", **value))

    def finish(self):
        self.summary.update(actual_attempts=len(self.trial.observations),
            status="completed" if len(self.summary["steps"]) == len(self.messages)
                and all(row["status"] == "terminal" for row in self.summary["steps"]) else "stopped-failure",
            saved_project_equal=True)
        self.journal.append(dict(event="finished", status=self.summary["status"], actual_attempts=self.summary["actual_attempts"]))
        (self.trial.root / "owned-summary.json").write_text(
            json.dumps(self.summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.summary

    def close(self):
        self.product.close()
        self.journal.close()

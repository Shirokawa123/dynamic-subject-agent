"""S117: existing synthetic continuous chat, scoped JSON, unlimited call audit.

No new materials or history store: reuse S112 material validation, canonical
branches, seed admission and one-shot stage tickets. Local finite ledgers audit
only the programmed seed; real calls use the independent unlimited audit.
Old live/candidate manifests and counters remain untouched.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock, get_ident
from uuid import UUID

from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import (DeepSeekTransport, DeepSeekUrlLibTransport,
    DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID, DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS)
from dynamic_subject_agent.development_model_calls import AUTHORIZATION, DevelopmentCallAudit
from dynamic_subject_agent.first_life_budget import FirstLifeBudget
from dynamic_subject_agent.first_life_reply_drafts import draft_wire, reply_scope_digest
from dynamic_subject_agent.first_life_reply_live import ApprovedReplyTrial, SCENARIOS_DIGEST, BACKGROUND_DIGEST
from dynamic_subject_agent.first_life_reply_live_provider import LiveReplyBudget, LiveReplyAdapter, _StageTicket
from dynamic_subject_agent.first_life_reply_protocol import preview_json_example, EXAMPLE_BODY, EXAMPLE_INTRO, EXAMPLE_END
from dynamic_subject_agent.first_life_reply_routes import (DEVELOPMENT_REPLY_POLICIES,
    WHOLE_DEVELOPMENT_POLICY, PLANNED_DEVELOPMENT_POLICY, WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY,
    WHOLE_REPLY_POLICIES)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.reply_protocol_trial import (GLOBAL_STYLE_SENTENCE, REPLY_TEXT_STYLE_SENTENCE,
    fixed_development_root, fixed_development_audit_path)


PURPOSE = "continuous-reply-development"
OFFLINE_BACKEND = "s117-offline"
OFFLINE_KEY = "no-credential"


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def scoped_reply_wire(task):
    if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
        return draft_wire(task)  # v4 / low remains byte exact.
    body = json.loads(preview_json_example(task).wire)
    system = body["messages"][0]
    if system["content"].count(GLOBAL_STYLE_SENTENCE) != 1:
        raise ValueError("exact original role style required")
    system["content"] = system["content"].replace(GLOBAL_STYLE_SENTENCE, REPLY_TEXT_STYLE_SENTENCE, 1)
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError("scoped reply exceeds the existing request byte bound")
    return wire


def _contract():
    from dynamic_subject_agent.first_life_reply_candidate import ROLE_POLICY, WHOLE_OUTPUT_POLICY, EXPRESSION_OUTPUT_POLICY
    return dict(role_policy=ROLE_POLICY.replace(GLOBAL_STYLE_SENTENCE, REPLY_TEXT_STYLE_SENTENCE, 1),
        whole_output=WHOLE_OUTPUT_POLICY, expression_output=EXPRESSION_OUTPUT_POLICY,
        example=dict(body=EXAMPLE_BODY, intro=EXAMPLE_INTRO, end=EXAMPLE_END),
        protocol=communication_protocol("thinking-high", "low"))


def development_reply_scope_digest(definition_basis, policy):
    if policy not in DEVELOPMENT_REPLY_POLICIES:
        raise ValueError("exact development reply policy required")
    local = WHOLE_LOCAL_POLICY if policy == WHOLE_DEVELOPMENT_POLICY else PLANNED_LOCAL_POLICY
    return digest(dict(version=policy, authorization=AUTHORIZATION, scenarios=SCENARIOS_DIGEST,
        background=BACKGROUND_DIGEST, original_design=reply_scope_digest(definition_basis, local),
        contract=_contract(), call_limit=None, retries=0))


def fixed_continuous_runs_root():
    return fixed_development_root() / "continuous-runs"


def _manifest(root, scenarios, background, live):
    if (type(live) is not bool or str(UUID(root.name)) != root.name
        or digest(scenarios) != SCENARIOS_DIGEST or digest(background) != BACKGROUND_DIGEST):
        raise ValueError("exact original synthetic material and UUID root required")
    if live:
        if root.parent != fixed_continuous_runs_root().resolve():
            raise ValueError("fixed live development directory required")
    elif root.is_relative_to(fixed_development_root().resolve()):
        raise ValueError("offline run cannot use the live directory")
    return dict(version="s117-continuous-development-1", authorization=AUTHORIZATION, root=str(root),
        live=live, provider="deepseek", call_limit=None, retries=0,
        scenarios=scenarios, background=background, contract=_contract())


@dataclass
class DevelopmentReplyTrial:
    root: Path
    manifest_digest: str
    observations: list = field(default_factory=list)

    def _manifest(self):
        root = self.root.resolve()
        value = json.loads((root / "approval.json").read_text(encoding="utf-8"))
        if (value != _manifest(root, value["scenarios"], value["background"], value["live"])
            or digest(value) != self.manifest_digest):
            raise ValueError("development trial manifest changed")
        return value

    def shared_budget(self):
        value = self._manifest()
        path = fixed_development_audit_path() if value["live"] else self.root / "offline-audit"
        if value["live"] and not path.with_name(path.name + "-initialized").is_dir():
            raise ValueError("existing development audit witness required")
        return DevelopmentCallAudit(path)

    def read(self):
        value = self._manifest()
        self.shared_budget().counts()
        return value

    @property
    def scenarios(self):
        return self.read()["scenarios"]

    def branch(self, branch_id):
        for scenario in self.scenarios["scenarios"]:
            for letter, policy in (("A", WHOLE_DEVELOPMENT_POLICY), ("B", PLANNED_DEVELOPMENT_POLICY)):
                if branch_id == scenario["id"] + "-" + letter:
                    return scenario, policy
        raise ValueError("one of the four frozen development branches required")

    def witness(self, branch_id):
        self.branch(branch_id)
        return dict(kind="s117-development", root=str(self.root.resolve()),
            manifest_digest=self.manifest_digest, branch_id=branch_id)

    def validate_task(self, branch_id, task):
        return ApprovedReplyTrial.validate_task(self, branch_id, task)


def development_trial_from_witness(witness):
    if (type(witness) is not dict or set(witness) != {"kind", "root", "manifest_digest", "branch_id"}
        or witness["kind"] != "s117-development"):
        raise ValueError("exact development trial witness required")
    result = DevelopmentReplyTrial(Path(witness["root"]), witness["manifest_digest"])
    if result.witness(witness["branch_id"]) != witness:
        raise ValueError("development witness changed")
    return result


def open_development_reply_trial(root, scenarios_path, *, live):
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("absolute development run root required")
    root = root.resolve()
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    background = json.loads(scenarios_path.with_name("s112-reviewed-background.json").read_text(encoding="utf-8"))
    manifest = _manifest(root, scenarios, background, live)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
        with (root / "approval.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        if not live:
            DevelopmentCallAudit(root / "offline-audit", initialize=True)
    result = DevelopmentReplyTrial(root, digest(manifest))
    if result.read() != manifest:
        raise ValueError("development trial cannot be reset or repurposed")
    return result


class DevelopmentReplyBudget(LiveReplyBudget):
    """Reuse one-shot tickets; all live claims use the unlimited metadata audit."""

    def __init__(self, local, trial, branch_id):
        from dynamic_subject_agent.first_life_free_input_trial import FreeInputReplyTrial
        if type(local) is not FirstLifeBudget or type(trial) not in (DevelopmentReplyTrial, FreeInputReplyTrial):
            raise ValueError("typed development audit and trial required")
        _, policy = trial.branch(branch_id)
        if local.path.resolve() != (trial.root / branch_id / "local-stage-budget").resolve():
            raise ValueError("exact seed-only local audit required")
        self._local, self._shared, self._policy = local, trial.shared_budget(), policy
        self._run_digest, self._branch_id = trial.manifest_digest, branch_id
        self._purpose = trial.read()["call_purpose"] if type(trial) is FreeInputReplyTrial else PURPOSE
        self._lock, self._ticket, self._pending, self._poisoned = RLock(), None, None, False
        self.counts()

    def counts(self):
        with self._lock:
            self._available()
            self._local.counts()
            return self._shared.counts()

    def life_counts(self, civil_day, *, development_run):
        if development_run is not True:
            raise ValueError("development-only call audit required")
        with self._lock:
            self.counts()
            decisions, shares, _ = self._local.life_counts(civil_day, development_run=True)
            return decisions, shares, None

    def _attempt(self, identity, operation, stage):
        return digest(dict(run=self._run_digest, branch=self._branch_id,
            identity=identity, operation=operation, stage=stage))

    def claim_life(self, identity_digest, operation_digest, stage, request_digest, *, purpose, civil_day, development_run):
        with self._lock:
            self._available()
            if (self._pending is not None or development_run is not True
                or purpose not in ("chat-planning", "chat-expression")
                or stage != ("planning" if purpose == "chat-planning" else "expression")
                or self.policy in WHOLE_REPLY_POLICIES and stage != "expression"):
                raise ValueError("one approved new development chat stage required")
            try:
                self._shared.claim(self._attempt(identity_digest, operation_digest, stage), request_digest,
                    purpose=self._purpose, run_digest=self._run_digest)
            except Exception:
                self._poisoned = True
                raise ValueError("development claim unavailable; no resend") from None
            self._pending = self._ticket = _StageTicket(identity_digest, operation_digest,
                stage, request_digest, self.policy, get_ident())

    def record(self, identity_digest, operation_digest, stage, *, status, output_digest=None):
        with self._lock:
            self._available()
            pending = self._pending
            if (pending is None or (pending.identity, pending.operation, pending.stage) != (identity_digest, operation_digest, stage)
                or pending.thread != get_ident() or self._ticket is not None):
                raise ValueError("consumed same-thread development claim required")
            try:
                self._shared.record(self._attempt(identity_digest, operation_digest, stage), status=status, output_digest=output_digest)
            except Exception:
                self._poisoned = True
                raise ValueError("development result audit failed") from None
            self._pending = None


class DevelopmentReplyAdapter(LiveReplyAdapter):
    """Existing strict delivery and diagnostics, exact new scoped wire only."""
    _development_wire = True

    def __init__(self, transport, credential_ref, budget, *, approval, branch_id):
        from dynamic_subject_agent.first_life_free_input_trial import FreeInputReplyTrial
        if (not isinstance(transport, DeepSeekTransport) or type(credential_ref) is not CredentialRef
            or type(budget) is not DevelopmentReplyBudget or type(approval) not in (DevelopmentReplyTrial, FreeInputReplyTrial)
            or DEEPSEEK_ENDPOINT != "https://api.deepseek.com/chat/completions" or DEEPSEEK_TIMEOUT_SECONDS != 30):
            raise ValueError("typed development transport and authority required")
        self._transport, self._credential_ref, self._budget = transport, credential_ref, budget
        self._approval, self._branch_id = approval, branch_id
        self._request_guard = lambda task: approval.validate_task(branch_id, task)
        self._real_credential = approval.read()["live"]
        self.rows = []
        self._verify_real_authority()

    def _verify_real_authority(self):
        manifest = self._approval.read()
        expected_ref = (DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID) if manifest["live"] else (OFFLINE_BACKEND, OFFLINE_KEY)
        from dynamic_subject_agent.first_life_free_input_trial import FreeInputReplyTrial, fixed_free_input_audit_path
        live_audit = fixed_free_input_audit_path() if type(self._approval) is FreeInputReplyTrial else fixed_development_audit_path()
        expected_path = live_audit if manifest["live"] else self._approval.root / "offline-audit"
        _, policy = self._approval.branch(self._branch_id)
        if (self._budget.policy != policy or self._budget._run_digest != self._approval.manifest_digest
            or self._budget._branch_id != self._branch_id
            or self._budget._purpose != manifest.get("call_purpose", PURPOSE)
            or self._budget._shared.path.resolve() != expected_path.resolve()
            or (self._credential_ref.backend_id, self._credential_ref.key_id) != expected_ref
            or not manifest["live"] and isinstance(self._transport, DeepSeekUrlLibTransport)):
            raise ValueError("development transport/credential/audit purpose mismatch")

    def _wire(self, task):
        from dynamic_subject_agent.first_life_free_input_trial import FreeInputReplyTrial, expression_wire
        if type(self._approval) is FreeInputReplyTrial:
            return expression_wire(task, self._approval.read().get("expression_variant", "baseline"))
        return scoped_reply_wire(task)

    def invoke(self, task):
        self._verify_real_authority()
        return super().invoke(task)

    def _validate_received(self, value):
        if type(value) is dict and value.get("reply_text") == EXAMPLE_BODY:
            raise ModelGatewayFailure("structured-choice-invalid")

"""S112's separate live allowance and one-shot delivery; no seed or retry path.

The shared ledger is the sole real-attempt count. The local life ledger only
audits branch stages. Their commits are deliberately conservative, not atomic:
an interrupted or failed half-commit never refunds a claim or permits resending.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from threading import RLock, get_ident
from time import perf_counter

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS, DeepSeekHttpResponse,
    DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID,
    DeepSeekResponseDiagnosticFailure, _ACCEPTED_RESPONSE_MODELS, _post_json_reply_content,
)
from dynamic_subject_agent.first_life_budget import FirstLifeBudget
from dynamic_subject_agent.first_life_reply_drafts import draft_wire
from dynamic_subject_agent.first_life_reply_routes import (
    WHOLE_LIVE_POLICY, PLANNED_LIVE_POLICY, REMOTE_REPLY_POLICIES,
    WHOLE_REPLY_POLICIES, CANDIDATE_REPLY_POLICIES,
)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ModelTask, ModelTaskKind, ModelResult, ModelGatewayFailure,
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
)


@dataclass(frozen=True)
class _StageTicket:
    identity: str
    operation: str
    stage: str
    request: str
    policy: str
    thread: int


class LiveReplyBudget:
    """Bridge one branch audit to the fixed, shared 42-attempt experiment cap."""

    def __init__(self, local_budget: FirstLifeBudget, shared_budget: CharacterChatBudget, *, policy: str):
        from dynamic_subject_agent.first_life_candidate_budget import CandidateTrialBudget
        expected_budget = CandidateTrialBudget if policy in CANDIDATE_REPLY_POLICIES else CharacterChatBudget
        if (not isinstance(local_budget, FirstLifeBudget) or type(shared_budget) is not expected_budget
            or policy not in REMOTE_REPLY_POLICIES
            or shared_budget.config["total"] != 42 or shared_budget.config["initial_used"] != 0
            or local_budget.path.resolve() == shared_budget.path.resolve()):
            raise ValueError("separate branch audit and exact shared S112 allowance required")
        local_budget.counts()
        shared_budget.counts()
        self._local, self._shared, self._policy = local_budget, shared_budget, policy
        self._lock = RLock()
        self._ticket = self._pending = None
        self._poisoned = False

    @property
    def policy(self):
        return self._policy

    def _available(self):
        if self._poisoned:
            raise ValueError("live allowance audit requires explicit failure handling")

    def counts(self):
        with self._lock:
            self._available()
            self._local.counts()
            return self._shared.counts()

    def life_counts(self, civil_day, *, development_run):
        with self._lock:
            self._available()
            return self._local.life_counts(civil_day, development_run=development_run)

    def claim_life(self, identity_digest, operation_digest, stage, request_digest, *, purpose, civil_day, development_run):
        with self._lock:
            self._available()
            if (self._pending is not None or development_run is not True
                or purpose not in ("chat-planning", "chat-expression")
                or stage != ("planning" if purpose == "chat-planning" else "expression")
                or self.policy in WHOLE_REPLY_POLICIES and purpose != "chat-expression"):
                raise ValueError("one new stage on the exact live reply route required")
            try:
                self._local.claim_life(identity_digest, operation_digest, stage, request_digest,
                    purpose=purpose, civil_day=civil_day, development_run=True)
                self._shared.claim(identity_digest, operation_digest, stage, request_digest)
            except Exception:
                self._poisoned = True
                raise ValueError("live stage claim did not complete safely") from None
            ticket = _StageTicket(identity_digest, operation_digest, stage, request_digest, self.policy, get_ident())
            self._pending = self._ticket = ticket

    def consume(self, task):
        """Burn a current in-process claim before validating or sending its task.

        Persisted claimed rows never issue tickets. Invalid use burns this ticket
        too, so correcting a task cannot accidentally retry a delivery attempt.
        """
        with self._lock:
            self._available()
            ticket, self._ticket = self._ticket, None
            allowed = ({ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY: "expression"}
                if self.policy in WHOLE_REPLY_POLICIES else {
                    ModelTaskKind.CHARACTER_COMMUNICATION_PLAN: "planning",
                    ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION: "expression"})
            if (ticket is None or type(task) is not ModelTask or task.kind not in allowed
                or ticket.thread != get_ident() or ticket.policy != self.policy
                or ticket.stage != allowed[task.kind]):
                raise ValueError("current one-shot live stage ticket required")
            try:
                request = sha256(canonical_json(asdict(task.payload)).encode()).hexdigest()
            except Exception:
                raise ValueError("exact typed live payload required") from None
            if request != ticket.request:
                raise ValueError("live payload does not match claimed request")

    def record(self, identity_digest, operation_digest, stage, *, status, output_digest=None):
        with self._lock:
            self._available()
            pending = self._pending
            if (pending is None or (pending.identity, pending.operation, pending.stage) != (
                identity_digest, operation_digest, stage) or pending.thread != get_ident()
                or self._ticket is not None):
                raise ValueError("consumed same-thread live claim required for result")
            failed = False
            # Each write is attempted, but no half-completed write is retried.
            for budget in (self._shared, self._local):
                try:
                    budget.record(identity_digest, operation_digest, stage, status=status, output_digest=output_digest)
                except Exception:
                    failed = True
            self._pending = None
            if failed:
                self._poisoned = True
                raise ValueError("live result audit did not complete safely") from None


class _ObservedTransport:
    """Keep bounded final content and scalar usage, never the response envelope."""

    def __init__(self, transport):
        self.transport = transport
        self.row = dict(model=None, usage={}, finish_reason=None, final_content=None)

    def post_json(self, **kwargs):
        response = self.transport.post_json(**kwargs)
        if type(response) is DeepSeekHttpResponse and type(response.body) is bytes and len(response.body) <= 65536:
            try:
                payload = json.loads(response.body.decode("utf-8"))
                if type(payload) is dict:
                    if payload.get("model") in _ACCEPTED_RESPONSE_MODELS:
                        self.row["model"] = payload["model"]
                    usage = payload.get("usage")
                    if type(usage) is dict:
                        self.row["usage"] = {key: usage[key] for key in (
                            "prompt_tokens", "completion_tokens", "total_tokens",
                            "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
                            if type(usage.get(key)) is int and 0 <= usage[key] <= 2**53 - 1}
                    choices = payload.get("choices")
                    if type(choices) is list and len(choices) == 1 and type(choices[0]) is dict:
                        finish = choices[0].get("finish_reason")
                        if finish in ("stop", "length", "tool_calls", "content_filter", "insufficient_system_resource"):
                            self.row["finish_reason"] = finish
                        message = choices[0].get("message")
                        if type(message) is dict and type(message.get("content")) is str:
                            self.row["final_content"] = message["content"]
            except (ValueError, UnicodeError, TypeError):
                pass
        return response


class LiveReplyAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("deepseek", "deepseek-flash", False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, transport, credential_ref, budget: LiveReplyBudget, *, request_guard=None, approval=None, branch_id=None):
        if (type(budget) is not LiveReplyBudget or DEEPSEEK_ENDPOINT != "https://api.deepseek.com/chat/completions"
            or DEEPSEEK_TIMEOUT_SECONDS != 30 or request_guard is not None and not callable(request_guard)):
            raise ValueError("exact approved S112 live delivery required")
        self._transport, self._credential_ref, self._budget = transport, credential_ref, budget
        self._request_guard = request_guard
        self._approval, self._branch_id = approval, branch_id
        self._real_credential = (credential_ref.backend_id == DEEPSEEK_CREDENTIAL_BACKEND_ID
            and credential_ref.key_id == DEEPSEEK_CREDENTIAL_KEY_ID)
        if self._real_credential:
            self._verify_real_authority()
        self.rows = []

    def _verify_real_authority(self):
        from dynamic_subject_agent.first_life_reply_live import ApprovedReplyTrial
        from dynamic_subject_agent.first_life_candidate_trial import ApprovedCandidateTrial
        candidate = self._budget.policy in CANDIDATE_REPLY_POLICIES
        expected_type = ApprovedCandidateTrial if candidate else ApprovedReplyTrial
        if type(self._approval) is not expected_type or self._approval.read()["live"] is not True:
            raise ValueError("real credential requires the one approved live experiment")
        _, policy = self._approval.branch(self._branch_id)
        expected_path = self._approval.parent_budget_path if candidate else self._approval.root / "real-budget"
        if (self._budget.policy != policy
            or self._budget._shared.path.resolve() != expected_path.resolve()
            or self._budget._local.path.resolve() != (self._approval.root / self._branch_id / "local-stage-budget").resolve()
            or candidate and self._budget._shared.grant_digest != self._approval.manifest_digest):
            raise ValueError("real sender requires the approved shared cap and branch audit")

    def invoke(self, task):
        if self._real_credential or self._request_guard is not None:
            try:
                if self._real_credential:
                    self._verify_real_authority()
                    self._approval.validate_task(self._branch_id, task)
                if self._request_guard is not None:
                    self._request_guard(task)
            except Exception:
                # Validation runs before consumption, but its failure still
                # burns any current ticket and cannot be corrected into retry.
                try:
                    self._budget.consume(task)
                except Exception:
                    pass
                raise ModelGatewayFailure("structured-choice-invalid") from None
        self._budget.consume(task)
        if (self._budget.policy in CANDIDATE_REPLY_POLICIES
            and task.kind is not ModelTaskKind.CHARACTER_COMMUNICATION_PLAN):
            from dynamic_subject_agent.first_life_reply_candidate import preview_reply_candidate
            wire = preview_reply_candidate(task).wire
        else:
            wire = draft_wire(task)
        observed = _ObservedTransport(self._transport)
        row = dict(task_kind=task.kind.value, payload=asdict(task.payload),
            request_digest=sha256(canonical_json(asdict(task.payload)).encode()).hexdigest(),
            wire_sha256=sha256(wire).hexdigest(), value=None, error_code=None)
        if self._budget.policy in CANDIDATE_REPLY_POLICIES:
            row["request_body"] = json.loads(wire)
        started = perf_counter()
        try:
            value = _post_json_reply_content(observed, self._credential_ref, wire, max_output_tokens=4096,
                require_complete=True, discard_reasoning=True, safe_diagnostics=True)
            row["value"] = value
        except CharacterCredentialUnavailable:
            row["error_code"] = "character-credential-unavailable"
            raise ModelGatewayFailure("character-credential-unavailable") from None
        except DeepSeekResponseDiagnosticFailure as failure:
            row["error_code"] = failure.diagnostic_code
            raise ModelGatewayFailure(failure.diagnostic_code) from None
        except Exception:
            row["error_code"] = "provider-failed"
            raise ModelGatewayFailure("provider-failed") from None
        finally:
            self.rows.append({**row, **observed.row, "elapsed_seconds": max(0.0, perf_counter() - started)})
        return ModelResult(task.kind, value)

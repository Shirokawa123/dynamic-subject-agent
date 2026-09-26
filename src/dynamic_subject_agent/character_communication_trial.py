"""Frozen two-stage experiment: bounded attempts, no state or restart continuation."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_communication_plan import (
    CommunicationFact, CommunicationPlanProjection, PLAN_POLICY, EXPRESSION_POLICY,
    _plan_projection, _projection_digest, _validate_projection, _qualify_plan,
    _expression_projection, _validated_expression,
)
from dynamic_subject_agent.character_reply_candidate import CharacterReplyProducer, CharacterReplyCandidateView
from dynamic_subject_agent.frozen_attempt import canonical_json, write_once, FrozenAttemptRun
from dynamic_subject_agent.model_gateway import ModelGatewayFailure, ModelTask, ModelTaskKind
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES

DERIVATION_VERSION = "communication-derive-1"
PERSONALITY_TRIAL_VERSION = "character-personality-communication-trial-1"
PERSONALITY_CONTRACT = "personality-envelope-1"
TECHNICAL_CODES = frozenset(code for code in REVIEW_DIAGNOSTIC_CODES if not code.startswith("review-")) | {"communication-task-failed"}
AMBIGUOUS_DELIVERY_CODES = frozenset(("transport-timeout", "transport-delivery-ambiguous"))


@dataclass(frozen=True)
class CommunicationTrialPlan:
    serialized: str

    @property
    def digest(self):
        return sha256(self.serialized.encode()).hexdigest()

    @property
    def payload(self):
        return json.loads(self.serialized)


@dataclass(frozen=True)
class CommunicationTrialExpressionRequest:
    """Local authorization only; the Adapter derives the HTTP projection itself."""
    context_digest: str


def _validate_cases(cases):
    if (type(cases) is not dict or set(cases) != {"version", "cases"}
            or cases["version"] != "character-communication-plan-cases-1"
            or type(cases["cases"]) is not list or len(cases["cases"]) != 6):
        raise ValueError("six fixed communication cases required")
    ids = set()
    for case in cases["cases"]:
        if (type(case) is not dict or set(case) != {"id", "message", "context_mode"}
                or not isinstance(case["id"], str) or not case["id"].strip() or len(case["id"]) > 80
                or case["id"] in ids or not isinstance(case["message"], str) or not case["message"].strip()
                or len(case["message"]) > 1000 or case["context_mode"] not in ("flat", "organized")):
            raise ValueError("invalid communication case")
        ids.add(case["id"])


def build_communication_trial_plan(preview_reply, *, reviewed_digest, subject_id, anchor_id,
                                    cases, max_knowledge_chars, protocol, planning_wire, expression_profile="standard", personality_binding=None):
    """Composition supplies pure protocol metadata and serialization, never a key."""
    _validate_cases(cases)
    rows, seen = [], set()
    for index, case in enumerate(cases["cases"]):
        view = preview_reply(CharacterChatContextRequest(subject_id, anchor_id, case["message"], case["context_mode"], max_knowledge_chars))
        if view.status != "previewed":
            raise ValueError("communication context not available")
        if personality_binding is None:
            projection = _plan_projection(view.projection)
        else:
            from dynamic_subject_agent.character_personality import CharacterPlanningEnvelope, frozen_personality_planning
            if type(view.projection) is not CharacterPlanningEnvelope: raise ValueError("personality preview required")
            projection = frozen_personality_planning(asdict(view.projection))
        digest = _projection_digest(projection)
        if digest in seen:
            raise ValueError("duplicate communication context")
        seen.add(digest)
        rows.append(dict(index=index, case_id=case["id"], message=case["message"], mode=case["context_mode"],
            request_digest=digest, projection=asdict(projection), outbound_digest=sha256(planning_wire(projection)).hexdigest()))
        if personality_binding is not None: rows[-1]["projection_contract"] = PERSONALITY_CONTRACT
    payload = dict(version="character-communication-trial-1", reviewed_digest=reviewed_digest,
        subject_id=subject_id, anchor_id=anchor_id, max_knowledge_chars=max_knowledge_chars,
        cases=cases["cases"], requests=rows, protocol=protocol, planning_policy=PLAN_POLICY, expression_policy=EXPRESSION_POLICY,
        derivation=DERIVATION_VERSION, limits=dict(cases=6, stages_per_case=2, max_calls=12, max_fact_refs=4),
        execution="Six ordered cases; each planning and expression at most once; stop on any source, credential, technical, adjudication or audit failure; never retry or resume delivery",
        scope="Reviewed current stage-one facts and foreground; expression derives only current qualified references/action and same foreground/message; no source text, internal IDs, history, old candidate or scoring labels in model input",
        retention="Independent local plan, stage attempts, validated action/refs, derived expression request and candidate or closed failure code; no reasoning, raw response, headers, exceptions or key",
        approval="New user approval for both semantic tasks and at most twelve calls must exist; exact digest is only the operator assertion")
    if expression_profile != "standard":
        payload["expression_profile"] = expression_profile
    if personality_binding is not None:
        from dynamic_subject_agent.character_personality import PERSONALITY_POLICY
        payload.update(version=PERSONALITY_TRIAL_VERSION, personality_binding=personality_binding,
                       personality_policy=PERSONALITY_POLICY, derivation="personality-derive-1",
                       scope="Current conversation projection plus complete resident character core and author personality interpretations; expression retains the same core/interpretations and only qualified conversation facts; no support IDs, source text, private history, reasoning or runtime updates")
    return CommunicationTrialPlan(canonical_json(payload))


def save_communication_trial_plan(root, plan):
    root.mkdir(parents=True, exist_ok=True)
    path = root / (plan.digest + ".plan.json")
    value = dict(plan=plan.payload, digest=plan.digest)
    try:
        write_once(path, value)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != canonical_json(value):
            raise ValueError("stored communication plan invalid") from None
    return path


def frozen_context(row):
    value = row["projection"]
    if row.get("projection_contract") == PERSONALITY_CONTRACT:
        from dynamic_subject_agent.character_personality import frozen_personality_planning
        projection = frozen_personality_planning(value)
        if _projection_digest(projection) != row["request_digest"]: raise ValueError("frozen personality digest invalid")
        return projection
    projection = CommunicationPlanProjection(tuple(CommunicationFact(**item) for item in value["self_knowledge"]),
        value["stage_description"], tuple(value["encounter"]), tuple(value["disclosure"]), value["current_message"], value["policy"])
    _validate_projection(projection)
    if _projection_digest(projection) != row["request_digest"]:
        raise ValueError("frozen context invalid")
    return projection


def _qualify_current(value, context):
    from dynamic_subject_agent.character_personality import CharacterPlanningEnvelope
    inner = context.conversation if type(context) is CharacterPlanningEnvelope else context
    return _qualify_plan(value, inner, _projection_digest(inner))


def _expression_current(value, context):
    from dynamic_subject_agent.character_personality import CharacterPlanningEnvelope, personality_expression
    if type(context) is CharacterPlanningEnvelope: return personality_expression(context, value)
    return _expression_projection(_qualify_current(value, context), context)


def stage_digest(row, stage):
    return sha256(canonical_json(dict(case_id=row["case_id"], context_digest=row["request_digest"], stage=stage)).encode()).hexdigest()


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_attempt(root, plan, row, stage):
    digest = stage_digest(row, stage)
    expected = dict(request_digest=digest, index=row["index"] * 2 + (stage == "expression"), status="attempted")
    attempt = _read(root / (digest + ".attempt.json"))
    if (type(attempt) is not dict or type(attempt.get("index")) is not int or attempt != expected
            or _read(root / "started.json") != dict(plan_digest=plan.digest, status="started")):
        raise ValueError("stage attempt invalid")
    return digest


def _stage_record(plan, row, stage, outbound_digest, status, code="", value=None):
    return dict(plan_digest=plan.digest, case_id=row["case_id"], stage=stage,
        context_digest=row["request_digest"], request_digest=stage_digest(row, stage),
        outbound_digest=outbound_digest, status=status, code=code, value=value)


def load_stage(root, plan, row, stage, outbound_digest):
    digest = validate_attempt(root, plan, row, stage)
    value = _read(root / (digest + ".result.json"))
    if type(value) is not dict or set(value) != set(_stage_record(plan, row, stage, outbound_digest, "")):
        raise ValueError("stage result shape invalid")
    binding = _stage_record(plan, row, stage, outbound_digest, value["status"], value["code"], value["value"])
    if value != binding:
        raise ValueError("stage result binding invalid")
    if value["status"] == ("planned" if stage == "planning" else "candidate"):
        if value["code"] != "":
            raise ValueError("completed stage failure invalid")
        if stage == "planning":
            _qualify_current(value["value"], frozen_context(row))
        else:
            _validated_expression(value["value"])
    elif value["status"] == "unavailable":
        if value["code"] != "character-credential-unavailable" or value["value"] is not None:
            raise ValueError("stage unavailable invalid")
    elif value["status"] == "failed-closed":
        allowed = (TECHNICAL_CODES - AMBIGUOUS_DELIVERY_CODES) | {"communication-plan-invalid" if stage == "planning" else "communication-expression-invalid"}
        if not isinstance(value["code"], str) or value["code"] not in allowed or value["value"] is not None:
            raise ValueError("stage failure invalid")
    elif value["status"] == "unknown":
        if (not isinstance(value["code"], str) or value["code"] not in AMBIGUOUS_DELIVERY_CODES
                or value["value"] is not None):
            raise ValueError("stage unknown invalid")
    else:
        raise ValueError("stage status invalid")
    return value


def derived_expression_request(plan, row, planning_result, expression_wire):
    context = frozen_context(row)
    if planning_result != _stage_record(plan, row, "planning", row["outbound_digest"], "planned", value=planning_result.get("value")):
        raise ValueError("audited planning required")
    projection = _expression_current(planning_result["value"], context)
    return projection, dict(version=plan.payload.get("derivation", DERIVATION_VERSION), plan_digest=plan.digest, case_id=row["case_id"],
        context_digest=row["request_digest"], planning_result_digest=sha256(canonical_json(planning_result).encode()).hexdigest(),
        projection=asdict(projection), outbound_digest=sha256(expression_wire(projection)).hexdigest())


def load_expression_request(root, plan, row, expression_wire):
    planning = load_stage(root, plan, row, "planning", row["outbound_digest"])
    projection, expected = derived_expression_request(plan, row, planning, expression_wire)
    actual = _read(root / (stage_digest(row, "expression") + ".request.json"))
    if canonical_json(actual) != canonical_json(expected):
        raise ValueError("expression derivation invalid")
    return projection, expected


class CharacterCommunicationTrial(CharacterReplyProducer):
    def __init__(self, plan, *, root, gateway, expression_wire, approved_plan, personality_preview=None):
        if type(plan) is not CommunicationTrialPlan or not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("typed communication plan and absolute root required")
        if approved_plan is not None and approved_plan != plan.digest:
            raise ValueError("current communication approval required")
        self._plan, self._gateway, self._expression_wire = plan, gateway, expression_wire
        if (plan.payload["version"] == PERSONALITY_TRIAL_VERSION) != (personality_preview is not None):
            raise ValueError("matching trial preview contract required")
        self._personality_preview = personality_preview
        self._rows = plan.payload["requests"]
        self._allowed = {row["request_digest"]: row for row in self._rows}
        self._case_index = 0
        save_communication_trial_plan(root, plan)
        self._ledger = FrozenAttemptRun(root, plan.digest, approved=approved_plan is not None)
        if self._ledger.resumed:
            self._gateway = None

    def preview(self, view, *, request=None):
        if view.status != "previewed":
            return view
        try:
            if self._personality_preview is not None:
                checked = self._personality_preview.preview(view, request=request)
                if checked.status != "previewed": return checked
                projection = checked.projection
            else:
                projection = _plan_projection(view.projection)
            digest = _projection_digest(projection)
            row = self._allowed.get(digest)
            expected = CharacterChatContextRequest(self._plan.payload["subject_id"], self._plan.payload["anchor_id"],
                row["message"], row["mode"], self._plan.payload["max_knowledge_chars"]) if row else None
            if type(request) is not CharacterChatContextRequest or request != expected:
                return CharacterReplyCandidateView("rejected", "communication-trial-not-in-plan")
            return CharacterReplyCandidateView("previewed", projection=projection, request_digest=digest)
        except Exception:
            return CharacterReplyCandidateView("failed-closed", "communication-context-unavailable")

    def _view(self, row, audit):
        return CharacterReplyCandidateView(audit["status"], audit["code"], request_digest=row["request_digest"],
            reply_text=audit["value"]["reply_text"] if audit["status"] == "candidate" else "",
            semantic_review="required" if audit["status"] == "candidate" else "not-performed")

    def _cached(self, row):
        digest = row["request_digest"]
        if digest in self._ledger.results:
            return self._ledger.results[digest]
        if not self._ledger.resumed:
            return None
        try:
            planning = load_stage(self._ledger.path, self._plan, row, "planning", row["outbound_digest"])
            if planning["status"] != "planned":
                expression_digest = stage_digest(row, "expression")
                if any((self._ledger.path / (expression_digest + suffix)).exists() for suffix in (".request.json", ".attempt.json", ".result.json")):
                    raise ValueError("expression after planning failure invalid")
                return self._view(row, planning)
            _, expected = load_expression_request(self._ledger.path, self._plan, row, self._expression_wire)
            expression = load_stage(self._ledger.path, self._plan, row, "expression", expected["outbound_digest"])
            return self._view(row, expression)
        except Exception:
            return CharacterReplyCandidateView("unknown", "communication-trial-previously-started", request_digest=digest)

    def _unknown(self, row, code):
        self._ledger.stop(code)
        result = CharacterReplyCandidateView("unknown", code, request_digest=row["request_digest"])
        self._ledger.results[row["request_digest"]] = result
        return result

    def _execute(self, row, stage, payload, outbound_digest):
        digest = stage_digest(row, stage)
        try:
            self._ledger.claim(digest)
        except Exception:
            return None, self._unknown(row, "communication-attempt-record-unavailable")
        try:
            kind = ModelTaskKind.CHARACTER_COMMUNICATION_PLAN if stage == "planning" else ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION
            value = self._gateway.execute(ModelTask(kind, payload)).value
        except ModelGatewayFailure as failure:
            unavailable = failure.code == "character-credential-unavailable"
            code = failure.code if isinstance(failure.code, str) and failure.code in TECHNICAL_CODES else "communication-task-failed"
            audit = _stage_record(self._plan, row, stage, outbound_digest,
                "unavailable" if unavailable else "unknown" if code in AMBIGUOUS_DELIVERY_CODES else "failed-closed",
                "character-credential-unavailable" if unavailable else code)
        except Exception:
            audit = _stage_record(self._plan, row, stage, outbound_digest, "failed-closed", "communication-task-failed")
        else:
            try:
                if stage == "planning":
                    _qualify_current(value, payload)
                else:
                    _validated_expression(value)
            except Exception:
                audit = _stage_record(self._plan, row, stage, outbound_digest, "failed-closed",
                    "communication-plan-invalid" if stage == "planning" else "communication-expression-invalid")
            else:
                audit = _stage_record(self._plan, row, stage, outbound_digest, "planned" if stage == "planning" else "candidate", value=value)
        try:
            self._ledger.record(digest, audit)
        except Exception:
            return None, self._unknown(row, "communication-result-record-unavailable")
        if audit["status"] in ("failed-closed", "unavailable", "unknown"):
            self._ledger.stop("communication-stage-failed")
            result = self._view(row, audit)
            self._ledger.results[row["request_digest"]] = result
            return audit, result
        return audit, None

    def propose(self, view):
        if view.status != "previewed":
            if self._ledger.approved and view.status in ("failed-closed", "unavailable"):
                self._ledger.stop("communication-context-unavailable")
            return view
        row = self._allowed[view.request_digest]
        if not self._ledger.approved:
            return CharacterReplyCandidateView("unavailable", "communication-trial-not-approved", request_digest=view.request_digest)
        cached = self._cached(row)
        if cached is not None:
            return cached
        if self._ledger.stopped or self._gateway is None:
            return CharacterReplyCandidateView("unavailable", "communication-trial-stopped", request_digest=view.request_digest)
        if self._case_index >= 6 or self._rows[self._case_index] != row or self._ledger.next != self._case_index * 2:
            return CharacterReplyCandidateView("rejected", "communication-trial-out-of-order", request_digest=view.request_digest)
        _, failure = self._execute(row, "planning", view.projection, row["outbound_digest"])
        if failure is not None:
            return failure
        try:
            planning = load_stage(self._ledger.path, self._plan, row, "planning", row["outbound_digest"])
            _, expression_request = derived_expression_request(self._plan, row, planning, self._expression_wire)
            write_once(self._ledger.path / (stage_digest(row, "expression") + ".request.json"), expression_request)
        except Exception:
            return self._unknown(row, "communication-derivation-record-unavailable")
        audit, failure = self._execute(row, "expression", CommunicationTrialExpressionRequest(row["request_digest"]), expression_request["outbound_digest"])
        if failure is not None:
            return failure
        result = self._view(row, audit)
        self._ledger.results[row["request_digest"]] = result
        self._case_index += 1
        return result

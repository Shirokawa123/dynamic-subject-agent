"""Six frozen expressions from a complete parent audit; no planning or state."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_communication_plan import (
    CommunicationFact, CommunicationExpressionProjection, _plan_projection, _projection_digest, _validated_expression,
)
from dynamic_subject_agent.character_communication_trial import (
    CommunicationTrialPlan, load_stage, load_expression_request, stage_digest,
    TECHNICAL_CODES, AMBIGUOUS_DELIVERY_CODES, save_communication_trial_plan,
)
from dynamic_subject_agent.character_reply_candidate import CharacterReplyProducer, CharacterReplyCandidateView
from dynamic_subject_agent.frozen_attempt import canonical_json, FrozenAttemptRun
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure

EXPRESSION_FAILURE_CODES = TECHNICAL_CODES | {"communication-expression-invalid", "expression-parent-invalid"}


def read_parent_plan(root, digest):
    if not isinstance(root, Path) or not root.is_absolute() or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("absolute parent root and exact digest required")
    path = root / (digest + ".plan.json")
    stored = json.loads(path.read_text(encoding="utf-8"))
    if type(stored) is not dict or set(stored) != {"digest", "plan"} or stored["digest"] != digest:
        raise ValueError("parent plan envelope invalid")
    plan = CommunicationTrialPlan(canonical_json(stored["plan"]))
    if plan.digest != digest or plan.payload.get("version") != "character-communication-trial-1" or len(plan.payload.get("requests", [])) != 6:
        raise ValueError("complete parent communication plan required")
    protocol = plan.payload.get("protocol")
    if (plan.payload.get("expression_profile", "standard") != "standard" or type(protocol) is not dict
            or protocol.get("expression") != dict(max_tokens=600, thinking={"type": "disabled"},
                temperature=0.3, response_format={"type": "json_object"}, stream=False)):
        raise ValueError("only original non-thinking expression parent is supported")
    return plan, sha256(path.read_bytes()).hexdigest()


def validated_parent_expressions(root, parent, original_expression_wire):
    run = root / parent.digest
    if (run / "stopped.json").exists():
        raise ValueError("completed successful parent required")
    files, rows = {"started.json"}, []
    for row in parent.payload["requests"]:
        planning = load_stage(run, parent, row, "planning", row["outbound_digest"])
        if planning["status"] != "planned":
            raise ValueError("completed parent planning required")
        projection, request = load_expression_request(run, parent, row, original_expression_wire)
        expression = load_stage(run, parent, row, "expression", request["outbound_digest"])
        if expression["status"] != "candidate":
            raise ValueError("completed parent expression required")
        for stage in ("planning", "expression"):
            for suffix in (".attempt.json", ".result.json"):
                files.add(stage_digest(row, stage) + suffix)
        files.add(stage_digest(row, "expression") + ".request.json")
        rows.append((row, projection))
    for suffix in (".attempt.json", ".result.json", ".request.json"):
        if {path.name for path in run.glob("*" + suffix)} != {name for name in files if name.endswith(suffix)}:
            raise ValueError("parent stage inventory invalid")
    fingerprints = {name: sha256((run / name).read_bytes()).hexdigest() for name in sorted(files)}
    return rows, fingerprints


def build_expression_trial_plan(*, parent, parent_file_digest, audited_rows, audit_fingerprints, protocol, expression_wire):
    rows, seen = [], set()
    for source, projection in audited_rows:
        digest = _projection_digest(projection)
        if digest in seen:
            raise ValueError("duplicate frozen expression")
        seen.add(digest)
        rows.append(dict(index=source["index"], case_id=source["case_id"], message=source["message"], mode=source["mode"],
            source_context_digest=source["request_digest"], request_digest=digest,
            projection=asdict(projection), outbound_digest=sha256(expression_wire(projection)).hexdigest()))
    payload = dict(version="character-expression-thinking-trial-1", parent_plan_digest=parent.digest,
        parent_file_digest=parent_file_digest, parent_audit_fingerprints=audit_fingerprints,
        reviewed_digest=parent.payload["reviewed_digest"], subject_id=parent.payload["subject_id"], anchor_id=parent.payload["anchor_id"],
        max_knowledge_chars=parent.payload["max_knowledge_chars"], cases=parent.payload["cases"], requests=rows, protocol=protocol,
        limits=dict(cases=6, expression_calls=6, planning_calls=0),
        scope="Exactly the six complete parent expression projections and original policy; no re-planning, added facts, old answers, audit identifiers or scoring labels in model input",
        execution="Six ordered expressions; one attempt each; stop on any source, parent integrity, credential, technical or audit failure; no retry or restart continuation",
        retention="Independent plan, attempt, candidate or closed failure audit; parent output is only fingerprinted locally; no reasoning, raw response, exception, header or key",
        approval="New approval for six high-thinking expression calls must exist; exact digest is only the operator assertion")
    return CommunicationTrialPlan(canonical_json(payload))


def frozen_expression(row):
    value = row["projection"]
    projection = CommunicationExpressionProjection(tuple(CommunicationFact(**item) for item in value["selected_facts"]),
        value["action"], value["stage_description"], tuple(value["encounter"]), tuple(value["disclosure"]), value["current_message"], value["policy"])
    if _projection_digest(projection) != row["request_digest"]:
        raise ValueError("frozen expression invalid")
    return projection


def verify_parent_fingerprints(parent_root, plan):
    digest = plan.payload["parent_plan_digest"]
    path = parent_root / (digest + ".plan.json")
    run = parent_root / digest
    if sha256(path.read_bytes()).hexdigest() != plan.payload["parent_file_digest"] or (run / "stopped.json").exists():
        raise ValueError("parent plan changed")
    fingerprints = plan.payload["parent_audit_fingerprints"]
    if any(sha256((run / name).read_bytes()).hexdigest() != value for name, value in fingerprints.items()):
        raise ValueError("parent audit changed")
    for suffix in (".attempt.json", ".result.json", ".request.json"):
        if {path.name for path in run.glob("*" + suffix)} != {name for name in fingerprints if name.endswith(suffix)}:
            raise ValueError("parent inventory changed")


def validate_expression_attempt(root, plan, row):
    value = json.loads((root / (row["request_digest"] + ".attempt.json")).read_text(encoding="utf-8"))
    if (type(value) is not dict or type(value.get("index")) is not int
            or value != dict(request_digest=row["request_digest"], index=row["index"], status="attempted")
            or json.loads((root / "started.json").read_text(encoding="utf-8")) != dict(plan_digest=plan.digest, status="started")):
        raise ValueError("expression attempt invalid")


def _record(plan, row, status, code="", value=None):
    return dict(plan_digest=plan.digest, case_id=row["case_id"], stage="expression", request_digest=row["request_digest"],
        source_context_digest=row["source_context_digest"], outbound_digest=row["outbound_digest"], status=status, code=code, value=value)


class CharacterExpressionThinkingTrial(CharacterReplyProducer):
    def __init__(self, plan, *, root, parent_root, gateway, approved_plan):
        if type(plan) is not CommunicationTrialPlan or plan.payload.get("version") != "character-expression-thinking-trial-1":
            raise ValueError("typed expression trial plan required")
        if approved_plan is not None and approved_plan != plan.digest:
            raise ValueError("current expression approval required")
        self._plan, self._parent_root, self._gateway = plan, parent_root, gateway
        self._rows = plan.payload["requests"]
        self._allowed = {row["source_context_digest"]: row for row in self._rows}
        save_communication_trial_plan(root, plan)
        self._ledger = FrozenAttemptRun(root, plan.digest, approved=approved_plan is not None)
        if self._ledger.resumed:
            self._gateway = None

    def preview(self, view, *, request=None):
        if view.status != "previewed":
            return view
        try:
            verify_parent_fingerprints(self._parent_root, self._plan)
            source_digest = _projection_digest(_plan_projection(view.projection))
            row = self._allowed.get(source_digest)
            expected = CharacterChatContextRequest(self._plan.payload["subject_id"], self._plan.payload["anchor_id"],
                row["message"], row["mode"], self._plan.payload["max_knowledge_chars"]) if row else None
            if type(request) is not CharacterChatContextRequest or request != expected:
                return CharacterReplyCandidateView("rejected", "expression-trial-not-in-plan")
            return CharacterReplyCandidateView("previewed", projection=frozen_expression(row), request_digest=row["request_digest"])
        except Exception:
            return CharacterReplyCandidateView("failed-closed", "expression-parent-unavailable")

    def _view(self, row, audit):
        return CharacterReplyCandidateView(audit["status"], audit["code"], request_digest=row["request_digest"],
            reply_text=audit["value"]["reply_text"] if audit["status"] == "candidate" else "",
            semantic_review="required" if audit["status"] == "candidate" else "not-performed")

    def _cached(self, row):
        if row["request_digest"] in self._ledger.results:
            return self._ledger.results[row["request_digest"]]
        if not self._ledger.resumed:
            return None
        try:
            validate_expression_attempt(self._ledger.path, self._plan, row)
            audit = self._ledger.read_result(row["request_digest"])
            if type(audit) is not dict or set(audit) != set(_record(self._plan, row, "")):
                raise ValueError("expression result shape invalid")
            if audit != _record(self._plan, row, audit["status"], audit["code"], audit["value"]):
                raise ValueError("expression result binding invalid")
            if audit["status"] == "candidate":
                if audit["code"] != "": raise ValueError("candidate failure code invalid")
                _validated_expression(audit["value"])
            elif audit["status"] == "unavailable":
                if audit["code"] != "character-credential-unavailable" or audit["value"] is not None: raise ValueError("unavailable result invalid")
            elif audit["status"] in ("unknown", "failed-closed"):
                allowed = AMBIGUOUS_DELIVERY_CODES if audit["status"] == "unknown" else EXPRESSION_FAILURE_CODES - AMBIGUOUS_DELIVERY_CODES
                if not isinstance(audit["code"], str) or audit["code"] not in allowed or audit["value"] is not None: raise ValueError("expression failure invalid")
            else:
                raise ValueError("expression status invalid")
            return self._view(row, audit)
        except Exception:
            return CharacterReplyCandidateView("unknown", "expression-trial-previously-started", request_digest=row["request_digest"])

    def propose(self, view):
        if view.status != "previewed":
            if self._ledger.approved and view.status in ("failed-closed", "unavailable"):
                self._ledger.stop("expression-context-unavailable")
            return view
        row = next(row for row in self._rows if row["request_digest"] == view.request_digest)
        if not self._ledger.approved:
            return CharacterReplyCandidateView("unavailable", "expression-trial-not-approved", request_digest=view.request_digest)
        cached = self._cached(row)
        if cached is not None: return cached
        if self._ledger.stopped or self._gateway is None:
            return CharacterReplyCandidateView("unavailable", "expression-trial-stopped", request_digest=view.request_digest)
        if self._ledger.next >= 6 or self._rows[self._ledger.next] != row:
            return CharacterReplyCandidateView("rejected", "expression-trial-out-of-order", request_digest=view.request_digest)
        try:
            self._ledger.claim(view.request_digest)
        except Exception:
            return self._unknown(row, "expression-attempt-record-unavailable")
        try:
            value = self._gateway.execute(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, view.projection)).value
        except ModelGatewayFailure as failure:
            unavailable = failure.code == "character-credential-unavailable"
            code = failure.code if isinstance(failure.code, str) and failure.code in EXPRESSION_FAILURE_CODES else "communication-task-failed"
            audit = _record(self._plan, row, "unavailable" if unavailable else "unknown" if code in AMBIGUOUS_DELIVERY_CODES else "failed-closed",
                "character-credential-unavailable" if unavailable else code)
        except Exception:
            audit = _record(self._plan, row, "failed-closed", "communication-task-failed")
        else:
            try: _validated_expression(value)
            except Exception: audit = _record(self._plan, row, "failed-closed", "communication-expression-invalid")
            else: audit = _record(self._plan, row, "candidate", value=value)
        try:
            self._ledger.record(view.request_digest, audit)
        except Exception:
            return self._unknown(row, "expression-result-record-unavailable")
        if audit["status"] != "candidate": self._ledger.stop("expression-stage-failed")
        result = self._view(row, audit)
        self._ledger.results[row["request_digest"]] = result
        return result

    def _unknown(self, row, code):
        self._ledger.stop(code)
        result = CharacterReplyCandidateView("unknown", code, request_digest=row["request_digest"])
        self._ledger.results[row["request_digest"]] = result
        return result

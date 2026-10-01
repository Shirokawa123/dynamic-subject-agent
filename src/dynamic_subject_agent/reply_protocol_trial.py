"""S116's isolated, Facade-facing reply-protocol experiment.

Basis: S115's checked official JSON guidance and exact eight-request package
already isolate one format-example change. Reuse its typed payload restoration,
standard builders/output checks, the existing ModelGateway and the independent
SQLite development audit. No new papers, dependencies, identity/QRI, Timeline
writer or generated reply-to-history adoption are needed for this technical lab.
Acceptance is exact request bytes, strict output handling, durable one-attempt
delivery, and separate template-echo reporting; none establishes dialogue quality.

The second response-format study follows S116's recorded decision: keep the
approved JSON-example request and vary only response_format.type. The same
strict JSON/output checks apply even when the wire requests text mode.
The instruction-scope study keeps that JSON-example wire in JSON mode and
limits one existing style sentence to reply_text, leaving outer fields explicit.
The reasoning-effort study uses that scoped wire for both arms, varying only
high versus low effort while retaining enabled thinking and the 4096-token cap.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import UUID

from dynamic_subject_agent.character_communication_plan import _validated_expression
from dynamic_subject_agent.first_life_reply_candidate import preview_reply_candidate, recorded_reply_task
from dynamic_subject_agent.first_life_reply_protocol import EXAMPLE_BODY, PROTOCOL_VERSION, preview_json_example
from dynamic_subject_agent.first_life_reply_routes import validate_whole_reply
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelGateway, ModelGatewayFailure, ModelTask, ModelTaskKind
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES


AUTHORIZATION = "user-unlimited-model-development-2026-10-01"
PURPOSE = "reply-protocol-comparison"
PACKAGE_DIGEST = "4e4ed6a664821d18f827d7a6f62d50aeec8b07222709ef238a9853bbba2e88e5"
VARIANTS = ("baseline", "json-example")
RESPONSE_FORMAT_VARIANTS = ("json-object", "text-json")
INSTRUCTION_SCOPE_VARIANTS = ("global-style", "reply-text-style")
REASONING_EFFORT_VARIANTS = ("high", "low")
STUDIES = ("json-example", "response-format", "instruction-scope", "reasoning-effort")
GLOBAL_STYLE_SENTENCE = "使用第一人称自然中文短消息，通常两三句；不输出动作旁白、档案、字段名、规则、分析或思考过程。"
REPLY_TEXT_STYLE_SENTENCE = (
    "本接口需要JSON数据，外层字段供程序读取。reply_text的值才是给用户看的正文："
    "使用第一人称自然中文短消息，通常两三句；这段正文不写动作旁白、档案、字段标签、规则说明、分析或思考过程。"
)
PROTOCOL_DIAGNOSTICS = (REVIEW_DIAGNOSTIC_CODES - {"review-schema", "review-quote", "review-label"}) | frozenset((
    "protocol-request-invalid", "protocol-run-invalid", "protocol-service-closed", "protocol-gateway-unavailable",
    "protocol-response-invalid", "protocol-attempt-already-recorded", "protocol-audit-failed",
    "protocol-authority-invalid", "character-credential-unavailable", "provider-failed", "format-example-copied",
))


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def fixed_development_root():
    return Path(os.environ["LOCALAPPDATA"]) / "DynamicSubjectAgent" / "development-calls"


def fixed_protocol_runs_root():
    return fixed_development_root() / "runs"


def fixed_development_audit_path():
    return fixed_development_root() / "audit"


@dataclass(frozen=True)
class ProtocolTrialRequest:
    case_id: str
    variant: str
    attempt_id: str


@dataclass(frozen=True)
class ProtocolTrialView:
    status: str
    diagnostic_code: str | None
    case_id: str
    variant: str
    attempt_id: str
    value: dict | None = None
    format_example_copied: bool = False


def _verified_package(package):
    if type(package) is not dict or package.get("package_sha256") != PACKAGE_DIGEST:
        raise ValueError("exact S115 protocol package required")
    content = dict(package)
    content.pop("package_sha256")
    if digest(content) != PACKAGE_DIGEST or package["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("protocol package content changed")
    case_ids = set()
    for row in package["cases"]:
        if row["case_id"] in case_ids:
            raise ValueError("unique protocol cases required")
        case_ids.add(row["case_id"])
        task = recorded_reply_task(row["task_kind"], row["payload"])
        baseline = preview_reply_candidate(task)
        example = preview_json_example(task)
        if (baseline.source_payload_sha256 != row["request_digest"]
            or baseline.wire != row["baseline_wire_utf8"].encode("utf-8")
            or baseline.candidate_wire_sha256 != row["baseline_wire_sha256"]
            or example.wire != row["candidate_wire_utf8"].encode("utf-8")
            or example.candidate_wire_sha256 != row["candidate_wire_sha256"]
            or example.appended_system != row["appended_system"]):
            raise ValueError("current protocol builders differ from reviewed exact bytes")
    sequence = package["sequence"]
    pairs = {(row["case_id"], row["variant"]) for row in sequence}
    if (len(case_ids) != 4 or len(sequence) != 8 or len(pairs) != 8
        or pairs != {(case_id, variant) for case_id in case_ids for variant in VARIANTS}
        or any(set(row) != {"case_id", "variant", "maximum_attempts"} or row["maximum_attempts"] != 1 for row in sequence)):
        raise ValueError("the fixed eight-entry experiment sequence changed")
    return package


def _run_id(root):
    value = root.name
    if str(UUID(value)) != value:
        raise ValueError("canonical UUID protocol run directory required")
    return value


def _variants(study):
    if study not in STUDIES:
        raise ValueError("known frozen protocol study required")
    return {"json-example": VARIANTS, "response-format": RESPONSE_FORMAT_VARIANTS,
        "instruction-scope": INSTRUCTION_SCOPE_VARIANTS, "reasoning-effort": REASONING_EFFORT_VARIANTS}[study]


def _sequence(package, study):
    _variants(study)
    if study == "json-example":
        return package["sequence"]
    names = dict(zip(VARIANTS, _variants(study), strict=True))
    return [dict(row, variant=names[row["variant"]]) for row in package["sequence"]]


def _study_wire(row, study, variant):
    if variant not in _variants(study):
        raise ValueError("variant does not belong to this study")
    if study == "json-example":
        return row["baseline_wire_utf8" if variant == "baseline" else "candidate_wire_utf8"].encode("utf-8")
    if study == "reasoning-effort":
        original = _study_wire(row, "instruction-scope", "reply-text-style")
        body = json.loads(original)
        if (body["reasoning_effort"] != "high" or body["thinking"] != {"type": "enabled"}
            or body["max_tokens"] != 4096 or body["response_format"] != {"type": "json_object"}):
            raise ValueError("exact scoped high-effort baseline required")
        if variant == "high":
            return original
        body["reasoning_effort"] = "low"
        return canonical_json(body).encode("utf-8")
    original = row["candidate_wire_utf8"].encode("utf-8")
    if variant in ("json-object", "global-style"):
        return original
    body = json.loads(original)
    if body["response_format"] != {"type": "json_object"}:
        raise ValueError("exact original JSON response format required")
    if study == "response-format":
        body["response_format"] = {"type": "text"}
    else:
        system = body["messages"][0]
        if system["role"] != "system" or system["content"].count(GLOBAL_STYLE_SENTENCE) != 1:
            raise ValueError("exactly one original style sentence is required")
        system["content"] = system["content"].replace(GLOBAL_STYLE_SENTENCE, REPLY_TEXT_STYLE_SENTENCE, 1)
    return canonical_json(body).encode("utf-8")


def _response_format_spec(package):
    cases = {row["case_id"]: row for row in package["cases"]}
    return dict(version="reply-response-format-study-1", source_variant="json-example",
        changed_field="response_format.type", variants=list(RESPONSE_FORMAT_VARIANTS),
        output_validation="unchanged-strict-json-and-original-reply-schema",
        sequence=[dict(case_id=row["case_id"], variant=row["variant"],
            wire_sha256=sha256(_study_wire(cases[row["case_id"]], "response-format", row["variant"])).hexdigest())
            for row in _sequence(package, "response-format")])


def _instruction_scope_spec(package):
    cases = {row["case_id"]: row for row in package["cases"]}
    return dict(version="reply-instruction-scope-study-1", source_variant="json-example",
        changed_field="messages[0].content", scope="style instructions apply only to the reply_text value",
        original_sentence=GLOBAL_STYLE_SENTENCE, replacement_sentence=REPLY_TEXT_STYLE_SENTENCE,
        variants=list(INSTRUCTION_SCOPE_VARIANTS), response_format=dict(type="json_object"),
        output_validation="unchanged-strict-json-and-original-reply-schema",
        sequence=[dict(case_id=row["case_id"], variant=row["variant"],
            wire_sha256=sha256(_study_wire(cases[row["case_id"]], "instruction-scope", row["variant"])).hexdigest())
            for row in _sequence(package, "instruction-scope")])


def _reasoning_effort_spec(package):
    cases = {row["case_id"]: row for row in package["cases"]}
    return dict(version="reply-reasoning-effort-study-1", base_study="instruction-scope",
        base_variant="reply-text-style", changed_field="reasoning_effort", variants=list(REASONING_EFFORT_VARIANTS),
        thinking=dict(type="enabled"), max_tokens=4096, response_format=dict(type="json_object"),
        output_validation="unchanged-strict-json-and-original-reply-schema",
        sequence=[dict(case_id=row["case_id"], variant=row["variant"],
            wire_sha256=sha256(_study_wire(cases[row["case_id"]], "reasoning-effort", row["variant"])).hexdigest())
            for row in _sequence(package, "reasoning-effort")])


def _manifest(root, package, live, study="json-example"):
    if type(live) is not bool or type(study) is not str:
        raise ValueError("explicit protocol execution mode and study required")
    _variants(study)
    run_id = _run_id(root)
    if live:
        if root.parent != fixed_protocol_runs_root().resolve():
            raise ValueError("live protocol run requires its fixed development directory")
    elif root.is_relative_to(fixed_development_root().resolve()):
        raise ValueError("offline protocol run cannot use the real development root")
    _verified_package(package)
    result = dict(version="reply-protocol-run-1", authorization=AUTHORIZATION, purpose=PURPOSE,
        call_limit=None, automatic_retries=0, live=live, run_id=run_id, root=str(root),
        package_digest=PACKAGE_DIGEST, package=package)
    if study == "response-format":
        result.update(version="reply-protocol-run-2", study=study, study_spec=_response_format_spec(package))
    elif study == "instruction-scope":
        result.update(version="reply-protocol-run-3", study=study, study_spec=_instruction_scope_spec(package))
    elif study == "reasoning-effort":
        result.update(version="reply-protocol-run-4", study=study, study_spec=_reasoning_effort_spec(package))
    return result


@dataclass(frozen=True)
class ProtocolRun:
    root: Path
    digest: str

    def read(self):
        try:
            root = self.root.resolve()
            value = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            if (value != _manifest(root, value["package"], value["live"], value.get("study", "json-example"))
                or digest(value) != self.digest):
                raise ValueError("protocol run manifest changed")
            return value
        except (KeyError, TypeError, AttributeError):
            raise ValueError("protocol run metadata is incomplete") from None

    @property
    def live(self):
        return self.read()["live"]

    @property
    def package(self):
        return self.read()["package"]

    @property
    def study(self):
        return self.read().get("study", "json-example")

    @property
    def variants(self):
        return _variants(self.study)

    @property
    def sequence(self):
        manifest = self.read()
        return tuple(_sequence(manifest["package"], manifest.get("study", "json-example")))

    def request_for(self, case_id, variant):
        if not any(row["case_id"] == case_id and row["variant"] == variant for row in self.sequence):
            raise ValueError("exact protocol case and variant required")
        attempt = digest(dict(run_digest=self.digest, case_id=case_id, variant=variant))
        return ProtocolTrialRequest(case_id, variant, attempt)

    def _case(self, request, manifest=None):
        if (type(request) is not ProtocolTrialRequest or type(request.case_id) is not str
            or type(request.variant) is not str or type(request.attempt_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", request.attempt_id) is None):
            raise ValueError("typed bounded protocol request required")
        manifest = self.read() if manifest is None else manifest
        package = manifest["package"]
        study = manifest.get("study", "json-example")
        expected = digest(dict(run_digest=self.digest, case_id=request.case_id, variant=request.variant))
        if (request.attempt_id != expected or request.variant not in _variants(study)
            or not any(row["case_id"] == request.case_id and row["variant"] == request.variant
                for row in _sequence(package, study))):
            raise ValueError("protocol request does not match its run and experiment entry")
        return next(row for row in package["cases"] if row["case_id"] == request.case_id)

    def wire_for(self, request):
        manifest = self.read()
        row = self._case(request, manifest)
        return _study_wire(row, manifest.get("study", "json-example"), request.variant)

    def task_for_case(self, request):
        row = self._case(request)
        return recorded_reply_task(row["task_kind"], row["payload"])

    def validate_output(self, request, value):
        task = self.task_for_case(request)
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
            text, _ = validate_whole_reply(task.payload, value)
        else:
            text = _validated_expression(value)
        return text == EXAMPLE_BODY


def open_protocol_run(root, package_path, *, live, study="json-example"):
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("absolute protocol run directory required")
    root = root.resolve()
    package = json.loads(package_path.read_text(encoding="utf-8"))
    manifest = _manifest(root, package, live, study)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
        with (root / "manifest.json").open("x", encoding="utf-8") as output:
            output.write(canonical_json(manifest))
            output.flush()
            os.fsync(output.fileno())
    result = ProtocolRun(root, digest(manifest))
    if result.read() != manifest:
        raise ValueError("protocol run cannot be reinitialized or repurposed")
    return result


class ReplyProtocolTrial:
    """An isolated result service; nothing here can admit a conversation turn."""

    def __init__(self, gateway, plan):
        if gateway is not None and not isinstance(gateway, ModelGateway) or type(plan) is not ProtocolRun:
            raise ValueError("typed protocol gateway and run required")
        self.gateway, self.plan = gateway, plan
        self._closed, self._lock = False, RLock()

    def close(self):
        with self._lock:
            self._closed = True

    def evaluate(self, request):
        ids = (request.case_id, request.variant, request.attempt_id) if type(request) is ProtocolTrialRequest else ("", "", "")
        def failed(code, status="failed-closed"):
            return ProtocolTrialView(status, code, *ids)
        with self._lock:
            if self._closed:
                return failed("protocol-service-closed", "unavailable")
        try:
            self.plan.wire_for(request)
        except Exception:
            return failed("protocol-request-invalid")
        if self.gateway is None:
            return failed("protocol-gateway-unavailable", "unavailable")
        try:
            value = self.gateway.execute(ModelTask(ModelTaskKind.CHARACTER_REPLY_PROTOCOL, request)).value
            copied = self.plan.validate_output(request, value)
        except ModelGatewayFailure as error:
            code = error.code if error.code in PROTOCOL_DIAGNOSTICS else "provider-failed"
            return failed(code, "unavailable" if code == "character-credential-unavailable" else "failed-closed")
        except Exception:
            return failed("protocol-response-invalid")
        with self._lock:
            if self._closed:
                return failed("protocol-service-closed", "unavailable")
        return ProtocolTrialView("format-example-copied" if copied else "structured",
            "format-example-copied" if copied else None, *ids, value=value, format_example_copied=copied)

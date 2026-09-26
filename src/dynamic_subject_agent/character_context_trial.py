"""Frozen, one-attempt character-context comparison; never runtime state."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_reply_candidate import (
    CharacterReplyCandidateView, CharacterReplyProjection, REPLY_POLICY,
)
from dynamic_subject_agent.deepseek import DEEPSEEK_ENDPOINT, _ACCEPTED_RESPONSE_MODELS
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind, ModelGatewayFailure

# Explicit V4.1-Flash alias for the user-approved new character route.
TRIAL_MODEL = "deepseek-flash"

TRIAL_POLICY = REPLY_POLICY + (
    "若self_knowledge含core，它是常驻的连贯自我认识；episode/detail仅是本轮选中的相关经历和细节。"
    "未选中或没有匹配不表示本人不知道、没有其他经历或资料全空。"
    "组织摘要由作者审核，basis=linked-evidence表示有审核依据；kind=belief不得当成已证实事实。"
    "仍按disclosure决定分享，不朗读核心档案，不补出未提供的具体经历。"
)


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def projection_digest(projection):
    return sha256(canonical_json(asdict(projection)).encode()).hexdigest()


def trial_preview(view):
    if view.status != "previewed" or view.projection is None:
        return view
    projection = replace(view.projection, policy=TRIAL_POLICY)
    return replace(view, projection=projection, request_digest=projection_digest(projection))


@dataclass(frozen=True)
class CharacterContextTrialPlan:
    """Immutable serialized plan; callers cannot mutate nested authorizations."""
    serialized: str

    @property
    def digest(self):
        return sha256(self.serialized.encode()).hexdigest()

    @property
    def payload(self):
        return json.loads(self.serialized)


def validate_cases(value):
    if (type(value) is not dict or set(value) != {"version", "cases"}
            or value["version"] != "character-context-cases-1"
            or type(value["cases"]) is not list or len(value["cases"]) != 12):
        raise ValueError("twelve fixed cases required")
    ids, messages = set(), set()
    for case in value["cases"]:
        if (type(case) is not dict or set(case) != {"id", "message"}
                or not isinstance(case["id"], str) or not case["id"].strip() or len(case["id"]) > 80
                or not isinstance(case["message"], str) or not case["message"].strip()
                or len(case["message"]) > 1000 or case["id"] in ids or case["message"] in messages):
            raise ValueError("invalid fixed case")
        ids.add(case["id"])
        messages.add(case["message"])


def build_trial_plan(preview_reply, *, reviewed_digest, subject_id, anchor_id, cases, max_knowledge_chars):
    """Use the existing Facade preview, not a second context assembler."""
    from dynamic_subject_agent.character_context_trial_provider import DeepSeekCharacterContextAdapter
    validate_cases(cases)
    requests = []
    for case in cases["cases"]:
        for mode in ("flat", "organized"):
            request = CharacterChatContextRequest(subject_id, anchor_id, case["message"], mode, max_knowledge_chars)
            view = trial_preview(preview_reply(request))
            if view.status != "previewed" or view.projection is None:
                raise ValueError("trial-context-not-available")
            wire = DeepSeekCharacterContextAdapter.outbound_bytes(view.projection)
            requests.append(dict(case_id=case["id"], mode=mode, request_digest=view.request_digest,
                                 outbound_digest=sha256(wire).hexdigest(), projection=asdict(view.projection)))
    payload = dict(version="character-context-trial-1", reviewed_digest=reviewed_digest,
        subject_id=subject_id, anchor_id=anchor_id, cases=cases["cases"], requests=requests,
        endpoint=DEEPSEEK_ENDPOINT, model=TRIAL_MODEL, accepted_response_models=list(_ACCEPTED_RESPONSE_MODELS),
        policy=TRIAL_POLICY, max_knowledge_chars=max_knowledge_chars,
        generation=dict(max_tokens=600, temperature=0.3, thinking={"type": "disabled"},
                        response_format={"type": "json_object"}, stream=False),
        execution="24 ordered requests; one attempt each; stop on any failure; no retry or restart continuation",
        retention="Independent local trial audit only: plan, identifiers, sanitized status and permitted reply; no key, headers, reasoning or raw response",
        scope="Reviewed character summaries and twelve fixed messages only; no source text, audit IDs, private history, future exclusions or runtime updates",
        approval="Exact digest is an operator assertion; user approval for this new data use must exist before execution")
    return CharacterContextTrialPlan(canonical_json(payload))


def _write_once(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(value))
        stream.flush()
        os.fsync(stream.fileno())


def save_trial_plan(root: Path, plan: CharacterContextTrialPlan):
    root.mkdir(parents=True, exist_ok=True)
    path = root / (plan.digest + ".plan.json")
    try:
        _write_once(path, dict(plan=plan.payload, digest=plan.digest))
    except FileExistsError:
        if path.read_text(encoding="utf-8") != canonical_json(dict(plan=plan.payload, digest=plan.digest)):
            raise ValueError("stored-trial-plan-invalid") from None
    return path


class CharacterContextTrial:
    """A separate Producer whose remote allowance is exactly one frozen plan."""
    def __init__(self, plan: CharacterContextTrialPlan, *, root: Path,
                 gateway: ModelGateway | None, approved_plan: str | None):
        if type(plan) is not CharacterContextTrialPlan or not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("typed trial plan and absolute root required")
        if approved_plan is not None and approved_plan != plan.digest:
            raise ValueError("current trial approval required")
        self._plan, self._root, self._gateway = plan, root, gateway
        self._requests = plan.payload["requests"]
        self._allowed = {row["request_digest"] for row in self._requests}
        self._next, self._stopped = 0, False
        self._results = {}
        self._approved = approved_plan is not None
        self._resumed = False
        save_trial_plan(root, plan)
        self._run = root / plan.digest
        if self._approved:
            # mkdir is the exclusive startup claim, even if the process crashes
            # before the start record is complete. Existing runs never resume.
            try:
                self._run.mkdir(exist_ok=False)
            except FileExistsError:
                self._resumed = True
                self._gateway = None
            else:
                _write_once(self._run / "started.json", dict(plan_digest=plan.digest, status="started"))

    def preview(self, view: CharacterReplyCandidateView):
        view = trial_preview(view)
        if view.status == "previewed" and view.request_digest not in self._allowed:
            return CharacterReplyCandidateView("rejected", "trial-request-not-in-plan")
        return view

    def _cached(self, digest):
        if digest in self._results:
            return self._results[digest]
        if self._resumed:
            try:
                value = json.loads((self._run / (digest + ".result.json")).read_text(encoding="utf-8"))
                if set(value) != {"status", "code", "request_digest", "reply_text", "semantic_review"}:
                    raise ValueError("invalid result")
                expected = {"candidate": ("", "required"), "failed-closed": ("trial-attempt-failed", "not-performed"),
                            "unavailable": ("character-credential-unavailable", "not-performed")}
                if (value["request_digest"] != digest or value["status"] not in expected
                        or (value["code"], value["semantic_review"]) != expected[value["status"]]
                        or value["semantic_review"] not in ("required", "not-performed")
                        or not isinstance(value["reply_text"], str) or len(value["reply_text"]) > 1200
                        or (value["status"] == "candidate" and not value["reply_text"].strip())
                        or (value["status"] != "candidate" and value["reply_text"] != "")):
                    raise ValueError("invalid result")
                return CharacterReplyCandidateView(**value)
            except Exception:
                return CharacterReplyCandidateView("unknown", "trial-previously-started", request_digest=digest)
        return None

    def _stop(self, reason):
        self._stopped = True
        if not self._resumed:
            try:
                _write_once(self._run / "stopped.json", dict(plan_digest=self._plan.digest, reason=reason))
            except OSError:
                pass  # The exclusive startup/attempt claims still forbid replay.

    def propose(self, view: CharacterReplyCandidateView):
        view = self.preview(view)
        if view.status != "previewed":
            if self._approved and view.status in ("failed-closed", "unavailable"):
                self._stop("trial-context-unavailable")
            return view
        if not self._approved:
            return CharacterReplyCandidateView("unavailable", "trial-not-approved", request_digest=view.request_digest)
        cached = self._cached(view.request_digest)
        if cached is not None:
            return cached
        if self._stopped or self._gateway is None:
            return CharacterReplyCandidateView("unavailable", "trial-stopped", request_digest=view.request_digest)
        if self._next >= len(self._requests) or self._requests[self._next]["request_digest"] != view.request_digest:
            return CharacterReplyCandidateView("rejected", "trial-request-out-of-order", request_digest=view.request_digest)
        # Claim the attempt durably before a credential can be resolved.
        try:
            _write_once(self._run / (view.request_digest + ".attempt.json"),
                        dict(request_digest=view.request_digest, index=self._next, status="attempted"))
        except Exception:
            self._stop("trial-attempt-record-unavailable")
            return CharacterReplyCandidateView("unknown", "trial-attempt-record-unavailable", request_digest=view.request_digest)
        self._next += 1
        try:
            value = self._gateway.execute(ModelTask(ModelTaskKind.CHARACTER_CONTEXT_REPLY, view.projection)).value
            if (type(value) is not dict or set(value) != {"reply_text", "language"}
                    or value["language"] != "zh" or not isinstance(value["reply_text"], str)
                    or not value["reply_text"].strip() or len(value["reply_text"]) > 1200):
                raise ValueError("invalid trial reply")
            result = CharacterReplyCandidateView("candidate", request_digest=view.request_digest,
                                                 reply_text=value["reply_text"], semantic_review="required")
        except ModelGatewayFailure as failure:
            self._stop("trial-attempt-failed")
            unavailable = failure.code == "character-credential-unavailable"
            result = CharacterReplyCandidateView("unavailable" if unavailable else "failed-closed",
                "character-credential-unavailable" if unavailable else "trial-attempt-failed",
                request_digest=view.request_digest)
        except Exception:
            self._stop("trial-attempt-failed")
            result = CharacterReplyCandidateView("failed-closed", "trial-attempt-failed", request_digest=view.request_digest)
        audit = {key: asdict(result)[key] for key in ("status", "code", "request_digest", "reply_text", "semantic_review")}
        try:
            _write_once(self._run / (view.request_digest + ".result.json"), audit)
        except Exception:
            self._stop("trial-result-record-unavailable")
            result = CharacterReplyCandidateView("unknown", "trial-result-record-unavailable", request_digest=view.request_digest)
        self._results[view.request_digest] = result
        return result

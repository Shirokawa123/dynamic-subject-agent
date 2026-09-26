"""Frozen candidate calibration, separate from generation allowances."""
from dataclasses import asdict, dataclass
from hashlib import sha256

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_reply_candidate import CharacterReplyProducer, CharacterReplyCandidateView
from dynamic_subject_agent.character_reply_review import (
    review_projection, review_candidate, validated_review,
)
from dynamic_subject_agent.character_context_trial import CharacterContextTrialPlan, save_trial_plan
from dynamic_subject_agent.frozen_attempt import canonical_json, FrozenAttemptRun
from dynamic_subject_agent.deepseek import DEEPSEEK_ENDPOINT, _ACCEPTED_RESPONSE_MODELS

REVIEW_MODEL = "deepseek-flash"


@dataclass(frozen=True)
class CharacterReplyReviewRequest:
    context_request: CharacterChatContextRequest
    case_id: str


def validate_review_cases(value):
    if (type(value) is not dict or set(value) != {"version", "cases"}
            or value["version"] != "character-reply-review-cases-1"
            or type(value["cases"]) is not list or len(value["cases"]) != 24):
        raise ValueError("twenty-four fixed review cases required")
    ids = set()
    for case in value["cases"]:
        if (type(case) is not dict or set(case) != {"id", "message", "context_mode", "candidate_text"}
                or not isinstance(case["id"], str) or not case["id"].strip() or len(case["id"]) > 80
                or case["id"] in ids or case["context_mode"] not in ("flat", "organized")
                or not isinstance(case["message"], str) or not case["message"].strip() or len(case["message"]) > 1000
                or not isinstance(case["candidate_text"], str) or not case["candidate_text"].strip()
                or len(case["candidate_text"]) > 1200):
            raise ValueError("invalid frozen review case")
        ids.add(case["id"])


def review_digest(projection):
    return sha256(canonical_json(asdict(projection)).encode()).hexdigest()


def build_review_plan(preview_reply, *, reviewed_digest, subject_id, anchor_id, cases, max_knowledge_chars):
    from dynamic_subject_agent.character_reply_review_provider import DeepSeekCharacterReplyReviewAdapter
    validate_review_cases(cases)
    requests, digests = [], set()
    for case in cases["cases"]:
        request = CharacterChatContextRequest(subject_id, anchor_id, case["message"], case["context_mode"], max_knowledge_chars)
        view = preview_reply(request)
        if view.status != "previewed" or view.projection is None:
            raise ValueError("review-context-not-available")
        projection = review_projection(view.projection, case["candidate_text"])
        digest = review_digest(projection)
        if digest in digests:
            raise ValueError("duplicate review request")
        digests.add(digest)
        wire = DeepSeekCharacterReplyReviewAdapter.outbound_bytes(projection)
        requests.append(dict(case_id=case["id"], mode=case["context_mode"], message=case["message"],
            context_request_digest=view.request_digest, request_digest=digest,
            outbound_digest=sha256(wire).hexdigest(), projection=asdict(projection)))
    payload = dict(version="character-reply-review-trial-1", reviewed_digest=reviewed_digest,
        subject_id=subject_id, anchor_id=anchor_id, cases=cases["cases"], requests=requests,
        endpoint=DEEPSEEK_ENDPOINT, model=REVIEW_MODEL, accepted_response_models=list(_ACCEPTED_RESPONSE_MODELS),
        max_knowledge_chars=max_knowledge_chars,
        generation=dict(max_tokens=600, temperature=0.0, thinking={"type": "disabled"},
                        response_format={"type": "json_object"}, stream=False),
        execution="24 ordered review requests only; one attempt each; stop on source, credential, transport, structure or audit failure; no retry or restart continuation",
        retention="Independent local review audit only: plan, identifiers, sanitized status and validated review; no key, headers, reasoning or raw response",
        scope="Reviewed self knowledge, stage, interaction branch, fixed messages and frozen candidate text only; no source text, author IDs, private history, expected labels or runtime updates; no generator",
        approval="Exact digest is an operator assertion; new user approval for review data use must exist before execution")
    return CharacterContextTrialPlan(canonical_json(payload))


class CharacterReplyReviewTrial(CharacterReplyProducer):
    """Full reply operation reviews its frozen candidate instead of generating."""

    def __init__(self, plan, *, root, gateway, approved_plan):
        from pathlib import Path
        if (type(plan) is not CharacterContextTrialPlan or not isinstance(root, Path) or not root.is_absolute()
                or plan.payload.get("version") != "character-reply-review-trial-1"):
            raise ValueError("typed review plan and absolute root required")
        if approved_plan is not None and approved_plan != plan.digest:
            raise ValueError("current review approval required")
        self._plan, self._gateway = plan, gateway
        self._requests = plan.payload["requests"]
        self._cases = {row["case_id"]: row for row in self._requests}
        save_trial_plan(root, plan)
        self._ledger = FrozenAttemptRun(root, plan.digest, approved=approved_plan is not None)
        if self._ledger.resumed:
            self._gateway = None

    def context_request(self, request):
        return request.context_request if type(request) is CharacterReplyReviewRequest else None

    def preview(self, view, *, request=None):
        if view.status != "previewed":
            return view
        if type(request) is not CharacterReplyReviewRequest or not isinstance(request.case_id, str):
            return CharacterReplyCandidateView("rejected", "review-request-not-in-plan")
        row = self._cases.get(request.case_id)
        if row is None or view.request_digest != row["context_request_digest"]:
            return CharacterReplyCandidateView("rejected", "review-request-not-in-plan")
        try:
            projection = review_projection(view.projection, row["projection"]["candidate_text"])
            digest = review_digest(projection)
            if digest != row["request_digest"]:
                raise ValueError("changed review projection")
            return CharacterReplyCandidateView("previewed", projection=projection, request_digest=digest)
        except Exception:
            return CharacterReplyCandidateView("failed-closed", "review-context-invalid")

    def _cached(self, view):
        digest = view.request_digest
        if digest in self._ledger.results:
            return self._ledger.results[digest]
        if not self._ledger.resumed:
            return None
        try:
            value = self._ledger.read_result(digest)
            if (type(value) is not dict or set(value) != {"status", "code", "request_digest", "reply_text",
                    "semantic_review", "review_verdict", "review_issues"} or value["request_digest"] != digest):
                raise ValueError("invalid review audit")
            verdict = value["review_verdict"]
            if verdict in ("supported", "unsupported", "uncertain"):
                verdict, issues = validated_review(dict(verdict=verdict, issues=value["review_issues"]), view.projection)
                expected = dict(status="candidate" if verdict == "supported" else "rejected",
                    code="" if verdict == "supported" else "reply-review-" + verdict,
                    reply_text=view.projection.candidate_text if verdict == "supported" else "",
                    semantic_review="model-" + verdict)
                if any(value[key] != item for key, item in expected.items()):
                    raise ValueError("invalid completed review")
                return CharacterReplyCandidateView(**{**value, "review_issues": issues})
            expected = {"failed-closed": "reply-review-failed", "unavailable": "character-credential-unavailable"}
            if (value["status"] not in expected or value["code"] != expected[value["status"]]
                    or value["reply_text"] != "" or value["semantic_review"] != "not-performed"
                    or verdict != "" or value["review_issues"] != []):
                raise ValueError("invalid failure review")
            return CharacterReplyCandidateView(**{**value, "review_issues": ()})
        except Exception:
            return CharacterReplyCandidateView("unknown", "review-previously-started", request_digest=digest)

    def propose(self, view):
        if view.status != "previewed":
            if self._ledger.approved and view.status in ("failed-closed", "unavailable"):
                self._ledger.stop("review-context-unavailable")
            return view
        if not self._ledger.approved:
            return CharacterReplyCandidateView("unavailable", "review-not-approved", request_digest=view.request_digest)
        cached = self._cached(view)
        if cached is not None:
            return cached
        if self._ledger.stopped or self._gateway is None:
            return CharacterReplyCandidateView("unavailable", "review-stopped", request_digest=view.request_digest)
        if (self._ledger.next >= len(self._requests)
                or self._requests[self._ledger.next]["request_digest"] != view.request_digest):
            return CharacterReplyCandidateView("rejected", "review-request-out-of-order", request_digest=view.request_digest)
        try:
            self._ledger.claim(view.request_digest)
        except Exception:
            self._ledger.stop("review-attempt-record-unavailable")
            return CharacterReplyCandidateView("unknown", "review-attempt-record-unavailable", request_digest=view.request_digest)
        result = review_candidate(self._gateway, view.projection, request_digest=view.request_digest)
        if result.status in ("failed-closed", "unavailable"):
            self._ledger.stop("review-attempt-failed")
        audit = {key: asdict(result)[key] for key in ("status", "code", "request_digest", "reply_text",
                                                   "semantic_review", "review_verdict", "review_issues")}
        try:
            self._ledger.record(view.request_digest, audit)
        except Exception:
            self._ledger.stop("review-result-record-unavailable")
            result = CharacterReplyCandidateView("unknown", "review-result-record-unavailable", request_digest=view.request_digest)
        self._ledger.results[view.request_digest] = result
        return result

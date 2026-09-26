"""Frozen, one-attempt character-context comparison; never runtime state."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun, canonical_json, write_once as _write_once
from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_reply_candidate import (
    CharacterReplyCandidateView, CharacterReplyProjection, CharacterReplyProducer, REPLY_POLICY,
)
from dynamic_subject_agent.deepseek import DEEPSEEK_ENDPOINT, _ACCEPTED_RESPONSE_MODELS
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind, ModelGatewayFailure

# Explicit V4.1-Flash alias for the user-approved new character route.
TRIAL_MODEL = "deepseek-flash"

TRIAL_POLICY = REPLY_POLICY + (
    "若self_knowledge含core，它是常驻的连贯自我认识；episode/detail仅是本轮选中的相关经历和细节。"
    "未选中或没有匹配不表示本人不知道、没有其他经历或资料全空。"
    "组织摘要由作者审核，basis=linked-evidence表示有审核依据；kind=belief不得当成已证实事实。"
    "答复采用两个来源：自述事实来自已给本人知识并保留原时间/频率；新意见用此刻的看法或条件句表达。只说这轮需要的部分。"
    "先辨明有依据与尚不能确认，再决定已知内容愿意讲多少。确定的否定也需要依据；未知身份对应与已知秘密是两种不同情况。"
    "下面四段是无关职业的表达演示，只学习如何承接，不把其中背景当成当前人物的事实或在回答中提及演示。"
    "演示一：某花艺师的已知背景只有多年从业。面对'你昨夜第一次插花还摆坏了'，答：'这行我做了有些年了。昨夜那段说法，你是从哪里听来的？'这只承接有依据的经验，给具体未明事件留下核实空间。"
    "演示二：某译者只在一次旧合作中遇过术语资料不足。面对开放聊天，答：'我想聊聊译名的取舍。准确和读起来顺口有冲突时，你更在意哪个？'这是当前话题和观点，无须添一段最近的烦恼或一贯流程。"
    "演示三：某人认识合作方署名，尚未确认其现实身份。被问'这个署名是不是你的亲人'，答：'我认得这个署名，不过你说的现实对应，我还不能确认。'这表达未确认，不用隐私保留暗示自己知道答案。"
    "演示四：某人确实使用一个笔名、与亲人同住。初识者问起时，可答：'那个名字我认得。'或'我有家人一起住，具体家事先不聊。'这保留已知事实，也保留披露选择。"
    "当前人物仍只用实际self_knowledge、stage_description与encounter。遇到没有根据的具体往事或频率，回答有把握的部分并自然澄清；提出意见时直接谈取舍。"
    "通常两三句即可，可以自然追问，也可以不追问。保持人物自己的声音，不朗读档案、输入、审核、演示或规则，不输出分析过程。"
)


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


def save_trial_plan(root: Path, plan: CharacterContextTrialPlan):
    root.mkdir(parents=True, exist_ok=True)
    path = root / (plan.digest + ".plan.json")
    try:
        _write_once(path, dict(plan=plan.payload, digest=plan.digest))
    except FileExistsError:
        if path.read_text(encoding="utf-8") != canonical_json(dict(plan=plan.payload, digest=plan.digest)):
            raise ValueError("stored-trial-plan-invalid") from None
    return path


class CharacterContextTrial(CharacterReplyProducer):
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
        save_trial_plan(root, plan)
        self._ledger = FrozenAttemptRun(root, plan.digest, approved=approved_plan is not None)
        if self._ledger.resumed:
            self._gateway = None

    def preview(self, view: CharacterReplyCandidateView, *, request=None):
        view = trial_preview(view)
        if view.status == "previewed" and view.request_digest not in self._allowed:
            return CharacterReplyCandidateView("rejected", "trial-request-not-in-plan")
        return view

    def _cached(self, digest):
        if digest in self._ledger.results:
            return self._ledger.results[digest]
        if self._ledger.resumed:
            try:
                value = self._ledger.read_result(digest)
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
        self._ledger.stop(reason)

    def propose(self, view: CharacterReplyCandidateView):
        view = self.preview(view)
        if view.status != "previewed":
            if self._ledger.approved and view.status in ("failed-closed", "unavailable"):
                self._stop("trial-context-unavailable")
            return view
        if not self._ledger.approved:
            return CharacterReplyCandidateView("unavailable", "trial-not-approved", request_digest=view.request_digest)
        cached = self._cached(view.request_digest)
        if cached is not None:
            return cached
        if self._ledger.stopped or self._gateway is None:
            return CharacterReplyCandidateView("unavailable", "trial-stopped", request_digest=view.request_digest)
        if self._ledger.next >= len(self._requests) or self._requests[self._ledger.next]["request_digest"] != view.request_digest:
            return CharacterReplyCandidateView("rejected", "trial-request-out-of-order", request_digest=view.request_digest)
        # Claim the attempt durably before a credential can be resolved.
        try:
            self._ledger.claim(view.request_digest)
        except Exception:
            self._stop("trial-attempt-record-unavailable")
            return CharacterReplyCandidateView("unknown", "trial-attempt-record-unavailable", request_digest=view.request_digest)
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
            self._ledger.record(view.request_digest, audit)
        except Exception:
            self._stop("trial-result-record-unavailable")
            result = CharacterReplyCandidateView("unknown", "trial-result-record-unavailable", request_digest=view.request_digest)
        self._ledger.results[view.request_digest] = result
        return result

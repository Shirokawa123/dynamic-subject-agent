"""Local candidate interpretations retained across planning and expression."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest, SelfKnowledge, prepare_context
from dynamic_subject_agent.character_evidence_model import CharacterModelRequest, CharacterEvidenceModel
from dynamic_subject_agent.character_communication_plan import (
    CommunicationFact, CommunicationPlanProjection, CommunicationExpressionProjection, _validate_projection,
    _plan_projection, _projection_digest, _qualify_plan, _expression_projection, _validated_expression,
)
from dynamic_subject_agent.character_reply_candidate import CharacterReplyProducer, CharacterReplyCandidateView, preview_reply
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind

PERSONALITY_POLICY = (
    "character_core是同一起点的已审常驻认识，保留kind及成立/知情范围；未选事实不表示人物不知道。"
    "personality是作者提出的有条件解释，不是原作事实、永久状态、诊断或当前情绪。"
    "support_includes_belief=true时支持包含本人信念，不能据此声称人格已被证实。"
    "结合when决定choice/表达倾向，保留limits；不同对象和话题可以有不同反应，不按关键词强制发怒、害羞、冷淡。"
    "常驻核心与解释不增加新经历、关系或生活状态；过去意义不等于当下目标，不照搬后期成长或家人称呼。"
    "conversation保持原action/fact_refs或reply_text/language契约，不输出分析、档案或内部规则。"
)


@dataclass(frozen=True)
class PersonalityInterpretation:
    title: str
    interpretation: str
    when: str
    choice: str
    expression: str
    limits: str
    basis: str = "author-interpretation"
    support_includes_belief: bool = False


@dataclass(frozen=True)
class CharacterPlanningEnvelope:
    conversation: CommunicationPlanProjection
    character_core: tuple[SelfKnowledge, ...]
    personality: tuple[PersonalityInterpretation, ...]
    policy: str = PERSONALITY_POLICY


@dataclass(frozen=True)
class CharacterExpressionEnvelope:
    conversation: CommunicationExpressionProjection
    character_core: tuple[SelfKnowledge, ...]
    personality: tuple[PersonalityInterpretation, ...]
    policy: str = PERSONALITY_POLICY


def _bounded_envelope(value):
    if len(canonical_json(asdict(value)).encode()) > 65536:
        raise ValueError("personality envelope too large")
    return value


def frozen_personality_planning(value):
    """Decode only the already frozen planning envelope, never author a new one."""
    conversation = value["conversation"]
    inner = CommunicationPlanProjection(tuple(CommunicationFact(**item) for item in conversation["self_knowledge"]),
        conversation["stage_description"], tuple(conversation["encounter"]), tuple(conversation["disclosure"]),
        conversation["current_message"], conversation["policy"])
    _validate_projection(inner)
    envelope = CharacterPlanningEnvelope(inner, tuple(SelfKnowledge(**item) for item in value["character_core"]),
        tuple(PersonalityInterpretation(**item) for item in value["personality"]), value["policy"])
    if (canonical_json(asdict(envelope)) != canonical_json(value) or envelope.policy != PERSONALITY_POLICY
            or not envelope.character_core or not 1 <= len(envelope.personality) <= 8
            or any(item.basis != "author-interpretation" or type(item.support_includes_belief) is not bool for item in envelope.personality)):
        raise ValueError("frozen personality envelope invalid")
    return _bounded_envelope(envelope)


def personality_expression(context, value):
    plan = _qualify_plan(value, context.conversation, _projection_digest(context.conversation))
    expression = _expression_projection(plan, context.conversation)
    return _bounded_envelope(CharacterExpressionEnvelope(expression, context.character_core, context.personality))


def load_personality_draft(model, sidecar_path, expected_digest):
    if (not isinstance(sidecar_path, Path) or not sidecar_path.is_absolute() or not isinstance(expected_digest, str)
            or len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest)):
        raise ValueError("reviewed personality sidecar required")
    with sidecar_path.open("rb") as stream:
        raw = stream.read(48001)
    if len(raw) > 48000 or sha256(raw).hexdigest() != expected_digest:
        raise ValueError("personality sidecar changed")
    value = json.loads(raw.decode("utf-8"))
    if (type(value) is not dict or set(value) != {"version", "status", "base_reviewed_digest", "subject_id", "anchor_id", "items"}
            or value["version"] != "character-personality-draft-1" or value["status"] != "local-interpretation-candidates"
            or value["base_reviewed_digest"] != model.draft_digest or value["subject_id"] != model.subject_id
            or value["anchor_id"] != model.anchor_id or type(value["items"]) is not list or not 1 <= len(value["items"]) <= 8
            or len(canonical_json(value)) > 12000):
        raise ValueError("personality sidecar binding invalid")
    known = {item.item_id: item for item in model.known}
    identities, result = set(), []
    text_fields = ("title", "interpretation", "when", "choice", "expression", "limits")
    for item in value["items"]:
        if (type(item) is not dict or set(item) != {"id", *text_fields, "claim_ids"}
                or not isinstance(item["id"], str) or not item["id"].strip() or len(item["id"]) > 80 or item["id"] in identities
                or any(not isinstance(item[key], str) or not item[key].strip() or len(item[key]) > (100 if key == "title" else 500)
                       or "\x00" in item[key] for key in text_fields)
                or type(item["claim_ids"]) is not list or not 1 <= len(item["claim_ids"]) <= 16
                or any(not isinstance(key, str) or key not in known for key in item["claim_ids"])
                or len(set(item["claim_ids"])) != len(item["claim_ids"])):
            raise ValueError("personality support or fields invalid")
        identities.add(item["id"])
        result.append(PersonalityInterpretation(**{key: item[key] for key in text_fields},
            support_includes_belief=any(known[key].kind == "belief" for key in item["claim_ids"])))
    return tuple(result), value


class CharacterPersonalityLab(CharacterReplyProducer):
    """One read-only source binding and two explicit local semantic tasks."""

    def __init__(self, *, model, sidecar_path, expected_digest, plan_gateway=None, expression_gateway=None):
        if (not isinstance(model, CharacterEvidenceModel) or not isinstance(sidecar_path, Path) or not sidecar_path.is_absolute()
                or not isinstance(expected_digest, str) or len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest)):
            raise ValueError("typed model and reviewed personality sidecar required")
        if (plan_gateway is None) != (expression_gateway is None):
            raise ValueError("both local gateways or preview only required")
        for gateway in (plan_gateway, expression_gateway):
            if gateway is not None and (not isinstance(gateway, ModelGateway) or gateway.capabilities.local is not True):
                raise ValueError("local-only-personality-gateway-required")
        self._model, self._path, self._digest = model, sidecar_path, expected_digest
        self._planner, self._expresser = plan_gateway, expression_gateway

    def _interpretations(self, model):
        return load_personality_draft(model, self._path, self._digest)[0]

    def preview(self, view, *, request=None):
        if view.status != "previewed": return view
        if type(request) is not CharacterChatContextRequest:
            return CharacterReplyCandidateView("rejected", "typed-personality-context-required")
        try:
            model = self._model.preview(CharacterModelRequest(request.subject_id, request.anchor_id))
            if model.status != "previewed":
                return CharacterReplyCandidateView(model.status, model.code)
            if not model.chat_stage_description or not any(item.dimension == "identity" for item in model.known):
                raise ValueError("personality source not available")
            context = prepare_context(model, request.current_message, context_mode=request.context_mode, max_knowledge_chars=request.max_knowledge_chars)
            checked = preview_reply(context)
            conversation = _plan_projection(view.projection)
            if checked.status != "previewed" or _projection_digest(_plan_projection(checked.projection)) != _projection_digest(conversation):
                raise ValueError("same verified source required")
            if model.chat_organization is not None:
                organized = prepare_context(model, request.current_message, context_mode="organized", max_knowledge_chars=20000)
                if organized.status != "previewed": raise ValueError("complete core unavailable")
                core = tuple(item for item in organized.self_knowledge if item.dimension == "core")
            else:
                core = tuple(SelfKnowledge(item.dimension, item.statement, item.kind, item.derivation, item.event_time, item.knowledge_time)
                             for item in model.known if item.dimension == "identity")
            if not core: raise ValueError("character core missing")
            envelope = _bounded_envelope(CharacterPlanningEnvelope(conversation, core, self._interpretations(model)))
            return CharacterReplyCandidateView("previewed", projection=envelope, request_digest=_projection_digest(envelope))
        except FileNotFoundError:
            return CharacterReplyCandidateView("unavailable", "character-personality-sidecar-missing")
        except Exception:
            return CharacterReplyCandidateView("failed-closed", "character-personality-unavailable")

    def propose(self, preview):
        if preview.status != "previewed": return preview
        if self._planner is None:
            return CharacterReplyCandidateView("unavailable", "personality-preview-only", request_digest=preview.request_digest)
        envelope = preview.projection
        try:
            if type(envelope) is not CharacterPlanningEnvelope or _projection_digest(envelope) != preview.request_digest:
                raise ValueError("typed current envelope required")
            value = self._planner.execute(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, envelope)).value
            plan = _qualify_plan(value, envelope.conversation, _projection_digest(envelope.conversation))
            expression = _expression_projection(plan, envelope.conversation)
            output = _bounded_envelope(CharacterExpressionEnvelope(expression, envelope.character_core, envelope.personality))
        except Exception:
            return CharacterReplyCandidateView("failed-closed", "personality-plan-unavailable", request_digest=preview.request_digest)
        try:
            value = self._expresser.execute(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, output)).value
            reply = _validated_expression(value)
        except Exception:
            return CharacterReplyCandidateView("failed-closed", "personality-expression-unavailable", request_digest=preview.request_digest)
        return CharacterReplyCandidateView("candidate", request_digest=preview.request_digest, reply_text=reply, semantic_review="required")

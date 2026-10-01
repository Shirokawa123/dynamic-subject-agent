"""Provider-neutral local reply projections and validation; no wire or sender.

The v4 planning selection is reused unchanged. These independent payload types
cannot be sent by its Adapter, and their digests grant no remote authority.
"""
from dataclasses import asdict, dataclass, replace
import re

from dynamic_subject_agent import first_life_followup as v4
from dynamic_subject_agent.character_chat_context import SelfKnowledge
from dynamic_subject_agent.character_communication_plan import (
    COMMUNICATION_ACTIONS, PLAN_POLICY, CommunicationFact,
    CommunicationPlanProjection, CommunicationExpressionProjection,
    _validate_projection, _validated_expression,
)
from dynamic_subject_agent.character_personality import PersonalityInterpretation
from dynamic_subject_agent.first_life import LIFE_FIELDS, LIFE_PHASES, validate_plan
from dynamic_subject_agent.first_life_relevance import CHAT_FOCUS
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection


WHOLE_LOCAL_POLICY = "first-life-whole-local-1"
PLANNED_LOCAL_POLICY = "first-life-planned-local-1"
LOCAL_REPLY_POLICIES = (WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY)
WHOLE_LIVE_POLICY = "first-life-whole-live-s112-1"
PLANNED_LIVE_POLICY = "first-life-planned-live-s112-1"
LIVE_REPLY_POLICIES = (WHOLE_LIVE_POLICY, PLANNED_LIVE_POLICY)
REPLY_POLICIES = LOCAL_REPLY_POLICIES + LIVE_REPLY_POLICIES
WHOLE_REPLY_POLICIES = (WHOLE_LOCAL_POLICY, WHOLE_LIVE_POLICY)
PLANNED_REPLY_POLICIES = (PLANNED_LOCAL_POLICY, PLANNED_LIVE_POLICY)
FACT_GROUNDING_POLICY = (
    "current_activity/current_plan/related_event是当前已核验的有限构图文字依据，可用于判断而不必朗读。"
    "dialogue_sources/selected_dialogue只证明对应说话者曾这样说；旧回复、主动分享和用户前提不覆盖当前依据。"
    "发生过、知道、准备说与已披露分开；拿到依据不等于必须披露。"
    "文字方案不证明真实房间布局、已经完成图片、技能变化或外部反馈；新建议不变已发生事件。"
    "use_life只表示本轮提议披露related_event所对应的既有生活内容，不创建新事件，不证明自由正文已经核实。"
    "use_life=false时仍用生活依据避免错误判断，但不主动讲述该事件；true时也只讲与当前交流有关的有限内容。"
)
WHOLE_REPLY_POLICY = FACT_GROUNDING_POLICY + (
    "以同一个虚构人物自然接续当前交流，默认两三句中文短消息，可以表达本轮取舍。"
    "self_knowledge保留kind、basis及成立/知情限定；知情不等于可以披露，disclosure仍约束公开。"
    "核心和作者解释是理解背景，不是每轮必说的清单；不补造过去、持续心理活动、关系或生活后果。"
    "只返回JSON exact {reply_text,language,use_life}；language=zh，reply_text非空且最多1200字符，"
    "use_life严格布尔，related_event为空时必须false。不要输出动作旁白、分析、内部字段或思考过程。"
)
FACT_EXPRESSION_POLICY = v4.LIFE_CHAT_EXPRESSION_POLICY + FACT_GROUNDING_POLICY + (
    "输入use_life是Python已裁决的本轮披露选择；事实始终保留供判断，不把事实可见误作必须说出的清单。"
    "selected_facts与selected_dialogue是本轮准备表达的材料，保留其完整限定及说话者。"
    "只返回JSON exact {reply_text,language}；language=zh，reply_text非空且最多1200字符。"
)


@dataclass(frozen=True)
class WholeReplyProjection:
    conversation: CommunicationPlanProjection
    character_core: tuple
    personality: tuple
    runtime_identity: RuntimeIdentityProjection
    dialogue_sources: tuple
    has_prior_committed_exchange: bool
    history_enabled: bool
    current_activity: dict
    current_plan: dict | None
    related_event: dict | None
    policy: str = WHOLE_REPLY_POLICY


@dataclass(frozen=True)
class FactExpressionProjection:
    conversation: CommunicationExpressionProjection
    character_core: tuple
    personality: tuple
    runtime_identity: RuntimeIdentityProjection
    selected_dialogue: tuple
    has_prior_committed_exchange: bool
    history_enabled: bool
    current_activity: dict
    current_plan: dict | None
    related_event: dict | None
    focus: str
    use_life: bool
    policy: str = FACT_EXPRESSION_POLICY


def _text(value, maximum=None, *, empty=False):
    if (not isinstance(value, str) or "\x00" in value or not empty and not value.strip()
        or maximum is not None and len(value) > maximum):
        raise ValueError("bounded projection text required")


def _common(projection):
    if (type(projection.runtime_identity) is not RuntimeIdentityProjection
        or type(projection.has_prior_committed_exchange) is not bool
        or type(projection.history_enabled) is not bool
        or type(projection.character_core) is not tuple or not projection.character_core
        or type(projection.personality) is not tuple or not 1 <= len(projection.personality) <= 8):
        raise ValueError("exact local reply background required")
    for row in projection.character_core:
        if type(row) is not SelfKnowledge:
            raise ValueError("typed character core required")
        for value in asdict(row).values():
            _text(value)
    for row in projection.personality:
        if (type(row) is not PersonalityInterpretation or row.basis != "author-interpretation"
            or type(row.support_includes_belief) is not bool):
            raise ValueError("typed bounded personality required")
        for field in ("title", "interpretation", "when", "choice", "expression", "limits"):
            _text(getattr(row, field), 100 if field == "title" else 500)
    activity = projection.current_activity
    if (type(activity) is not dict or set(activity) != {"project_kind", "phase", "revision", "allowed_actions"}
        or activity["project_kind"] != "drawing-composition-text" or activity["phase"] not in LIFE_PHASES
        or type(activity["revision"]) is not int or activity["revision"] < 0):
        raise ValueError("exact activity judgment facts required")
    actions = {"unstarted": ["start", "defer"], "drafted": ["revise", "defer"],
        "revised": ["keep", "rework", "defer"], "rework": ["revise", "defer"], "kept": [], "deferred": []}
    if type(activity["allowed_actions"]) is not list or activity["allowed_actions"] != actions[activity["phase"]]:
        raise ValueError("exact activity actions required")
    if projection.current_plan is not None:
        validate_plan(projection.current_plan)
    event = projection.related_event
    if event is not None:
        if (type(event) is not dict or set(event) != {"kind", "revision", "summary", "differences", "simulated", "content_kind"}
            or type(event["revision"]) is not int or not 0 <= event["revision"] <= activity["revision"]
            or type(event["simulated"]) is not bool or event["content_kind"] != "creative-composition-text-not-image"
            or type(event["differences"]) is not list or len(event["differences"]) > 3):
            raise ValueError("exact related event judgment facts required")
        _text(event["kind"], 80)
        _text(event["summary"], 2000)
        fields = []
        for difference in event["differences"]:
            if (type(difference) is not dict or set(difference) != {"field", "before", "after"}
                or difference["field"] not in LIFE_FIELDS):
                raise ValueError("exact event differences required")
            fields.append(difference["field"])
            maximum = {"subject": 160, "composition": 800, "focus": 400}[difference["field"]]
            _text(difference["before"], maximum, empty=True)
            _text(difference["after"], maximum)
        if len(set(fields)) != len(fields):
            raise ValueError("unique event differences required")
    if len(canonical_json(asdict(projection)).encode()) > 65536:
        raise ValueError("local reply projection oversized")


def _planning(planning):
    if (type(planning) is not v4.FirstLifeChatPlanning or planning.policy != v4.LIFE_CHAT_POLICY
        or type(planning.conversation) is not CommunicationPlanProjection
        or planning.conversation.policy != v4.LIFE_CHAT_SELECTION_POLICY):
        raise ValueError("exact v4 planning basis required")
    _validate_projection(replace(planning.conversation, policy=PLAN_POLICY))
    v4._validate_sources(planning.dialogue_sources, planning.history_enabled)
    _common(planning)


def _whole(projection):
    if (type(projection) is not WholeReplyProjection or projection.policy != WHOLE_REPLY_POLICY
        or type(projection.conversation) is not CommunicationPlanProjection
        or projection.conversation.policy != WHOLE_REPLY_POLICY):
        raise ValueError("exact whole local reply projection required")
    _validate_projection(replace(projection.conversation, policy=PLAN_POLICY))
    v4._validate_sources(projection.dialogue_sources, projection.history_enabled)
    _common(projection)


def _expression(projection):
    if (type(projection) is not FactExpressionProjection or projection.policy != FACT_EXPRESSION_POLICY
        or type(projection.conversation) is not CommunicationExpressionProjection
        or projection.conversation.policy != FACT_EXPRESSION_POLICY
        or projection.focus not in CHAT_FOCUS or type(projection.use_life) is not bool
        or projection.use_life and projection.related_event is None
        or projection.focus == "explain-encounter" and projection.selected_dialogue):
        raise ValueError("exact fact-preserving expression required")
    conversation = projection.conversation
    facts = conversation.selected_facts
    if (conversation.action not in COMMUNICATION_ACTIONS or type(facts) is not tuple or len(facts) > 2
        or any(type(row) is not CommunicationFact for row in facts)
        or any(re.fullmatch(r"F[1-9][0-9]*", row.label) is None for row in facts)
        or len({row.label for row in facts}) != len(facts)):
        raise ValueError("bounded selected facts required")
    # Reuse the inner text/foreground bounds without changing selected F labels.
    checked_facts = tuple(replace(row, label=f"F{index}") for index, row in enumerate(facts, 1))
    _validate_projection(CommunicationPlanProjection(checked_facts, conversation.stage_description,
        conversation.encounter, conversation.disclosure, conversation.current_message))
    v4._validate_sources(projection.selected_dialogue, projection.history_enabled, selected=True)
    _common(projection)


def whole_reply_projection(planning):
    _planning(planning)
    result = WholeReplyProjection(replace(planning.conversation, policy=WHOLE_REPLY_POLICY),
        planning.character_core, planning.personality, planning.runtime_identity, planning.dialogue_sources,
        planning.has_prior_committed_exchange, planning.history_enabled, planning.current_activity,
        planning.current_plan, planning.related_event)
    _whole(result)
    return result


def fact_expression_projection(planning, value):
    _planning(planning)
    selected, use_life = v4.life_chat_expression(planning, value)
    result = FactExpressionProjection(replace(selected.conversation, policy=FACT_EXPRESSION_POLICY),
        selected.character_core, selected.personality, selected.runtime_identity, selected.selected_dialogue,
        selected.has_prior_committed_exchange, selected.history_enabled, planning.current_activity,
        planning.current_plan, planning.related_event, selected.focus, use_life)
    _expression(result)
    return result, use_life


def validate_whole_reply(projection, value):
    _whole(projection)
    if (type(value) is not dict or set(value) != {"reply_text", "language", "use_life"}
        or type(value["use_life"]) is not bool or value["use_life"] and projection.related_event is None):
        raise ValueError("exact whole reply and bounded disclosure choice required")
    text = _validated_expression({key: value[key] for key in ("reply_text", "language")})
    _text(text, 1200)
    return text, value["use_life"]

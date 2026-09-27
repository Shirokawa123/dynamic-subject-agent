"""Read-only bounded life views; event/source/database IDs remain local."""
from dataclasses import asdict, dataclass, replace

from dynamic_subject_agent.first_life import LIFE_POLICY, SHARE_POLICY, LIFE_CHAT_POLICY, LIFE_CHAT_SELECTION_POLICY, LIFE_REASONS
from dynamic_subject_agent.character_chat_context import prepare_context
from dynamic_subject_agent.reviewed_character_chat import sealed_model, planning_projection, ReviewedChatPlanning, ReviewedChatExpression
from dynamic_subject_agent.character_personality import PersonalityInterpretation
from dynamic_subject_agent.frozen_attempt import canonical_json


@dataclass(frozen=True)
class LifeModelProjection:
    runtime_identity: object
    character_core: tuple
    personality: tuple
    self_knowledge: tuple
    stage_description: str
    current_activity: dict
    current_plan: dict | None
    related_event: dict | None
    foreground: dict
    policy: str


@dataclass(frozen=True)
class FirstLifeChatPlanning:
    conversation: object
    character_core: tuple
    personality: tuple
    runtime_identity: object
    recent_dialogue: tuple
    has_prior_committed_exchange: bool
    history_enabled: bool
    current_activity: dict
    current_plan: dict | None
    related_event: dict | None
    policy: str = LIFE_CHAT_POLICY


@dataclass(frozen=True)
class FirstLifeChatExpression:
    conversation: object
    character_core: tuple
    personality: tuple
    runtime_identity: object
    recent_dialogue: tuple
    has_prior_committed_exchange: bool
    history_enabled: bool
    current_activity: dict
    current_plan: dict | None
    related_event: dict | None
    policy: str = LIFE_CHAT_POLICY


def current_activity(basis):
    return dict(project_kind="drawing-composition-text", phase=basis.record.phase, revision=basis.record.revision,
        allowed_actions=list({"unstarted": ("start", "defer"), "drafted": ("revise", "defer"), "revised": ("keep", "rework", "defer"),
                            "rework": ("revise", "defer"), "kept": (), "deferred": ()}[basis.record.phase]))


def select_event(basis, message=""):
    if not basis.events: return None
    if any(token in message for token in ("改", "修", "哪里", "前后", "区别", "版本")):
        revisions = [event for event in basis.events if event.kind in ("revise", "revised", "draft-revised")]
        if revisions: return revisions[-1]
    return basis.events[-1]


def event_projection(basis, event):
    if event is None: return None
    version = next((version for version in basis.versions if version.revision == event.revision), None)
    differences = version.differences if version is not None and event.kind in ("revise", "revised", "draft-revised", "start", "draft-saved") else ()
    return dict(kind=event.kind, revision=event.revision, summary=event.summary,
        differences=[asdict(diff) for diff in differences], simulated=event.simulated,
        content_kind="creative-composition-text-not-image")


def life_model_projection(envelope, identity, basis, *, share=False, target_event=None):
    model = sealed_model(envelope)
    context = prepare_context(model, "绘画构图主题创作与具体能力取舍")
    if context.status != "previewed": raise ValueError("bounded reviewed life basis unavailable")
    core = tuple(item for item in context.self_knowledge if item.dimension == "core")
    if not core:
        core = tuple(item for item in context.self_knowledge if item.dimension == "identity")
    if not core: raise ValueError("complete character core unavailable")
    projection = LifeModelProjection(identity, core, tuple(PersonalityInterpretation(**item) for item in envelope["runtime_asset"]["personality"]),
        context.self_knowledge, model.chat_stage_description, current_activity(basis),
        None if basis.record.plan is None else asdict(basis.record.plan), event_projection(basis, target_event or select_event(basis)),
        dict(has_committed_dialogue=basis.has_dialogue, sharing_allowed=basis.record.sharing_enabled), SHARE_POLICY if share else LIFE_POLICY)
    if len(canonical_json(asdict(projection)).encode()) > 65536: raise ValueError("life model request too large")
    return projection


def life_chat_planning(envelope, identity, message, dialogue, history_enabled, basis):
    base = planning_projection(envelope, identity, message, dialogue, history_enabled)
    event = select_event(basis, message)
    projection = event_projection(basis, event)
    # No offline/not-connected or permanently frozen foreground is copied.
    encounter = tuple(text for text in base.conversation.encounter if "人物时点仍是定义的起点" not in text and "尚未接入" not in text)
    encounter += ("本独立分支已接入有限构图文字活动；仅以已提交版本和事件解释当前变化，不推进原作直播/揭露剧情。",)
    conversation = replace(base.conversation, encounter=encounter, policy=LIFE_CHAT_SELECTION_POLICY)
    result = FirstLifeChatPlanning(conversation, base.character_core, base.personality, base.runtime_identity,
        base.recent_dialogue, base.has_prior_committed_exchange, base.history_enabled, current_activity(basis),
        None if basis.record.plan is None else asdict(basis.record.plan), projection)
    if len(canonical_json(asdict(result)).encode()) > 65536: raise ValueError("life chat projection too large")
    return result, event


def life_chat_expression(planning, value):
    from dynamic_subject_agent.character_communication_plan import _qualify_plan, _expression_projection, _projection_digest
    # The explicit life selection is local and at most one related event. The
    # model selects whether to use it, but cannot invent its payload or ID.
    if type(value) is not dict or set(value) != {"action", "fact_refs", "use_life"} or type(value["use_life"]) is not bool:
        raise ValueError("exact life-chat selection required")
    if value["use_life"] and planning.related_event is None: raise ValueError("no committed event to disclose")
    inner = dict(action=value["action"], fact_refs=value["fact_refs"])
    plan = _qualify_plan(inner, planning.conversation, _projection_digest(planning.conversation))
    conversation = _expression_projection(plan, planning.conversation)
    return FirstLifeChatExpression(conversation, planning.character_core, planning.personality, planning.runtime_identity,
        planning.recent_dialogue, planning.has_prior_committed_exchange, planning.history_enabled,
        planning.current_activity if value["use_life"] else {}, planning.current_plan if value["use_life"] else None,
        planning.related_event if value["use_life"] else None), value["use_life"]

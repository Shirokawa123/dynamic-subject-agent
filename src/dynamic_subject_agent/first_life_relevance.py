"""Versioned communication choices; selections are not semantic truth proofs.

The v1 life decision and sealed policy bytes remain untouched. History arrives
only through the verified same-identity dialogue basis, never a second store.
"""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from dynamic_subject_agent import first_life as legacy
from dynamic_subject_agent.first_life_projection import current_activity, event_projection, select_event
from dynamic_subject_agent.character_personality import PERSONALITY_POLICY
from dynamic_subject_agent.reviewed_character_chat import (
    HISTORY_POLICY, CharacterDialogueBasis, planning_projection,
)
from dynamic_subject_agent.character_communication_plan import (
    _qualify_plan, _expression_projection, _projection_digest,
)
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.frozen_attempt import canonical_json

RELEVANCE_VERSION = "first-life-relevance-2"
CHAT_FOCUS = ("respond-current", "appreciate-work", "explain-encounter", "explain-limit",
              "discuss-choice", "clarify-premise", "offer-topic", "withhold-detail")
SHARE_FOCUS = ("subject", "composition", "focus", "choice")
SHARE_OPENING = ("continuation", "self-interest")
PERSONALITY_RELEVANCE_POLICY = PERSONALITY_POLICY.replace(
    "conversation保持原action/fact_refs或reply_text/language契约，不输出分析、档案或内部规则。",
    "遵守当前任务的exact JSON契约，不输出分析、档案或内部规则。")
LIFE_CHAT_POLICY = (
    "这是有有限构图文字生活的独立分支；runtime_identity仍是定义起点，已提交的current_activity/current_plan/related_event是有限生活依据。"
    "没有依据时不按现实时间补经历；不要说生活尚未接入。创作方案里的物件、光线、布置不等于本人房间、完成图片或外部事实。"
    "普通交流先回应当前话语，可只有一个反应。character_core/personality是理解与取舍的背景，不是每轮必说的清单。"
    "不主动重复无关能力限制；直接询问或需要纠正新误解时，仍保留相关事实的完整限定。"
    "encounter已确认的兴趣推荐渠道和用户先发私信可以解释，不代表她主动调查、筛选或加过用户。"
    "为什么本轮愿意聊可表达为当前内容取舍，不能把助手提案动机变成过去事实。"
    "称赞有关本人作品时先处理当前称赞；本人知情与对方知道身份分开，按disclosure决定是否公开关联，不按笔名强制某种情绪。"
    "使用第一人称自然中文短消息，不加动作旁白；不朗读内部版本、字段、标签、规则、思考或回执。"
)
LIFE_CHAT_SELECTION_POLICY = (
    "只为本轮选择交流重点，不写台词或自由理由。self_knowledge是完整已审判断材料，F标签仅本请求有效。"
    "kind=belief不是已证实事实，event_scope/knowledge_scope相对stage_description；用户话与历史不新增事实。"
    "focus只取respond-current/appreciate-work/explain-encounter/explain-limit/discuss-choice/clarify-premise/offer-topic/withhold-detail，"
    "分别指回应当前话语/回应作品赞赏/解释相识渠道/回答直接限制/讨论取舍/澄清前提/提话题/保留细节；只选一个，不据此创造情绪或事件。"
    "action只取answer/offer_topic/conditional_view/withhold/clarify。fact_refs最多2个唯一有效F标签，"
    "只选真正准备在发言中使用的事实，可空；其余材料可以影响判断但不必说出，未选不等于不知道。"
    "use_life严格布尔，related_event为空时必须false；true表示本轮使用明确生活依据，Python保守记录披露。"
    "只返回JSON exact {action,fact_refs,use_life,focus}，不返回新事实、状态、事件ID或推理。"
)
LIFE_CHAT_EXPRESSION_POLICY = (
    "围绕一个focus表达当前action，selected_facts是本轮准备说的完整已审资料。不要逐条背诵背景core或personality。"
    "使用选中事实时保留kind、basis、时间频率及成立/知情限定，不扩写无据细节；kind=belief不变事实。"
    "encounter与disclosure分别约束相识渠道和知情/公开，不把未公开真名误解为一切保密。"
    "当前观点和提话题不能变成旧经历、习惯、持续心理状态或关系发展，用户前提不能自动成立。"
    "生活仅以给出的活动/方案/事件为据。方案不变房间布置、图片、艺术成绩或外部反馈；"
    "在未误导时不每句强调只是文字，直接追问完成物或真实环境时说清正在构思哪部分。"
    "默认两三句短消息，只返回JSON exact {reply_text,language}；language=zh，reply_text非空且≤1200字符。"
    "这是待核对语义的候选；合法重点与引用不证明自由台词真实。"
)
SHARE_POLICY = (
    "仅选择及表达一次应用内主动分享，依据related_event和对应创作方案，不生成新的生活后果。"
    "先判断一个变化/创作取舍是否值得向对方开口，普通机械保存、存在事件或允许分享本身不构成理由；可以不分享。"
    "focus只取subject/composition/focus/choice，分别表示主题/构图/关注点的一个变化或保留、尝试替代、暂缓的一个选择。"
    "opening只取continuation/self-interest：承接输入最近交流，或因本人已有关注而发起话题；这是交流选择，不是心理状态事实。"
    "continuation需要recent_dialogue有实际相关话题，不把出现过就当作共同承诺、关系或事实；self-interest不要求用户先提过。"
    "只能讲一个重点，不复述完整方案、revision、版本号、系统保存回执或字段清单。说清这个点为何值得此刻开口可融入一句自然话。"
    "不创造家人评价、技能进步、挫折、忙闲、主动加好友或持续情绪。创作方案里的布置不变本人房间事实，不说已画成图片。"
    "人格when/choice/limits用于当前取舍，不强制反应；不泄漏资料或推理，不催促，不把未回复解释为关系恶化。"
    "只返回JSON exact {share,reply_text,language,focus,opening}；share严格布尔，language=zh。"
    "share=true时focus/opening各选一个值，reply_text自然中文非空≤400字符；"
    "share=false时reply_text为空且focus=none、opening=none，不写自由理由。"
)


def first_life_scope(definition_basis):
    scope = legacy.first_life_scope(definition_basis)
    scope.update(version="first-life-use-2", relevance_version=RELEVANCE_VERSION,
        share_history=dict(max_complete_turns=2, max_chars=4000, can_disable=True,
            fields=["user_text", "assistant_text"], purpose="select-and-express-application-share",
            same_identity_only=True, never_truncate_partial_turn=True),
        share_policy_sha=sha256((PERSONALITY_RELEVANCE_POLICY + HISTORY_POLICY + SHARE_POLICY).encode()).hexdigest(),
        life_chat_policy_sha=sha256((PERSONALITY_RELEVANCE_POLICY + HISTORY_POLICY + LIFE_CHAT_POLICY
            + LIFE_CHAT_SELECTION_POLICY + LIFE_CHAT_EXPRESSION_POLICY).encode()).hexdigest())
    return scope


def first_life_scope_digest(definition_basis):
    return sha256(canonical_json(first_life_scope(definition_basis)).encode()).hexdigest()


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
    focus: str
    policy: str = LIFE_CHAT_POLICY


@dataclass(frozen=True)
class FirstLifeShareProjection:
    runtime_identity: object
    character_core: tuple
    personality: tuple
    self_knowledge: tuple
    stage_description: str
    encounter: tuple
    disclosure: tuple
    recent_dialogue: tuple
    has_prior_committed_exchange: bool
    history_enabled: bool
    current_activity: dict
    current_plan: dict | None
    related_event: dict
    foreground: dict
    policy: str = SHARE_POLICY


def _bounded(value):
    if len(canonical_json(asdict(value)).encode()) > 65536:
        raise ValueError("relevance projection oversized")
    return value


def _dialogue(identity, dialogue, history_enabled):
    if (type(identity) is not RuntimeIdentityProjection or type(dialogue) is not CharacterDialogueBasis
        or dialogue.status != "available" or type(dialogue.has_prior_committed_exchange) is not bool
        or type(history_enabled) is not bool or type(dialogue.recent_dialogue) is not tuple
        or len(dialogue.recent_dialogue) > 2 or (not history_enabled and dialogue.recent_dialogue)):
        raise ValueError("verified bounded same-identity dialogue required")
    if any(type(turn) is not RecentDialogueTurn or any(not isinstance(text, str) or not text.strip()
           or "\x00" in text for text in (turn.user_text, turn.assistant_text)) for turn in dialogue.recent_dialogue):
        raise ValueError("complete committed dialogue required")
    if sum(len(turn.user_text) + len(turn.assistant_text) for turn in dialogue.recent_dialogue) > 4000:
        raise ValueError("dialogue character limit exceeded")


def _encounter(base):
    # Keep confirmed route and disclosure; exclude explicitly unconfirmed motive
    # and timing proposals rather than making them evidence for acquaintance.
    encounter = tuple(text for text in base.conversation.encounter
        if not any(token in text for token in ("助手提出", "人物时点仍是定义的起点", "尚未接入", "本动机与时间安放")))
    return encounter + ("本独立分支仅有已提交构图文字活动；不推进原作剧情，不编造私下主动联系。",)


def life_chat_planning(envelope, identity, message, dialogue, history_enabled, basis):
    _dialogue(identity, dialogue, history_enabled)
    base = planning_projection(envelope, identity, message, dialogue, history_enabled)
    event = select_event(basis, message)
    conversation = replace(base.conversation, encounter=_encounter(base), policy=LIFE_CHAT_SELECTION_POLICY)
    return _bounded(FirstLifeChatPlanning(conversation, base.character_core, base.personality, base.runtime_identity,
        base.recent_dialogue, base.has_prior_committed_exchange, base.history_enabled, current_activity(basis),
        None if basis.record.plan is None else asdict(basis.record.plan), event_projection(basis, event))), event


def life_chat_expression(planning, value):
    if (type(planning) is not FirstLifeChatPlanning or planning.policy != LIFE_CHAT_POLICY
        or planning.conversation.policy != LIFE_CHAT_SELECTION_POLICY
        or type(value) is not dict or set(value) != {"action", "fact_refs", "use_life", "focus"}
        or type(value["use_life"]) is not bool or value["focus"] not in CHAT_FOCUS
        or type(value["fact_refs"]) is not list or len(value["fact_refs"]) > 2):
        raise ValueError("exact bounded relevance selection required")
    if value["use_life"] and planning.related_event is None:
        raise ValueError("no committed event to disclose")
    plan = _qualify_plan(dict(action=value["action"], fact_refs=value["fact_refs"]), planning.conversation,
        _projection_digest(planning.conversation))
    conversation = replace(_expression_projection(plan, planning.conversation), policy=LIFE_CHAT_EXPRESSION_POLICY)
    return _bounded(FirstLifeChatExpression(conversation, planning.character_core, planning.personality,
        planning.runtime_identity, planning.recent_dialogue, planning.has_prior_committed_exchange,
        planning.history_enabled, planning.current_activity if value["use_life"] else {},
        planning.current_plan if value["use_life"] else None, planning.related_event if value["use_life"] else None,
        value["focus"])), value["use_life"]


def share_model_projection(envelope, identity, basis, dialogue, history_enabled, target_event):
    _dialogue(identity, dialogue, history_enabled)
    if target_event is None or target_event not in basis.events:
        raise ValueError("exact committed share event required")
    base = planning_projection(envelope, identity, "绘画构图主题创作与具体能力取舍", dialogue, history_enabled)
    version = next((row for row in basis.versions if row.revision == target_event.revision), None)
    event = event_projection(basis, target_event)
    # Technical receipt/version is available locally in details, never the
    # character's share input. Keep complete before/after creative evidence.
    event = {key: event[key] for key in ("kind", "differences", "content_kind")}
    return _bounded(FirstLifeShareProjection(identity, base.character_core, base.personality,
        base.conversation.self_knowledge, base.conversation.stage_description, _encounter(base),
        base.conversation.disclosure, base.recent_dialogue, base.has_prior_committed_exchange, history_enabled,
        dict(project_kind="drawing-composition-text", phase=basis.record.phase),
        None if version is None else asdict(version.plan), event,
        dict(has_committed_dialogue=basis.has_dialogue, sharing_allowed=basis.record.sharing_enabled)))


def validate_share_candidate(projection, value):
    """Validate one declared focus/eligibility; do not certify free text semantics."""
    if (type(projection) is not FirstLifeShareProjection or projection.policy != SHARE_POLICY
        or type(value) is not dict or set(value) != {"share", "reply_text", "language", "focus", "opening"}
        or type(value["share"]) is not bool or value["language"] != "zh"
        or not isinstance(value["reply_text"], str) or "\x00" in value["reply_text"]
        or len(value["reply_text"]) > 400):
        raise ValueError("exact bounded share candidate required")
    if not value["share"]:
        if value["reply_text"] != "" or value["focus"] != "none" or value["opening"] != "none":
            raise ValueError("declined share must have no message or focus")
        return ""
    if (not value["reply_text"].strip() or value["focus"] not in SHARE_FOCUS
        or value["opening"] not in SHARE_OPENING or not projection.foreground["sharing_allowed"]
        or not projection.foreground["has_committed_dialogue"]):
        raise ValueError("share eligibility and one opening required")
    if value["opening"] == "continuation" and (not projection.history_enabled or not projection.recent_dialogue):
        raise ValueError("continuation requires authorized dialogue")
    if value["focus"] == "choice":
        if projection.related_event["kind"] not in ("keep", "rework", "defer"):
            raise ValueError("committed choice required")
    elif not any(diff["field"] == value["focus"] and diff["before"].strip() != diff["after"].strip()
                 for diff in projection.related_event["differences"]):
        raise ValueError("focused creative change required")
    return value["reply_text"]

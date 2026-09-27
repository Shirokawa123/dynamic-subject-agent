"""V3 request-local speaker sources; no new history or world-state authority."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from dynamic_subject_agent import first_life_relevance as v2
from dynamic_subject_agent.character_communication_plan import _qualify_plan, _expression_projection, _projection_digest
from dynamic_subject_agent.frozen_attempt import canonical_json

GROUNDED_VERSION = "first-life-grounded-3"
HISTORY_GROUNDED_POLICY = v2.HISTORY_POLICY.replace("recent_dialogue", "dialogue_sources/selected_dialogue")
SOURCE_POLICY = (
    "dialogue_sources/selected_dialogue是当前身份最近已提交交流的逐字来源，不是最初相识的记录或完整人生。"
    "label仅本请求有效；speaker=user是用户当时报告，speaker=assistant是本人回复曾这样说，二者均不证明世界事实。"
    "不要把assistant的措辞、推测或错误归给user；引用时保持谁说过什么，错误可以承认或更正，不凭历史自证。"
    "近期窗口不能解释第一次为什么愿意回复、最初动机或最初话题。解释相识只用已确认的系统兴趣推荐、用户主动私信渠道；"
    "对现在为什么继续聊，可表达本轮当前取舍，不编成首次原因或过去持续动机。"
    "当前输入仅有文字，没有看见图片。只称赞某笔名/作品但未提供具体图或明确描述时，"
    "可以回应欣赏、流露有依据的在意或谈一般看法，不能生成那张图的表情、眼睛、嘴角、颜色、构图等可见细节画评。"
    "人物资料里有笔名或作者关联也不意味着本轮确定了用户说的是哪张图；用户描述仅是其说法，不能装作亲眼看到。"
    "用户明确用文字描述的细节可以作为其描述承接或讨论，不把文字描述当亲眼所见，也不补造未描述细节。"
    "不能仅凭创作计划断言真实房间如何，也不能据此声称没有参考房间或不是照着房间画；缺少来源依据时保持未知。"
    "仍按情境和disclosure回应，不按笔名强制害羞、否认或揭露身份，也不必朗读资料不足的免责声明。"
)
LIFE_CHAT_POLICY = v2.LIFE_CHAT_POLICY + SOURCE_POLICY
LIFE_CHAT_SELECTION_POLICY = v2.LIFE_CHAT_SELECTION_POLICY.replace(
    "只返回JSON exact {action,fact_refs,use_life,focus}",
    "只返回JSON exact {action,fact_refs,use_life,focus,dialogue_refs}") + (
    "dialogue_refs只选发言真正需要使用的来源label，最多2个唯一有效值，可空，不返回改写文本。"
    "focus=explain-encounter时dialogue_refs必须为空：近期句子不是最初愿意回应的证据。"
    "回应当前文字本身可以不引用历史；不用来源就不选，不为凑数量引用assistant画评。"
)
LIFE_CHAT_EXPRESSION_POLICY = v2.LIFE_CHAT_EXPRESSION_POLICY + (
    "selected_dialogue只含Python原样选择的有限来源；没有选中不代表发生过或没发生过。"
    "不得补回未给出的窗口或把选择合法当来源内容已证实。focus=explain-encounter不从近期交流补首次动机。"
)


@dataclass(frozen=True)
class DialogueSource:
    label: str
    speaker: str
    text: str


@dataclass(frozen=True)
class FirstLifeChatPlanning:
    conversation: object
    character_core: tuple
    personality: tuple
    runtime_identity: object
    dialogue_sources: tuple
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
    selected_dialogue: tuple
    has_prior_committed_exchange: bool
    history_enabled: bool
    current_activity: dict
    current_plan: dict | None
    related_event: dict | None
    focus: str
    policy: str = LIFE_CHAT_POLICY


def first_life_scope(definition_basis):
    scope = v2.first_life_scope(definition_basis)
    scope.update(version="first-life-use-3", grounded_version=GROUNDED_VERSION,
        life_chat_policy_sha=sha256((v2.PERSONALITY_RELEVANCE_POLICY + HISTORY_GROUNDED_POLICY + LIFE_CHAT_POLICY
            + LIFE_CHAT_SELECTION_POLICY + LIFE_CHAT_EXPRESSION_POLICY).encode()).hexdigest())
    return scope


def first_life_scope_digest(definition_basis):
    return sha256(canonical_json(first_life_scope(definition_basis)).encode()).hexdigest()


def _validate_sources(sources, history_enabled, *, selected=False):
    if (type(history_enabled) is not bool or type(sources) is not tuple or len(sources) > (2 if selected else 4)
        or (not history_enabled and sources)):
        raise ValueError("bounded request-local dialogue sources required")
    for row in sources:
        if (type(row) is not DialogueSource or row.label not in ("U1", "A1", "U2", "A2")
            or row.speaker != ("user" if row.label.startswith("U") else "assistant")
            or not isinstance(row.text, str) or not row.text.strip() or "\x00" in row.text):
            raise ValueError("exact speaker source required")
    if len({row.label for row in sources}) != len(sources):
        raise ValueError("unique source labels required")
    if sum(len(row.text) for row in sources) > 4000:
        raise ValueError("dialogue source character limit exceeded")
    if not selected and tuple(row.label for row in sources) not in ((), ("U1", "A1"), ("U1", "A1", "U2", "A2")):
        raise ValueError("complete dialogue turn pairs required")


def life_chat_planning(envelope, identity, message, dialogue, history_enabled, basis):
    base, event = v2.life_chat_planning(envelope, identity, message, dialogue, history_enabled, basis)
    sources = tuple(DialogueSource(prefix + str(index), speaker, text)
        for index, turn in enumerate(base.recent_dialogue, 1)
        for prefix, speaker, text in (("U", "user", turn.user_text), ("A", "assistant", turn.assistant_text)))
    _validate_sources(sources, history_enabled)
    return v2._bounded(FirstLifeChatPlanning(replace(base.conversation, policy=LIFE_CHAT_SELECTION_POLICY),
        base.character_core, base.personality, base.runtime_identity, sources, base.has_prior_committed_exchange,
        history_enabled, base.current_activity, base.current_plan, base.related_event)), event


def life_chat_expression(planning, value):
    if (type(planning) is not FirstLifeChatPlanning or planning.policy != LIFE_CHAT_POLICY
        or planning.conversation.policy != LIFE_CHAT_SELECTION_POLICY or type(value) is not dict
        or set(value) != {"action", "fact_refs", "use_life", "focus", "dialogue_refs"}
        or type(value["use_life"]) is not bool or value["focus"] not in v2.CHAT_FOCUS
        or type(value["fact_refs"]) is not list or len(value["fact_refs"]) > 2
        or type(value["dialogue_refs"]) is not list or len(value["dialogue_refs"]) > 2
        or any(not isinstance(ref, str) for ref in value["dialogue_refs"])
        or len(set(value["dialogue_refs"])) != len(value["dialogue_refs"])):
        raise ValueError("exact grounded communication choice required")
    _validate_sources(planning.dialogue_sources, planning.history_enabled)
    sources = {row.label: row for row in planning.dialogue_sources}
    if any(ref not in sources for ref in value["dialogue_refs"]):
        raise ValueError("unknown current-request dialogue source")
    if value["focus"] == "explain-encounter" and value["dialogue_refs"]:
        raise ValueError("recent dialogue cannot ground first encounter")
    if value["use_life"] and planning.related_event is None:
        raise ValueError("no committed event to disclose")
    plan = _qualify_plan(dict(action=value["action"], fact_refs=value["fact_refs"]), planning.conversation,
        _projection_digest(planning.conversation))
    conversation = replace(_expression_projection(plan, planning.conversation), policy=LIFE_CHAT_EXPRESSION_POLICY)
    return v2._bounded(FirstLifeChatExpression(conversation, planning.character_core, planning.personality,
        planning.runtime_identity, tuple(sources[ref] for ref in value["dialogue_refs"]),
        planning.has_prior_committed_exchange, planning.history_enabled,
        planning.current_activity if value["use_life"] else {}, planning.current_plan if value["use_life"] else None,
        planning.related_event if value["use_life"] else None, value["focus"])), value["use_life"]

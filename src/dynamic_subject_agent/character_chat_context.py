"""Offline chat preparation from a verified stage view, never a model task."""
from dataclasses import asdict, dataclass
import json
import re
import unicodedata

from dynamic_subject_agent.character_evidence_model import CharacterModelView

MAX_KNOWLEDGE_CHARS = 20_000
MAX_RELATED_UNITS = 6


@dataclass(frozen=True)
class CharacterChatContextRequest:
    subject_id: str
    anchor_id: str
    current_message: str
    context_mode: str = "auto"
    max_knowledge_chars: int = MAX_KNOWLEDGE_CHARS


@dataclass(frozen=True)
class SelfKnowledge:
    dimension: str
    content: str
    kind: str
    basis: str
    event_scope: str
    knowledge_scope: str


@dataclass(frozen=True)
class KnowledgeSelection:
    unit_id: str
    group: str
    claim_ids: tuple[str, ...]
    matched_terms: tuple[str, ...]
    decision: str


@dataclass(frozen=True)
class ContextSelection:
    mode: str
    reviewed_digest: str
    knowledge_chars: int
    max_knowledge_chars: int
    units: tuple[KnowledgeSelection, ...]
    limitations: tuple[str, ...] = (
        "按显式线索及文本片段选择，不是通用语义检索。",
        "未选中或没有匹配不表示本人不知道或没有其他经历。",
        "摘要由作者审核；引用合规不证明摘要语义正确。",
    )


@dataclass(frozen=True)
class EncounterPreview:
    status: str = "proposed-branch"
    channel: str = "社交软件的文字私信"
    world_context: str = (
        "用户保持现实身份，角色生活在自己的世界；双方知道这个跨世界聊天渠道存在。"
        "她把自己的世界当作真实生活，只知道用户来自另一个世界；不预知用户看过她的故事。"
    )
    route: str = "系统按兴趣推荐联系人，用户主动发送第一条私信。"
    public_interests: tuple[str, ...] = ("绘画", "插画")
    interest_basis: str = "这是相识草案的共同兴趣假设，尚未读取或确认用户个人兴趣档案。"
    public_identity: str = "仅公开兴趣；未设定公开真名、年龄、职业笔名关联或家事。"
    relationship: str = "初识；推荐不代表熟悉、互相信任或有义务回复。"
    proposed_motive: str = (
        "助手提出的分支动机：她想看看其他人关于绘画和插画的想法，遇到合适的话题可以聊几句。"
        "这不是小说已有事件、固定习惯或对用户的预先好感。"
    )
    proposed_timing: str = (
        "助手提出的时间安放：在明确起点的短暂交流空档收到首次私信；"
        "不设精确分钟数，不把原作后续事件推进为已发生，也不每轮重置同一空档。"
    )
    unresolved: tuple[str, ...] = (
        "本动机与时间安放仍是可审分支提案，尚未成为正式运行情境。",
        "后续离线时间、忙闲与原作进度尚未接入；不能假称等待、已直播或刚完成作品。",
    )


@dataclass(frozen=True)
class PublicOpening:
    channel: str
    recommendation: str
    visible_interests: tuple[str, ...]
    explanation: str
    status: str = "proposed-branch"


def public_opening(encounter: EncounterPreview) -> PublicOpening:
    """Public surface derives only from encounter fields, never private knowledge."""
    return PublicOpening(
        channel=encounter.channel,
        recommendation="基于" + "、".join(encounter.public_interests) + "兴趣推荐的联系人",
        visible_interests=encounter.public_interests,
        explanation="你们尚未认识。你可以从共同兴趣开始发一条私信，对方可以选择是否回应。",
    )


DISCLOSURE = (
    "本人知识与公开资料分开；知道不等于愿意向初识网友透露。",
    "不愿透露、确实不知情、资料暂缺是不同情况，不能统一成否认本人经历。",
    "未在聊天介绍不代表用户不可能知道；用户提及也不能自动确认其所有前提。",
    "拒绝或保留不要求泄漏秘密；不把全部核心背景直接朗读给用户。",
    "当前可以表达看法、澄清或提出话题，但不能把观点补成过去的经历。",
)
CONTINUITY = (
    "此入口仅为离线预览，未接共同聊天历史；空历史不表示人物没有人生。",
    "用户当轮说法不改写本人知识，未来模型回复也不能自证事件发生。",
    "过去愿望不等于当前任务，预告不等于已完成事件；不自动推进时间或关系。",
    "场景草案不是原作事实或已发生共同经历，尚未批准作为新的Provider投影。",
)


@dataclass(frozen=True)
class CharacterChatContextView:
    status: str
    code: str = ""
    self_knowledge: tuple[SelfKnowledge, ...] = ()
    encounter: EncounterPreview | None = None
    disclosure: tuple[str, ...] = ()
    continuity: tuple[str, ...] = ()
    current_message: str = ""
    history_status: str = "not-connected"
    provider_ready: bool = False
    can_chat: bool = False
    stage_description: str = ""
    opening: PublicOpening | None = None
    selection: ContextSelection | None = None


def valid_request(request: object) -> bool:
    return (type(request) is CharacterChatContextRequest
            and isinstance(request.subject_id, str) and bool(request.subject_id)
            and isinstance(request.anchor_id, str) and bool(request.anchor_id)
            and isinstance(request.current_message, str)
            and bool(request.current_message.strip()) and len(request.current_message) <= 1000
            and isinstance(request.context_mode, str) and request.context_mode in ("auto", "flat", "organized")
            and type(request.max_knowledge_chars) is int
            and 1 <= request.max_knowledge_chars <= MAX_KNOWLEDGE_CHARS)


def knowledge_chars(knowledge) -> int:
    """Count the exact self_knowledge array representation used in reply JSON."""
    return len(json.dumps([asdict(item) for item in knowledge], ensure_ascii=False,
                          sort_keys=True, separators=(",", ":")))


def _text_terms(text):
    # Short Chinese words cannot depend on whitespace tokenization. This small
    # lexical baseline deliberately makes no semantic/negation interpretation.
    terms = set(re.findall(r"[a-z0-9]{3,}", text.casefold()))
    stop = {"自己", "一个", "没有", "不是", "什么", "可以", "知道", "我们", "你们", "他们", "这个", "那个"}
    particles = "的了是在也和与"
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for width in (2, 3):
            terms.update(run[i:i + width] for i in range(len(run) - width + 1)
                         if run[i:i + width] not in stop
                         and run[i] not in particles and run[i + width - 1] not in particles)
    return terms


def _direct_short_term(message):
    """Ignore only surrounding punctuation/space, preserving the query body."""
    text = message.casefold()
    start, end = 0, len(text)
    while start < end and (text[start].isspace() or unicodedata.category(text[start]).startswith("P")):
        start += 1
    while end > start and (text[end - 1].isspace() or unicodedata.category(text[end - 1]).startswith("P")):
        end -= 1
    return text[start:end]


def _organized_knowledge(model, message, budget):
    organization = model.chat_organization
    claims = {item.item_id: item for item in model.known}
    knowledge, decisions, core_contents = [], [], set()

    def material(unit, group):
        basis = [claims[key] for key in unit.claim_ids]
        return SelfKnowledge(group, unit.title + "：" + unit.content,
            "belief" if any(item.kind == "belief" for item in basis) else "fact",
            "linked-evidence", "at" if any(item.event_time == "at" for item in basis) else "before",
            "at" if any(item.knowledge_time == "at" for item in basis) else "before")

    for unit in organization.core:
        knowledge.append(material(unit, "core"))
        core_contents.add("".join(unit.content.split()).casefold())
        decisions.append(KnowledgeSelection(unit.unit_id, "core", unit.claim_ids, (), "always-included"))
    if knowledge_chars(knowledge) > budget:
        return (), None, "organized-core-too-large"

    message_terms = _text_terms(message)
    direct_term = _direct_short_term(message)
    ranked = []
    for group, units in (("episode", organization.episodes), ("detail", organization.details)):
        for unit in units:
            cues = tuple(sorted({cue for cue in unit.cues if cue.casefold().strip() in message.casefold()}))
            overlaps = tuple(sorted(message_terms & _text_terms(unit.title + " " + unit.content)))
            # One incidental bigram in a long question is too weak. Keep exact
            # short-word requests useful, and let reviewed cues take priority.
            strong_overlap = (len(overlaps) >= 2 or any(len(term) >= 3 for term in overlaps)
                              or direct_term in overlaps)
            terms = cues or (overlaps if strong_overlap else ())
            if not terms:
                decisions.append(KnowledgeSelection(unit.unit_id, group, unit.claim_ids, (), "no-lexical-match"))
            elif group == "detail" and "".join(unit.content.split()).casefold() in core_contents:
                decisions.append(KnowledgeSelection(unit.unit_id, group, unit.claim_ids, terms, "content-already-in-core"))
            else:
                ranked.append((-(100 * len(cues) + len(overlaps)), len(ranked), unit, group, terms))
    selected = 0
    for _, _, unit, group, terms in sorted(ranked, key=lambda row: (row[0], row[1])):
        item = material(unit, group)
        decision = "included"
        if selected >= MAX_RELATED_UNITS:
            decision = "related-unit-limit"
        elif knowledge_chars([*knowledge, item]) > budget:
            decision = "material-budget"
        else:
            knowledge.append(item)
            selected += 1
        decisions.append(KnowledgeSelection(unit.unit_id, group, unit.claim_ids, terms, decision))
    selection = ContextSelection("organized", model.draft_digest, knowledge_chars(knowledge), budget, tuple(decisions))
    return tuple(knowledge), selection, ""


def prepare_context(model: CharacterModelView, message: str, *, context_mode: str = "auto",
                    max_knowledge_chars: int = MAX_KNOWLEDGE_CHARS) -> CharacterChatContextView:
    """Use reviewed organization when present; keep an explicit flat baseline."""
    if model.status != "previewed":
        return CharacterChatContextView(model.status, model.code)
    if not model.chat_stage_description:
        return CharacterChatContextView("unavailable", "chat-stage-not-reviewed")
    if not model.known:
        return CharacterChatContextView("unavailable", "no-eligible-self-knowledge")
    mode = ("organized" if model.chat_organization is not None else "flat") if context_mode == "auto" else context_mode
    selection = None
    if mode == "organized":
        if model.chat_organization is None:
            return CharacterChatContextView("unavailable", "chat-organization-not-reviewed")
        knowledge, selection, code = _organized_knowledge(model, message, max_knowledge_chars)
        if code:
            return CharacterChatContextView("rejected", code)
    else:
        knowledge = tuple(SelfKnowledge(
            item.dimension, item.statement, item.kind, item.derivation,
            item.event_time, item.knowledge_time,
        ) for item in model.known)
        if knowledge_chars(knowledge) > max_knowledge_chars:
            return CharacterChatContextView("rejected", "self-knowledge-too-large")
    encounter = EncounterPreview()
    return CharacterChatContextView(
        "previewed", self_knowledge=knowledge, encounter=encounter,
        disclosure=DISCLOSURE, continuity=CONTINUITY, current_message=message,
        stage_description=model.chat_stage_description, opening=public_opening(encounter),
        selection=selection,
    )

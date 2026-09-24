"""Offline chat preparation from a verified stage view, never a model task."""
from dataclasses import asdict, dataclass
import json

from dynamic_subject_agent.character_evidence_model import CharacterModelView

MAX_KNOWLEDGE_CHARS = 20_000


@dataclass(frozen=True)
class CharacterChatContextRequest:
    subject_id: str
    anchor_id: str
    current_message: str


@dataclass(frozen=True)
class SelfKnowledge:
    dimension: str
    content: str
    kind: str
    basis: str
    event_scope: str
    knowledge_scope: str


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


def valid_request(request: object) -> bool:
    return (type(request) is CharacterChatContextRequest
            and isinstance(request.subject_id, str) and bool(request.subject_id)
            and isinstance(request.anchor_id, str) and bool(request.anchor_id)
            and isinstance(request.current_message, str)
            and bool(request.current_message.strip()) and len(request.current_message) <= 1000)


def prepare_context(model: CharacterModelView, message: str) -> CharacterChatContextView:
    """Keep the entire eligible basis; never copy author-side audit metadata."""
    if model.status != "previewed":
        return CharacterChatContextView(model.status, model.code)
    if not model.chat_stage_description:
        return CharacterChatContextView("unavailable", "chat-stage-not-reviewed")
    if not model.known:
        return CharacterChatContextView("unavailable", "no-eligible-self-knowledge")
    knowledge = tuple(SelfKnowledge(
        item.dimension, item.statement, item.kind, item.derivation,
        item.event_time, item.knowledge_time,
    ) for item in model.known)
    # Budget the actual escaped field representation, not only the prose.
    if len(json.dumps([asdict(item) for item in knowledge], ensure_ascii=False)) > MAX_KNOWLEDGE_CHARS:
        return CharacterChatContextView("rejected", "self-knowledge-too-large")
    encounter = EncounterPreview()
    return CharacterChatContextView(
        "previewed", self_knowledge=knowledge, encounter=encounter,
        disclosure=DISCLOSURE, continuity=CONTINUITY, current_message=message,
        stage_description=model.chat_stage_description, opening=public_opening(encounter),
    )

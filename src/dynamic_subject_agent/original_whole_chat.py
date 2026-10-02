"""The independently approved whole reply: pure contract and minimum projection."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import re

from dynamic_subject_agent.character_chat_context import prepare_context, knowledge_chars, MAX_KNOWLEDGE_CHARS
from dynamic_subject_agent.character_personality import PERSONALITY_POLICY
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.reviewed_character_chat import HISTORY_POLICY, sealed_model, CharacterDialogueBasis
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn

WHOLE_AUTHORITY = "original-character-whole-chat-deepseek-s127-1"
WHOLE_VERSION = "original-character-whole-chat-s127-1"
APPROVED_POLICY_SHA = "4849cf2c42313b2dffe5b95e859ee8eb0d79e0a6ad85cab0b05b3ea064fb3218"
APPROVED_BINDING = dict(
    definition_basis="8b492ec9f7a047a4b0f4ae3fdb4eaa4326348f1607d89bd0abe96ae56924769c",
    runtime_asset_sha="eab3ee8b1f7c88756154010f0542fc2af918376fec88613d5e1a073bc5554c82",
    persona_digest="e1340c3ba240190e530d969166e37b2740c911a521582900112df58a5d8e85c8",
    review_basis="1d1feb3f81641d1e722799b1d602a16e65983ba5885f918e91ce4478020b4f13",
    scope_digest="6d17c578c37ca029b4be928bf3e80c6cc5f82c35432cfc8e1977645915cec378",
    subject_id="sagiri", anchor_id="v1-pre-broadcast")
WHOLE_USE_POLICY = PERSONALITY_POLICY + HISTORY_POLICY + (
    "以background.runtime_identity中的虚构人物自然交流，先回应turn.current_message，再选择相关背景。"
    "background.self_knowledge保留事实或信念类型及成立/知情限定；personality是有边界的作者解释。"
    "人物核心与资料不是每轮必说的清单，知情不等于愿意披露。"
    "exchange仅用于理解本次实际提供的双方原话与理由，不建立新世界事实、关系或持久人格。"
    "用户当前提到的细节不表示本人先前说过，回顾时先核对实际原话；构想仍作为构想承接。"
    "当前可以提出意见或新设想，不补造过去、近期活动、画作完成、外部反馈或持续心理活动。"
    "本拟用途不接生活系统，evidence的活动、方案和事件均为空，不依据时间或聊天轮数造经历。"
    "使用第一人称自然中文短消息，通常两三句；不朗读档案、内部字段、审计流程或思考过程。"
    "只返回JSON exact {reply_text,language}；language=zh，reply_text非空且最多1200字符。"
)


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def whole_contract(binding):
    if (type(binding) is not dict or binding != APPROVED_BINDING
        or sha256(WHOLE_USE_POLICY.encode()).hexdigest() != APPROVED_POLICY_SHA):
        raise ValueError("exact S126 approved object and use required")
    return dict(version=WHOLE_VERSION, authorization="user-approved-original-whole-use-2026-10-02",
        **binding, provider="deepseek", endpoint="https://api.deepseek.com/chat/completions", model="deepseek-flash",
        credential_use="existing-Windows-slot-HTTPS-Bearer-only", max_current_chars=1000,
        max_complete_turns=2, max_exchange_chars=4000, max_reply_chars=1200, max_tokens=4096,
        timeout_seconds=30, thinking="enabled", reasoning_effort="high", max_requests_per_turn=1,
        automatic_retries=0, call_limit=None, policy_sha=APPROVED_POLICY_SHA,
        retention="canonical-Timeline-only", excluded="S1-life-persona-relation-writeback-cloud-migration")


def validate_whole_envelope(envelope, contract):
    # Hash labels alone do not prove a mutable in-process envelope. Recompute
    # the complete sealed asset/source/mapping basis at activation and every
    # send, before comparing it with the independently approved whole object.
    from dynamic_subject_agent.reviewed_character_definition import validate_reviewed_envelope
    validate_reviewed_envelope(envelope)
    binding = {key: contract[key] for key in APPROVED_BINDING}
    if contract != whole_contract(binding):
        raise ValueError("whole contract changed")
    asset = envelope["runtime_asset"]
    if (envelope["definition_basis"] != binding["definition_basis"]
        or envelope["runtime_asset_sha"] != binding["runtime_asset_sha"]
        or asset["persona_digest"] != binding["persona_digest"]
        or asset["subject"]["subject_id"] != binding["subject_id"]
        or asset["anchor"]["anchor_id"] != binding["anchor_id"]):
        raise ValueError("whole sealed object mismatch")


def matches_whole_source_contract(source, contract):
    try:
        return (type(contract) is dict and contract == whole_contract({key: contract[key] for key in APPROVED_BINDING})
            and source.source_asset_refs == ("reviewed-definition:" + contract["definition_basis"],
                "runtime-asset:" + contract["runtime_asset_sha"], "use:private-character-chat"))
    except Exception:
        return False


@dataclass(frozen=True)
class OriginalWholeProjection:
    turn: dict
    background: dict
    exchange: tuple[RecentDialogueTurn, ...]
    evidence: dict


def whole_projection(envelope, identity, message, dialogue, enabled):
    if (type(identity) is not RuntimeIdentityProjection or type(dialogue) is not CharacterDialogueBasis
        or dialogue.status != "available" or type(enabled) is not bool):
        raise ValueError("verified whole character dialogue required")
    model = sealed_model(envelope)
    context = prepare_context(model, message)
    if context.status != "previewed":
        raise ValueError("sealed whole context unavailable")
    core = tuple(row for row in context.self_knowledge if row.dimension == ("core" if model.chat_organization else "identity"))
    related = tuple(row for row in context.self_knowledge if row not in core)
    background = dict(runtime_identity=asdict(identity), character_core=tuple(asdict(row) for row in core),
        self_knowledge=tuple(asdict(row) for row in related), personality=tuple(envelope["runtime_asset"]["personality"]),
        stage_description=context.stage_description,
        encounter=("社交软件的文字私信", context.encounter.world_context,
            "系统按兴趣推荐联系人，本轮由用户主动发送消息。",
            "已存在此前提交的交流；不据此推断信任、亲密或时间推进。" if dialogue.has_prior_committed_exchange
            else "初识；不据此推断信任、亲密或时间推进。"), disclosure=tuple(context.disclosure))
    result = OriginalWholeProjection(dict(current_message=message, history_enabled=enabled,
        has_prior_committed_exchange=dialogue.has_prior_committed_exchange), background,
        dialogue.recent_dialogue, dict(current_activity=None, current_plan=None, related_event=None))
    validate_whole_projection(result)
    if knowledge_chars(context.self_knowledge) > MAX_KNOWLEDGE_CHARS:
        raise ValueError("whole selected knowledge oversized")
    return result


def validate_whole_projection(projection):
    if type(projection) is not OriginalWholeProjection:
        raise ValueError("exact whole projection required")
    turn, background = projection.turn, projection.background
    if (type(turn) is not dict or set(turn) != {"current_message", "history_enabled", "has_prior_committed_exchange"}
        or type(turn["current_message"]) is not str or not turn["current_message"].strip()
        or len(turn["current_message"]) > 1000 or "\x00" in turn["current_message"]
        or type(turn["history_enabled"]) is not bool or type(turn["has_prior_committed_exchange"]) is not bool
        or type(projection.exchange) is not tuple or len(projection.exchange) > 2
        or any(type(row) is not RecentDialogueTurn for row in projection.exchange)
        or sum(len(row.user_text) + len(row.assistant_text) for row in projection.exchange) > 4000
        or not turn["history_enabled"] and projection.exchange
        or projection.evidence != dict(current_activity=None, current_plan=None, related_event=None)):
        raise ValueError("bounded submitted whole turn required")
    if (type(background) is not dict or set(background) != {"runtime_identity", "character_core", "self_knowledge",
            "personality", "stage_description", "encounter", "disclosure"}
        or type(background["runtime_identity"]) is not dict
        or set(background["runtime_identity"]) != {"subject_name", "subject_identity", "canon_start"}
        or not background["character_core"] or not 1 <= len(background["personality"]) <= 8
        or len(canonical_json(background["personality"])) > 12000
        or len(canonical_json(background["character_core"] + background["self_knowledge"])) > 20000
        or len(canonical_json(asdict(projection)).encode()) > 65536):
        raise ValueError("bounded whole background required")


def validate_whole_reply(value):
    if (type(value) is not dict or set(value) != {"reply_text", "language"} or value["language"] != "zh"
        or type(value["reply_text"]) is not str or not value["reply_text"].strip()
        or len(value["reply_text"]) > 1200 or "\x00" in value["reply_text"]):
        raise ValueError("exact whole reply required")
    return value["reply_text"]


@dataclass(frozen=True)
class OriginalWholeAuthorization:
    identity_id: str
    contract_digest: str
    history_enabled: bool
    history_revision: int
    identity_revision: int

    def __post_init__(self):
        if (not isinstance(self.identity_id, str) or re.fullmatch(r"[0-9a-f]{64}", self.contract_digest) is None
            or type(self.history_enabled) is not bool
            or any(type(value) is not int or value < 0 for value in (self.history_revision, self.identity_revision))):
            raise ValueError("exact whole authorization required")

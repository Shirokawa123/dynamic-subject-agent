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
from dynamic_subject_agent.whole_context_boundary import CONTEXT_AUTHORITY, CONTEXT_VERSION
from dynamic_subject_agent.shared_activity import (
    SHARED_AUTHORITY, SHARED_AUTHORITIES, shared_contract, SHARED_LIVE_VERSION, SHARED_EXPRESSION_VERSION, SHARED_SELF_DIRECTED_VERSION)

WHOLE_AUTHORITY = "original-character-whole-chat-deepseek-s127-1"
WHOLE_AUTHORITIES = (WHOLE_AUTHORITY, CONTEXT_AUTHORITY, *SHARED_AUTHORITIES)
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
JSON_EXAMPLE_VERSION = "original-whole-json-format-example-s129-1"
JSON_EXAMPLE_SUFFIX = (
    '\n合法JSON格式示例：{"reply_text":"按当前话题自然回答。","language":"zh"}\n'
    '这个示例只展示字段、引号和合法JSON格式，不是人物台词，也不是本轮答案。不要复述示例内容；请按当前话题自然回答。'
)
GROUNDED_POLICY_VERSION = "original-whole-assertion-scope-s130-1"
_PAST_SCOPE_PARAGRAPH = "当前可以提出意见或新设想，不补造过去、近期活动、画作完成、外部反馈或持续心理活动。"
GROUNDED_SCOPE_PARAGRAPH = (
    "本人既往经历只说已审依据支持的范围，概括经历不证明额外的具体细节或因果；exchange的双方原话只证明曾这样说，"
    "用户前提和自己旧话都不自动成为生平事实，旧话越界时修正有关范围并继续交流。"
    "资料未支持不等于从未发生、心理失忆或明知却不愿说，也不要用这些解释填空；可以说明当前不能确定的细节，继续回应已有范围。"
    "本轮仍可有意见、理由、不同看法和条件下的艺术假想，保持未执行范围；知道、取到资料与愿意披露分开。"
)


def _grounded_policy():
    if WHOLE_USE_POLICY.count(_PAST_SCOPE_PARAGRAPH) != 1:
        raise ValueError("exact baseline past scope paragraph required")
    return WHOLE_USE_POLICY.replace(_PAST_SCOPE_PARAGRAPH, GROUNDED_SCOPE_PARAGRAPH, 1) + JSON_EXAMPLE_SUFFIX


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def whole_contract(binding, *, technical_variant="baseline"):
    if (type(binding) is not dict or binding != APPROVED_BINDING
        or sha256(WHOLE_USE_POLICY.encode()).hexdigest() != APPROVED_POLICY_SHA):
        raise ValueError("exact S126 approved object and use required")
    result = dict(version=WHOLE_VERSION, authorization="user-approved-original-whole-use-2026-10-02",
        **binding, provider="deepseek", endpoint="https://api.deepseek.com/chat/completions", model="deepseek-flash",
        credential_use="existing-Windows-slot-HTTPS-Bearer-only", max_current_chars=1000,
        max_complete_turns=2, max_exchange_chars=4000, max_reply_chars=1200, max_tokens=4096,
        timeout_seconds=30, thinking="enabled", reasoning_effort="high", max_requests_per_turn=1,
        automatic_retries=0, call_limit=None, policy_sha=APPROVED_POLICY_SHA,
        retention="canonical-Timeline-only", excluded="S1-life-persona-relation-writeback-cloud-migration")
    if technical_variant == "baseline":
        return result
    if technical_variant == "json-example":
        policy_sha = sha256((WHOLE_USE_POLICY + JSON_EXAMPLE_SUFFIX).encode()).hexdigest()
        return dict(result, version="original-character-whole-chat-json-example-s129-1", policy_sha=policy_sha,
            technical_variant=dict(name="json-example", version=JSON_EXAMPLE_VERSION, selector="baseline", policy_sha=policy_sha))
    if technical_variant in ("grounded", "context-boundary"):
        from dynamic_subject_agent.original_whole_followup import SELECTOR_VERSION, selector_digest
        policy_sha = sha256(_grounded_policy().encode()).hexdigest()
        grounded = dict(result, version="original-character-whole-chat-grounded-s130-1", policy_sha=policy_sha,
            technical_variant=dict(name="grounded", selector_version=SELECTOR_VERSION, selector_digest=selector_digest(),
                json_example_version=JSON_EXAMPLE_VERSION, policy_version=GROUNDED_POLICY_VERSION, policy_sha=policy_sha))
        if technical_variant == "context-boundary":
            grounded["version"] = "original-character-whole-context-s132-1"
            grounded["technical_variant"] = dict(grounded["technical_variant"], name="context-boundary",
                local_context_version=CONTEXT_VERSION, timeline_schema=4)
        return grounded
    if technical_variant != "followup":
        raise ValueError("known exact whole technical variant required")
    from dynamic_subject_agent.original_whole_followup import SELECTOR_VERSION, selector_digest
    return dict(result, version="original-character-whole-chat-followup-s128-1",
        technical_variant=dict(name="followup", selector_version=SELECTOR_VERSION, selector_digest=selector_digest()))


def contract_variant(contract):
    if type(contract) is not dict:
        raise ValueError("exact whole contract required")
    if contract.get('version') == 'working-understanding-local-s145-1':
        from dynamic_subject_agent.working_understanding import working_contract
        if contract != working_contract({key:contract[key] for key in APPROVED_BINDING}):
            raise ValueError('exact working LOCAL contract required')
        return 'working-local'
    if contract.get('version')=='working-understanding-live-s146-1':
        from dynamic_subject_agent.working_understanding_live import working_live_contract
        if contract!=working_live_contract({key:contract[key] for key in APPROVED_BINDING}):
            raise ValueError('exact approved working LIVE contract required')
        return 'working-live'
    if contract.get('version') == 'living-activity-local-s142-1':
        from dynamic_subject_agent.living_activity import living_contract
        if contract != living_contract({key: contract[key] for key in APPROVED_BINDING}):
            raise ValueError('exact living LOCAL contract required')
        return 'living-local'
    if contract.get('version') == 'living-activity-live-s142-1':
        from dynamic_subject_agent.living_activity_live import living_live_contract
        if contract != living_live_contract({key: contract[key] for key in APPROVED_BINDING}):
            raise ValueError('exact approved living LIVE contract required')
        return 'living-live'
    if contract.get('version') == 'living-final-text-live-s144-1':
        from dynamic_subject_agent.living_activity_live import living_final_text_contract
        if contract != living_final_text_contract({key: contract[key] for key in APPROVED_BINDING}):
            raise ValueError('exact continued final-text living contract required')
        return 'living-final-text-live'
    if contract.get('version') in (SHARED_LIVE_VERSION, SHARED_EXPRESSION_VERSION, SHARED_SELF_DIRECTED_VERSION):
        from dynamic_subject_agent.shared_activity_live import shared_live_contract
        technical_variant = {SHARED_EXPRESSION_VERSION: 'natural-expression',
            SHARED_SELF_DIRECTED_VERSION: 'self-directed-activity'}.get(contract['version'], 'baseline')
        if contract != shared_live_contract({key: contract[key] for key in APPROVED_BINDING}, technical_variant=technical_variant):
            raise ValueError('exact approved shared activity contract required')
        return 'shared-live'
    if contract.get("version") == "shared-activity-s139-1":
        if contract != shared_contract({key: contract[key] for key in APPROVED_BINDING}):
            raise ValueError("exact local shared activity contract required")
        return "shared-local"
    variant = "baseline"
    if "technical_variant" in contract:
        witness = contract["technical_variant"]
        if type(witness) is not dict or witness.get("name") not in ("followup", "json-example", "grounded", "context-boundary"):
            raise ValueError("known whole technical witness required")
        variant = witness["name"] if witness["name"] in ("json-example", "grounded", "context-boundary") else "followup-legacy" if witness == LEGACY_FOLLOWUP_WITNESS else "followup"
    binding = {key: contract[key] for key in APPROVED_BINDING}
    expected = (_legacy_followup_contract(binding) if variant == "followup-legacy"
        else whole_contract(binding, technical_variant=variant))
    if contract != expected:
        raise ValueError("whole technical contract changed")
    return variant


LEGACY_FOLLOWUP_WITNESS = dict(name="followup", selector_version="original-whole-user-followup-selection-s128-1",
    selector_digest="096496df339ea4eb730c66e3e6d34ec7403a68155dc64473b8729cdd0b51dfd5")


def _legacy_followup_contract(binding):
    """Exact immutable v1 witness for qualification/receipt reads, never activation."""
    return dict(whole_contract(binding), version="original-character-whole-chat-followup-s128-1",
        technical_variant=dict(LEGACY_FOLLOWUP_WITNESS))


def whole_publication_key(contract):
    variant = contract_variant(contract)
    if variant == 'working-local':
        return 'original-working-understanding-local-s145-' + digest(contract)
    if variant=='working-live':
        return 'original-working-understanding-live-s146-'+digest(contract)
    if variant == 'living-local':
        return 'original-living-activity-local-s142-' + digest(contract)
    if variant == 'living-live':
        return 'original-living-activity-live-s142-' + digest(contract)
    if variant == 'living-final-text-live':
        return 'original-living-final-text-live-s144-' + digest(contract)
    if variant == "shared-local":
        return "original-shared-activity-local-s139-" + digest(contract)
    if variant == "shared-live":
        if contract['version'] == SHARED_SELF_DIRECTED_VERSION:
            return "original-shared-activity-live-s141-" + digest(contract)
        if contract['version'] == SHARED_EXPRESSION_VERSION:
            return "original-shared-activity-live-s140-" + digest(contract)
        return "original-shared-activity-live-s139-" + digest(contract)
    key = "original-character-whole-" + contract["definition_basis"] + "-" + contract["scope_digest"]
    if variant == "baseline":
        return key
    marker = "-s132-" if variant == "context-boundary" else "-s130-" if variant == "grounded" else "-s129-" if variant == "json-example" else "-s128-"
    return key + marker + digest(contract["technical_variant"])


def policy_for_contract(contract):
    """Resolve one exact closed policy; never consume caller-provided policy text."""
    variant = contract_variant(contract)
    if variant == "followup-legacy":
        raise ValueError("legacy followup qualification is receipt-only")
    if variant in ("shared-local", "shared-live", "living-local", "living-live", "living-final-text-live", 'working-live'):
        raise ValueError("this local qualification has no original-whole remote policy")
    policy = (_grounded_policy() if variant in ("grounded", "context-boundary") else WHOLE_USE_POLICY + JSON_EXAMPLE_SUFFIX
        if variant == "json-example" else WHOLE_USE_POLICY)
    if sha256(policy.encode()).hexdigest() != contract["policy_sha"]:
        raise ValueError("whole policy witness changed")
    return policy


def validate_whole_envelope(envelope, contract):
    # Hash labels alone do not prove a mutable in-process envelope. Recompute
    # the complete sealed asset/source/mapping basis at activation and every
    # send, before comparing it with the independently approved whole object.
    from dynamic_subject_agent.reviewed_character_definition import validate_reviewed_envelope
    validate_reviewed_envelope(envelope)
    binding = {key: contract[key] for key in APPROVED_BINDING}
    contract_variant(contract)
    asset = envelope["runtime_asset"]
    if (envelope["definition_basis"] != binding["definition_basis"]
        or envelope["runtime_asset_sha"] != binding["runtime_asset_sha"]
        or asset["persona_digest"] != binding["persona_digest"]
        or asset["subject"]["subject_id"] != binding["subject_id"]
        or asset["anchor"]["anchor_id"] != binding["anchor_id"]):
        raise ValueError("whole sealed object mismatch")


def matches_whole_source_contract(source, contract, *, allow_legacy=False):
    try:
        if contract_variant(contract) == "followup-legacy" and not allow_legacy:
            return False
        return (type(contract) is dict
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
    return _projection_from_context(envelope, identity, message, dialogue, enabled, model, context)


def projection_for_contract(envelope, identity, message, dialogue, enabled, contract):
    variant = contract_variant(contract)
    if variant == "followup-legacy":
        raise ValueError("legacy followup qualification is receipt-only")
    if variant in ("baseline", "json-example"):
        return whole_projection(envelope, identity, message, dialogue, enabled)
    if (type(identity) is not RuntimeIdentityProjection or type(dialogue) is not CharacterDialogueBasis
        or dialogue.status != "available" or type(enabled) is not bool):
        raise ValueError("verified whole character dialogue required")
    from dynamic_subject_agent.original_whole_followup import select_followup_context
    model = sealed_model(envelope)
    context, _, _ = select_followup_context(model, message, dialogue, enabled)
    return _projection_from_context(envelope, identity, message, dialogue, enabled, model, context)


def _projection_from_context(envelope, identity, message, dialogue, enabled, model, context):
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

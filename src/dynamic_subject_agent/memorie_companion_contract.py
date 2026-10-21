"""The separately approved S160 use, within the reviewed-chat qualification family.

No legacy chat grant qualifies this version. Immutable request bytes are built
from the sealed definition and verified committed dialogue, never local drafts.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit

VERSION = 'memorie-companion-chat-s160-1'
ATTRIBUTION_VERSION = 'memorie-companion-attribution-s160-2'
INTENT_VERSION = 'memorie-companion-intent-s160-3'
NATIVE_VERSION = 'memorie-native-interaction-m002-1'
VERSIONS = (VERSION, ATTRIBUTION_VERSION, INTENT_VERSION, NATIVE_VERSION)
DEFINITION = '00c2a880579c2aa920f6c7c3440efe4d88a311bc2431523765bfb2e201eca2e2'
ASSET = '3cb87a26c47ca7f8bd34bd97c3e4a997eb254f00e6cc9fca136beb95382772a4'
REVIEW = '88ae7f75f194ccfc3cf5b34e12f8a1d83b5c6ed908e31ee4650db17c90924496'
REVIEW_SHA = 'b0ec3b196fdc99a1385d469b2809cc8dcf92c624c55750ae3fbcd6e1a27577fe'
SCOPE = '48acff80e1c5d32501dd26ca5790c0950e0198bb095b4e140149708a13022112'
USE_REVIEW = '8fbf7f3dbb4c15e24a1ae3c27d42918650b4b069882c5df8c3bd8d0331da641a'
PURPOSE = 'memorie-companion-reply'


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def policy(version=VERSION):
    from dynamic_subject_agent.memorie_companion_preparation import POLICY
    if version == VERSION:
        return POLICY
    if version not in (ATTRIBUTION_VERSION, INTENT_VERSION):
        raise ValueError('unknown Memorie technical version')
    result = POLICY + (
        '接续交流时区分来源与阶段：exchange的user_text才是用户说过的话，assistant_text是你自己的回复。'
        '你提出的办法仍是你的建议，不能因它出现在历史、用户听懂或觉得有意思，就说成用户的目标、决定或承诺。'
        '用户明确采纳且指代清楚时可以承接，不要一律说未决定或反复索要确认；采纳也不等于已经执行或完成。'
        '回顾时按实际证据自然区分“你说想做”“我刚才建议”“你后来决定”，未提供的采纳、进度或结果不要补造。'
        '窗口里缺少证据只表示此处未提供，不能断言用户从未说过或做过。保持角色口吻，不朗读这些分类或规则。'
    )
    if version == INTENT_VERSION:
        result += (
            '尚未采纳你的具体建议，不等于用户没有表达过自己的意图。回顾时先承接用户已经说过的打算，'
            '按原话保留“想试试、打算、决定、已开始、已完成”的语气和阶段，不擅自升级，也不要把较弱的意向抹掉。'
            '即使用户问“已经决定了什么”，也可自然说明他先前想做什么、哪些具体办法还未确定，'
            '不要只用“没有记录”或“你还没告诉我”顶替已有原话。简短接话即可，不反复播报确认规则或许诺替用户记下计划。'
        )
    return result


def contract(envelope, scope_digest, review_request_basis, *, version=VERSION):
    if version == NATIVE_VERSION:
        from dynamic_subject_agent.memorie_native import contract as native_contract
        return native_contract(envelope, scope_digest, review_request_basis)
    selected_policy = policy(version)
    if (envelope['definition_basis'] != DEFINITION or envelope['runtime_asset_sha'] != ASSET
        or scope_digest != SCOPE or review_request_basis != USE_REVIEW):
        raise ValueError('exact approved Memorie definition and use required')
    result = dict(version=version, definition_basis=DEFINITION, runtime_asset_sha=ASSET,
        scope_digest=SCOPE, review_request_basis=USE_REVIEW, consolidated_review=REVIEW,
        model='deepseek-flash', thinking='disabled', max_tokens=4096,
        timeout_seconds=30, automatic_retries=0, recent_turns=2, recent_chars=4000,
        max_current_chars=1000, max_reply_chars=1200, call_limit=None,
        policy_sha256=sha256(selected_policy.encode()).hexdigest())
    if version == ATTRIBUTION_VERSION:
        result['technical_parent_version'] = VERSION
    elif version == INTENT_VERSION:
        result['technical_parent_version'] = ATTRIBUTION_VERSION
    return result


def validate_approval(value):
    if (type(value) is not dict or value.get('version') != 'memorie-review-approval-s160-1'
        or value.get('user_reply') != '确认' or value.get('review_basis') != REVIEW
        or value.get('review_sha256') != REVIEW_SHA or value.get('definition_basis') != DEFINITION
        or value.get('use_review_basis') != USE_REVIEW
        or value.get('install_plan_sha256') != '082dcc933cbe24f53f99ab74254fc5c04f4d6826b28a99bb45d99f5069d1ac14'
        or any(value.get(k) is not True for k in ('rights_confirmed', 'definition_confirmed',
            'model_use_confirmed', 'install_confirmed', 'trial_confirmed'))):
        raise ValueError('separate exact user approval required')


def load_approval(path):
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError('absolute approval receipt required')
    raw = path.read_bytes()
    if len(raw) > 8192:
        raise ValueError('approval oversized')
    value = json.loads(raw)
    validate_approval(value)
    return value


class MemorieCallAudit(DevelopmentCallAudit):
    """Reuse the verified SQLite claim/head; no legacy finite budget conversion."""
    purposes = frozenset((PURPOSE,))

    @staticmethod
    def configuration():
        return dict(version='memorie-call-audit-s160-1', authorization=REVIEW,
            provider='deepseek', purpose=PURPOSE, limit=None)


@dataclass(frozen=True)
class MemorieReplyProjection:
    payload_json: str
    version: str = VERSION


def projection(envelope, message, dialogue, history_enabled, *, version=VERSION):
    from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
    contract(envelope, SCOPE, USE_REVIEW, version=version)
    asset = envelope['runtime_asset']
    if digest(asset) != ASSET:
        raise ValueError('sealed Memorie asset changed')
    if (type(dialogue) is not CharacterDialogueBasis or dialogue.status != 'available'
        or type(history_enabled) is not bool or not history_enabled and dialogue.recent_dialogue):
        raise ValueError('verified same-identity dialogue required')
    payload = dict(character=dict(name='梅莫莉', stage=asset['initial_stage'], knowledge=[
        {key: item[key] for key in ('dimension', 'kind', 'statement', 'event_time', 'knowledge_time')}
        for item in asset['eligible']]), personality=asset['personality'],
        exchange=[dict(user_text=t.user_text, assistant_text=t.assistant_text) for t in dialogue.recent_dialogue],
        current_message=message)
    result = MemorieReplyProjection(canonical_json(payload), version)
    wire(result)
    return result


def wire(value):
    if type(value) is not MemorieReplyProjection or value.version == NATIVE_VERSION or len(value.payload_json.encode()) > 60000:
        raise ValueError('typed bounded Memorie projection required')
    payload = json.loads(value.payload_json)
    if (set(payload) != {'character', 'personality', 'exchange', 'current_message'}
        or not _text(payload['current_message'], 1000)
        or type(payload['exchange']) is not list or len(payload['exchange']) > 2):
        raise ValueError('approved Memorie fields required')
    for turn in payload['exchange']:
        if (type(turn) is not dict or set(turn) != {'user_text', 'assistant_text'}
            or not _text(turn['user_text'], 1000) or not _text(turn['assistant_text'], 1200)):
            raise ValueError('complete bounded exchange required')
    if sum(len(t['user_text']) + len(t['assistant_text']) for t in payload['exchange']) > 4000:
        raise ValueError('complete exchange exceeds disclosure limit')
    body = dict(model='deepseek-flash', messages=[dict(role='system', content=policy(value.version)),
        dict(role='user', content=canonical_json(payload))], thinking={'type': 'disabled'},
        max_tokens=4096, stream=False)
    raw = canonical_json(body).encode()
    if len(raw) > 65536:
        raise ValueError('Memorie wire oversized')
    return raw


def _text(value, limit):
    return type(value) is str and bool(value.strip()) and len(value) <= limit and '\x00' not in value


def validate_reply(value):
    if not _text(value, 1200):
        raise ValueError('complete bounded final text required')
    return value


def is_memorie_dialogue_control(message):
    """Topic nouns are allowed; explicit transfer/withdrawal acts stay local."""
    from dynamic_subject_agent.first_life_dialogue import is_first_life_dialogue_control
    from dynamic_subject_agent.whole_dialogue_scope import whole_dialogue_scope, WITHDRAWAL, UNRESOLVED
    return (is_first_life_dialogue_control(message)
        or whole_dialogue_scope(message) in (WITHDRAWAL, UNRESOLVED))

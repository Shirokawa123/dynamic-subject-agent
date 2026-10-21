"""M002 typed nonverbal interaction, exact approved projection and qualification.

No migration, UI, clock polling or second store. The canonical Timeline owns all
Admission/Publication and reconstructs this type from its independent schema10.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit

VERSION = 'memorie-native-interaction-m002-1'
INPUT_VERSION = 'memorie-native-input-m002-1'
INTENT = 'memorie-native-interaction'
RUNTIME_CONTRACT = 'memorie-native-cycle-m002-1'
REVIEW = '081866a662cd62d469c2ea40ac195e8e2bd2191e9faad75a6df0963c169792a4'
REVIEW_SHA = '24ad40dc4a3411dc0576228e04883a192582be57fc1265dc03dc02e6a71c35ce'
SCOPE = REVIEW
PURPOSE = 'memorie-native-reply'
DDL = 'CREATE TABLE memorie_native_input (operation_id BLOB PRIMARY KEY REFERENCES subject_operation(operation_id), input_json TEXT NOT NULL, payload_fingerprint BLOB NOT NULL)'
POLICY_EXTENSION = (
    '当前输入使用interaction：kind=character-click只表示用户点击了你，没有用户原话；'
    'kind=text的text才是用户明确发送的话。exchange每项的interaction同样区分这两种来源。'
    'situation.timer_phase只表示本次观察到的游戏计时阶段：idle未计时、work专注计时、rest休息计时、paused暂停。'
    '计时状态不证明用户已学习、掌握知识、完成任务或你本人正在做什么。'
    '未知处境为null，不猜测；快照不证明持续时长、前序活动、现实日期或离线经历。'
    '点击时用一两句自然中文简短回应，最多120字符；不把非言语点击引用成用户说过的话。'
    '文字交流沿相同人物与所给已提交交流接续。只返回正文，不输出游戏指令、Yarn或动作名。'
)


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def policy():
    from dynamic_subject_agent.memorie_companion_contract import policy as old_policy, INTENT_VERSION
    value = old_policy(INTENT_VERSION).replace('exchange只证明本次实际提供的双方原话',
        'exchange只证明本次实际提供的互动与回复').replace(
        'exchange的user_text才是用户说过的话，assistant_text是你自己的回复。',
        'exchange内kind=text的interaction.text才是用户说过的话，assistant_text是你自己的回复。') + POLICY_EXTENSION
    if sha256(value.encode()).hexdigest() != 'eaaee1b0e74c43f136827f768796789668e34906214fbc9ba8888e3b14d88ab8':
        raise ValueError('approved native policy changed')
    return value


def contract(envelope, scope_digest, review_request_basis):
    from dynamic_subject_agent.memorie_companion_contract import DEFINITION, ASSET
    if (envelope.get('definition_basis') != DEFINITION or envelope.get('runtime_asset_sha') != ASSET
        or scope_digest != SCOPE or review_request_basis != REVIEW):
        raise ValueError('exact approved native definition and use required')
    return dict(version=VERSION, definition_basis=DEFINITION, runtime_asset_sha=ASSET,
        scope_digest=SCOPE, review_request_basis=REVIEW, consolidated_review=REVIEW,
        model='deepseek-flash', thinking='disabled', max_tokens=4096, timeout_seconds=30,
        automatic_retries=0, recent_turns=2, recent_chars=4000, max_current_chars=1000,
        max_reply_chars=1200, max_click_reply_chars=120, call_limit=None,
        policy_sha256=sha256(policy().encode()).hexdigest())


def validate_approval(value):
    from dynamic_subject_agent.memorie_companion_contract import DEFINITION
    expected = dict(version='memorie-native-approval-m002-1', review_basis=REVIEW,
        review_sha256=REVIEW_SHA, definition_basis=DEFINITION, user_reply='同意',
        model_use_confirmed=True, installation_included=False, migration_included=False)
    if type(value) is not dict or value != expected or any(type(value[k]) is not bool for k in (
        'model_use_confirmed', 'installation_included', 'migration_included')):
        raise ValueError('separate exact native use approval required')


def load_approval(path):
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError('absolute native approval path required')
    raw = path.read_bytes()
    if len(raw) > 8192:
        raise ValueError('native approval oversized')
    value = json.loads(raw)
    validate_approval(value)
    return value


class NativeCallAudit(DevelopmentCallAudit):
    purposes = frozenset((PURPOSE,))

    @staticmethod
    def configuration():
        return dict(version='memorie-native-call-audit-m002-1', authorization=REVIEW,
            provider='deepseek', purpose=PURPOSE, limit=None)


def _text(value, limit):
    return type(value) is str and bool(value.strip()) and len(value) <= limit and '\x00' not in value


def validate_interaction(value):
    if type(value) is not dict or (value != {'kind': 'character-click'} and not (
        set(value) == {'kind', 'text'} and value['kind'] == 'text' and _text(value['text'], 1000))):
        raise ValueError('typed click or bounded explicit text required')
    return value


def validate_situation(value):
    if value is not None and (type(value) is not dict or set(value) != {'timer_phase'}
        or value['timer_phase'] not in ('idle', 'work', 'rest', 'paused')):
        raise ValueError('minimal observed timer phase or null required')
    return value


@dataclass(frozen=True)
class NativeInteractionInput:
    target_profile_id: str
    target_timeline_id: str
    interaction_json: str
    situation_json: str
    input_version: str = INPUT_VERSION

    def __post_init__(self):
        for value in (self.target_profile_id, self.target_timeline_id):
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError('canonical target UUID required')
        if self.input_version != INPUT_VERSION:
            raise ValueError('unsupported native input version')
        for raw, validate in ((self.interaction_json, validate_interaction), (self.situation_json, validate_situation)):
            if type(raw) is not str or len(raw.encode()) > 6000 or canonical_json(validate(json.loads(raw))) != raw:
                raise ValueError('canonical typed native input required')
        if self.interaction['kind'] == 'character-click' and self.situation is None:
            raise ValueError('click requires a current known situation')

    @property
    def interaction(self): return json.loads(self.interaction_json)
    @property
    def situation(self): return json.loads(self.situation_json)
    @property
    def utterance(self): return self.interaction.get('text', '')
    @property
    def declared_intent(self): return INTENT
    @property
    def language(self): return 'zh'
    @property
    def provenance(self): return 'project-original'
    @property
    def contract_version(self):
        from dynamic_subject_agent.timeline import CONTRACT_VERSION
        return CONTRACT_VERSION
    @property
    def payload_fingerprint(self):
        return digest([INPUT_VERSION, self.target_profile_id, self.target_timeline_id,
            self.interaction, self.situation])


@dataclass(frozen=True)
class NativeTurn:
    head_sequence: int
    interaction_json: str
    assistant_text: str

    @property
    def user_text(self): return json.loads(self.interaction_json).get('text', '')


@dataclass(frozen=True)
class NativeDialogueBasis:
    status: str
    turns: tuple[NativeTurn, ...] = ()


@dataclass(frozen=True)
class NativeReplyProjection:
    payload_json: str


def projection(envelope, command, dialogue, enabled):
    from dynamic_subject_agent.memorie_companion_contract import ASSET
    contract(envelope, SCOPE, REVIEW)
    if (type(command) is not NativeInteractionInput or type(dialogue) is not NativeDialogueBasis
        or dialogue.status != 'available' or type(enabled) is not bool
        or not enabled and dialogue.turns or digest(envelope['runtime_asset']) != ASSET):
        raise ValueError('verified current native command and dialogue required')
    asset = envelope['runtime_asset']
    payload = dict(character=dict(name='梅莫莉', stage=asset['initial_stage'], knowledge=[
        {key: item[key] for key in ('dimension', 'kind', 'statement', 'event_time', 'knowledge_time')}
        for item in asset['eligible']]), personality=asset['personality'],
        interaction=command.interaction, situation=command.situation,
        exchange=[dict(interaction=json.loads(t.interaction_json), assistant_text=t.assistant_text) for t in dialogue.turns])
    result = NativeReplyProjection(canonical_json(payload))
    wire(result)
    return result


def validate_reply(text, interaction):
    validate_interaction(interaction)
    if not _text(text, 120 if interaction['kind'] == 'character-click' else 1200):
        raise ValueError('complete bounded native final text required')
    return text


def wire(value):
    if type(value) is not NativeReplyProjection or len(value.payload_json.encode()) > 60000:
        raise ValueError('typed bounded native projection required')
    payload = json.loads(value.payload_json)
    if type(payload) is not dict or set(payload) != {'character', 'personality', 'interaction', 'situation', 'exchange'}:
        raise ValueError('exact native fields required')
    if (digest(payload['character']) != 'b9ee98a316d3129f1063a3a7cdcd3d44dbcb13255b43361560e4a700d4e7df69'
        or digest(payload['personality']) != 'fe341d55223f6818802f60692f5ef5764e4580d5be78ce3b3bb831161801d7e2'):
        raise ValueError('exact approved character projection required')
    validate_interaction(payload['interaction'])
    validate_situation(payload['situation'])
    if payload['interaction']['kind'] == 'character-click' and payload['situation'] is None:
        raise ValueError('unknown click situation is unavailable')
    turns = payload['exchange']
    if type(turns) is not list or len(turns) > 2:
        raise ValueError('at most two complete typed exchanges required')
    count = 0
    for turn in turns:
        if type(turn) is not dict or set(turn) != {'interaction', 'assistant_text'}:
            raise ValueError('complete typed exchange required')
        validate_interaction(turn['interaction'])
        validate_reply(turn['assistant_text'], turn['interaction'])
        count += len(turn['interaction'].get('text', '')) + len(turn['assistant_text'])
    if count > 4000:
        raise ValueError('typed exchange exceeds approved disclosure limit')
    body = dict(model='deepseek-flash', messages=[dict(role='system', content=policy()),
        dict(role='user', content=canonical_json(payload))], thinking={'type': 'disabled'}, max_tokens=4096, stream=False)
    raw = canonical_json(body).encode()
    if len(raw) > 65536:
        raise ValueError('native wire oversized')
    return raw


def preview_wire(prepared, interaction, situation, exchange=()):
    """Read-only authoring surface; these supplied examples are not history."""
    from dynamic_subject_agent.memorie_companion_preparation import preview_memorie_wire
    from dynamic_subject_agent.memorie_companion_contract import INTENT_VERSION
    old = json.loads(preview_memorie_wire(prepared, '仅用于构造未发送审阅样例。', contract_version=INTENT_VERSION))
    payload = json.loads(old['messages'][1]['content'])
    payload.pop('current_message')
    if type(exchange) is not tuple:
        raise ValueError('explicit authoring exchange required')
    payload.update(interaction=interaction, situation=situation, exchange=list(exchange))
    return wire(NativeReplyProjection(canonical_json(payload)))

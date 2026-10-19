"""Read-only Memorie definition and exact use preparation; contains no sender."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from dynamic_subject_agent.character_evidence_model import (
    CharacterEntity, CharacterEvidenceModel, CharacterModelItem, CharacterModelView, DIMENSIONS,
)
from dynamic_subject_agent.character_identity_preparation import (
    CharacterDefinitionPreparationRequest, prepare_character_identity,
)
from dynamic_subject_agent.frozen_attempt import canonical_json


SUBJECT = 'memorie'
ANCHOR = 'postgame-story-055'
VERSION = 'memorie-companion-use-preparation-1'
POLICY = (
    '你是《梅莫莉：治愈物语》通关后继续与玩家相处的梅莫莉，以自然中文短消息交流。'
    'character是已核人物资料，personality是有边界的作者解释；不逐条朗读档案。'
    '原作前史与本次启用后的真实聊天分别处理；已经重逢，不重新扮演第一次连接。'
    '通关后的村庄与花已安全抵达，花已绽放；保持见习魔法使的局限和自己的关注。'
    '对电脑与游戏的理解来自原作的有限经历，不假称掌握API、代码、真实读屏或摄像头。'
    'exchange只证明本次实际提供的双方原话，错误不会因此变成原作或新事件。'
    '不根据现实时间、静态原作的“今天”或聊天轮数补造新活动、天气、进步和用户经历。'
    '可以有自己的意见、好奇与不同看法，仍可提出未来设想；不随机对抗或催促用户。'
    '专注、休息和学习进展只承接实际提供的信息，不把计时等同于掌握知识。'
    '直接返回一句或几句自然中文正文，最多1200字符；不输出JSON、分析、Yarn或游戏命令。'
)


def _digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class MemoriePreparationRequest:
    profile_path: Path
    profile_sha256: str
    nodes_path: Path
    personality_path: Path
    personality_sha256: str


@dataclass(frozen=True)
class MemoriePreparationView:
    status: str
    problem_code: str = ''
    definition_json: str = ''
    definition_basis: str = ''
    scope_json: str = ''
    review_basis: str = ''
    source_claims: int = 0
    remote_authorized: bool = False
    identity_created: bool = False


def _load(path, limit, expected=None):
    if not isinstance(path, Path) or not path.is_absolute() or path.anchor.startswith('\\\\'):
        raise ValueError('absolute private preparation path required')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or expected is not None and sha256(raw).hexdigest() != expected:
        raise ValueError('preparation source changed')
    return json.loads(raw.decode('utf-8')), sha256(raw).hexdigest()


def _model(profile, nodes, profile_digest, source_digest):
    if (type(profile) is not dict or set(profile) != {
            'version', 'subject_id', 'anchor_id', 'name', 'stage', 'source_nodes_sha256',
            'claims', 'chat_organization'}
        or profile['version'] != 'memorie-postgame-profile-1'
        or profile['subject_id'] != SUBJECT or profile['anchor_id'] != ANCHOR
        or profile['name'] != '梅莫莉' or profile['source_nodes_sha256'] != source_digest
        or type(profile['stage']) is not str or not 1 <= len(profile['stage']) <= 450
        or type(profile['claims']) is not list or not 1 <= len(profile['claims']) <= 60
        or type(nodes) is not list):
        raise ValueError('invalid Memorie source package')
    source = {}
    for node in nodes:
        for instruction in node['instructions']:
            if instruction['kind'] == 'line' and instruction.get('text_zh_hans'):
                source[(node['name'], instruction['value'])] = instruction['text_zh_hans']
    known, ids = [], set()
    for claim in profile['claims']:
        if (type(claim) is not dict or set(claim) != {'id', 'dimension', 'kind', 'statement', 'support'}
            or type(claim['id']) is not str or not claim['id'] or claim['id'] in ids
            or claim['dimension'] not in DIMENSIONS or claim['kind'] not in ('fact', 'belief')
            or type(claim['statement']) is not str or not 1 <= len(claim['statement']) <= 450
            or '\x00' in claim['statement'] or type(claim['support']) is not list
            or not 1 <= len(claim['support']) <= 12):
            raise ValueError('invalid Memorie claim')
        ids.add(claim['id'])
        evidence = []
        for reference in claim['support']:
            if type(reference) is not dict or set(reference) != {'node', 'line_id', 'text_sha256'}:
                raise ValueError('invalid source reference')
            text = source.get((reference['node'], reference['line_id']))
            if text is None or sha256(text.encode()).hexdigest() != reference['text_sha256']:
                raise ValueError('Memorie evidence unavailable')
            evidence.append(reference['node'] + ':' + reference['line_id'])
        known.append(CharacterModelItem(claim['id'], claim['dimension'], claim['kind'],
            claim['statement'], (SUBJECT,), '', tuple(evidence), derivation='linked-evidence',
            knower_id=SUBJECT, event_time='before', knowledge_time='before'))
    organization = CharacterEvidenceModel._organization(dict(subject_id=SUBJECT,
        anchor={'id': ANCHOR}, chat_organization=profile['chat_organization']), known)
    return CharacterModelView('previewed', subject_id=SUBJECT, anchor_id=ANCHOR,
        known=tuple(known), entities=(CharacterEntity(SUBJECT, '梅莫莉', 'person-reference'),),
        draft_digest=profile_digest, chat_stage_description=profile['stage'], chat_organization=organization)


def prepare_memorie_companion(request):
    if type(request) is not MemoriePreparationRequest:
        return MemoriePreparationView('rejected', 'typed-memorie-preparation-required')
    if any(type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None
           for value in (request.profile_sha256, request.personality_sha256)):
        return MemoriePreparationView('rejected', 'memorie-source-digest-required')
    try:
        profile, profile_digest = _load(request.profile_path, 100_000, request.profile_sha256)
        nodes, source_digest = _load(request.nodes_path, 16_000_000)
        model = _model(profile, nodes, profile_digest, source_digest)
        definition = prepare_character_identity(model, personality_request=CharacterDefinitionPreparationRequest(
            SUBJECT, ANCHOR, request.personality_path, request.personality_sha256))
        if definition.status != 'previewed':
            return MemoriePreparationView(definition.status, definition.code)
        scope = dict(version=VERSION, definition_basis=definition.definition_basis,
            runtime_asset_sha=definition.runtime_asset_sha, profile_sha256=profile_digest,
            source_use='private-character-chat', endpoint='https://api.deepseek.com/chat/completions',
            provider='deepseek', model='deepseek-flash', credential_use='existing-Windows-slot-HTTPS-Bearer-only',
            max_current_chars=1000, max_complete_turns=2, max_exchange_chars=4000,
            max_reply_chars=1200, max_tokens=4096, thinking='disabled', automatic_retries=0,
            timeout_seconds=30, call_limit=None, policy=POLICY,
            input_fields=['character', 'personality', 'exchange', 'current_message'],
            excluded=['raw-game-text', 'source-ids', 'save-data', 'unsent-drafts', 'screen-camera',
                'timer-state', 'other-identities', 'notifications', 'new-life-events'],
            retention='existing-single-canonical-Timeline; client holds only an unsent draft and original request',
            approval_state='pending', identity_action='new-isolated-definition-and-Timeline')
        basis = _digest(dict(definition_basis=definition.definition_basis, scope=scope))
        return MemoriePreparationView('prepared', definition_json=canonical_json(asdict(definition)),
            definition_basis=definition.definition_basis, scope_json=canonical_json(scope),
            review_basis=basis, source_claims=len(model.known))
    except FileNotFoundError:
        return MemoriePreparationView('unavailable', 'memorie-source-missing')
    except Exception:
        return MemoriePreparationView('failed-closed', 'memorie-preparation-unverified')


def preview_memorie_wire(prepared, message, exchange=(), *, contract_version=None):
    """Prepare exact bytes for review; this function cannot contact a Provider."""
    if type(prepared) is not MemoriePreparationView or prepared.status != 'prepared':
        raise ValueError('prepared Memorie review required')
    from dynamic_subject_agent.reviewed_character_definition import validate_character_preparation
    validate_character_preparation(prepared.definition_json, prepared.definition_basis)
    definition, scope = json.loads(prepared.definition_json), json.loads(prepared.scope_json)
    asset = json.loads(definition['runtime_asset_json'])
    if (definition['definition_basis'] != prepared.definition_basis
        or _digest(asset) != definition['runtime_asset_sha'] or scope['runtime_asset_sha'] != _digest(asset)
        or scope['definition_basis'] != prepared.definition_basis or scope['policy'] != POLICY
        or _digest(dict(definition_basis=prepared.definition_basis, scope=scope)) != prepared.review_basis
        or prepared.remote_authorized is not False or prepared.identity_created is not False
        or type(message) is not str or not message.strip() or len(message) > 1000 or '\x00' in message
        or type(exchange) is not tuple or len(exchange) > 2):
        raise ValueError('invalid Memorie review or message')
    for turn in exchange:
        if (type(turn) is not dict or set(turn) != {'user_text', 'assistant_text'}
            or any(type(turn[k]) is not str or not turn[k].strip() or '\x00' in turn[k] for k in turn)):
            raise ValueError('complete exchange required')
    if sum(len(t['user_text']) + len(t['assistant_text']) for t in exchange) > 4000:
        raise ValueError('exchange too large')
    # Source references and internal identifiers never enter the proposed request.
    character = dict(name='梅莫莉', stage=asset['initial_stage'], knowledge=[
        {key: item[key] for key in ('dimension', 'kind', 'statement', 'event_time', 'knowledge_time')}
        for item in asset['eligible']])
    projection = dict(character=character, personality=asset['personality'],
        exchange=exchange, current_message=message)
    body = dict(model='deepseek-flash', messages=[dict(role='system', content=POLICY),
        dict(role='user', content=canonical_json(projection))], thinking={'type': 'disabled'},
        max_tokens=4096, stream=False)
    from dynamic_subject_agent.memorie_companion_contract import VERSION, contract, policy
    if contract_version is not None and contract_version != VERSION:
        contract(dict(definition_basis=prepared.definition_basis, runtime_asset_sha=definition['runtime_asset_sha']),
            _digest(scope), prepared.review_basis, version=contract_version)
        body['messages'][0]['content'] = policy(contract_version)
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError('Memorie request oversized')
    return wire

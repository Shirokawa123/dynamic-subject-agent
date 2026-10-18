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
DEFINITION = '00c2a880579c2aa920f6c7c3440efe4d88a311bc2431523765bfb2e201eca2e2'
ASSET = '3cb87a26c47ca7f8bd34bd97c3e4a997eb254f00e6cc9fca136beb95382772a4'
REVIEW = '88ae7f75f194ccfc3cf5b34e12f8a1d83b5c6ed908e31ee4650db17c90924496'
REVIEW_SHA = 'b0ec3b196fdc99a1385d469b2809cc8dcf92c624c55750ae3fbcd6e1a27577fe'
SCOPE = '48acff80e1c5d32501dd26ca5790c0950e0198bb095b4e140149708a13022112'
USE_REVIEW = '8fbf7f3dbb4c15e24a1ae3c27d42918650b4b069882c5df8c3bd8d0331da641a'
PURPOSE = 'memorie-companion-reply'


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def contract(envelope, scope_digest, review_request_basis):
    from dynamic_subject_agent.memorie_companion_preparation import POLICY
    if (envelope['definition_basis'] != DEFINITION or envelope['runtime_asset_sha'] != ASSET
        or scope_digest != SCOPE or review_request_basis != USE_REVIEW):
        raise ValueError('exact approved Memorie definition and use required')
    return dict(version=VERSION, definition_basis=DEFINITION, runtime_asset_sha=ASSET,
        scope_digest=SCOPE, review_request_basis=USE_REVIEW, consolidated_review=REVIEW,
        model='deepseek-flash', thinking='disabled', max_tokens=4096,
        timeout_seconds=30, automatic_retries=0, recent_turns=2, recent_chars=4000,
        max_current_chars=1000, max_reply_chars=1200, call_limit=None,
        policy_sha256=sha256(POLICY.encode()).hexdigest())


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


def projection(envelope, message, dialogue, history_enabled):
    from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
    contract(envelope, SCOPE, USE_REVIEW)
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
    result = MemorieReplyProjection(canonical_json(payload))
    wire(result)
    return result


def wire(value):
    from dynamic_subject_agent.memorie_companion_preparation import POLICY
    if type(value) is not MemorieReplyProjection or len(value.payload_json.encode()) > 60000:
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
    body = dict(model='deepseek-flash', messages=[dict(role='system', content=POLICY),
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

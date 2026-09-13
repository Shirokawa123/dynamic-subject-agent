"""A bounded local confirmation, sourced by two separately committed messages."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from uuid import UUID

TTL_US = 30 * 60 * 1_000_000

def choice(message: str) -> str | None:
    text = message.strip().rstrip('。！!')
    return {'是补充': 'supplement', '补充': 'supplement', '作为补充': 'supplement',
        '替换': 'replace', '是替换': 'replace', '换成新的': 'replace',
        '算了': 'cancel', '取消': 'cancel', '先不改了': 'cancel'}.get(text)

def inventory_digest(records) -> str:
    rows = sorted((r.memory_id, r.content, r.status, r.preference_additive) for r in records if r.status == 'active')
    return sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

@dataclass(frozen=True)
class PreferenceQuestion:
    source_id: str
    profile_id: str
    timeline_id: str
    source_text: str
    evidence: str
    prompt: str
    inventory_digest: str
    opened_at_us: int
    version: int = 1

    def to_dict(self):
        return asdict(self)

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            return None
        try:
            q = cls(**value)
            for identifier in (q.source_id, q.profile_id, q.timeline_id):
                UUID(identifier)
            if (type(q.version) is not int or q.version != 1 or type(q.opened_at_us) is not int or q.opened_at_us < 1
                or not all(isinstance(v, str) for v in (q.source_text, q.evidence, q.prompt, q.inventory_digest))
                or not 1 <= len(q.evidence) <= 500 or q.evidence not in q.source_text
                or not 1 <= len(q.source_text) <= 1000 or not 1 <= len(q.prompt) <= 4000
                or len(q.inventory_digest) != 64 or any(c not in '0123456789abcdef' for c in q.inventory_digest)):
                return None
            return q
        except (ValueError, TypeError, AttributeError):
            return None

@dataclass(frozen=True)
class PendingPreference:
    question: PreferenceQuestion
    prefix_digest: str

def make_question(message, records, *, complete, source_id, profile_id, timeline_id, now):
    from dynamic_subject_agent.scoped_preferences import route_preference
    from dynamic_subject_agent.recent_dialogue import is_dialogue_control
    route = route_preference(message, records, complete=complete)
    if route is None or not route.needs_choice or is_dialogue_control(message):
        return None
    q = PreferenceQuestion(source_id, profile_id, timeline_id, message, route.evidence, route.reply, inventory_digest(records), now)
    return q if PreferenceQuestion.parse(q.to_dict()) is not None else None

def resolve(message, pending, records, *, complete, profile_id, timeline_id, now):
    from dynamic_subject_agent.scoped_preferences import PreferenceRoute, _preference
    selected = choice(message)
    if selected is None:
        return None
    if not complete:
        return PreferenceRoute('none', reply='这次无法核实待确认问题或偏好范围，没有更新，请重新说明。')
    if pending is None:
        return PreferenceRoute('none', reply='当前没有可确认的偏好问题，请重新写明场景和颜色。')
    if not isinstance(pending, PendingPreference) or not isinstance(pending.question, PreferenceQuestion):
        return PreferenceRoute('none', reply='待确认问题无法核实，这次没有更新。')
    q = pending.question
    if (q.profile_id != profile_id or q.timeline_id != timeline_id
        or inventory_digest(records) != q.inventory_digest):
        return PreferenceRoute('none', reply='偏好记录或可用范围已经变化，这次没有更新，请重新说明。')
    expected = make_question(q.source_text, records, complete=complete, source_id=q.source_id,
        profile_id=profile_id, timeline_id=timeline_id, now=q.opened_at_us)
    if expected != q:
        return PreferenceRoute('none', reply='原确认内容已不再适用，请重新说明。')
    if not q.opened_at_us <= now <= q.opened_at_us + TTL_US:
        return PreferenceRoute('none', reply='这个偏好确认已过期或时间无法核实，请重新说明场景和颜色。')
    if selected == 'cancel':
        return PreferenceRoute('none', reply='已取消这次偏好更新，原有记录保持不变。')
    pref = _preference(q.evidence)
    if pref is None:
        return PreferenceRoute('none', reply='原偏好内容无法确认，这次没有更新。')
    if selected == 'supplement':
        return PreferenceRoute('create', q.evidence)
    matches = [(r, p) for r in records if r.status == 'active' and (p := _preference(r.content)) is not None and p.scope == pref.scope]
    if len(matches) != 1 or matches[0][1].tail:
        return PreferenceRoute('none', reply='替换对象不唯一或还包含其他内容，这次没有更新；请提供完整旧原文和新原文。')
    return PreferenceRoute('revise', q.evidence, matches[0][0].memory_id)

def valid_confirmation(value) -> bool:
    if not isinstance(value, dict) or set(value) != {'version', 'source_id', 'confirmation_id', 'choice'}:
        return False
    try:
        UUID(value['source_id']); UUID(value['confirmation_id'])
        return type(value['version']) is int and value['version'] == 1 and value['choice'] in ('supplement', 'replace') and value['source_id'] != value['confirmation_id']
    except (ValueError, TypeError, AttributeError):
        return False

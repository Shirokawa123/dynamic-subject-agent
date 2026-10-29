"""M030 source decisions. Pure values only; persistence belongs to Timeline."""
from dataclasses import dataclass, asdict
from datetime import date


# A conservative cap for explicit Chinese day qualifiers in this product's
# current language. It never selects a memory or lengthens its lifetime, and
# is not a general semantic parser (quoted qualifiers may shorten retention).
_TODAY_LIMITS = ('只限今天', '仅限今天', '今天只是', '只是今天', '就今天',
    '仅今天', '只在今天', '仅在今天', '明天不一定')


@dataclass(frozen=True)
class NaturalExperience:
    quote: str
    duration: str
    source_head_sequence: int
    local_day: str

    def __post_init__(self):
        if (type(self.quote) is not str or not self.quote.strip() or len(self.quote) > 400 or '\x00' in self.quote
                or self.duration not in ('today', 'until_changed')
                or type(self.source_head_sequence) is not int or self.source_head_sequence < 1
                or type(self.local_day) is not str or date.fromisoformat(self.local_day).isoformat() != self.local_day):
            raise ValueError('bounded original source and local day required')


def visible_experience(value, local_day):
    if type(local_day) is not str or date.fromisoformat(local_day).isoformat() != local_day:
        raise ValueError('exact local calendar day required')
    if value is None:
        return None
    if type(value) is not NaturalExperience:
        raise ValueError('typed experience required')
    if local_day < value.local_day:
        raise ValueError('clock precedes source day')
    return None if value.duration == 'today' and value.local_day != local_day else value


def selection_projection(value, local_day):
    value = visible_experience(value, local_day)
    return None if value is None else dict(quote=value.quote, duration=value.duration)


def adjudicate_experience(proposal, *, current_text, previous, source_head_sequence, local_day):
    """Copy the complete user original, never a model-written quote or persona."""
    old = visible_experience(previous, local_day)
    if (type(current_text) is not str or not current_text.strip() or len(current_text) > 1000 or '\x00' in current_text
            or type(source_head_sequence) is not int or source_head_sequence < 1
            or previous is not None and source_head_sequence <= previous.source_head_sequence):
        raise ValueError('new user source required')
    if type(proposal) is not dict or set(proposal) != {'action', 'duration', 'reason_code'}:
        raise ValueError('exact proposal fields required')
    action, duration, reason = (proposal[k] for k in ('action', 'duration', 'reason_code'))
    if action == 'keep' and duration is None and reason in ('irrelevant', 'unclear', 'too-long'):
        return old
    if action == 'forget' and duration is None and reason == 'explicit-forget':
        return None
    if (action != 'remember' or duration not in ('today', 'until_changed') or len(current_text) > 400
            or reason not in ('temporary', 'ongoing', 'correction')
            or reason == 'temporary' and duration != 'today'
            or reason == 'correction' and old is None):
        raise ValueError('unsupported source decision')
    if duration == 'until_changed' and any(marker in current_text for marker in _TODAY_LIMITS):
        duration = 'today'
    return NaturalExperience(current_text, duration, source_head_sequence, local_day)


def encode_experience(value):
    return None if value is None else asdict(value)


def decode_experience(value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != {'quote', 'duration', 'source_head_sequence', 'local_day'}:
        raise ValueError('exact source record required')
    return NaturalExperience(**value)

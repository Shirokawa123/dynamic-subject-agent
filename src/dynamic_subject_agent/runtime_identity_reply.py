"""Deterministic expression safety for runtime-identity-grounded replies."""

from __future__ import annotations

import re
from dynamic_subject_agent.recent_dialogue import shortening_limit


_SENTENCE_PATTERN = re.compile(r"[^。！？!?]+[。！？!?]?")
CREATIVE_REPLY_PREFIX = '这是现在的即兴创作，不是资料事实或已发生的经历：\n'
_UNSUPPORTED_CURRENT_ACTIVITY_MARKERS = (
    "我也刚",
    "我正好",
    "我刚刚",
    "我刚",
    "我今天",
    "我正在",
    "我已经",
    "我还没",
    "我尚未",
    "我这边",
)


def guard_runtime_identity_reply(text: object) -> str | None:
    """Remove current subject activity; no Slice-16 reply input can ground one."""

    if not isinstance(text, str) or not text.strip():
        return None
    kept = tuple(
        sentence.strip()
        for sentence in _SENTENCE_PATTERN.findall(text)
        if sentence.strip()
        and not any(
            marker in sentence
            for marker in _UNSUPPORTED_CURRENT_ACTIVITY_MARKERS
        )
    )
    guarded = "".join(kept).strip()
    return guarded or None


def activity_boundary_reply(message: str) -> str | None:
    """Recognize explicit activity questions; elapsed time is never an event."""
    # Exclude only creative clauses/titles, not independent activity questions
    # elsewhere in the same message.
    unquoted = re.sub(r'“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"', '', message)
    message = '。'.join(clause for clause in re.split(r'[。！？!?，,]', unquoted)
        if not explicit_creation_request(clause))
    offline = any(word in message for word in ('关掉', '关闭', '离线', '我不在', '我离开', '没上线'))
    if offline and '你' in message and any(word in message for word in ('做', '忙', '想', '等', '发生')):
        return '应用关闭时，我不会在后台继续活动或替你思考。你想做的事，我们可以现在一起继续。'
    if re.search(r'你(?:现在|此刻|这会儿)?(?:在)?(?:忙|做|干|想)(?:什么|嘛)|你(?:刚才|刚刚|刚)(?:做|忙|干|想)(?:完|了)?(?:什么|嘛)|你(?:现在|此刻|刚才)?(?:有没有|是不是|是否)在', message):
        return '我现在就在这里和你聊。至于聊天之外刚做了什么，我没有这样的经历可以告诉你。'
    return None


def explicit_creation_request(message: str) -> bool:
    message = re.sub(r'“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"', '', message)
    # A constraint on style does not withdraw the requested act of writing.
    message = re.sub(r'(?:别|不要)写(?=成|得)', '', message)
    if any(word in message for word in ('别编', '不要编', '不许编', '不要写', '别写', '不要创作', '不要想象', '什么意思', '怎么做', '的是谁', '的人是谁', '解释一下', '解释这')):
        return False
    if message.strip().startswith('如果让你') and '你会写什么' in message:
        return True
    # An imperative clause, not a mention inside a past account or quotation.
    return any(re.match(r'^(?:(?:请|帮我|替我)(?:给[^。！？!?，,]{0,20}|为[^。！？!?，,]{1,20})?|给[^。！？!?，,]{0,20}|为[^。！？!?，,]{1,20})?(?:写(?:一句|一首|个|一个)|配(?:一句话|一句|个文案)|创作|想象一下|编(?:一个|个))', clause.strip())
        for clause in re.split(r'[。！？!?，,]', message))


def contextual_reply(text: object, *, message: str, reply_kind: str = 'conversation', continuation_allowed: bool = False) -> str | None:
    """Both primary and fallback text cross this same local expression check."""
    if not isinstance(reply_kind, str):
        return None
    activity = activity_boundary_reply(message)
    if activity is not None:
        return activity
    if reply_kind == 'activity':
        return '我没有可据实讲述的额外活动。我们可以从现在的这段对话继续。'
    if reply_kind not in {'conversation', 'creative'}:
        return None
    limit = shortening_limit(message)
    if limit is not None and isinstance(text, str):
        body = text.strip().removeprefix(CREATIVE_REPLY_PREFIX).strip()
        if len(body) >= 2 and (body[0], body[-1]) in {('“', '”'), ('「', '」'), ('"', '"'), ('‘', '’')}:
            body = body[1:-1]
        if len(re.sub(r'\s+', '', body)) > limit:
            return None
    if reply_kind == 'creative':
        if not (explicit_creation_request(message) or continuation_allowed) or not isinstance(text, str) or not text.strip():
            return None
        return CREATIVE_REPLY_PREFIX + text.strip()
    if isinstance(text, str) and re.search(r'我(?:倒是)?(?:正想歇|替你留了|一直在等|一直在想)', text):
        return None
    return guard_runtime_identity_reply(text)


def repeats_previous_expression(text: str, previous: str) -> bool:
    def body(value: str) -> str:
        value = value.strip()
        while value.startswith(CREATIVE_REPLY_PREFIX):
            value = value.removeprefix(CREATIVE_REPLY_PREFIX).strip()
        return value
    return body(text) == body(previous)


__all__ = ["guard_runtime_identity_reply"]

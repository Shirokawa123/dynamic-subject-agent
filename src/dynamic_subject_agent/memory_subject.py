"""Literal binding for a bounded, complete named-memory question grammar."""

from __future__ import annotations

import re

from dynamic_subject_agent.recent_dialogue import expression_request_text, is_dialogue_control


_SUBJECT = r'(?P<subject>[^，,。！？!?；;：:\n「」“”《》]{2,80}?)'
_QUESTIONS = tuple(re.compile(pattern) for pattern in (
    r'(?:请问，?)?' + _SUBJECT + r'(?:现在|原来|之前)?(?:定在|安排在)(?:什么时间|什么时候|哪天)(?:整理|处理|完成)?',
    r'(?:请问，?)?' + _SUBJECT + r'的(?:安排|计划)(?:是)?(?:什么|怎样)',
    r'(?:再说说|说说)' + _SUBJECT + r'的安排[，,](?:当时|之前)定的是哪天',
))
_NON_LITERAL_PREFIX = re.compile(
    r'^(?:我|你|我们|这|那|哪|它|他|她|如果|假如|据说|听说'
    r'|现在|目前|刚才|刚刚|当时|之前|原来|最近|过去|上次|今天|昨天|明天|后天)'
)


def requested_memory_subject(message: object) -> str | None:
    """Return only an explicit current object span, not a guessed entity/alias.

    Multiple questions, quotes, reports, controls and recommendations remain
    outside this grammar. Literal containment is a necessary condition only;
    it does not prove semantic identity or disambiguate overlapping names.
    """
    if not isinstance(message, str):
        return None
    text = message.strip().rstrip('？?。')
    if (is_dialogue_control(text) or expression_request_text(text) != text
        or any(word in text for word in ('建议', '应该', '适合', '不如', '帮我', '替我', '如果', '假如', '不要'))):
        return None
    for pattern in _QUESTIONS:
        match = pattern.fullmatch(text)
        if match is not None:
            subject = match['subject'].strip()
            if subject and not _NON_LITERAL_PREFIX.match(subject):
                return subject
    return None


def supports_memory_subject(content: str, subject: str) -> bool:
    return subject in content

"""Literal binding for a bounded, complete named-memory question grammar."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dynamic_subject_agent.recent_dialogue import expression_request_text, is_dialogue_control

if TYPE_CHECKING:
    from dynamic_subject_agent.timeline import LivingMemoryRecord


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
_ACTION_OBJECT = re.compile(r'(?:整理|处理|完成)(?P<name>[^，,。！？!?；;：:\n]{2,80})$')
_NAMED_CHANGE = re.compile(r'^(?P<name>[^，,。！？!?；;：:\n]{2,80}?)(?:改为|改到|定在|安排在)')
_DOCUMENT_KINDS = ('小册子', '手册', '报告', '笔记')


def requested_memory_subject(message: object) -> str | None:
    """Return only an explicit current object span, not a guessed entity/alias.

    Multiple questions, quotes, reports, controls and recommendations remain
    outside this grammar. Literal containment is a necessary condition only;
    it does not infer arbitrary aliases or a general semantic entity identity.
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


def _record_subject(content: str) -> str | None:
    """Extract a single complete object from supported scheduling frames."""
    names = set()
    for clause in re.split(r'[，,。！？!?；;：:\n]', content):
        clause = clause.strip()
        change = _NAMED_CHANGE.match(clause)
        action = _ACTION_OBJECT.search(clause)
        for match in (change, action):
            if match is None:
                continue
            name = match['name'].strip()
            for opening, closing in (('《', '》'), ('「', '」'), ('“', '”'), ('"', '"')):
                if name.startswith(opening) and name.endswith(closing):
                    name = name[1:-1].strip()
                    break
            if name and not _NON_LITERAL_PREFIX.match(name):
                names.add(name)
    return next(iter(names)) if len(names) == 1 else None


def select_subject_memories(
    records: tuple[LivingMemoryRecord, ...], subject: str,
) -> tuple[LivingMemoryRecord, ...]:
    """Match complete names; a short form must resolve to one complete name.

    An already typed name cannot lose another suffix: a notebook is not its
    notebook report. Names mentioned outside an object slot are not evidence.
    """
    named = tuple((record, _record_subject(record.content)) for record in records)
    exact = tuple(record for record, name in named if name == subject)
    if exact:
        return exact
    if subject.endswith(_DOCUMENT_KINDS):
        return ()
    aliases = {name for _, name in named if name is not None
               and any(name == subject + kind for kind in _DOCUMENT_KINDS)}
    return tuple(record for record, name in named if name in aliases) if len(aliases) == 1 else ()

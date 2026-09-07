"""Bounded, non-persistent dialogue text for one capability-local reply."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dynamic_subject_agent.timeline import ConversationTurnRecord

MAX_DIALOGUE_TURNS = 2
MAX_DIALOGUE_CHARS = 4_000


@dataclass(frozen=True)
class RecentDialogueTurn:
    user_text: str
    assistant_text: str


def is_dialogue_control(message: str) -> bool:
    """Conservative boundary for the added history use, not a state classifier."""
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', message)).casefold()
    if re.search(r'(?:不要|不再|不用|不能|不许|不准|禁止|停止|别|勿)[^。！？!?]*(?:记|提|说|留|存|保留|使用|分享|发送)', text):
        return True
    if re.search(r'(?:donot|don\x27t|never|stop).*(?:remember|keep|store|say|mention|retain|use|share|record)', text):
        return True
    memory_object = r'(?:记忆|记着|记得|记录|memory)'
    change = r'(?:改成|改为|换成|换为|更新|替换|修改|update|replace|change)'
    if re.search(memory_object + r'[^。！？!?，,]*' + change + '|' + change + r'[^。！？!?，,]*' + memory_object, text):
        return True
    return any(marker in text for marker in (
        '忘记', '忘掉', '遗忘', '别再提', '不要再提', '别记', '不要记',
        '删除', '删掉', '清除', '移除', '不要保留', '更正', '纠正', '修正', '记错', '说错',
        '记住', '记下', '记录下来', '保存', '目标', '承诺',
        '一开始', '最初', '错误', '更正前', '改之前',
        'forget', 'delete', 'erase', 'remove', 'correct',
    ))


def is_dialogue_continuation(message: str) -> bool:
    if is_dialogue_control(message):
        return False
    patterns = (
        r'(?:那|就|请)?按(?:这个|那个|刚才的|上面的)意思(?:再)?写(?:一句|一版)(?:吧)?',
        r'(?:请|帮我)?把(?:上一句|刚才那句|这句|那句)(?:改短|缩短)(?:一些|一点|点)?(?:吧)?',
        r'(?:请)?再给我(?:一个版本|一版)(?:吧)?',
    )
    return any(re.fullmatch(pattern, clause.strip()) for clause in re.split(r'[。！？!?，,]', message)
        for pattern in patterns)


def select_recent_dialogue(records: tuple[ConversationTurnRecord, ...], *, after_sequence: int = 0) -> tuple[RecentDialogueTurn, ...]:
    selected = []
    chars = 0
    for record in reversed(records[-MAX_DIALOGUE_TURNS:]):
        if record.head_sequence <= after_sequence:
            break
        summary = record.outcome_summary
        if (is_dialogue_control(record.user_text) or summary is None
            or summary.memory_revision is not False
            or summary.living_memory_status not in {'accepted', 'no-op'}):
            break
        size = len(record.user_text) + len(record.assistant_text)
        if chars + size > MAX_DIALOGUE_CHARS:
            break
        selected.append(RecentDialogueTurn(record.user_text, record.assistant_text))
        chars += size
    return tuple(reversed(selected))

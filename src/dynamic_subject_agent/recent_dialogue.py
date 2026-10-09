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


def is_dialogue_control(message: str, *, legacy_topic_markers: bool = True) -> bool:
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
        '记住', '记下', '记录下来', '保存',
        'forget', 'delete', 'erase', 'remove', 'correct',
    ) + (('目标', '承诺', '一开始', '最初', '错误', '更正前', '改之前') if legacy_topic_markers else ()))


def is_dialogue_continuation(message: str) -> bool:
    if is_dialogue_control(message) or is_rewrite_withdrawn(message):
        return False
    if shortening_limit(message) is not None or sentence_revision_index(message) is not None:
        return True
    message = expression_request_text(message)
    patterns = (
        r'(?:那|就|请)?按(?:这个|那个|刚才的|上面的)意思(?:再)?写(?:一句|一版)(?:吧)?',
        r'(?:请|帮我)?把(?:上一句|刚才那句|这句|那句)(?:改短|缩短)(?:一些|一点|点)?(?:吧)?',
        r'(?:请)?再给我(?:一个版本|一版)(?:吧)?',
    )
    return any(re.fullmatch(pattern, clause.strip()) for clause in re.split(r'[。！？!?，,]', message)
        for pattern in patterns)


def is_previous_expression_rewrite(message: str) -> bool:
    """Only an entire, explicit nearest-reply request narrows the window."""
    if shortening_limit(message) is not None or sentence_revision_index(message) is not None:
        return True
    return re.fullmatch(
        r'(?:请|帮我)?把(?:上一句|刚才那句)(?:改短|缩短)(?:一些|一点|点)?(?:吧)?[。！？!?]?',
        message.strip(),
    ) is not None


def sentence_revision_index(message: str) -> int | None:
    """Recognize a direct sentence edit, even when privacy forbids its history."""
    if is_rewrite_withdrawn(message):
        return None
    text = expression_request_text(message)
    if any(marker in text for marker in ('什么意思', '是否', '是不是')):
        return None
    from dynamic_subject_agent.natural_writing import natural_sentence_index
    return natural_sentence_index(message)


def shortening_limit(message: str) -> int | None:
    """A direct bounded rewrite request; surrounding comments are not history."""
    if is_dialogue_control(message) or is_rewrite_withdrawn(message):
        return None
    unquoted = expression_request_text(message)
    matches = []
    for clause in re.split(r'[。！？!?，,]', unquoted):
        match = re.fullmatch(r'(?:能|可以|请|帮我)?(?:把(?:上一句|刚才那句|这句))?(?:缩到|缩短到|改短到)([0-9一二三四五六七八九十两]{1,3})个?字以内(?:吗|吧)?', clause.strip())
        if match is not None:
            token = match[1]
            if token.isascii() and token.isdigit():
                value = int(token)
            elif re.fullmatch(r'[一二三四五六七八九两]?十[一二三四五六七八九]?|[一二三四五六七八九两]', token):
                digits = {char: index for index, char in enumerate('零一二三四五六七八九')}
                digits['两'] = 2
                if '十' in token:
                    tens, units = token.split('十')
                    value = digits.get(tens, 1) * 10 + digits.get(units, 0)
                else:
                    value = digits[token]
            else:
                return None
            if not 1 <= value <= 99:
                return None
            matches.append(value)
    return matches[0] if len(matches) == 1 else None


def is_rewrite_withdrawn(message: str) -> bool:
    unquoted = expression_request_text(message)
    unquoted = re.sub(r'(?:别|不要)写(?=成|得)', '', unquoted)
    return re.search(r'(?:别|不要|不用|不必|不许|停止|取消)(?:再)?(?:改|缩|写|编|创作|想象)', unquoted) is not None


def expression_request_text(message: str) -> str:
    unquoted = re.sub(r'“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"',
        lambda match: '。' if match[0][-2:-1] in '。！？!?' else '', message)
    return '。'.join(sentence for sentence in re.split(r'[。！？!?]', unquoted)
        if not re.match(r'^(?:我|他|她|朋友)?(?:昨天|前天|之前|上次|曾经)[^，,：:]*(?:说|问|要求)[^，,：:]*[，,：:]', sentence.strip()))


def select_recent_dialogue_records(records: tuple[ConversationTurnRecord, ...], *, after_sequence: int = 0,
                                  control_predicate=is_dialogue_control) -> tuple[ConversationTurnRecord, ...]:
    """Keep canonical source identity through the exact bounded selection.

    Text projection happens only after this selection. Equal words in two
    different Publications are not evidence that both records were supplied.
    """
    selected = []
    chars = 0
    for record in reversed(records[-MAX_DIALOGUE_TURNS:]):
        if record.head_sequence <= after_sequence:
            break
        summary = record.outcome_summary
        if (control_predicate(record.user_text) or summary is None
            or summary.memory_revision is not False
            or summary.living_memory_status not in {'accepted', 'no-op'}):
            break
        size = len(record.user_text) + len(record.assistant_text)
        if chars + size > MAX_DIALOGUE_CHARS:
            break
        selected.append(record)
        chars += size
    return tuple(reversed(selected))


def select_recent_dialogue(records: tuple[ConversationTurnRecord, ...], *, after_sequence: int = 0,
                           control_predicate=is_dialogue_control) -> tuple[RecentDialogueTurn, ...]:
    return tuple(RecentDialogueTurn(record.user_text, record.assistant_text)
        for record in select_recent_dialogue_records(records, after_sequence=after_sequence,
            control_predicate=control_predicate))

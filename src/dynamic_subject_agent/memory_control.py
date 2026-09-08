"""Local, explicit selection for forward-only withdrawal of a single memory."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dynamic_subject_agent.timeline import LivingMemoryRecord


@dataclass(frozen=True)
class MemoryWithdrawal:
    target_memory_id: str | None
    reason_code: str

    @property
    def restricts_disclosure(self) -> bool:
        return self.reason_code != 'not_requested'


_NAME_OBJECT = r'(?:我(?:的|之前报的|之前说的|之前告诉你的)?|之前(?:报的|说的))?(?:名字|姓名|昵称)'
_NAME_RECORD = re.compile(r'(?:记住[：:]?)?(?:我叫|我的(?:名字|姓名|昵称)是)[^，,。！？!?；;\s]{1,40}[。]?')
_VERB = r'(?:忘记|忘掉|遗忘)'


def select_memory_withdrawal(message: str, active: tuple[LivingMemoryRecord, ...]) -> MemoryWithdrawal | None:
    """Only an unambiguous complete command can select an active record.

    Other withdrawal-looking messages are handled locally without guessing or
    allowing a model to promise success. Quoted/narrated commands never select.
    """
    stop_retention = r'(?:不要|别|不用|不再)(?:再)?(?:保存|保留|记住|记着)'
    control_marker = _VERB + r'|(?:删除|删掉).*(?:记忆|记录|名字|姓名)|' + stop_retention
    if not re.search(control_marker, message):
        return None
    clauses = [c.strip() for c in re.split(r'[。！？!?；;\n]', message) if c.strip()]
    # A quoted literal may itself contain punctuation, so match the entire
    # command before attempting the narrower name/alias clause form.
    quoted = re.fullmatch(r'(?:请)?' + _VERB + r'(?:这条记忆[：:]?)?[「“](.+)[」”](?:吧)?[。]?', message.strip())
    if quoted:
        targets = [m for m in active if m.status == 'active' and m.content.strip() == quoted[1].strip()]
    else:
        unquoted = re.sub(r'[「“"].*?[」”"]', '', message)
        retained_name = re.fullmatch(r'(?:请)?(?:不要|别|不用|不能|不许|不准)(?:再)?'
            + _VERB + _NAME_OBJECT + r'[。！？!?]?', unquoted.strip())
        # Removing a quoted object must not remove the authority-relevant verb.
        if not re.search(_VERB + r'|删除|删掉|' + stop_retention, unquoted) or retained_name:
            return MemoryWithdrawal(None, 'not_requested')
        commands = []
        for clause in clauses:
            if re.fullmatch(r'这里叫我[^，,]{1,30}(?:就好|就行)', clause):
                continue
            suffix = r'(?:吧)?(?:[，,](?:不用|不要)再?(?:保存|记住)(?:了)?)?'
            if (re.fullmatch(r'(?:请)?把?' + _NAME_OBJECT + _VERB + suffix, clause)
                or re.fullmatch(r'(?:请)?' + _VERB + _NAME_OBJECT + suffix, clause)
                or re.fullmatch(r'(?:请)?' + stop_retention + _NAME_OBJECT + r'(?:了)?', clause)):
                commands.append(clause)
            else:
                return MemoryWithdrawal(None, 'unsupported_or_conflicting_request')
        if len(commands) != 1:
            return MemoryWithdrawal(None, 'ambiguous_request')
        targets = [m for m in active if m.status == 'active' and _NAME_RECORD.fullmatch(m.content.strip())]
    if len(targets) != 1:
        return MemoryWithdrawal(None, 'target_not_unique')
    return MemoryWithdrawal(targets[0].memory_id, 'selected')


def memory_withdrawal_reply(status: str | None) -> str | None:
    if status is None:
        return None
    if status == 'accepted':
        return '已停止把这条记录作为活跃记忆使用。旧聊天和本地审计原文仍保留；这不是物理删除。'
    if status == 'no-op':
        return '没有停用任何记忆，原有记录保持不变。'
    return '这次没有停用任何记忆。请明确指出唯一一条记录；也可以用「原文」指定要忘记的完整记忆。'


def is_memory_inventory_query(message: str) -> bool:
    text = re.sub(r'\s+', '', message).rstrip('。？！?!')
    return bool(re.fullmatch(
        r'(?:那)?你(?:手头)?(?:关于我的)?(?:记录|记忆)(?:里|中)?[，,]?(?:现在)?(?:还)?(?:留着|保存了|存着)(?:哪些|什么)(?:内容|信息|记忆)?'
        r'|你(?:现在)?(?:还)?记得(?:哪些|什么)(?:内容|信息|记忆)?', text))


def missing_name_answer(message: str, available: tuple[LivingMemoryRecord, ...], *, complete: bool) -> str | None:
    query = re.fullmatch(r'(?:最初|一开始)?(?:你还记得)?我(?:之前|最初|一开始)?(?:报的|说过的|告诉你的)?'
        r'(?:名字|姓名|昵称)(?:是|叫)?(?:什么|啥)(?:吗)?[。！？!?]?', message.strip())
    if query and (not complete or not any(_NAME_RECORD.fullmatch(m.content.strip()) for m in available)):
        return '当前没有可确认并可用于回复的姓名记录；这不表示你从未提供过姓名。'
    return None

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


_NAME_OBJECT = r'(?:我(?:的|之前报的|之前说的|之前告诉你的)?|之前(?:报的|说的))?(?:名字|姓名|昵称)'
_NAME_RECORD = re.compile(r'(?:记住[：:]?)?(?:我叫|我的(?:名字|姓名|昵称)是)[^，,。！？!?；;\s]{1,40}[。]?')
_VERB = r'(?:忘记|忘掉|遗忘)'


def select_memory_withdrawal(message: str, active: tuple[LivingMemoryRecord, ...]) -> MemoryWithdrawal | None:
    """Only an unambiguous complete command can select an active record.

    Other withdrawal-looking messages are handled locally without guessing or
    allowing a model to promise success. Quoted/narrated commands never select.
    """
    if not re.search(_VERB + r'|(?:删除|删掉|不再保存|不再保留).*(?:记忆|记录|名字|姓名)', message):
        return None
    clauses = [c.strip() for c in re.split(r'[。！？!?；;\n]', message) if c.strip()]
    # A quoted literal may itself contain punctuation, so match the entire
    # command before attempting the narrower name/alias clause form.
    quoted = re.fullmatch(r'(?:请)?' + _VERB + r'(?:这条记忆[：:]?)?[「“](.+)[」”](?:吧)?[。]?', message.strip())
    if quoted:
        targets = [m for m in active if m.status == 'active' and m.content.strip() == quoted[1].strip()]
    else:
        commands = []
        for clause in clauses:
            if re.fullmatch(r'这里叫我[^，,]{1,30}(?:就好|就行)', clause):
                continue
            suffix = r'(?:吧)?(?:[，,](?:不用|不要)再?(?:保存|记住)(?:了)?)?'
            if (re.fullmatch(r'(?:请)?把?' + _NAME_OBJECT + _VERB + suffix, clause)
                or re.fullmatch(r'(?:请)?' + _VERB + _NAME_OBJECT + suffix, clause)):
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
    return '这次没有停用任何记忆。请明确指出唯一一条记录；也可以用「原文」指定要忘记的完整记忆。'

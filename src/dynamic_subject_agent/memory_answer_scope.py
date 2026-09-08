"""Local limits on what a reply may infer from a memory selection."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING
from dynamic_subject_agent.recent_dialogue import expression_request_text
from dynamic_subject_agent.runtime_identity_reply import explicit_creation_request

if TYPE_CHECKING:
    from dynamic_subject_agent.timeline import LivingMemoryRecord

NO_SELECTED_MEMORY = '本轮没有选到可用于回答这条问题的相关活跃记忆。这不代表全部记忆为空，也不表示你从未提供过相关内容。'
MEMORY_SCOPE_UNAVAILABLE = '这次无法核实相关记忆的可用范围，不能据此断言没有记录或已停用。'


def is_memory_status_query(message: str) -> bool:
    return any(not explicit_creation_request(clause)
        and re.search(r'活跃记忆|活跃记录|这条记录|那条记录', clause)
        and re.search(r'吗|是否|有没有|还在|还活跃|停用|状态', clause)
        for clause in re.split(r'[。！？!?]', expression_request_text(message)))


def unsupported_inventory_claim(text: str) -> bool:
    unquoted = expression_request_text(text)
    return bool(re.search(r'(?:我(?:现在|目前)?|当前|现在|目前)(?:没有|不存在)(?:任何|可用的?|活跃的?)*(?:记忆|记录)(?:了)?(?=[，,。！？!?；;\s]|$)', unquoted)
        or re.search(r'你(?:之前|以前)?(?:从未|从来没(?:有)?)(?:告诉|提供|说)', unquoted))


def selected_memory_answer(contents: tuple[str, ...], *, available: bool) -> str:
    if not available:
        return MEMORY_SCOPE_UNAVAILABLE
    if not contents:
        return NO_SELECTED_MEMORY
    return '本轮选中的可用记录如下；是否是你指的那条，需要你确认：\n' + '\n'.join(f'「{content}」' for content in contents)


def exact_memory_status_answer(message: str, history: tuple[LivingMemoryRecord, ...], *, complete: bool, readable: bool) -> str | None:
    match = re.fullmatch(r'[「“](.+)[」”](?:这条)?(?:记忆|记录)(?:现在)?(?:还)?(?:活跃|在用|停用)(?:吗)?[。！？!?]?', message.strip())
    if match is None:
        return None
    if not complete or not readable:
        return MEMORY_SCOPE_UNAVAILABLE
    records = [record for record in history if record.content.strip() == match[1].strip()]
    if len(records) != 1:
        return '本轮无法按该原文唯一确认记录状态；这不表示你从未提供过相关内容。'
    return {
        'active': '这条记录目前处于活跃状态。',
        'forgotten': '这条记录已停用，不再作为活跃记忆使用。旧聊天与审计原文仍保留。',
        'superseded': '这条记录已被后续修订替代，不是当前活跃版本。',
    }.get(records[0].status, MEMORY_SCOPE_UNAVAILABLE)

"""Memory operation acknowledgements derived only from adjudicated outcomes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from dynamic_subject_agent.recent_dialogue import expression_request_text
from dynamic_subject_agent.runtime_identity_reply import CREATIVE_REPLY_PREFIX
from dynamic_subject_agent.memory_answer_scope import is_memory_status_query

if TYPE_CHECKING:
    from dynamic_subject_agent.timeline import ExperienceDomainOutcome


def explicit_memory_write_request(message: str) -> bool:
    text = expression_request_text(message)
    return any(re.match(
        r'^(?:(?:请|帮我)?(?:记住|记下)(?!了?吗)|(?:请|帮我)(?:记录|保存)'
        r'|(?:记录|保存|更正记忆|修改记忆|更新记忆)[：:])', clause.strip())
        for clause in re.split(r'[。；;\n]', text))


def independent_memory_question(message: str, evidence: str) -> bool:
    """Recognize an unquoted question distinct from operation confirmation."""
    rest = re.sub(r'“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"', '', message)
    if evidence and '?' not in evidence and '？' not in evidence and rest.count(evidence) == 1:
        rest = rest.replace(evidence, '', 1)
    for question in re.findall(r'[^。！？!?；;\n]+[？?]', rest):
        unquoted = expression_request_text(question)
        if not unquoted.strip('。 '):
            continue
        tail = re.split(r'[，,：:]', unquoted)[-1]
        if (explicit_memory_write_request(tail) or is_memory_status_query(tail)
            or re.search(r'(?:记住|记下|保存|记录|更正|修改|更新).*(?:了吗|了没|成功|完成)', tail)
            or re.search(r'(?:是否|有没有).*(?:记住|记下|保存|记录|更正)', tail)):
            continue
        return True
    return False


def contains_memory_write_claim(text: str) -> bool:
    """A discussion continuation cannot also assert an operation result."""
    text = expression_request_text(text)
    return bool(re.search(
        r'(?:我(?:已经|已|会|将)?(?:帮你|替你)?|(?:已经|已)(?:帮你|替你)?)(?:把[^。]{0,40})?'
        r'(?:记住|记下|记录|保存|更正|修改|更新)'
        r'|(?:记住|记下|记录|保存|更正|修改|更新)(?:成功|完成|好了|了)', text))


def memory_write_receipt(outcome: ExperienceDomainOutcome, *, requested: bool) -> str | None:
    if not requested or outcome.memory_withdrawal_status is not None:
        return None
    status = outcome.living_memory_status.value
    if status == 'accepted' and outcome.living_memory_content:
        import json
        confirmation = json.loads(outcome.decision.reason).get('living_memory', {}).get('preference_confirmation')
        if confirmation is not None:
            from dynamic_subject_agent.preference_clarification import valid_confirmation
            if valid_confirmation(confirmation):
                verb = '补充记录' if confirmation['choice'] == 'supplement' else '更正记录'
                return f'已按你的确认{verb}此前提供的偏好：「{outcome.living_memory_content}」'
        prefix = '已更正这条记忆，新内容是：' if outcome.memory_revision is True else '已记录你的原话：'
        return prefix + f'「{outcome.living_memory_content}」'
    if status == 'failed-closed':
        return '这次没能完成记忆写入，没有新增或更正记忆。'
    if status == 'rejected':
        return '这次没有保存或更正这条记忆，原有记录保持不变。'
    return '本轮没有新增或更正记忆。'


def combine_memory_write_receipt(receipt: str, text: str) -> str:
    # Keep the established first-paragraph draft format available to subsequent
    # sentence edits; receipts are separate status prose, never draft sentences.
    parts = (text, receipt) if text.startswith(CREATIVE_REPLY_PREFIX) else (receipt, text)
    return '\n\n'.join(part for part in parts if part.strip())

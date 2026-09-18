"""Canonical subject tasks and the minimal, authorized proposal projection."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import re
import unicodedata
from uuid import UUID

TASK_INTENT = 'subject-task-v1'
KINDS = ('draft_text', 'save_text')
OPEN = ('accepted', 'needs_input', 'deferred', 'executing')
STATUSES = (*OPEN, 'declined', 'cancelled', 'completed', 'failed')
POLICY = ('subject-tasks-1.0: only draft_text and save_text; propose accept, clarify, defer or decline. '
    'Accept explicit text work, clarify unclear requests, defer when another accepted task is open, '
    'decline unsupported external actions. Acceptance is not execution. Saving requires separate exact approval. '
    'Return only JSON {decision, reason}; reason is supported_request, clarification_requested, capacity, or unsupported_request.')


@dataclass(frozen=True)
class SubjectTaskCommand:
    action: str
    kind: str = ''
    message: str = ''
    task_id: str | None = None
    expected_revision: int | None = None
    content: str = ''

    def __post_init__(self):
        if self.action not in ('request', 'revise', 'cancel'):
            raise ValueError('unsupported task action')
        if not isinstance(self.content, str) or len(self.content) > 16000:
            raise ValueError('invalid local text')
        if self.action in ('request', 'revise'):
            if self.kind not in KINDS or not isinstance(self.message, str) or not 1 <= len(self.message.strip()) <= 1000 or len(self.message) > 1000:
                raise ValueError('invalid current task request')
        elif self.kind or self.message or self.content:
            raise ValueError('cancel carries no new content')
        if self.action == 'request':
            if self.task_id is not None or self.expected_revision is not None:
                raise ValueError('new task cannot name old state')
        else:
            if not isinstance(self.task_id, str) or str(UUID(self.task_id)) != self.task_id:
                raise ValueError('invalid task reference')
            if type(self.expected_revision) is not int or self.expected_revision < 1:
                raise ValueError('invalid task revision')
        encoded = self.to_json()
        encoded.encode('utf-8')
        if len(encoded) > 32768:
            raise ValueError('local text exceeds canonical command bound')

    def to_json(self) -> str:
        # Admission normalizes NFC. Escape non-NFC values so local text remains exact.
        return '{' + ','.join(json.dumps(key) + ':' + json.dumps(value,
            ensure_ascii=isinstance(value, str) and unicodedata.normalize('NFC', value) != value,
            separators=(',', ':')) for key, value in sorted(asdict(self).items())) + '}'

    @classmethod
    def from_json(cls, text: str):
        value = json.loads(text)
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError('invalid task command')
        return cls(**value)


@dataclass(frozen=True)
class SubjectTaskRecord:
    task_id: str
    kind: str
    summary: str
    status: str
    request_text: str
    content: str
    revision: int
    reason: str

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError('invalid task record')
        item = cls(**value)
        if (str(UUID(item.task_id)) != item.task_id or item.kind not in KINDS or item.status not in STATUSES
            or type(item.revision) is not int or item.revision < 1
            or not isinstance(item.request_text, str) or not 1 <= len(item.request_text) <= 1000
            or item.summary != item.request_text[:200] or not isinstance(item.content, str) or len(item.content) > 16000
            or item.reason not in ('supported_request', 'clarification_requested', 'capacity', 'unsupported_request',
                'provider_failed', 'invalid_proposal', 'missing_content', 'cancelled', 'save_approved', 'saved', 'file_failed')):
            raise ValueError('invalid task record values')
        return item


@dataclass(frozen=True)
class SubjectTaskProposal:
    decision: str
    reason: str

    def __post_init__(self):
        if {'accept':'supported_request','clarify':'clarification_requested','defer':'capacity',
            'decline':'unsupported_request'}.get(self.decision) != self.reason:
            raise ValueError('invalid task proposal')


@dataclass(frozen=True)
class SubjectTaskProjection:
    current_user_message: str
    active_tasks: tuple[dict, ...]

    @classmethod
    def build(cls, message: str, records: tuple[SubjectTaskRecord, ...]):
        return cls(message, tuple({'kind': r.kind, 'summary': r.summary, 'status': r.status}
            for r in records if r.status in OPEN)[:5])

    def payload(self) -> dict:
        if (not isinstance(self.current_user_message, str) or not 1 <= len(self.current_user_message) <= 1000
            or type(self.active_tasks) is not tuple or len(self.active_tasks) > 5):
            raise ValueError('invalid agency projection')
        for task in self.active_tasks:
            if (type(task) is not dict or set(task) != {'kind','summary','status'} or task['kind'] not in KINDS
                or task['status'] not in OPEN or not isinstance(task['summary'], str) or not 1 <= len(task['summary']) <= 200):
                raise ValueError('invalid agency task summary')
        return {'current_user_message': self.current_user_message, 'active_tasks': list(self.active_tasks),
            'task_catalog': list(KINDS), 'policy': POLICY}


def decide(command: SubjectTaskCommand, proposal: SubjectTaskProposal | None,
    records: tuple[SubjectTaskRecord, ...], *, new_id: str) -> tuple[SubjectTaskRecord | None, str]:
    old = next((r for r in records if r.task_id == command.task_id), None)
    if command.action != 'request' and (old is None or old.revision != command.expected_revision or old.status not in OPEN or old.status=='executing'):
        return None, '任务状态已变化或不能操作，请刷新后查看。'
    if command.action == 'cancel':
        return replace(old, status='cancelled', revision=old.revision+1, reason='cancelled'), '已取消这项主体任务，没有执行文件操作。'
    others = tuple(r for r in records if r.status in OPEN and (old is None or r.task_id != old.task_id))
    if len(others) >= 5:
        status, reason = 'declined', 'capacity'
    elif re.match(r'^(?:请)?(?:帮我|替我)?(?:发送邮件|发邮件|联网|设置定时|定时提醒|删除文件|执行命令|运行脚本|转账|购买)', command.message.strip()):
        status, reason = 'declined', 'unsupported_request'
    elif not isinstance(proposal, SubjectTaskProposal):
        status, reason = 'failed', 'provider_failed'
    elif proposal.decision == 'decline':
        status, reason = 'failed', 'invalid_proposal'
    elif command.kind == 'save_text' and not command.content.strip():
        status, reason = 'needs_input', 'missing_content'
    elif proposal.decision == 'clarify':
        status, reason = 'needs_input', proposal.reason
    elif any(r.status in ('accepted','executing') for r in others):
        status, reason = 'deferred', 'capacity'
    elif proposal.decision == 'defer':
        status, reason = 'failed', 'invalid_proposal'
    else:
        status, reason = 'accepted', 'supported_request'
    if old is not None and (status in ('failed','declined') or (old.status == 'accepted' and status != 'accepted')):
        return None, '这次修订没有被接受，原任务保持不变；请补充说明或稍后重试。'
    record = SubjectTaskRecord(old.task_id if old else new_id, command.kind, command.message[:200],
        status, command.message, command.content, old.revision+1 if old else 1, reason)
    SubjectTaskRecord.from_dict(asdict(record))
    reply = {'accepted':'已接受这项主体任务，当前为待处理；尚未生成成品或保存文件。',
        'needs_input':'这项任务需要补充说明或保存正文；尚未接受执行，请编辑后重新提交。',
        'deferred':'已有接受的任务尚未结束，这项任务暂缓；不会自动后台执行。',
        'declined':'这次没有接受任务；请查看支持的文字任务范围及未结束任务。',
        'failed':'这次任务提议未能通过校验，没有接受或执行任务。'}[status]
    return record, reply


def validate_task_reason(value: dict) -> None:
    if set(value) != {'code','provenance','subject_task','reply','proposal'} or value['code'] != 'subject-task.result':
        raise ValueError('invalid task outcome')
    if not isinstance(value['reply'], str) or not 1 <= len(value['reply']) <= 1000:
        raise ValueError('invalid task receipt')
    if value['subject_task'] is not None:
        SubjectTaskRecord.from_dict(value['subject_task'])
    if value['proposal'] is not None:
        if not isinstance(value['proposal'],dict) or set(value['proposal']) != {'decision','reason'}:
            raise ValueError('invalid task proposal record')
        SubjectTaskProposal(**value['proposal'])

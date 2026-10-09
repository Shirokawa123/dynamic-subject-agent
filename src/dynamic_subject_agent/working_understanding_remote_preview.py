"""Exact S145 unsent requests; pending authority has no transport/key path."""
from dataclasses import dataclass
from hashlib import sha256
import re

from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTask, ModelTaskKind, ModelGatewayFailure)
from dynamic_subject_agent.working_understanding import FORM_POLICY, CHOICE_POLICY, REPLY_POLICY


@dataclass(frozen=True)
class PendingWorkingUnderstandingGrant:
    review_sha256: str
    status: str = 'unapproved'

    def __post_init__(self):
        if self.status != 'unapproved' or re.fullmatch('[0-9a-f]{64}', self.review_sha256) is None:
            raise ValueError('only pending working review is representable')


def working_remote_request_preview(task):
    policies = {ModelTaskKind.WORKING_UNDERSTANDING_FORM:FORM_POLICY,
        ModelTaskKind.WORKING_ACTIVITY_CHOICE:CHOICE_POLICY, ModelTaskKind.WORKING_ACTIVITY_REPLY:REPLY_POLICY}
    if type(task) is not ModelTask or task.kind not in policies:
        raise ValueError('typed working task required')
    preview, policy = task.payload, policies[task.kind]
    if type(preview) is not dict or set(preview) != {'policy','payload'} or preview['policy'] != policy:
        raise ValueError('exact LOCAL execution policy required')
    protocol = communication_protocol('thinking-high','low')
    options = dict(protocol['expression'])
    if task.kind is ModelTaskKind.WORKING_ACTIVITY_REPLY:
        options.pop('response_format', None)
    body = dict(model=protocol['model'], messages=[dict(role='system',content=policy),
        dict(role='user',content=canonical_json(preview['payload']))], **options)
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError('bounded working wire required')
    return dict(status='unapproved-preview-only', purpose=task.kind.value,
        endpoint='https://api.deepseek.com/chat/completions', timeout_seconds=30, automatic_retries=0,
        requests_per_manual_action=1, credential_use='existing-Windows-slot-HTTPS-Bearer-only-after-separate-approval',
        body=body, wire_sha256=sha256(wire).hexdigest())


class UnapprovedWorkingUnderstandingAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek','deepseek-flash',False,(StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, grant):
        if type(grant) is not PendingWorkingUnderstandingGrant:
            raise ValueError('typed pending working review required')
        self.grant = grant

    def invoke(self, task):
        raise ModelGatewayFailure('working-understanding-use-unapproved')

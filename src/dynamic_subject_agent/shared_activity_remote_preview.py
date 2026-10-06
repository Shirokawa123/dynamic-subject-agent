"""Exact unsent candidate protocol, with an explicitly unapproved Adapter.

No transport, credential resolver, activation or remote grant exists here.
"""
from dataclasses import dataclass
from hashlib import sha256
import re

from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.shared_activity import CHOICE_POLICY, shared_reply_policy, SHARED_TECHNICAL_VARIANTS


@dataclass(frozen=True)
class PendingSharedActivityGrant:
    review_sha256: str
    status: str = 'unapproved'

    def __post_init__(self):
        if self.status != 'unapproved' or re.fullmatch(r'[0-9a-f]{64}', self.review_sha256) is None:
            raise ValueError('only a typed pending review can be represented before approval')


def shared_remote_request_preview(task, *, technical_variant='baseline'):
    """The future single request's exact body, generated from the local builder.

    It remains review data. Passing this value never creates an execution ticket.
    """
    if type(technical_variant) is not str or technical_variant not in SHARED_TECHNICAL_VARIANTS:
        raise ValueError('known exact shared technical variant required')
    if type(task) is not ModelTask or task.kind not in (ModelTaskKind.SHARED_ACTIVITY_CHOICE, ModelTaskKind.SHARED_ACTIVITY_REPLY):
        raise ValueError('typed shared activity task required')
    preview = task.payload
    reply_policy = shared_reply_policy(technical_variant)
    expected_policy = CHOICE_POLICY if task.kind is ModelTaskKind.SHARED_ACTIVITY_CHOICE else reply_policy
    if type(preview) is not dict or set(preview) != {'policy', 'payload'} or preview['policy'] != expected_policy:
        raise ValueError('candidate policy must be the exact local execution policy')
    protocol = communication_protocol('thinking-high', 'low')
    body = dict(model=protocol['model'], messages=[dict(role='system', content=expected_policy),
        dict(role='user', content=canonical_json(preview['payload']))], **protocol['expression'])
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError('bounded candidate wire required')
    return dict(status='unapproved-preview-only', purpose=task.kind.value,
        endpoint='https://api.deepseek.com/chat/completions', timeout_seconds=30, automatic_retries=0,
        requests_per_manual_action=1, credential_use='existing-Windows-slot-HTTPS-Bearer-only-after-separate-approval',
        body=body, wire_sha256=sha256(wire).hexdigest())


class UnapprovedSharedActivityAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, grant):
        if type(grant) is not PendingSharedActivityGrant:
            raise ValueError('an exact pending shared activity review is required')
        self.grant = grant

    def invoke(self, task):
        raise ModelGatewayFailure('shared-activity-use-unapproved')

"""Unsent exact S142 wire review. No transport, credential or LIVE grant."""
from dataclasses import dataclass
from hashlib import sha256
import re

from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ModelTask, ModelTaskKind, ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGatewayFailure)
from dynamic_subject_agent.living_activity import SHARE_POLICY, REPLY_POLICY
from dynamic_subject_agent.shared_activity import shared_choice_policy

SHARE_OUTPUT_SCHEMA = dict(type='object', additionalProperties=False,
    required=['share', 'reply_text', 'language'], properties=dict(share=dict(type='boolean'),
        reply_text=dict(type='string', maxLength=400), language=dict(type='string', const='zh')),
    allOf=[{'if': {'properties': {'share': {'const': True}}},
        'then': {'properties': {'reply_text': {'minLength': 1}}},
        'else': {'properties': {'reply_text': {'const': ''}}}}])
# The exact Python adjudicator additionally enforces phase/action/plan and the
# conditional false->empty relationship. This review does not claim provider
# strict-schema support; actual protocol remains JSON object.
OUTPUT_CONTRACTS = {
    ModelTaskKind.LIVING_ACTIVITY_CHOICE: dict(fields=['action', 'plan', 'reason_code', 'basis_refs', 'decision_note'],
        action='phase-allowed closed set', plan=dict(subject_max=160, composition_max=800, focus_max=400),
        basis_refs=[[], ['E1']], decision_note_max=160),
    ModelTaskKind.LIVING_ACTIVITY_SHARE: dict(fields=['share', 'reply_text', 'language'],
        share='boolean', reply_text_max=400, false_text='', true_text='nonempty', language='zh'),
    ModelTaskKind.LIVING_ACTIVITY_REPLY: dict(fields=['reply_text', 'language'], reply_text_max=1200, reply_text='nonempty', language='zh'),
}


@dataclass(frozen=True)
class PendingLivingActivityGrant:
    review_sha256: str
    status: str = 'unapproved'

    def __post_init__(self):
        if self.status != 'unapproved' or type(self.review_sha256) is not str or re.fullmatch('[0-9a-f]{64}', self.review_sha256) is None:
            raise ValueError('only an exact unapproved living review may be represented')


def living_remote_request_preview(task):
    policies = {ModelTaskKind.LIVING_ACTIVITY_CHOICE: shared_choice_policy('self-directed-activity'),
        ModelTaskKind.LIVING_ACTIVITY_SHARE: SHARE_POLICY, ModelTaskKind.LIVING_ACTIVITY_REPLY: REPLY_POLICY}
    if type(task) is not ModelTask or task.kind not in policies:
        raise ValueError('typed closed living task required')
    if type(task.payload) is not dict or set(task.payload) != {'policy', 'payload'} or task.payload['policy'] != policies[task.kind]:
        raise ValueError('exact actual living policy required')
    protocol = communication_protocol('thinking-high', 'low')
    body = dict(model=protocol['model'], messages=[dict(role='system', content=policies[task.kind]),
        dict(role='user', content=canonical_json(task.payload['payload']))], **protocol['expression'])
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError('bounded living wire required')
    return dict(status='unapproved-preview-only', purpose=task.kind.value,
        endpoint='https://api.deepseek.com/chat/completions', body=body, timeout_seconds=30,
        requests_per_action=1, automatic_retries=0, output_contract=OUTPUT_CONTRACTS[task.kind],
        credential_use='existing-Windows-slot-HTTPS-Bearer-only-after-exact-separate-approval',
        wire_sha256=sha256(wire).hexdigest())


class UnapprovedLivingActivityAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, grant):
        if type(grant) is not PendingLivingActivityGrant:
            raise ValueError('exact pending living review required')
        self.grant = grant

    def invoke(self, task):
        raise ModelGatewayFailure('living-activity-use-unapproved')

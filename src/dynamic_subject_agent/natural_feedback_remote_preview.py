"""Unsent exact new-purpose bodies. No transport or credential resolver."""
from dataclasses import dataclass
from hashlib import sha256
import re

from dynamic_subject_agent.model_gateway import (
    ModelTask, ModelTaskKind, ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGatewayFailure)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.natural_feedback import FEEDBACK_POLICY, feedback_choice_policy


def natural_feedback_remote_request_preview(task, *, technical_variant='baseline'):
    if type(task) is not ModelTask or task.kind not in (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.SHARED_ACTIVITY_CHOICE):
        raise ValueError('exact candidate feedback or activity choice task required')
    expected = FEEDBACK_POLICY if task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK else feedback_choice_policy()
    if technical_variant=='scoped' and task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
        from dynamic_subject_agent.natural_feedback_frame import SCOPED_POLICY
        expected=SCOPED_POLICY
    if technical_variant in ('intent-only','multi-span','choice-low','choice-final') and task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
        from dynamic_subject_agent.natural_feedback_intent import INTENT_POLICY
        expected=INTENT_POLICY
    if (type(task.payload) is not dict or set(task.payload) != {'policy', 'payload'}
        or task.payload['policy'] != expected):
        raise ValueError('exact candidate policy required')
    validate_payload(task.kind, task.payload['payload'])
    from dynamic_subject_agent.natural_feedback_budget import feedback_protocol
    protocol = feedback_protocol(task.kind, technical_variant)
    body = dict(model=protocol['model'], messages=[dict(role='system', content=expected),
        dict(role='user', content=canonical_json(task.payload['payload']))], **protocol['expression'])
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError('bounded candidate wire required')
    return dict(status='unapproved-preview-only', purpose=task.kind.value,
        endpoint='https://api.deepseek.com/chat/completions', body=body, timeout_seconds=30,
        max_requests_per_action=1, automatic_retries=0, wire_sha256=sha256(wire).hexdigest(),
        credential_use='existing-Windows-slot-HTTPS-Bearer-only-after-separate-approval')


def _source(value, label):
    if value is not None and (type(value) is not dict or set(value) != {'label', 'quote'}
        or value['label'] != label or type(value['quote']) is not str or not value['quote'].strip()
        or len(value['quote']) > 400 or '\x00' in value['quote']):
        raise ValueError('one actual bounded source required')


def validate_payload(kind, payload):
    from dynamic_subject_agent.first_life import validate_plan
    from dynamic_subject_agent.shared_activity import allowed_actions
    from dynamic_subject_agent.original_whole_chat import OriginalWholeProjection, validate_whole_projection
    from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
    if type(payload) is not dict:
        raise ValueError('closed payload required')
    if kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
        if (set(payload) != {'turn', 'background', 'exchange', 'evidence', 'current_plan', 'activity_revision', 'current_feedback'}
            or type(payload['activity_revision']) is not int or payload['activity_revision'] < 0
            or type(payload['evidence']) is not dict or set(payload['evidence']) != {'shared_experience'}):
            raise ValueError('exact feedback projection required')
        # Reuse only the existing background/current/two-complete-round checks;
        # its always-null old life placeholders are not part of this wire.
        if type(payload['exchange']) not in (tuple, list):
            raise ValueError('complete exchange rows required')
        exchange = tuple(RecentDialogueTurn(**row) for row in payload['exchange'])
        projection = OriginalWholeProjection(payload['turn'], payload['background'], exchange,
            dict(current_activity=None, current_plan=None, related_event=None))
        validate_whole_projection(projection)
        _source(payload['evidence']['shared_experience'], 'E1')
    elif kind is ModelTaskKind.SHARED_ACTIVITY_CHOICE:
        if set(payload) != {'background', 'shared_experience', 'current_activity', 'current_plan', 'current_feedback'}:
            raise ValueError('exact feedback choice projection required')
        state = payload['current_activity']
        if (type(state) is not dict or set(state) != {'phase', 'allowed_actions'}
            or tuple(state['allowed_actions']) != allowed_actions(state['phase'])):
            raise ValueError('exact current allowed actions required')
        # Validate the character background with the same closed projection.
        validate_whole_projection(OriginalWholeProjection(dict(current_message='当前文字活动。', history_enabled=False,
            has_prior_committed_exchange=False), payload['background'], (),
            dict(current_activity=None, current_plan=None, related_event=None)))
        _source(payload['shared_experience'], 'E1')
    else:
        raise ValueError('closed feedback purpose required')
    if payload['current_plan'] is not None:
        validate_plan(payload['current_plan'])
    _source(payload['current_feedback'], 'F1')
    if payload['current_plan'] is None and payload['current_feedback'] is not None:
        raise ValueError('feedback reference requires an eligible plan')


@dataclass(frozen=True)
class PendingNaturalFeedbackGrant:
    review_sha256: str
    status: str = 'unapproved'
    def __post_init__(self):
        if self.status != 'unapproved' or re.fullmatch('[0-9a-f]{64}', self.review_sha256) is None:
            raise ValueError('only an exact unapproved review may be represented')


class UnapprovedNaturalFeedbackAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False, (StructuredOutputMode.JSON_OBJECT,))
    def __init__(self, grant):
        if type(grant) is not PendingNaturalFeedbackGrant:
            raise ValueError('exact pending grant required')
        self.grant = grant
    def invoke(self, task):
        raise ModelGatewayFailure('natural-feedback-use-unapproved')

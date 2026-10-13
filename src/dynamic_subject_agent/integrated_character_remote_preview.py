"""Exact unsent three-purpose review; deliberately no sender or credential use."""
from hashlib import sha256

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.integrated_character import integrated_policies
from dynamic_subject_agent.natural_feedback import feedback_choice_policy
from dynamic_subject_agent.natural_feedback_choice_budget import choice_protocol
from dynamic_subject_agent.natural_feedback_remote_preview import validate_payload
from dynamic_subject_agent.living_activity import living_policies


def integrated_remote_request_preview(task, *, technical_variant='baseline'):
    feedback, choice, share_policy = integrated_policies(technical_variant=technical_variant)
    policies = {ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK: feedback,
        ModelTaskKind.LIVING_ACTIVITY_CHOICE: choice, ModelTaskKind.LIVING_ACTIVITY_SHARE: share_policy}
    plain_reply = False
    if technical_variant == 'conversation-text' and type(task) is ModelTask and task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
        from dynamic_subject_agent.integrated_character_text import has_writable_frame, CONVERSATION_TEXT_POLICY
        if not has_writable_frame(task.payload['payload']):
            policies[task.kind] = CONVERSATION_TEXT_POLICY
            plain_reply = True
    if (type(task) is not ModelTask or task.kind not in policies or type(task.payload) is not dict
        or set(task.payload) != {'policy', 'payload'} or task.payload['policy'] != policies[task.kind]):
        raise ValueError('exact integrated task and policy required')
    payload = task.payload['payload']
    if task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
        if type(payload) is not dict or type(payload.get('evidence')) is not dict or set(payload['evidence']) != {'shared_experience', 'latest_share'}:
            raise ValueError('exact integrated feedback evidence required')
        share = payload['evidence']['latest_share']
        if share is not None and (type(share) is not dict or set(share) != {'text'}
            or type(share['text']) is not str or not share['text'].strip() or len(share['text']) > 400 or '\x00' in share['text']):
            raise ValueError('bounded exact S1 text required')
        base = dict(payload, evidence=dict(shared_experience=payload['evidence']['shared_experience']))
        validate_payload(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, base)
        if not payload['turn']['history_enabled'] and (share is not None or payload['current_feedback'] is not None
            or payload['evidence']['shared_experience'] is not None):
            raise ValueError('history-off must exclude conversation sources')
        output = dict(fields=['intent', 'reply_text'], intents=['chat', 'clarify', 'revise'], reply_text_max=1200,
            effect='Python-only exact frame, <=8 targets, <=4 unique disjoint edits, before<=160, after<=240')
    elif task.kind is ModelTaskKind.LIVING_ACTIVITY_CHOICE:
        validate_payload(ModelTaskKind.SHARED_ACTIVITY_CHOICE, payload)
        output = dict(fields=['action','plan','reason_code','basis_refs','decision_note'],
            plan_max=dict(subject=160, composition=800, focus=400), decision_note_max=160)
    else:
        from dynamic_subject_agent.living_activity_live import validate_living_request_payload
        validate_living_request_payload(task)
        output = dict(fields=['share','reply_text','language'], reply_text_max=400,
            true_text='nonempty', false_text='', language='zh')
    # The already diagnosed final-output mode, with the original 4096 ceiling.
    kind = ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK if task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK else ModelTaskKind.SHARED_ACTIVITY_CHOICE
    protocol = choice_protocol(kind, 'choice-final')
    body = dict(model=protocol['model'], messages=[dict(role='system', content=policies[task.kind]),
        dict(role='user', content=canonical_json(payload))], **protocol['expression'])
    if plain_reply:
        body.pop('response_format')
        output = dict(final_content='natural-text', nonempty=True, max_chars=1200,
            local_wrapper=dict(intent='chat-typed-no-effect', reply_text='original-final-content'),
            classifier='not-model-generated', effect='none; independently ineligible for plan mutation')
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError('bounded integrated wire required')
    return dict(status='unapproved-preview-only', purpose=task.kind.value,
        endpoint=protocol['endpoint'], timeout_seconds=protocol['timeout_seconds'], body=body,
        requests_per_action=1, automatic_retries=0, output_contract=output,
        credential_use='existing-Windows-slot-HTTPS-Bearer-only-after-exact-approval',
        wire_sha256=sha256(wire).hexdigest())

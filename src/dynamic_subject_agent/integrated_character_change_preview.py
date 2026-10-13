"""Unsent review candidate only; no grant, sender or runtime registration."""
from copy import deepcopy
from hashlib import sha256

from dynamic_subject_agent.current_activity_change import validate_current_activity_change
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview
from dynamic_subject_agent.model_gateway import ModelTaskKind

CHANGE_POLICY = '''current_result_change is verified evidence of only the currently visible committed revision, not a full history. changes contains exact changed excerpts; an empty before/after means insertion/deletion. unexpanded_fields names changes whose complete excerpts exceed the bound: do not invent their old text. null means no safe change evidence is available, not that nothing ever changed. When asked what changed, use this evidence and the current plan; do not claim unrecorded actions, dates or completed images.'''


def current_change_request_preview(task, change, *, technical_variant='intent-text'):
    """Review a locally validated projection without enabling its delivery."""
    if task.kind not in (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.LIVING_ACTIVITY_SHARE):
        raise ValueError('change evidence is proposed for reply and share only')
    change = validate_current_activity_change(change)
    preview = deepcopy(integrated_remote_request_preview(task, technical_variant=technical_variant))
    payload = deepcopy(task.payload['payload'])
    if task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK and not payload['turn']['history_enabled'] and change is not None:
        raise ValueError('history-off cannot expose result change')
    payload['current_result_change'] = deepcopy(change)
    preview['body']['messages'][0]['content'] += '\n\n' + CHANGE_POLICY
    preview['body']['messages'][1]['content'] = canonical_json(payload)
    wire = canonical_json(preview['body']).encode()
    if len(wire) > 65536:
        raise ValueError('bounded proposed wire required')
    preview['wire_sha256'] = sha256(wire).hexdigest()
    preview['status'] = 'unapproved-change-preview-only'
    return preview

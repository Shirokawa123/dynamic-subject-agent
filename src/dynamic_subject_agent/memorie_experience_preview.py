"""Read-only candidate from typed native history, never a memory write receipt."""
from dataclasses import dataclass
from hashlib import sha256
import json

from dynamic_subject_agent.frozen_attempt import canonical_json


@dataclass(frozen=True)
class NativeExperiencePreviewRequest:
    target_profile_id: str
    target_timeline_id: str
    source_head_sequence: int
    quote: str
    confirmed: bool = False


@dataclass(frozen=True)
class NativeExperiencePreview:
    status: str
    problem_code: str = ''
    preview_json: str = ''
    can_apply: bool = False
    canonical_eligibility_verified: bool = False


def preview(application, binding, request):
    if type(request) is not NativeExperiencePreviewRequest:
        return NativeExperiencePreview('unavailable','typed-native-experience-preview-required')
    if request.target_profile_id!=binding.profile_id or request.target_timeline_id!=binding.timeline_id:
        return NativeExperiencePreview('unavailable','native-experience-target-mismatch')
    if request.confirmed is False:
        return NativeExperiencePreview('cancelled')
    if (request.confirmed is not True or type(request.source_head_sequence) is not int or request.source_head_sequence<=0
        or type(request.quote) is not str or not request.quote.strip() or len(request.quote)>400 or '\x00' in request.quote):
        return NativeExperiencePreview('unavailable','native-experience-preview-invalid')
    try:
        status=application.reviewed_character_chat_status()
        if status.status!='active' or status.history_enabled is not True:
            return NativeExperiencePreview('unavailable','native-experience-history-not-enabled')
        history=application.query_memorie_interactions(limit=20)
        if history.status!='available':
            return NativeExperiencePreview(history.status,'native-experience-history-unverified')
        matches=[turn for turn in history.turns if turn.head_sequence==request.source_head_sequence]
        if len(matches)!=1:
            return NativeExperiencePreview('unavailable','native-experience-source-not-visible')
        interaction=json.loads(matches[0].interaction_json)
        if interaction.get('kind')!='text' or request.quote not in interaction['text']:
            return NativeExperiencePreview('unavailable','native-experience-source-not-user-text')
        if application.reviewed_character_chat_status()!=status:
            return NativeExperiencePreview('unavailable','native-experience-source-changed')
        body=dict(version='memorie-native-experience-selection-preview-m014-1',
            scope_key=sha256((binding.profile_id+':'+binding.timeline_id).encode()).hexdigest(),
            source_head_sequence=request.source_head_sequence,quote=request.quote,source_kind='explicit-user-text',
            source_input_digest=sha256(matches[0].interaction_json.encode()).hexdigest(),can_apply=False,
            canonical_eligibility_verified=False,requires='fresh-canonical-source-and-qualified-shared-capability-before-commit')
        body['selection_digest']=sha256(canonical_json(body).encode()).hexdigest()
        return NativeExperiencePreview('previewed',preview_json=canonical_json(body))
    except Exception:
        return NativeExperiencePreview('failed-closed','native-experience-preview-unverified')

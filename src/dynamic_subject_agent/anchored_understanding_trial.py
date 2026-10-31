"""Exact M036 material authority; reuses the bounded M035 delivery runner."""
from hashlib import sha256
from pathlib import Path
import json
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.character_understanding_trial import UnderstandingDelivery
from dynamic_subject_agent.anchored_character_understanding import UNDERSTANDING_POLICY,REPLY_POLICY,validate_material,validate_understanding,reply_projection

REVIEW='2f28c4d192d14502157cae7532cebfee182a8eabf3be2b563982ab816e6cfa09'
VERSION='anchored-character-understanding-trial-m036-1'


def validate_trial(request):
    raw=(request.review_directory/'review.json').read_bytes()
    if sha256(raw).hexdigest()!=REVIEW:raise ValueError('exact M036 review required')
    review=json.loads(raw);approval=json.loads(request.approval_path.read_bytes())
    expected=dict(version=VERSION,review_sha256=REVIEW,human_confirmed=True,anchor_and_direct_reference_use_confirmed=True,
        maximum_requests=14,automatic_retries=0,persona_activation_included=False,installation_included=False,
        authorization_source='direct-user-reply:2026-10-31-current-chat')
    if (set(approval)!=set(expected)|{'user_reply'} or type(approval['user_reply']) is not str or not approval['user_reply'].strip()
            or canonical_json({k:approval[k] for k in expected})!=canonical_json(expected)):
        raise ValueError('exact current-anchor comparison approval required')
    if review['policies']!=dict(understanding=UNDERSTANDING_POLICY,reply=REPLY_POLICY):raise ValueError('reviewed policies changed')
    for name in ('source_file','anchor_source'):
        source=review[name]
        if sha256(Path(source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('source or reviewed anchor changed')
    materials={}
    for role,digest in review['material_sha256'].items():
        raw=(request.review_directory/(role+'.material.json')).read_bytes()
        if sha256(raw).hexdigest()!=digest:raise ValueError('anchored packet changed')
        materials[role]=json.loads(raw);validate_material(materials[role])
    for name,digest in review['example_sha256'].items():
        if sha256((request.review_directory/(name+'.UNSENT.json')).read_bytes()).hexdigest()!=digest:raise ValueError('preview changed')
    return review,materials


class AnchoredUnderstandingDelivery(UnderstandingDelivery):
    validate_inputs=staticmethod(validate_trial)
    decode_understanding=staticmethod(validate_understanding)
    project_reply=staticmethod(reply_projection)
    maximum_requests=14

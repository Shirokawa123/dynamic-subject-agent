"""One bounded recovery under the original fourteen-call authorization.

Never resend the first call or erase the original failed adjudication/stop.
Only unused cases from the original approved plan may execute.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json,os
from dynamic_subject_agent import anchored_understanding_trial as original
from dynamic_subject_agent.anchored_character_understanding import validate_understanding,propose_understanding,reply_from_understanding,understanding_coverage
from dynamic_subject_agent.character_understanding_trial import _run_cases
from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun,canonical_json,write_once

RECOVERY_REVIEW='c20b446e2eb7317b73a934c059aa6341a242d52a78c5e2c9ba5431ed8fc5b33d'
VERSION='anchored-understanding-format-recovery-m036-1'


def validate_recovery(request,review_path,audit_parent):
    review,materials=original.validate_trial(request)
    raw=review_path.read_bytes()
    if sha256(raw).hexdigest()!=RECOVERY_REVIEW:raise ValueError('exact format recovery review required')
    recovery=json.loads(raw)
    authority=recovery['authorization']
    if (authority.get('basis')!='original-M036-user-approval' or authority.get('new_user_approval_claimed') is not False
            or authority.get('approval_sha256')!=sha256(request.approval_path.read_bytes()).hexdigest()):
        raise ValueError('recovery must remain within the actual original approval')
    if (recovery['parent_review_sha256']!=original.REVIEW or request.output.resolve()!=Path(recovery['original_output']).resolve()
            or recovery['original_requests']!=1 or recovery['maximum_new_requests']!=13 or recovery['maximum_total_requests']!=14):
        raise ValueError('same original root and remaining thirteen only')
    for name,digest in recovery['retained_files_sha256'].items():
        if sha256((request.output/name).read_bytes()).hexdigest()!=digest:raise ValueError('retained first evidence changed')
    first_case=review['cases'][0]
    if first_case['id']!=recovery['first_case'] or first_case['purpose']!='understanding' or len(review['cases'])!=14:
        raise ValueError('exact first checkpoint required')
    first=json.loads((request.output/(first_case['id']+'.result.json')).read_bytes())
    stopped=json.loads((request.output/'results.json').read_bytes())
    if (first['status']!='failed-closed' or first['error_code']!='source-understanding-invalid'
            or first['finish_reason']!='stop' or stopped['attempts']!=1 or stopped['status']!='stopped'):
        raise ValueError('only completed first-response format adjudication is recoverable')
    material=materials[first_case['role']]
    expected_body=canonical_json(dict(review['parameters'],response_format=dict(type='json_object'),messages=[
        dict(role='system',content=review['policies']['understanding']),dict(role='user',content=canonical_json(material))])).encode()
    digest=sha256(expected_body).hexdigest()
    if first['request_sha256']!=digest or json.loads((request.output/(first_case['id']+'.request.json')).read_bytes())!=json.loads(expected_body):
        raise ValueError('first response belongs to another request')
    parent=audit_parent/original.REVIEW
    claims=list(parent.glob('*.attempt.json'));results=list(parent.glob('*.result.json'))
    if (len(claims)!=1 or len(results)!=1 or not (parent/'stopped.json').exists()
            or json.loads((parent/(digest+'.attempt.json')).read_bytes())['index']!=0
            or json.loads((parent/(digest+'.result.json')).read_bytes())!=first):
        raise ValueError('original global journal must retain exactly one attempt and result')
    understanding=validate_understanding(material,first['value'])
    if (understanding.status!='unreviewed-model-proposal'
            or sha256(understanding.raw_proposal_json.encode()).hexdigest()!=recovery['raw_proposal_sha256']
            or sha256(understanding.proposal_json.encode()).hexdigest()!=recovery['normalized_proposal_sha256']
            or list(understanding.normalizations)!=recovery['normalizations']):
        raise ValueError('only the reviewed lossless normalization may recover')
    return review,materials,understanding,parent


def resume_trial(request,recovery_review_path,*,_transport_factory=None,_audit_parent=None):
    if _audit_parent is not None and _transport_factory is None:raise ValueError('real journal cannot be redirected')
    audit=_audit_parent if _transport_factory is not None else Path(os.environ['LOCALAPPDATA'])/'DynamicSubjectAgent/anchored-understanding-m036'
    review,materials,understanding,parent=validate_recovery(request,recovery_review_path,audit)
    recovery_parent=parent/'format-recovery';recovery_parent.mkdir(exist_ok=True)
    journal=FrozenAttemptRun(recovery_parent,RECOVERY_REVIEW,approved=True)
    if journal.resumed:raise ValueError('recovery already started; no second continuation')
    # Cumulative index includes the one retained original call. The new epoch
    # writes only indices 1..13, leaving the original ledger byte-for-byte intact.
    journal.next=1
    class Delivery(original.AnchoredUnderstandingDelivery):
        def body(self,task,index):
            validate_recovery(request,recovery_review_path,audit)
            if index<1:raise ValueError('first call cannot be resent')
            return super().body(task,index)
    delivery=Delivery(request,journal,_transport_factory)
    role=review['cases'][0]['role'];delivery.understandings[role]=understanding
    try:
        write_once(request.output/(role+'.understanding.json'),asdict(understanding))
        write_once(request.output/(role+'.coverage.json'),understanding_coverage(materials[role],understanding))
        write_once(request.output/'format-recovery.json',dict(recovery_review_sha256=RECOVERY_REVIEW,retained_requests=1,
            authority='original-approved-M036-scope',original_approval_sha256=sha256(request.approval_path.read_bytes()).hexdigest(),
            first_request_resent=False,normalizations=list(understanding.normalizations)))
        result=_run_cases(request,review,materials,journal,delivery,propose_understanding,reply_from_understanding,understanding_coverage,
            start_at=1,understandings={role:understanding},rows=[dict(case=review['cases'][0]['id'],status='recovered-proposal',
                observations=len(understanding.observations),interpretations=len(understanding.interpretations),from_retained_response=True)],
            result_name='results.recovered.json')
        return result
    except Exception:
        journal.stop('recovery-failed');raise

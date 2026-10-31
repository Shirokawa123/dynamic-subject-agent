from hashlib import sha256
import json
import pytest
from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun,canonical_json,write_once
from dynamic_subject_agent import anchored_understanding_trial as original
from dynamic_subject_agent import anchored_understanding_recovery as recovery
from dynamic_subject_agent.anchored_character_understanding import validate_understanding
from test_anchored_understanding_trial import prepared,Transport
from test_anchored_character_understanding import proposal


@pytest.fixture
def retained(prepared,monkeypatch):
    request,audit=prepared;review,materials=original.validate_trial(request)
    request.output.mkdir();audit.mkdir()
    journal=FrozenAttemptRun(audit,original.REVIEW,approved=True)
    case=review['cases'][0];value=proposal();value['scene_readings'][0]['observation']['about']='甲'
    body=dict(review['parameters'],response_format=dict(type='json_object'),messages=[dict(role='system',content=review['policies']['understanding']),dict(role='user',content=canonical_json(materials[case['role']]))])
    digest=sha256(canonical_json(body).encode()).hexdigest();journal.claim(digest)
    row=dict(case=case['id'],purpose='understanding',request_sha256=digest,status='failed-closed',error_code='source-understanding-invalid',finish_reason='stop',value=value)
    journal.record(digest,row);journal.stop('source-understanding-invalid')
    write_once(request.output/(case['id']+'.request.json'),body);write_once(request.output/(case['id']+'.result.json'),row)
    write_once(request.output/'results.json',dict(status='stopped',attempts=1))
    u=validate_understanding(materials[case['role']],value)
    manifest=dict(parent_review_sha256=original.REVIEW,original_output=str(request.output),first_case=case['id'],original_requests=1,
        authorization=dict(basis='original-M036-user-approval',new_user_approval_claimed=False,approval_sha256=sha256(request.approval_path.read_bytes()).hexdigest()),
        maximum_new_requests=13,maximum_total_requests=14,retained_files_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in request.output.iterdir()},
        raw_proposal_sha256=sha256(u.raw_proposal_json.encode()).hexdigest(),normalized_proposal_sha256=sha256(u.proposal_json.encode()).hexdigest(),normalizations=list(u.normalizations))
    review_path=request.output.parent/'recovery-review.json';write_once(review_path,manifest)
    checksum=sha256(review_path.read_bytes()).hexdigest();monkeypatch.setattr(recovery,'RECOVERY_REVIEW',checksum)
    return request,audit,review_path



def test_only_thirteen_new_requests_and_original_failed_prefix_stays_intact(retained):
    request,audit,review=retained;t=Transport()
    before={p:sha256(p.read_bytes()).hexdigest() for p in request.output.iterdir()}
    parent=audit/original.REVIEW
    before.update({p:sha256(p.read_bytes()).hexdigest() for p in parent.iterdir() if p.is_file()})
    result=recovery.resume_trial(request,review,_transport_factory=lambda _:t,_audit_parent=audit)
    assert result['status']=='complete' and result['attempts']==14 and len(t.calls)==13
    assert result['rows'][0]['from_retained_response'] is True
    assert 'current_message' in t.calls[0]
    assert sum('current_message' not in p for p in t.calls)==1
    assert all(sha256(p.read_bytes()).hexdigest()==h for p,h in before.items())
    assert (request.output/'results.recovered.json').exists()
    with pytest.raises(ValueError,match='already started'):
        recovery.resume_trial(request,review,_transport_factory=lambda _:t,_audit_parent=audit)
    assert len(t.calls)==13


def test_changed_retained_model_result_cannot_be_recovered(retained):
    request,audit,review=retained;t=Transport()
    manifest=json.loads(review.read_bytes());path=request.output/(manifest['first_case']+'.result.json')
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='retained first evidence'):
        recovery.resume_trial(request,review,_transport_factory=lambda _:t,_audit_parent=audit)
    assert not t.calls


def test_recovery_permission_is_rechecked_at_final_delivery(retained,monkeypatch):
    request,audit,review=retained
    from dynamic_subject_agent import character_understanding_trial as sender
    monkeypatch.setattr(sender,'urlopen',lambda *a,**k:pytest.fail('network reached'))
    def factory(opener):
        def revoke(kwargs):
            from urllib.request import Request
            r=json.loads(request.approval_path.read_bytes());r['human_confirmed']=False
            request.approval_path.write_text(canonical_json(r),encoding='utf-8')
            opener(Request('https://api.deepseek.com/chat/completions',data=kwargs['body'],method='POST'),timeout=30)
        return Transport(callback=revoke)
    result=recovery.resume_trial(request,review,_transport_factory=factory,_audit_parent=audit)
    assert result['status']=='stopped' and result['attempts']==2

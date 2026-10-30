from dataclasses import replace
from hashlib import sha256
import json
import pytest
from dynamic_subject_agent.activity_reply_review import outbound_bytes, VERSION
from dynamic_subject_agent.activity_reply_review_trial import ActivityReviewTrialRequest, run_trial
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from test_activity_reply_review import payload


@pytest.fixture
def material(tmp_path,monkeypatch):
    root=tmp_path/'.artifacts';root.mkdir()
    review_dir=root/'review';review_dir.mkdir()
    source=root/'source';source.mkdir()
    preparation=root/'preparation.json';preparation.write_text('{}')
    (source/'results.json').write_text('{}')
    cases=[]
    for i in range(10):
        projection=payload();projection['current_message']=f'合成问题{i}'
        raw=outbound_bytes(projection);name=f'case-{i}'
        (review_dir/(name+'.request.json')).write_bytes(raw)
        cases.append(dict(id=name,request_sha256=sha256(raw).hexdigest()))
    digest=sha256(b'{}').hexdigest()
    review=dict(preparation_sha256=digest,source_summary_sha256=digest,source_file_sha256={},cases=cases)
    raw=canonical_json(review).encode();checksum=sha256(raw).hexdigest()
    (review_dir/'review.json').write_bytes(raw)
    import dynamic_subject_agent.activity_reply_review_trial as module
    monkeypatch.setattr(module,'REVIEW',checksum)
    receipt=root/'approval.json'
    receipt.write_text(canonical_json(dict(version=VERSION,review_sha256=checksum,human_confirmed=True,
        maximum_requests=10,automatic_retries=0,installation_included=False,user_data_upgrade_included=False,
        authorization_source='direct-user-reply:2026-10-30-current-chat',user_reply='合成批准')),
        encoding='utf-8')
    return ActivityReviewTrialRequest(review_dir,receipt,source,preparation,root/'result'),root/'audit'


class Transport(DeepSeekTransport):
    def __init__(self,bad=False,callback=None):self.calls=0;self.bad=bad;self.callback=callback
    def post_json(self,**kwargs):
        self.calls+=1
        if self.callback:self.callback(kwargs)
        value=dict(verdict='unsupported',issues=[dict(quote='不在候选中的伪造引文',kind='unsupported_event',basis_labels=[])]) if self.bad else dict(verdict='supported',issues=[])
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop',message=dict(role='assistant',content=canonical_json(value)))],
            usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))).encode())


def test_frozen_ten_reviews_no_generation_or_identity_and_no_second_root(material):
    request,audit=material;transport=Transport()
    before={p:sha256(p.read_bytes()).hexdigest() for p in request.source_directory.rglob('*') if p.is_file()}
    result=run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit)
    assert result['status']=='complete' and result['attempts']==transport.calls==10
    assert result['canonical_writes']==result['reply_generation_calls']==0
    assert not (request.output/'identity').exists()
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}
    with pytest.raises(ValueError,match='already started'):
        run_trial(replace(request,output=request.output.with_name('other')),_transport_factory=lambda _:transport,_audit_parent=audit)
    assert transport.calls==10


def test_unapproved_or_tampered_requests_stop_before_transport(material):
    request,audit=material;transport=Transport()
    path=request.review_directory/'case-0.request.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='exact frozen'):
        run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit)
    assert transport.calls==0 and not request.output.exists()


def test_invalid_review_stops_without_retry_or_returning_text(material):
    request,audit=material;transport=Transport(bad=True)
    result=run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit)
    assert result['status']=='stopped' and transport.calls==result['attempts']==1
    row=json.loads((request.output/'case-0.result.json').read_bytes())
    assert row['error_code']=='review-quote' and row['accepted_reply'] is None


def test_revocation_after_preparation_blocks_final_send(material,monkeypatch):
    request,audit=material
    import dynamic_subject_agent.activity_reply_review_trial as module
    monkeypatch.setattr(module,'urlopen',lambda *a,**k:pytest.fail('network reached'))
    def factory(opener):
        def revoke(kwargs):
            from urllib.request import Request
            receipt=json.loads(request.approval_path.read_bytes());receipt['human_confirmed']=False
            request.approval_path.write_text(canonical_json(receipt),encoding='utf-8')
            opener(Request('https://api.deepseek.com/chat/completions',data=kwargs['body'],method='POST'),timeout=30)
        return Transport(callback=revoke)
    result=run_trial(request,_transport_factory=factory,_audit_parent=audit)
    assert result['status']=='stopped' and result['attempts']==1

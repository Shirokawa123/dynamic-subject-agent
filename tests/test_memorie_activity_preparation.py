"""Exact unsent native use, metadata-only continuation and quote preview."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.memorie_activity_use import validate_review
from dynamic_subject_agent.memorie_activity_continuation import NativeActivityContinuationRequest
from dynamic_subject_agent.memorie_experience_preview import NativeExperiencePreviewRequest
from dynamic_subject_agent.memorie_companion_preparation import MemoriePreparationView
from dynamic_subject_agent.memorie_qualification_continuation import MemorieContinuationRequest, MemorieContinuationConsent
from dynamic_subject_agent.local_product import open_memorie_native_product
from test_memorie_native import native, Transport, command, send
from test_memorie_continuation import legacy, send_old, files


@pytest.fixture
def prepared():
    path=Path(os.environ.get('MEMORIE_NATIVE_QUALIFICATION','missing'))/'preparation.json'
    if not path.is_file(): pytest.skip('Explicit private Memorie definition required')
    return MemoriePreparationView(**json.loads(path.read_bytes()))


def test_native_use_exact_typed_fields_and_no_runtime_grant(prepared,monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    from dynamic_subject_agent.host import RuntimeHost
    monkeypatch.setattr(ModelGateway,'execute',lambda *_:pytest.fail('preparation executed a model'))
    monkeypatch.setattr(RuntimeHost,'open',lambda *a,**k:pytest.fail('use preview opened a Host'))
    old=ApplicationFacade.preview_memorie_native_message(prepared,{'kind':'character-click'},{'timer_phase':'idle'})
    view=ApplicationFacade.prepare_memorie_activity_use(prepared)
    assert view.status=='prepared' and not view.remote_authorized and not view.activation_supported
    assert validate_review(view.review_json)==view.review_basis
    review=json.loads(view.review_json); cases=json.loads(view.examples_json)
    assert len(cases)==7 and review['limits']['share_chars']==120
    click=json.loads(cases['idle_click']['messages'][1]['content'])
    assert set(click)==set(review['input_fields']['reply']) and click['interaction']=={'kind':'character-click'}
    for name in ('activity_choice','independent_choice','activity_share'):
        payload=json.loads(cases[name]['messages'][1]['content'])
        assert 'interaction' not in payload and 'exchange' not in payload and 'situation' not in payload
        assert cases[name]['response_format']==dict(type='json_object')
    assert 'background' not in canonical_json(cases)
    assert ApplicationFacade.preview_memorie_native_message(prepared,{'kind':'character-click'},{'timer_phase':'idle'})==old
    from dynamic_subject_agent.memorie_native import wire,NativeReplyProjection
    with pytest.raises(ValueError): wire(NativeReplyProjection(canonical_json(click)))
    tampered=json.loads(view.review_json);tampered['limits']['share_chars']=400
    with pytest.raises(ValueError):validate_review(canonical_json(tampered))


@pytest.mark.parametrize('kwargs',[
    dict(purpose='reply',interaction={'kind':'character-click','text':'伪造台词'},situation={'timer_phase':'idle'}),
    dict(purpose='reply',interaction={'kind':'character-click'},situation=None),
    dict(purpose='reply',interaction={'kind':'text','text':'合成。'},experience={'label':'E1','quote':'x'*401}),
    dict(purpose='choice',interaction={'kind':'text','text':'伪造新消息'}),
    dict(purpose='choice',phase='unknown'),dict(purpose='share'),
    dict(purpose='reply',interaction={'kind':'text','text':'合成。'},latest_share={'text':'x'*121}),
    dict(purpose='reply',interaction={'kind':'text','text':'合成。'},experience={'label':'E1','quote':'合成','scope_key':'forbidden'}),
    dict(purpose='choice',activity_result={'kind':'not-an-outline','plan':{}}),
])
def test_native_preview_rejects_extra_or_unbounded_sources(prepared,kwargs):
    with pytest.raises(ValueError):ApplicationFacade.preview_memorie_activity_message(prepared,**kwargs)


@pytest.fixture
def continued(legacy,prepared):
    opening,config,private,root=legacy
    p=opening();old=send_old(p,'合成旧原话：按问题分栏。','activity-source-1');p.close()
    predecessor=ApplicationFacade.prepare_memorie_continuation(MemorieContinuationRequest(config.state_path,config.product_parent,
        private/'native-approval.json',root/'continued-audit'))
    assert predecessor.status=='available'
    assert ApplicationFacade.apply_memorie_continuation(predecessor,MemorieContinuationConsent(predecessor.plan_digest,True)).status=='continued'
    model=Transport();p=open_memorie_native_product(config,approval_path=private/'native-approval.json',audit_path=root/'continued-audit',_transport=model)
    assert send(p,command(p),'preview-click-1').status=='terminal'
    assert send(p,command(p,{'kind':'text','text':'合成新原话：外观另列。'}),'preview-text-1').status=='terminal'
    scope=sha256((p.profile_id+':'+p.timeline_id).encode()).hexdigest()
    request=NativeActivityContinuationRequest(predecessor,ApplicationFacade.prepare_memorie_activity_use(prepared).review_json,scope)
    yield p,model,config,root,request,old
    p.close()


def test_active_source_proof_preserves_original_requests_without_writes(continued):
    p,model,config,root,request,old=continued
    before=files(root);calls=len(model.calls)
    result=ApplicationFacade.prepare_memorie_activity_continuation(replace(request,expected_owner_pid=os.getpid()))
    assert result.status=='prepared',result
    assert result.publication_prefix_verified and not result.cold_source_observed and not result.apply_supported
    body=json.loads(result.proposal_json)
    assert [row['head_sequence'] for row in body['original_request_proofs']]==[1,2,3]
    assert body['original_request_proofs'][0]['payload_fingerprint']==old.payload_fingerprint
    assert '合成旧原话' not in result.proposal_json and '合成新原话' not in result.proposal_json
    assert body['activation']['old_nonce_redelivery'] is False
    assert body['activation']['copy_development_timeline'] is False
    assert files(root)==before and len(model.calls)==calls
    assert ApplicationFacade.apply_memorie_continuation(result,MemorieContinuationConsent(result.proposal_digest,True)).status=='unavailable'


def test_cold_blueprint_is_still_not_an_executable_upgrade(continued):
    p,model,config,root,request,_=continued;p.close()
    before=files(root)
    result=ApplicationFacade.prepare_memorie_activity_continuation(request)
    assert result.status=='prepared' and result.cold_source_observed and result.apply_supported is False
    assert json.loads(result.proposal_json)['status']=='blueprint-not-executable'
    assert files(root)==before
    assert ApplicationFacade.prepare_memorie_activity_continuation(replace(request,expected_scope='f'*64)).status=='unavailable'


def test_source_advancing_during_prepare_cannot_freeze_a_stale_proposal(continued,monkeypatch):
    p,model,config,root,request,_=continued
    import dynamic_subject_agent.memorie_continuation as observation
    inspect=observation.inspect_memorie_source;calls=[]
    def advancing(value):
        result=inspect(value);calls.append(result)
        if len(calls)==1:
            assert send(p,command(p,{'kind':'text','text':'合成的新交流，不重跑旧终态。'}),'advance-during-review-1').status=='terminal'
        return result
    monkeypatch.setattr(observation,'inspect_memorie_source',advancing)
    result=ApplicationFacade.prepare_memorie_activity_continuation(request)
    assert result.status=='unavailable' and not result.proposal_json
    assert len(p.application.query_memorie_interactions().turns)==4


def test_native_selection_preview_distinguishes_user_text_click_and_assistant(continued):
    p,model,config,root,_,_=continued;before=files(root);calls=len(model.calls)
    request=NativeExperiencePreviewRequest(p.profile_id,p.timeline_id,1,'按问题分栏',True)
    selected=p.application.preview_memorie_experience_selection(request)
    assert selected.status=='previewed' and not selected.can_apply and not selected.canonical_eligibility_verified
    assert json.loads(selected.preview_json)['quote']=='按问题分栏'
    assert p.application.preview_memorie_experience_selection(replace(request,source_head_sequence=2)).status=='unavailable'
    assert p.application.preview_memorie_experience_selection(replace(request,source_head_sequence=3,quote='合成短回应')).status=='unavailable'
    assert p.application.preview_memorie_experience_selection(replace(request,target_profile_id=str(uuid4()))).status=='unavailable'
    assert p.application.preview_memorie_experience_selection(replace(request,confirmed=False)).status=='cancelled'
    assert p.application.preview_memorie_experience_selection(replace(request,quote='x'*401)).status=='unavailable'
    assert p.application.query_shared_activity().status=='unavailable'
    assert files(root)==before and len(model.calls)==calls
    assert p.application.set_reviewed_character_history(False).history_enabled is False
    assert p.application.preview_memorie_experience_selection(request).status=='unavailable'

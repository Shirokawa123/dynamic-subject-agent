import json
from dataclasses import asdict
import pytest
from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_natural_feedback_live import feedback_live_fixture,state
from test_natural_feedback_multispan import multispan_fixture,MultispanTransport,PLAN,MESSAGE,recorded_edits
from test_shared_activity import step_request,select
from dynamic_subject_agent.local_product import open_natural_feedback_product_live,validate_natural_feedback_entry
from dynamic_subject_agent.natural_feedback_choice_budget import NaturalFeedbackChoiceBudgetGrant,CHOICE_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW,open_natural_feedback_audit
from dynamic_subject_agent.natural_feedback_remote_preview import natural_feedback_remote_request_preview
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json

def options(opts,variant):
    return dict(opts,grant=NaturalFeedbackChoiceBudgetGrant(APPROVED_FEEDBACK_REVIEW,CHOICE_DEVELOPMENT,variant),
        audit_path=opts['audit_path'].with_name(variant+'-audit'))

@pytest.mark.parametrize('variant',['choice-low','choice-final'])
def test_only_choice_mode_changes_while_feedback_and_original_budget_are_exact(multispan_fixture,variant):
    _,config,opts=multispan_fixture
    with open_natural_feedback_product_live(config,**options(opts,variant),_transport=MultispanTransport()) as p:
        task=ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE,p.application.preview_shared_activity_step().view)
        old=natural_feedback_remote_request_preview(task,technical_variant='multi-span')['body']
        new=natural_feedback_remote_request_preview(task,technical_variant=variant)['body']
        expected=dict(old)
        if variant=='choice-low':expected['reasoning_effort']='low'
        else:expected['thinking']={'type':'disabled'};expected.pop('reasoning_effort')
        assert new==expected and new['messages']==old['messages'] and new['max_tokens']==4096
        feedback=ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,p.application.preview_natural_feedback('合成当前问题。').view)
        assert natural_feedback_remote_request_preview(feedback,technical_variant=variant)['body']==natural_feedback_remote_request_preview(feedback,technical_variant='multi-span')['body']

@pytest.mark.parametrize('variant',['choice-low','choice-final'])
def test_candidate_facade_keeps_complete_long_frame_reopen_and_privacy_receipt(multispan_fixture,variant):
    _,config,opts=multispan_fixture;t=MultispanTransport();o=options(opts,variant)
    p=open_natural_feedback_product_live(config,**o,_transport=t)
    try:
        assert send(p,'空间暂叫青台。','s157-source').status=='terminal' and select(p,'空间暂叫青台。').status=='committed'
        result=p.application.advance_shared_activity(step_request(p,'s157-start-first-activity'))
        assert result.status=='committed',result
        assert send(p,MESSAGE,'s157-frame').status=='terminal'
        assert asdict(state(p)['current_plan'])=={f:x.replace('青台','禾台') for f,x in PLAN.items()}
        edits=recorded_edits(p);assert len(edits)==4 and sum(e['field']=='composition' for e in edits)==2
        for i in range(3):assert send(p,'合成普通话题'+str(i),'s157-topic-'+str(i)).status=='terminal'
        saved=history(p);ids=p.profile_id,p.timeline_id;p.close();fresh=MultispanTransport()
        p=open_natural_feedback_product_live(config,**o,_transport=fresh)
        assert not fresh.calls and history(p)==saved and (p.profile_id,p.timeline_id)==ids
        validate_natural_feedback_entry(config,profile_id=p.profile_id,timeline_id=p.timeline_id,technical_variant=variant)
        with pytest.raises(RuntimeError):validate_natural_feedback_entry(config,profile_id=p.profile_id,timeline_id=p.timeline_id)
        assert p.application.advance_shared_activity(step_request(p,'s157-after-gap-first-activity')).status=='committed'
        assert state(p)['activity_revision']==3 and '禾台' in state(p)['current_plan'].composition
        assert p.application.set_reviewed_character_history(False).status=='active'
        preview=p.application.preview_shared_activity_step().view['payload']
        assert preview['current_feedback'] is None and preview['current_plan'] is None
    finally:p.close()

@pytest.mark.parametrize('variant',['choice-low','choice-final'])
def test_choice_length_still_unpublished_and_original_nonce_never_retries(multispan_fixture,variant):
    _,config,opts=multispan_fixture
    class Length(MultispanTransport):
        def post_json(self,**kwargs):
            self.calls.append(json.loads(kwargs['body']))
            return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='length',message=dict(content=''))],
                usage=dict(prompt_tokens=100,completion_tokens=4096,total_tokens=4196))).encode())
    t=Length();o=options(opts,variant)
    with open_natural_feedback_product_live(config,**o,_transport=t) as p:
        request=step_request(p,'s157-first-length')
        assert p.application.advance_shared_activity(request).status=='failed-closed'
        assert p.application.advance_shared_activity(request).status=='failed-closed'
        assert len(t.calls)==1 and not history(p)
    rows=open_natural_feedback_audit(o['audit_path'],technical_variant=variant).snapshot()
    assert len(rows)==1 and rows[0]['status']=='failed-closed'

@pytest.mark.parametrize('variant',['choice-low','choice-final'])
def test_existing_multispan_qualification_is_not_upgraded(multispan_fixture,variant):
    opening,config,opts=multispan_fixture;p=opening();p.close();before=config.state_path.read_bytes()
    with pytest.raises(RuntimeError):open_natural_feedback_product_live(config,**options(opts,variant),_transport=MultispanTransport())
    assert config.state_path.read_bytes()==before and not options(opts,variant)['audit_path'].exists()

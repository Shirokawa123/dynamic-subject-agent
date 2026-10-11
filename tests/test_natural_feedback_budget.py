import json
from copy import deepcopy
from dataclasses import asdict
import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_natural_feedback_live import feedback_live_fixture,FeedbackTransport,state
from test_shared_activity import step_request
from dynamic_subject_agent.natural_feedback_budget import NaturalFeedbackBudgetDevelopmentGrant,BUDGET_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW,open_natural_feedback_audit
from dynamic_subject_agent.local_product import open_natural_feedback_product_live
from dynamic_subject_agent.natural_feedback_remote_preview import natural_feedback_remote_request_preview
from dynamic_subject_agent.natural_feedback_output_metadata import output_metadata
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse,_diagnostic_json_reply_content,DeepSeekResponseDiagnosticFailure
from dynamic_subject_agent.frozen_attempt import canonical_json


class BudgetTransport(FeedbackTransport):
    def __init__(self,force_length=False):super().__init__();self.force_length=force_length
    def post_json(self,**kwargs):
        body=json.loads(kwargs['body'])
        if body['thinking']['type']=='enabled' and 'current_activity' not in json.loads(body['messages'][1]['content']) or self.force_length:
            self.calls.append(body)
            return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='length',
                message=dict(role='assistant',content='',reasoning_content='SYNTHETIC_HIDDEN_NEVER_LOG'))],
                usage=dict(prompt_tokens=100,completion_tokens=4096,total_tokens=4196,completion_tokens_details=dict(reasoning_tokens=4096)))).encode())
        response=super().post_json(**kwargs)
        value=json.loads(response.body);value['usage']['completion_tokens_details']=dict(reasoning_tokens=0)
        return DeepSeekHttpResponse(200,canonical_json(value).encode())


def budget_options(options):
    return dict(options,grant=NaturalFeedbackBudgetDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,BUDGET_DEVELOPMENT),
        audit_path=options['audit_path'].with_name('direct-final-audit'))


def test_original_truncated_final_pattern_still_fails_before_json_decode():
    final=''
    # Public deterministic fixture for the observed pattern. The original
    # private saved fields are inspected separately, not a test dependency.
    rebuilt=DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='length',
        message=dict(role='assistant',content=final))],usage=dict(prompt_tokens=2697,completion_tokens=4096,total_tokens=6793))).encode())
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as error:
        _diagnostic_json_reply_content(rebuilt,max_output_tokens=4096,discard_reasoning=True,require_complete=True)
    assert error.value.diagnostic_code=='response-truncated' and final==''


def test_baseline_budget_exhaustion_is_uncommitted_and_metadata_not_reasoning(feedback_live_fixture):
    opening,_,options,_=feedback_live_fixture;transport=BudgetTransport();observations=[]
    product=opening(transport,observations)
    result=send(product,'新的合成普通消息。','budget-baseline')
    assert result.status=='failed-closed' and result.projection.failure_code=='original-whole-response-truncated'
    assert not history(product) and len(transport.calls)==1
    assert observations[-1]['reasoning_tokens']==4096 and observations[-1]['final_chars']==0
    assert 'SYNTHETIC_HIDDEN' not in canonical_json(observations)


def test_direct_final_same_payload_and_limit_avoids_simulated_thinking_exhaustion(feedback_live_fixture):
    _,config,options,_=feedback_live_fixture;transport=BudgetTransport();observations=[]
    with open_natural_feedback_product_live(config,**budget_options(options),_transport=transport,observations=observations) as product:
        preview=product.application.preview_natural_feedback('新的合成普通消息。');assert preview.status=='previewed'
        task=ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,preview.view)
        old=natural_feedback_remote_request_preview(task)['body'];new=natural_feedback_remote_request_preview(task,technical_variant='direct-final')['body']
        assert old['messages']==new['messages'] and old['max_tokens']==new['max_tokens']==4096
        expected=dict(old,thinking={'type':'disabled'});expected.pop('reasoning_effort')
        assert new==expected
        assert send(product,'新的合成普通消息。','budget-direct').status=='terminal'
        assert transport.calls[-1]==new and observations[-1]['reasoning_tokens']==0 and observations[-1]['final_chars']>0
        assert len(history(product))==1 and len(transport.calls)==1
        assert product.application.advance_shared_activity(step_request(product,'budget-choice-original-high')).status=='committed'
        assert transport.calls[-1]['thinking']=={'type':'enabled'} and transport.calls[-1]['reasoning_effort']=='high'


def test_direct_final_does_not_accept_real_truncation_or_retry(feedback_live_fixture):
    _,config,options,_=feedback_live_fixture;transport=BudgetTransport(force_length=True)
    with open_natural_feedback_product_live(config,**budget_options(options),_transport=transport) as product:
        assert send(product,'新合成故障。','budget-failed').status=='failed-closed'
        assert send(product,'新合成故障。','budget-failed').status=='failed-closed'
        assert len(transport.calls)==1 and not history(product)
    rows=open_natural_feedback_audit(budget_options(options)['audit_path'],technical_variant='direct-final').snapshot()
    assert len(rows)==1 and rows[0]['status']=='failed-closed'


def test_new_contract_cannot_upgrade_existing_baseline_root(feedback_live_fixture):
    opening,config,options,_=feedback_live_fixture
    product=opening();product.close();before=config.state_path.read_bytes()
    with pytest.raises(RuntimeError):open_natural_feedback_product_live(config,**budget_options(options),_transport=BudgetTransport())
    assert config.state_path.read_bytes()==before and not budget_options(options)['audit_path'].exists()


@pytest.mark.parametrize('tokens',[None,-1,21,True])
def test_unavailable_or_invalid_reasoning_usage_is_not_fabricated(tokens):
    response=DeepSeekHttpResponse(200,canonical_json(dict(choices=[dict(finish_reason='stop',message=dict(content='final'))],
        usage=dict(completion_tokens=20,completion_tokens_details=dict(reasoning_tokens=tokens)))).encode())
    value=output_metadata(response)
    assert value['reasoning_tokens'] is None and value['final_chars']==5

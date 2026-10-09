"""Pure control/boundary verification for the main-owned first LIVE helper."""
import importlib.util
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper():
    path=Path(__file__).resolve().parents[1]/'scripts/run_s146_live_acceptance.py'
    spec=importlib.util.spec_from_file_location('s146_live_helper_fixture',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_cli_does_not_construct_resources_or_runtime(helper,monkeypatch,tmp_path,capsys):
    root=tmp_path/'unused-first-resource'
    monkeypatch.setattr(helper,'preflight',lambda:({},root,'0'*64))
    def forbidden(*_args,**_kwargs):
        raise AssertionError('preflight constructed runtime')
    monkeypatch.setattr(helper,'FirstRun',forbidden)
    monkeypatch.setattr(helper,'SafeReport',forbidden)
    assert helper.main(['--preflight'])==0
    assert not root.exists()
    meta=json.loads(capsys.readouterr().out)
    assert meta['product_roots_created']==meta['remote_calls']==meta['credential_reads']==0
    assert meta['product_opened'] is False and meta['transport_created'] is False


@pytest.mark.parametrize('line,expected',[
    ('','canonical-semantic-review-eof'),
    ('{"statement_sha256":"wrong","decision":"continue"}','canonical-semantic-review-token-invalid'),
    ('{"statement_sha256":"%s","decision":"unknown"}','canonical-semantic-review-token-invalid'),
    ('{"statement_sha256":"%s","decision":"stop-out-of-scope"}','canonical-working-understanding-out-of-scope'),
])
def test_semantic_gate_stops_with_no_following_operation(helper,monkeypatch,line,expected,capsys):
    statement='合成限定认识。'; checksum=helper.text_sha(statement)
    line=line % checksum if '%s' in line else line
    report=SimpleNamespace(data={'semantic_reviews':[]},checked_save=lambda _code:None,save=lambda:True)
    run=object.__new__(helper.FirstRun)
    run.report=report; run.view=lambda:{'current_plan':None}
    monkeypatch.setattr(helper.sys,'stdin',StringIO(line))
    with pytest.raises(helper.AcceptanceStopped) as error:
        run.semantic_gate('form-fixture',{'statement':statement},4)
    assert error.value.code==expected
    assert report.data['semantic_reviews'][0]['status']=='stopped'
    assert statement not in capsys.readouterr().out


@pytest.mark.parametrize('failure',[RuntimeError('PRIVATE_EXCEPTION_BODY'), 'normal'])
def test_first_stop_aborts_fixed_scene_without_rescue(helper,failure):
    calls=[]
    class Run:
        def reply(self,label,text,**_kwargs):
            calls.append(label)
            if len(calls)==2:
                if failure=='normal': raise helper.NormalEnd('fixture-noop')
                raise failure
            return 1
        def choice(self,*_args,**_kwargs):
            raise AssertionError('choice after first stop')
    scene={'source_messages':['fixture-one','fixture-two']}
    with pytest.raises(helper.NormalEnd if failure=='normal' else RuntimeError):
        helper.execute_scene(Run(),scene)
    assert calls==['source-reply-1','source-reply-2']


def test_form_insufficient_is_normal_noop_without_semantic_gate(helper):
    from dynamic_subject_agent.shared_activity import SharedActivityResponse
    run=object.__new__(helper.FirstRun)
    before={'revision':2,'understanding':None}
    after={'revision':3,'understanding':None,'formation_status':'insufficient'}
    views=iter((before,after)); run.view=lambda:next(views)
    preview={'policy':'fixture','payload':{'exchanges':[{'label':'U1','quote':'first'},{'label':'U2','quote':'second'}],'activity_result':None}}
    run.product=SimpleNamespace(profile_id='fixture-profile',timeline_id='fixture-timeline',application=SimpleNamespace(
        preview_working_understanding=lambda _request:SharedActivityResponse('previewed',view=preview)))
    row={}; saved=[]
    run.report=SimpleNamespace(checked_save=lambda code:saved.append(code))
    run.model_stage=lambda *_args:(SharedActivityResponse('no-op',problem_code='working-understanding-insufficient'),row,{'formation_status':'insufficient'})
    def forbidden(*_args): raise AssertionError('insufficient opened semantic gate')
    run.semantic_gate=forbidden
    with pytest.raises(helper.NormalEnd) as error:
        run.form('insufficient-fixture',[(1,'first'),(2,'second')])
    assert error.value.code=='working-understanding-insufficient'
    assert row['typed_insufficient_noop'] is True


@pytest.mark.parametrize('status',['unavailable','unknown','failed-closed','busy'])
def test_model_failure_status_retained_and_stage_does_not_retry(helper,status):
    run=object.__new__(helper.FirstRun); attempted=[]; stages=[]
    class Report:
        io_error_types=[]
        data={'transport':[]}
        def begin(self,label,**metadata):
            row={'stage':label,'status':'started',**metadata}; stages.append(row); return row
        def checked_save(self,_code): pass
        def save(self): return True
    run.report=Report(); run.observations=[]; run.counts=lambda:0; run.audit=lambda:[]
    run.transport=SimpleNamespace(total_calls=0,arm=lambda *_args:{},disarm=lambda:None)
    def operation():
        attempted.append(True)
        return SimpleNamespace(status=status)
    with pytest.raises(helper.AcceptanceStopped) as error:
        run.model_stage('first-fixture',helper.PURPOSES[0],{},operation)
    assert error.value.code=='first-technical-failure-'+status
    assert attempted==[True] and stages[0]['status']==status


def test_metadata_retains_first_failure_without_exception_body(helper,tmp_path):
    report=helper.SafeReport(tmp_path,'0'*64)
    report.begin('first-fixture',maximum_requests=1)
    report.stop(RuntimeError('PRIVATE_BODY_OR_CREDENTIAL_SENTINEL'))
    first=dict(report.data['first_failure'])
    report.stop(helper.AcceptanceStopped('final-product-close-unverified'))
    assert report.data['first_failure']==first
    body=(tmp_path/'metadata.json').read_text(encoding='utf-8')
    assert 'PRIVATE_BODY_OR_CREDENTIAL_SENTINEL' not in body
    assert report.data['first_failure']['error_type']=='RuntimeError'


def test_response_boundary_discards_final_and_reasoning_text(helper):
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
    content='PRIVATE_SYNTHETIC_FINAL'; reasoning='PRIVATE_SYNTHETIC_REASONING'
    response=DeepSeekHttpResponse(200,json.dumps(dict(model='deepseek-flash',usage=dict(prompt_tokens=1,completion_tokens=2),
        choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content,reasoning_content=reasoning))])).encode())
    boundary=helper.final_boundary(response,helper.PURPOSES[2],{})
    assert boundary['exact_output_contract'] is True
    assert boundary['reply_sha256']==helper.text_sha(content)
    assert content not in json.dumps(boundary) and reasoning not in json.dumps(boundary)
    duplicate=DeepSeekHttpResponse(200,b'{"choices":[],"choices":[]}')
    assert helper.final_boundary(duplicate,helper.PURPOSES[2],{})['exact_output_contract'] is False


def test_stale_working_support_cannot_pass_actual_choice_projection(helper):
    run=object.__new__(helper.FirstRun)
    view={'visible_understanding':None,'current_plan':None}
    preview={'payload':{'shared_experience':None,'working_understanding':None,'current_plan':None}}
    run.verify_support(preview,helper.PURPOSES[1],view)
    preview['payload']['working_understanding']={'statement':'PRIVATE_STALE_UNDERSTANDING'}
    with pytest.raises(helper.AcceptanceStopped) as error:
        run.verify_support(preview,helper.PURPOSES[1],view)
    assert error.value.code=='preview-working-support-differs-from-current-canonical-closure'


def test_self_check_is_pure(helper):
    value=helper.self_check()
    assert value['semantic_gate_rejections']==4 and value['private_text_exported'] is False
    assert value['product_roots_created']==value['remote_calls']==value['credential_reads']==0

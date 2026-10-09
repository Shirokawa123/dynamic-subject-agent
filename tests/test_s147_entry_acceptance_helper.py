"""Pure stopping and privacy fixtures for the main-owned S147 pilot helper."""
import importlib.util
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[1]/'scripts/run_s147_entry_acceptance.py'
    spec = importlib.util.spec_from_file_location('s147_entry_helper_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_self_check_and_preflight_never_construct_runtime_or_server(helper,monkeypatch,tmp_path,capsys):
    assert helper.self_check()['temporary_server_created'] is False
    root = tmp_path/'unused-first-root'
    monkeypatch.setattr(helper,'preflight',lambda:({},root,'0'*64))
    def forbidden(*_args,**_kwargs):
        raise AssertionError('pure mode constructed runtime')
    monkeypatch.setattr(helper,'FirstRun',forbidden)
    monkeypatch.setattr(helper,'SafeReport',forbidden)
    assert helper.main(['--preflight']) == 0
    assert not root.exists()
    meta = json.loads(capsys.readouterr().out)
    assert meta['product_roots_created'] == meta['remote_calls'] == meta['credential_reads'] == 0
    assert meta['product_opened'] is meta['transport_created'] is meta['temporary_server_created'] is False


def test_frozen_scene_matches_pin_and_rejects_unbounded_or_reordered_work(helper):
    scene = json.loads(helper.SCENE_PATH.read_text(encoding='utf-8'))
    assert helper.validate_scene(scene) is scene
    assert helper.digest(scene) == helper.SCENE_SHA
    assert scene['order'] == helper.SCENE_ORDER and len(scene['gap_messages']) == 2
    assert scene['maximum_first_requests'] == 8
    for key,value in [('maximum_first_requests',9),('automatic_retries',1),('production_service_started',True)]:
        changed = dict(scene,**{key:value})
        with pytest.raises(helper.AcceptanceStopped): helper.validate_scene(changed)
    changed = dict(scene,order=list(reversed(scene['order'])))
    with pytest.raises(helper.AcceptanceStopped): helper.validate_scene(changed)


@pytest.mark.parametrize('line,expected',[
    ('','canonical-semantic-review-eof'),
    ('{"statement_sha256":"wrong","decision":"continue"}','canonical-semantic-review-token-invalid'),
    ('{"statement_sha256":"%s","decision":"unknown"}','canonical-semantic-review-token-invalid'),
    ('{"statement_sha256":"%s","decision":"stop-out-of-scope"}','canonical-working-understanding-out-of-scope'),
])
def test_semantic_gate_retains_stop_and_never_exports_statement(helper,monkeypatch,line,expected,capsys):
    statement = '合成限定认识。'; checksum = helper.text_sha(statement)
    line = line % checksum if '%s' in line else line
    run = object.__new__(helper.FirstRun)
    run.report = SimpleNamespace(data={'semantic_reviews':[]},checked_save=lambda _code:None,save=lambda:True)
    run.view = lambda:{'current_plan':None}
    monkeypatch.setattr(helper.sys,'stdin',StringIO(line))
    with pytest.raises(helper.AcceptanceStopped) as error:
        run.semantic_gate('form-fixture',{'statement':statement},4)
    assert error.value.code == expected
    assert run.report.data['semantic_reviews'][0]['status'] == 'stopped'
    assert statement not in capsys.readouterr().out


@pytest.mark.parametrize('status',['unavailable','unknown','failed-closed','busy'])
def test_first_http_typed_failure_ends_without_retry(helper,status):
    run = object.__new__(helper.FirstRun); attempts=[]; stages=[]
    class Report:
        io_error_types=[]
        data={'transport':[]}
        def begin(self,label,**metadata):
            row=dict(stage=label,status='started',**metadata); stages.append(row); return row
        def checked_save(self,_code): pass
        def save(self): return True
    run.report=Report(); run.observations=[]; run.counts=lambda:0; run.audit=lambda:[]
    run.transport=SimpleNamespace(total_calls=0,arm=lambda *_args:{},disarm=lambda:None)
    def operation():
        attempts.append(True)
        return dict(status=status,ok=False)
    with pytest.raises(helper.AcceptanceStopped) as error:
        run.model_stage('first-fixture',helper.PURPOSES[0],{},operation)
    assert error.value.code == 'first-technical-failure-'+status
    assert attempts == [True] and stages[0]['status'] == status


@pytest.mark.parametrize('failure',[RuntimeError('PRIVATE_EXCEPTION_BODY'),'normal'])
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
    with pytest.raises(helper.NormalEnd if failure=='normal' else RuntimeError):
        helper.execute_scene(Run(),{'source_messages':['fixture-one','fixture-two']})
    assert calls == ['source-reply-1','source-reply-2']


def test_form_insufficient_stops_before_semantic_review_and_later_choice(helper):
    from dynamic_subject_agent.shared_activity import SharedActivityResponse
    run=object.__new__(helper.FirstRun)
    views=iter(({'revision':2,'understanding':None},
        {'revision':3,'understanding':None,'formation_status':'insufficient'}))
    run.view=lambda:next(views)
    preview={'policy':'fixture','payload':{'scope':'composition-text',
        'exchanges':[{'label':'U1','quote':'first'},{'label':'U2','quote':'second'}],'activity_result':None}}
    run.entry=SimpleNamespace(product=SimpleNamespace(profile_id='fixture-profile',timeline_id='fixture-timeline',
        application=SimpleNamespace(preview_working_understanding=lambda _request:SharedActivityResponse('previewed',view=preview))))
    row={}; run.report=SimpleNamespace(checked_save=lambda _code:None)
    run.model_stage=lambda *_args:({'status':'no-op','shared_problem_code':'working-understanding-insufficient'},row,{'formation_status':'insufficient'})
    def zero(label,_action):
        if label=='select-two-committed-http-sources-zero-model':
            return {'ok':True,'archive':{'rows':[{'head_sequence':1,'user_text':'first'},{'head_sequence':2,'user_text':'second'}]}}
        return {'ok':True,'working_preview':preview['payload']}
    run.zero=zero
    run.semantic_gate=lambda *_args:pytest.fail('insufficient opened gate')
    with pytest.raises(helper.NormalEnd) as error:
        run.form('fixture',[(1,'first'),(2,'second')])
    assert error.value.code == 'working-understanding-insufficient' and row['typed_insufficient_noop'] is True


def test_response_boundary_and_first_failure_metadata_never_export_private_text(helper,tmp_path):
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
    content='PRIVATE_SYNTHETIC_FINAL'; reasoning='PRIVATE_SYNTHETIC_REASONING'
    response=DeepSeekHttpResponse(200,json.dumps(dict(model='deepseek-flash',usage=dict(prompt_tokens=1,completion_tokens=2),
        choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content,reasoning_content=reasoning))])).encode())
    boundary=helper.final_boundary(response,helper.PURPOSES[2],{})
    assert boundary['exact_output_contract'] is True and boundary['reply_sha256']==helper.text_sha(content)
    assert content not in json.dumps(boundary) and reasoning not in json.dumps(boundary)
    assert helper.final_boundary(DeepSeekHttpResponse(200,b'{"choices":[],"choices":[]}'),helper.PURPOSES[2],{})['exact_output_contract'] is False
    report=helper.SafeReport(tmp_path,'0'*64)
    report.begin('first-fixture',maximum_requests=1)
    report.stop(RuntimeError(content))
    first=dict(report.data['first_failure'])
    report.stop(helper.AcceptanceStopped('final-entry-or-server-close-unverified'))
    assert report.data['first_failure']==first
    assert content not in (tmp_path/'metadata.json').read_text(encoding='utf-8')


def test_original_nonce_query_cannot_resubmit_or_change_canonical_state(helper):
    run=object.__new__(helper.FirstRun); calls=[]
    run.fingerprint=lambda:'canonical-stable'
    run.verify_http_state=lambda state:None
    run.zero=lambda _label,action:action()
    def http(route,payload):
        calls.append((route,payload))
        return {'shared_status':'replayed','state':{}}
    run.http=http
    request={'request_id':'original-nonce','expected_revision':7}
    run.nonce(request)
    assert calls==[('/working-understanding-request',{'kind':'advance','request':request})]


def test_successful_async_replayed_result_requires_this_stage_single_audited_request(helper):
    run=object.__new__(helper.FirstRun); count=[0]; preview={'policy':'fixture','payload':{}}
    raw={'exact_output_contract':True,'final_value_sha256':'1'*64}
    row={}
    run.report=SimpleNamespace(io_error_types=[],data={'transport':[]},
        begin=lambda _label,**metadata:row.update(metadata) or row,checked_save=lambda _code:None,save=lambda:True)
    run.transport=SimpleNamespace(total_calls=0,arm=lambda *_args:{},disarm=lambda:None)
    run.observations=[];run.counts=lambda:count[0]
    audit={'status':'complete','purpose':helper.PURPOSES[1],
        'request_digest':helper.digest(preview),'output_digest':raw['final_value_sha256']}
    run.audit=lambda:[audit]
    run.verify_http_state=lambda _state:None
    def operation():
        count[0]=run.transport.total_calls=1
        run.report.data['transport'].append({'response_boundary':raw})
        return {'status':'replayed','ok':True,'state':{}}
    result,stage,_raw=run.model_stage('fixture',helper.PURPOSES[1],preview,operation)
    assert result['status']=='replayed' and stage['raw_http_matches_completed_audit'] is True


def test_inflight_disarm_keeps_received_response_and_boundary_without_new_admission(helper):
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
    body=b'synthetic-exact-request'
    content='PRIVATE_SYNTHETIC_FINAL';reasoning='PRIVATE_SYNTHETIC_REASONING'
    response=DeepSeekHttpResponse(200,json.dumps(dict(model='deepseek-flash',usage=dict(prompt_tokens=1,completion_tokens=2),
        choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content,reasoning_content=reasoning))])).encode())
    transport=object.__new__(helper.ObservedTransport)
    transport.report=SimpleNamespace(io_error_types=[],data={'transport':[]},checked_save=lambda _code:None,save=lambda:True)
    transport.expected={'purpose':helper.PURPOSES[2],'endpoint':'https://api.deepseek.com/chat/completions',
        'wire_sha256':helper.sha256(body).hexdigest(),'preview':{'policy':'synthetic','payload':{}}}
    transport.active_stage='inflight-fixture';transport.stage_calls=transport.total_calls=0
    attempts=[]
    def received_then_disarmed(**_kwargs):
        attempts.append(True)
        # Model-stage cleanup can revoke the armed request while the delegate
        # still holds its already received response. No thread or socket is
        # needed to exercise this ordering deterministically.
        transport.disarm()
        return response
    transport.delegate=SimpleNamespace(post_json=received_then_disarmed)
    kwargs={'endpoint':transport.expected['endpoint'],'timeout_seconds':30,'body':body}
    assert transport.post_json(**kwargs) is response
    row=transport.report.data['transport'][0]
    assert row['stage']=='inflight-fixture' and row['status']=='response-received' and row['error_type'] is None
    assert row['response_boundary']['exact_output_contract'] is True
    assert row['response_boundary']['reply_sha256']==helper.text_sha(content)
    assert row['response_boundary']['response_body_sha256']==helper.sha256(response.body).hexdigest()
    assert content not in json.dumps(row) and reasoning not in json.dumps(row) and 'preview' not in row
    with pytest.raises(helper.AcceptanceStopped) as error:
        transport.post_json(**kwargs)
    assert error.value.code=='extra-or-unarmed-transport-request' and attempts==[True]

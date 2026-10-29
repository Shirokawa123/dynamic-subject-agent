from hashlib import sha256
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import tempfile

import pytest
from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent import memorie_natural_trial as trial, local_product
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse, DeepSeekCredentialResolver
from dynamic_subject_agent.frozen_attempt import canonical_json


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    product=Path(os.environ.get('MEMORIE_M030_PRODUCT','missing'))
    if not (product/'.local/qualification/natural-experience-approval.json').is_file():pytest.skip('Approved local M030 material required')
    private=tmp_path/'inputs';private.mkdir()
    review=tmp_path/'.artifacts/review'
    shutil.copytree(product/'.artifacts/natural-experience-m030-review-001',review)
    for name in ['preparation.json','natural-experience-approval.json','native-activity-approval.json']:
        shutil.copyfile(product/'.local/qualification'/name,private/name)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'account'))
    for key in ('TEMP','TMP','TMPDIR'):monkeypatch.setenv(key,str(tmp_path))
    monkeypatch.setattr(tempfile,'tempdir',None)
    return trial.NaturalExperienceTrialRequest(review,private/'natural-experience-approval.json',private/'preparation.json',tmp_path/'.artifacts/run')


class Fake(DeepSeekTransport):
    def __init__(self,request):
        self.calls=[];self.names={sha256(v).hexdigest():k for k,v in trial.validate_material(request).items()}
        self.expected=json.loads((request.review_directory/'authored-expectations.NOT-MODEL-RESULTS.json').read_bytes())
    def post_json(self,**kwargs):
        name=self.names[sha256(kwargs['body']).hexdigest()];self.calls.append(name)
        if name in trial.DIAGNOSTIC_SELECTIONS:value=dict(action='remember',duration='today',reason_code='temporary' if name.endswith('temporary') else 'correction')
        elif name in self.expected:value=self.expected[name]['proposal']
        elif name=='choice_after_memory':value=dict(action='defer',plan=None,reason_code='defer-comparison',basis_refs=['E1'],decision_note='合成暂缓。')
        elif name=='share_after_memory':value=dict(share=False,reply_text='',language='zh')
        else:value='合成回复；没有真实用户输入。'
        content=value if isinstance(value,str) else canonical_json(value)
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content))],usage=dict(prompt_tokens=100,completion_tokens=30))).encode())


def test_facade_runs_ten_frozen_examples_and_second_run_cannot_resend(prepared,monkeypatch):
    fake=Fake(prepared)
    monkeypatch.setattr(trial,'DeepSeekUrlLibTransport',lambda **kw:fake)
    result=ApplicationFacade.run_memorie_natural_experience_trial(prepared)
    assert result['status']=='complete' and result['attempts']==10 and len(fake.calls)==10
    assert not result['user_canonical_opened'] and not result['runtime_memory_implemented']
    with pytest.raises(ValueError,match='already started'):
        ApplicationFacade.run_memorie_natural_experience_trial(replace(prepared,output=prepared.output.with_name('another-run')))
    assert len(fake.calls)==10


def test_changed_body_is_rejected_before_audit_or_credentials(prepared,monkeypatch):
    p=prepared.review_directory/'temporary.request.json';p.write_bytes(p.read_bytes()+b' ')
    monkeypatch.setattr(local_product,'_WindowsLabResolver',lambda:pytest.fail('credential resolver must not be constructed'))
    with pytest.raises(ValueError,match='request changed'):ApplicationFacade.run_memorie_natural_experience_trial(prepared)
    assert not prepared.output.exists()


def test_approval_change_during_secret_resolution_blocks_final_send(prepared,monkeypatch):
    resolved=[]
    class Resolver(DeepSeekCredentialResolver):
        def resolve(self,ref):
            resolved.append(True)
            value=json.loads(prepared.approval_path.read_bytes());value['human_confirmed']=False
            prepared.approval_path.write_text(json.dumps(value),encoding='utf-8')
            return 'fixture-only-not-a-real-key'
    monkeypatch.setattr(local_product,'_WindowsLabResolver',Resolver)
    monkeypatch.setattr(trial,'urlopen',lambda *a,**kw:pytest.fail('revoked request must not be sent'))
    result=ApplicationFacade.run_memorie_natural_experience_trial(prepared)
    assert result['status']=='stopped' and result['attempts']==1
    assert resolved==[True]


@pytest.fixture
def diagnostic(prepared):
    product=Path(os.environ['MEMORIE_M030_PRODUCT'])
    folder=prepared.review_directory.with_name('diagnostic')
    shutil.copytree(product/'.artifacts/natural-experience-m030-diagnostic-002',folder)
    approval=prepared.approval_path.with_name('natural-experience-diagnostic-approval.json')
    first=prepared.approval_path.with_name('first-results.json')
    shutil.copyfile(product/'.local/qualification/natural-experience-diagnostic-approval.json',approval)
    shutil.copyfile(product/'.artifacts/natural-experience-m030-live-001/results.json',first)
    return replace(prepared,diagnostic_directory=folder,diagnostic_approval_path=approval,first_results_path=first)


def test_diagnostic_runs_only_its_six_requests_and_cannot_replay_in_new_root(diagnostic,monkeypatch):
    fake=Fake(diagnostic)
    monkeypatch.setattr(trial,'DeepSeekUrlLibTransport',lambda **kw:fake)
    result=ApplicationFacade.run_memorie_natural_experience_trial(diagnostic)
    assert result['status']=='complete' and result['attempts']==6
    assert tuple(fake.calls)==trial.DIAGNOSTIC_SELECTIONS+trial.DIAGNOSTIC_REPLIES
    with pytest.raises(ValueError,match='already started'):
        ApplicationFacade.run_memorie_natural_experience_trial(replace(diagnostic,output=diagnostic.output.with_name('diagnostic-retry')))
    assert len(fake.calls)==6


def test_parent_approval_cannot_authorize_diagnostic(diagnostic,monkeypatch):
    diagnostic.diagnostic_approval_path.write_bytes(diagnostic.approval_path.read_bytes())
    monkeypatch.setattr(local_product,'_WindowsLabResolver',lambda:pytest.fail('no credentials before exact diagnostic consent'))
    with pytest.raises(ValueError,match='diagnostic approval'):
        ApplicationFacade.run_memorie_natural_experience_trial(diagnostic)
    assert not diagnostic.output.exists()


def test_diagnostic_request_change_is_rejected_before_credentials(diagnostic,monkeypatch):
    p=diagnostic.diagnostic_directory/'B_correction.request.json';p.write_bytes(p.read_bytes()+b' ')
    monkeypatch.setattr(local_product,'_WindowsLabResolver',lambda:pytest.fail('changed request must not reach credentials'))
    with pytest.raises(ValueError,match='diagnostic request changed'):
        ApplicationFacade.run_memorie_natural_experience_trial(diagnostic)

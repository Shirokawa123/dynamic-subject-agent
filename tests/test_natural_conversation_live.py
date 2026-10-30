"""Synthetic approved LIVE transport; no private persona, credentials or network."""
from dataclasses import replace
from hashlib import sha256
import json
import pytest
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.natural_conversation_live import NaturalConversationRequest, run_trial
from test_original_whole_chat import approved, model_fixture, personality_fixture

TEXTS = ['今天想轻松聊聊，明天不一定。', '想听听你自己的想法。',
    '刚才说错了，今天想一起想办法，不要替我安排。', '我们接着聊。', '这段经历不用再记了。', '你刚才在做什么？']


@pytest.fixture
def trial_material(approved, tmp_path, monkeypatch):
    author, _, freeze, view = approved
    author.close()
    import dynamic_subject_agent.memorie_companion_contract as memorie
    import dynamic_subject_agent.natural_conversation_live as live
    import dynamic_subject_agent.natural_experience_cycle as cycle
    monkeypatch.setattr(memorie, 'DEFINITION', view.definition_basis)
    root = tmp_path / '.artifacts'; root.mkdir()
    directory = root / 'review'; directory.mkdir()
    preparation = root / 'preparation.json'
    preparation.write_text(canonical_json(dict(definition_json=freeze.preparation_json)), encoding='utf-8')
    source = dict(character=dict(synthetic=True), personality=[], current_user_text=TEXTS[0], current_experience=None)
    preview = canonical_json(dict(messages=[{}, dict(content=canonical_json(source))]))
    (directory / 'first-selection.UNSENT.json').write_text(preview, encoding='utf-8')
    parameters = dict(model='deepseek-flash', thinking=dict(type='disabled'), max_tokens=4096)
    review = dict(preparation_sha256=sha256(preparation.read_bytes()).hexdigest(),
        illustrative_unsent_request_sha256={'first-selection':sha256(preview.encode()).hexdigest()},
        selection=dict(parameters=dict(parameters,response_format=dict(type='json_object')),policy='Synthetic selector',
            fields=list(source)),
        reply=dict(parameters=parameters,policy='Synthetic reply',fields=['character','personality','current_user_text','experience','exchange','activity_evidence']),
        scenario=[dict(id='t'+str(i+1),text=text,reopen_before=i==3) for i,text in enumerate(TEXTS)])
    raw = canonical_json(review); digest = sha256(raw.encode()).hexdigest()
    (directory / 'review.json').write_text(raw, encoding='utf-8')
    monkeypatch.setattr(live, 'REVIEW', digest)
    monkeypatch.setattr(cycle, 'LIVE_REVIEW', digest)
    approval = root / 'approval.json'
    approval.write_text(canonical_json(dict(version='memorie-natural-conversation-m032-1',review_sha256=digest,
        human_confirmed=True,user_reply='同意这次隔离试验',authorization_source='direct-user-reply:2026-10-30-current-chat',
        maximum_requests=12,automatic_retries=0,installation_included=False,user_data_upgrade_included=False)),encoding='utf-8')
    return NaturalConversationRequest(directory,approval,preparation,root/'result'), root/'audit'


class Transport(DeepSeekTransport):
    def __init__(self, *, callback=None, invalid=False, fail_correction_reply=False):
        self.calls=[]; self.callback=callback; self.invalid=invalid
        self.fail_correction_reply=fail_correction_reply

    def post_json(self, **kwargs):
        body=json.loads(kwargs['body']); payload=json.loads(body['messages'][1]['content'])
        self.calls.append(payload)
        if self.callback:self.callback(kwargs)
        text=payload['current_user_text']
        if 'current_experience' in payload:
            if text in (TEXTS[0],TEXTS[2]):
                value=dict(action='remember',duration='today',reason_code='correction' if text==TEXTS[2] else 'temporary')
            elif text==TEXTS[4]:value=dict(action='forget',duration=None,reason_code='explicit-forget')
            else:value=dict(action='keep',duration=None,reason_code='irrelevant')
            content='{}' if self.invalid else canonical_json(value)
        else:
            content='' if self.fail_correction_reply and text==TEXTS[2] else '合成自然正文：'+text
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content))],
            usage=dict(prompt_tokens=10,completion_tokens=10,total_tokens=20))).encode())


def test_six_turns_atomic_live_history_correction_reopen_forget_and_no_repeat(trial_material):
    request,audit=trial_material; transport=Transport()
    result=run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit)
    assert result['status']=='complete',result
    assert result['attempts']==12 and len(transport.calls)==12
    assert result['reopen']==dict(same_scope=True,same_state=True,model_calls=0)
    assert result['rows'][2]['experience']['duration']=='today'
    assert transport.calls[3]['exchange'][0]['user_text']==TEXTS[0]
    assert transport.calls[5]['exchange']==[]
    assert transport.calls[7]['exchange']==[dict(user_text=TEXTS[2],assistant_text='合成自然正文：'+TEXTS[2])]
    assert transport.calls[9]['exchange']==[]
    assert transport.calls[11]['experience'] is None
    assert transport.calls[11]['exchange']==[dict(user_text=TEXTS[4],assistant_text='合成自然正文：'+TEXTS[4])]
    assert result['rows'][4]['experience'] is None
    for payload in transport.calls:
        assert 'identity_id' not in canonical_json(payload) and 'local_day' not in canonical_json(payload)
    with pytest.raises(ValueError,match='already started'):
        run_trial(replace(request,output=request.output.with_name('new-root')),_transport_factory=lambda _:transport,_audit_parent=audit)
    assert len(transport.calls)==12


def test_unapproved_material_never_initializes_identity_or_sender(trial_material):
    request,audit=trial_material
    receipt=json.loads(request.approval_path.read_bytes());receipt['human_confirmed']=False
    request.approval_path.write_text(canonical_json(receipt),encoding='utf-8')
    with pytest.raises(ValueError,match='approval'):
        run_trial(request,_transport_factory=lambda _:pytest.fail('no transport'),_audit_parent=audit)
    assert not request.output.exists() and not audit.exists()


def test_invalid_selection_stops_without_reply_or_memory_publication(trial_material):
    request,audit=trial_material;transport=Transport(invalid=True)
    result=run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit)
    assert result['status']=='stopped' and result['attempts']==1
    assert result['rows'][0]['experience'] is None and result['rows'][0]['failure_code']
    assert len(transport.calls)==1


def test_approval_revoked_at_final_delivery_prevents_network(trial_material,monkeypatch):
    request,audit=trial_material
    import dynamic_subject_agent.natural_conversation_live as live
    monkeypatch.setattr(live,'urlopen',lambda *a,**k:pytest.fail('revoked request reached network'))
    def factory(opener):
        def revoke(kwargs):
            from urllib.request import Request
            receipt=json.loads(request.approval_path.read_bytes());receipt['human_confirmed']=False
            request.approval_path.write_text(canonical_json(receipt),encoding='utf-8')
            opener(Request('https://api.deepseek.com/chat/completions',data=kwargs['body'],method='POST'),timeout=30)
        return Transport(callback=revoke)
    result=run_trial(request,_transport_factory=factory,_audit_parent=audit)
    assert result['status']=='stopped' and result['attempts']==1


def test_failed_free_reply_keeps_previous_experience_atomically(trial_material):
    request,audit=trial_material;transport=Transport(fail_correction_reply=True)
    result=run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit)
    assert result['status']=='stopped' and result['attempts']==6
    assert result['rows'][-1]['failure_code']
    assert result['rows'][-1]['experience']['quote']==TEXTS[0]

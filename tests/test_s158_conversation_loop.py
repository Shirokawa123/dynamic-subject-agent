"""Raw text preservation, strict JSON separation and first-attempt boundaries."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture
from test_integrated_character import integrated_fixture
from test_s158_live_loop import loop_fixture
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s158_conversation_loop as conversation


@pytest.mark.parametrize('plain',[True,False])
def test_raw_final_and_response_preserved_plain_only_local_wrapper(tmp_path,monkeypatch,plain):
    engine=conversation.engine
    root=tmp_path/'first';root.mkdir()
    monkeypatch.setattr(conversation,'ROOT',root)
    monkeypatch.setattr(engine,'ROOT',root)
    monkeypatch.setattr(engine.evidence,'ROOT',root)
    raw='  你想把箱子上的哪几个字换成什么？  ' if plain else '{"intent":"chat","reply_text":"首稿保留"},'
    body=dict(messages=[dict(role='system',content='synthetic'),dict(role='user',content=json.dumps(dict(turn=dict(current_message='合成'))))])
    if not plain:body['response_format']=dict(type='json_object')
    wire=engine.canonical_json(body).encode()
    response=DeepSeekHttpResponse(200,engine.canonical_json(dict(choices=[dict(message=dict(content=raw,reasoning_content='DO-NOT-SAVE'),finish_reason='stop')],usage=dict(completion_tokens=20))).encode())
    report=dict(calls=[],credential_read_attempts=0)
    transport=engine.evidence.CapturingTransport(report)
    transport.delegate=SimpleNamespace(post_json=lambda **kwargs:response)
    transport.arm('first',wire)
    actual=transport.post_json(endpoint='https://api.deepseek.com/chat/completions',timeout_seconds=30,body=wire)
    assert actual is response and transport.final==raw
    saved=json.loads((root/'finals/first.json').read_text(encoding='utf-8'))
    assert saved==dict(final=raw)
    assert report['calls'][0]['final_sha256']==sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(conversation,'preview',lambda task:dict(body=body))
    if plain:
        task_preview=dict(payload=dict(current_plan=None,turn=dict(current_message='合成',history_enabled=False)))
        wrapped=conversation.decode_model_final(transport.final,task_preview,engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)
        assert wrapped==dict(intent='chat',reply_text=raw)
        assert engine.digest(wrapped)!=engine.digest(raw)
        with pytest.raises(RuntimeError):conversation.decode_model_final(raw,{},engine.ModelTaskKind.LIVING_ACTIVITY_CHOICE)
    else:
        assert transport.final==raw and not (root/'interpretations').exists()
        with pytest.raises(json.JSONDecodeError):conversation.decode_model_final(raw,{},engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)
        with pytest.raises(json.JSONDecodeError):engine.decode_model_final(raw,{},engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)
    assert transport.final==raw and json.loads((root/'finals/first.json').read_text(encoding='utf-8'))==dict(final=raw)
    assert report['credential_read_attempts']==0
    assert all('DO-NOT-SAVE' not in p.read_text(encoding='utf-8') for p in root.rglob('*.json'))


def test_plain_reference_has_no_effect_and_no_invented_model_label(monkeypatch,tmp_path):
    engine=conversation.engine
    root=tmp_path/'reference';root.mkdir()
    monkeypatch.setattr(conversation,'ROOT',root)
    state=dict(current_plan=dict(subject='回帆',composition='近架和远箱',focus='手部'),activity_revision=1)
    original=engine.reference_checks
    value=dict(intent='chat',reply_text='你指哪几个字，要换成什么？')
    assert original(value,state,state)==dict(reference_clarifies_without_effect=False)
    with conversation.configured():
        assert engine.reference_checks(value,state,state)==dict(reference_no_effect=True,reference_model_intent_not_applicable=True)
        assert engine.reference_checks(value,state,dict(state,activity_revision=2))['reference_no_effect'] is False
        assert value['intent']=='chat'
    assert engine.reference_checks is original


def test_conversation_first_failure_remains_terminal_without_retry(loop_fixture,monkeypatch):
    report,captures,options=loop_fixture;options['fail']=True
    engine=conversation.engine
    original_capture=engine.evidence.CapturingTransport
    monkeypatch.setattr(conversation,'ROOT',engine.ROOT)
    monkeypatch.setattr(conversation,'opening',engine.opening)
    monkeypatch.setattr(conversation,'preview',engine.integrated_remote_request_preview)
    with conversation.configured():
        assert engine.next_stage(report)==2
        with pytest.raises(RuntimeError):engine.next_stage(report)
        assert engine.inspect(report)['inspection_requests']==0
    assert engine.evidence.CapturingTransport is original_capture
    assert report['status']=='bounded-terminal' and sum(c.total for c in captures)==1


def test_conversation_wire_entry_and_pins_are_independent(monkeypatch):
    engine=conversation.engine
    old_root,old_scene=engine.ROOT,engine.SCENE
    calls=[]
    monkeypatch.setitem(sys.modules,'serve_integrated_character_chat',SimpleNamespace(IntegratedCharacterChatEntry=
        lambda root,**kwargs:(calls.append((root,kwargs)) or SimpleNamespace(product=SimpleNamespace(profile_id='p',timeline_id='t')))))
    monkeypatch.setattr(conversation,'_base_preview',lambda task,**kwargs:(task,kwargs))
    with conversation.configured():
        engine.opening(dict(provider_observations=[],profile_id='p',timeline_id='t'),object())
        assert calls[0][1]['technical_variant']=='conversation-text'
        assert engine.integrated_remote_request_preview('task')==('task',dict(technical_variant='conversation-text'))
        bound=engine.pins()
        for path in (Path(conversation.__file__),conversation.SCENE,Path(engine.__file__)):
            assert bound[str(path.relative_to(conversation.REPO))]==sha256(path.read_bytes()).hexdigest()
        plan=dict(subject='道具室',composition='近处回帆，远处回帆。',focus='手部动作')
        result=engine.derive_feedback(plan)
        assert result['old']=='回帆' and result['new']=='归帆' and not result['long_eligible']
    assert (engine.ROOT,engine.SCENE)==(old_root,old_scene)

"""New header/text/JSON decoding and bounded scene ownership, no real calls."""
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
import run_s158_intent_loop as intent


def test_header_raw_preserved_and_local_parser_can_accept_or_decline(tmp_path,monkeypatch):
    engine=intent.engine
    root=tmp_path/'first';root.mkdir()
    monkeypatch.setattr(engine,'ROOT',root);monkeypatch.setattr(engine.evidence,'ROOT',root)
    payload=dict(current_plan=dict(subject='潮序',composition='入口铭牌潮序，远处旗上潮序。',focus='手部动作'),
        activity_revision=1,turn=dict(current_message='把所有“潮序”换成“潮声”，其他照旧。',history_enabled=True))
    body=dict(messages=[dict(role='system',content='synthetic'),dict(role='user',content=engine.canonical_json(payload))])
    wire=engine.canonical_json(body).encode()
    raw='[revise]\n  只把这几处展览名改成潮声，其他安排保留。'
    raw=raw.replace('\\n','\n')
    response=DeepSeekHttpResponse(200,engine.canonical_json(dict(choices=[dict(message=dict(content=raw,reasoning_content='DO-NOT-SAVE'),finish_reason='stop')])).encode())
    report=dict(calls=[],credential_read_attempts=0)
    transport=engine.evidence.CapturingTransport(report)
    transport.delegate=SimpleNamespace(post_json=lambda **kwargs:response)
    transport.arm('first',wire)
    assert transport.post_json(endpoint='https://api.deepseek.com/chat/completions',timeout_seconds=30,body=wire) is response
    monkeypatch.setattr(intent,'preview',lambda task:dict(body=body,output_contract=dict(final_content='intent-prefixed-text')))
    value=intent.decode_model_final(transport.final,dict(payload=payload),engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)
    assert value==dict(intent='revise',reply_text=raw.split('\n',1)[1])
    assert transport.final==raw and json.loads((root/'finals/first.json').read_text(encoding='utf-8'))==dict(final=raw)
    assert report['calls'][0]['final_sha256']==sha256(raw.encode()).hexdigest()
    declined=intent.decode_model_final('[chat]\n暂时保留这个名字，我想先考虑人物的位置。',dict(payload=payload),engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)
    assert declined['intent']=='chat'
    for invalid in ('{"intent":"revise","reply_text":"改好了"}', '{"json_object":{"intent":"revise"}}', '[revise]改好了'):
        with pytest.raises(ValueError):intent.decode_model_final(invalid,dict(payload=payload),engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)
    assert report['credential_read_attempts']==0
    assert all('DO-NOT-SAVE' not in p.read_text(encoding='utf-8') for p in root.rglob('*.json'))


def test_plain_and_json_routes_remain_distinct(monkeypatch):
    engine=intent.engine
    monkeypatch.setattr(intent,'preview',lambda task:dict(body={},output_contract=dict(final_content='plain-text')))
    raw='  你想把旗上的哪几个字改成什么？  '
    payload=dict(current_plan=None,turn=dict(current_message='那个改一下',history_enabled=True))
    assert intent.decode_model_final(raw,dict(payload=payload),engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)==dict(intent='chat',reply_text=raw)
    with pytest.raises(RuntimeError):intent.decode_model_final(raw,dict(payload=payload),engine.ModelTaskKind.LIVING_ACTIVITY_SHARE)
    monkeypatch.setattr(intent,'preview',lambda task:dict(body=dict(response_format=dict(type='json_object'))))
    assert intent.decode_model_final('{"share":false}',{},engine.ModelTaskKind.LIVING_ACTIVITY_SHARE)==dict(share=False)
    with pytest.raises(json.JSONDecodeError):intent.decode_model_final('{"share":false},',{},engine.ModelTaskKind.LIVING_ACTIVITY_SHARE)


def test_long_special_input_original_bounds_and_independent_wrapper(monkeypatch):
    engine=intent.engine;old_root=engine.ROOT;calls=[]
    monkeypatch.setitem(sys.modules,'serve_integrated_character_chat',SimpleNamespace(IntegratedCharacterChatEntry=
        lambda root,**kwargs:(calls.append((root,kwargs)) or SimpleNamespace(product=SimpleNamespace(profile_id='p',timeline_id='t')))))
    monkeypatch.setattr(intent,'_base_preview',lambda task,**kwargs:(task,kwargs))
    with intent.configured():
        assert len(engine.SOURCE)<=400 and '长距专项' in engine.SOURCE and '250–350' in engine.SOURCE
        engine.opening(dict(provider_observations=[],profile_id='p',timeline_id='t'),object())
        assert calls[0][1]['technical_variant']=='intent-text'
        assert engine.integrated_remote_request_preview('task')==('task',dict(technical_variant='intent-text'))
        for path in (Path(intent.__file__),intent.SCENE,Path(engine.__file__),intent.REPO/'scripts/run_s158_conversation_loop.py'):
            assert engine.pins()[str(path.relative_to(intent.REPO))]==sha256(path.read_bytes()).hexdigest()
        plan=dict(subject='长画幅',composition='近处铭牌写潮序。'+'人物侧身扶住栏杆，留白与远处船帆保持相互呼应。'*11+'远处旗上写潮序。',focus='看手上的动作')
        found=engine.derive_feedback(plan)
        assert found['long_eligible'] and found['spans']['composition']>160 and len(found['edits'])<=4
        assert found['expected_plan']=={key:text.replace('潮序','潮声') for key,text in plan.items()}
        assert not engine.derive_feedback(dict(plan,composition='潮序短稿。'))['long_eligible']
        assert engine.derive_feedback(dict(plan,composition='潮序'*9)) is None
    assert engine.ROOT==old_root


def test_intent_first_failure_is_terminal_without_retry(loop_fixture,monkeypatch):
    report,captures,options=loop_fixture;options['fail']=True
    engine=intent.engine;original_capture=engine.evidence.CapturingTransport
    monkeypatch.setattr(intent,'ROOT',engine.ROOT)
    monkeypatch.setattr(intent,'opening',engine.opening)
    monkeypatch.setattr(intent,'preview',engine.integrated_remote_request_preview)
    with intent.configured():
        assert engine.next_stage(report)==2
        with pytest.raises(RuntimeError):engine.next_stage(report)
        assert engine.inspect(report)['inspection_requests']==0
    assert engine.evidence.CapturingTransport is original_capture
    assert report['status']=='bounded-terminal' and sum(c.total for c in captures)==1

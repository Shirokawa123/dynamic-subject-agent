"""Focused wrapper isolation and first-attempt behavior, all synthetic."""
from hashlib import sha256
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_integrated_character import integrated_fixture
from test_s158_live_loop import loop_fixture

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s158_focused_loop as focused


def test_wrapper_selects_focused_entry_wire_and_binds_both_files(monkeypatch,tmp_path):
    baseline=focused.engine
    original={key:getattr(baseline,key) for key in ('ROOT','SCENE','STAGES','opening','pins','integrated_remote_request_preview')}
    calls=[]
    def entry(root,**kwargs):
        calls.append((root,kwargs))
        return SimpleNamespace(product=SimpleNamespace(profile_id='same-profile',timeline_id='same-timeline'))
    monkeypatch.setitem(sys.modules,'serve_integrated_character_chat',SimpleNamespace(IntegratedCharacterChatEntry=entry))
    monkeypatch.setattr(focused,'_base_preview',lambda task,**kwargs:(task,kwargs))
    with focused.configured() as engine:
        engine.opening(dict(provider_observations=[],profile_id='same-profile',timeline_id='same-timeline'),object())
        assert calls[0][0]==focused.ROOT/'entry'
        assert calls[0][1]['technical_variant']=='focused'
        assert engine.integrated_remote_request_preview('task')==('task',dict(technical_variant='focused'))
        bound=engine.pins()
        for path in (Path(focused.__file__),focused.SCENE,Path(engine.__file__)):
            assert bound[str(path.relative_to(focused.REPO))]==sha256(path.read_bytes()).hexdigest()
        assert engine.ROOT!=original['ROOT'] and engine.STAGES[0][1]==focused.SOURCE
    assert original=={key:getattr(baseline,key) for key in original}


def test_focused_unknown_is_terminal_and_preserves_baseline_module(loop_fixture,monkeypatch):
    report,captures,options=loop_fixture
    options['fail']=True
    base=focused.engine
    original_root,original_opening,original_preview=base.ROOT,base.opening,base.integrated_remote_request_preview
    # The existing LOCAL fixture exercises bounded orchestration; no LIVE
    # factory or credential is constructed for this injected first failure.
    monkeypatch.setattr(focused,'ROOT',original_root)
    monkeypatch.setattr(focused,'opening',original_opening)
    monkeypatch.setattr(focused,'preview',original_preview)
    with focused.configured() as engine:
        assert engine.next_stage(report)==2
        assert report['stages'][0]['text']==focused.SOURCE
        assert (engine.ROOT/'attempts/00.json').exists()
        with pytest.raises(RuntimeError):engine.next_stage(report)
        assert engine.inspect(report)['inspection_requests']==0
    assert base.ROOT==original_root and base.opening is original_opening
    assert report['status']=='bounded-terminal' and sum(c.total for c in captures)==1


def test_new_scene_keeps_frozen_name_scope_and_long_gate_separate():
    plan=dict(subject='末班车站',composition='近处站牌迟灯，少女转身看向车尾迟灯。',focus='看她转身时的手势')
    with focused.configured() as engine:
        short=engine.derive_feedback(plan)
        assert short['text']=='把所有“迟灯”换成“微灯”，其他照旧。'
        assert short['occurrences']==2 and short['long_eligible'] is False
        assert short['expected_plan']=={key:text.replace('迟灯','微灯') for key,text in plan.items()}
        long_plan=dict(plan,composition='近处站牌迟灯。'+'手势和站台留白保持，轨道通向远处车尾。'*11+'车尾标识迟灯。')
        long=engine.derive_feedback(long_plan)
        assert long['long_eligible'] and long['spans']['composition']>160 and len(long['edits'])<=4
        assert engine.derive_feedback(dict(plan,composition='迟灯'*9)) is None

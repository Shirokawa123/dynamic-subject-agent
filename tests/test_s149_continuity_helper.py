import importlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s149_action_continuity as trial
from test_living_activity_chat_entry import living_entry_setup,approved,personality_fixture,model_fixture,entry_setup
from test_living_action_contract import ActionTransport


def test_new_scene_helper_full_facade_rework_reopen_and_same_day_zero_gate(living_entry_setup,tmp_path,monkeypatch):
    _,_,_,options,_,_,_=living_entry_setup
    root=tmp_path/'new-s149-owned';monkeypatch.setattr(trial,'ROOT',root)
    # Global helper destinations are restored by monkeypatch after this test.
    monkeypatch.setattr(trial.life,'ROOT',root);monkeypatch.setattr(trial.evidence,'ROOT',root)
    monkeypatch.setattr(trial.life,'NEXT_DAY',trial.NEXT_DAY)
    actual=trial.ActionContractLivingChatEntry
    fake=ActionTransport()
    def factory(path,**kwargs):
        kwargs['transport'].delegate=fake
        return actual(path,**dict(options,**kwargs))
    monkeypatch.setattr(trial,'ActionContractLivingChatEntry',factory)
    assert trial.main(['day1'])==0
    report=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    assert report['status']=='day1-complete-awaiting-real-next-day'
    assert report['this_invocation_remote_calls']==len(fake.calls)==9
    assert report['rework_without_new_plan'] and report['final_reopen_verified']
    assert len(list((root/'finals').glob('*.json')))==9
    # Completed-date gate runs before creating any factory/transport/credential.
    monkeypatch.setattr(trial,'ActionContractLivingChatEntry',lambda *a,**k:(_ for _ in ()).throw(AssertionError('same-day-opened-product')))
    assert trial.main(['next-day'])==0
    assert len(fake.calls)==9
    with pytest.raises(RuntimeError,match='no-repeat'):trial.main(['day1'])


def test_feedback_quote_is_bounded_exact_current_plan_prefix_and_not_a_summary():
    plan=dict(subject='原创主题',composition='正面中景；'+'构'*795)
    value=trial.feedback_for(plan)
    assert plan['subject'] in value and plan['composition'][:80] in value
    assert value.endswith(trial.FEEDBACK) and len(value)<=400
    assert '正面中景' in value

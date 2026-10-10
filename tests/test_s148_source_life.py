import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s148_source_life_continuation as life
from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_living_activity_live import living_live_fixture
from test_living_final_text import final_text_fixture,FinalTextTransport


@pytest.mark.parametrize('share',[False,True])
def test_source_share_choice_and_correction_chain_via_existing_facade(final_text_fixture,tmp_path,monkeypatch,share):
    opening,_,options,_=final_text_fixture
    monkeypatch.setattr(life,'ROOT',tmp_path/'evidence')
    monkeypatch.setattr(life.evidence,'ROOT',life.ROOT)
    report=dict(calls=[],stages=[],credential_read_attempts=0)
    transport=life.evidence.CapturingTransport(report)
    fake=FinalTextTransport()
    original=fake.post_json
    def post(**kwargs):
        payload=json.loads(json.loads(kwargs['body'])['messages'][1]['content'])
        if 'activity_result' in payload and 'turn' not in payload:
            fake.override=dict(share=share,reply_text='合成分享。' if share else '',language='zh')
        else: fake.override=None
        return original(**kwargs)
    fake.post_json=post;transport.delegate=fake
    product=opening(transport)
    run=life.LifeRun(product,transport,report,options['audit_path'])
    head=run.reply('source',life.SOURCE);run.select('select',head,life.SOURCE);run.controls(False,True)
    assert run.choice('activity')=='start'
    before=len(run.history());assert run.share() is share
    assert len(run.history())==before
    head=run.reply('feedback',life.FEEDBACK);run.select('correction',head,life.FEEDBACK)
    assert run.view()['current_plan'] is None and run.view()['latest_share'] is None
    assert run.choice('corrected')=='revise'
    run.reply('result',life.RESULT)
    run.controls(True,False)
    assert transport.total==6 and all(x.get('audit_matches_raw_final') for x in report['stages'] if x['requests'])
    assert run.view()['permission']['paused'] and not run.view()['permission']['sharing_enabled']
    # Source, old model dialogue and share disappear from the corrected wire.
    corrected=json.loads(fake.calls[-2]['messages'][1]['content'])
    assert corrected['shared_experience']['quote']==life.FEEDBACK and corrected['current_plan'] is None
    assert 'working_understanding' not in corrected


def test_next_day_requires_actual_later_date_and_only_ready_scene():
    report=dict(status='day1-complete-awaiting-real-next-day',day1_civil_date='2026-10-09',feedback_completed_civil_date='2026-10-10')
    assert not life.next_day_allowed(report,'2026-10-10')
    assert life.next_day_allowed(report,'2026-10-11')
    assert not life.next_day_allowed(dict(report,status='stopped-first-failure'),'2026-10-11')


def test_reserved_next_day_is_durably_burned_before_any_product_or_credential(tmp_path,monkeypatch):
    monkeypatch.setattr(life,'ROOT',tmp_path/'owned')
    monkeypatch.setattr(life,'today',lambda:'2026-10-11')
    report=dict(status='day1-complete-awaiting-real-next-day',feedback_completed_civil_date='2026-10-10')
    life.reserve_next_day(report)
    stored=json.loads((life.ROOT/'metadata.json').read_text(encoding='utf-8'))
    assert stored['status']=='next-day-attempt-started' and stored['next_day_attempt']['idempotency_key']
    assert not life.next_day_allowed(stored,'2026-10-11')
    with pytest.raises(RuntimeError,match='not-ready'):life.reserve_next_day(stored)

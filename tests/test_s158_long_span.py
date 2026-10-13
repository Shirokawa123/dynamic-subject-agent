"""Five-stage long-only result, short first result and no automatic rerun."""
from pathlib import Path
import sys
import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture
from test_integrated_character import integrated_fixture
from test_s158_live_loop import loop_fixture

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s158_long_span as long_span


@pytest.mark.parametrize('long',[True,False])
def test_five_stages_end_with_actual_long_result_and_no_person_grade(loop_fixture,monkeypatch,long):
    report,captures,options=loop_fixture
    base=long_span.engine
    middle='人物扶着行李望向窗外，光线从售票窗边落在手上，地面留出通向远方的空白。'*7 if long else '人物扶着行李。'
    options['plan']=dict(subject='索道候车室',composition='近处售票窗牌写山信。'+middle+'远处指示牌写山信。',focus='手和行李的位置')
    monkeypatch.setattr(long_span,'ROOT',base.ROOT)
    monkeypatch.setattr(long_span,'opening',base.opening)
    monkeypatch.setattr(long_span,'preview',base.integrated_remote_request_preview)
    monkeypatch.setattr(long_span,'decode_model_final',base.decode_model_final)
    original_root=base.ROOT
    with long_span.configured():
        assert len(base.SOURCE)<=400 and '工程专项' in base.SOURCE and len(base.STAGES)==5
        for _ in base.STAGES:assert base.next_stage(report)==0,report
        assert report['status']==('long-span-passed' if long else 'long-span-not-met')
        assert report['long_span_result']['passed'] is long
        assert report['long_span_result']['unchanged_outside_frame'] is True
        assert report['long_span_result']['person_effect_scored'] is False
        assert report['human_content_reviews']=={}
        assert len(report['calls'])==5 and report['next_stage']==5
        assert report['final_view']['activity_revision']==2
        with pytest.raises(RuntimeError):base.next_stage(report)
    assert base.ROOT==original_root and sum(c.total for c in captures)==5
    with pytest.raises(SystemExit):long_span.main(['grade'])


def test_long_first_failure_keeps_terminal_and_no_fallback(loop_fixture,monkeypatch):
    report,captures,options=loop_fixture;options['fail']=True
    base=long_span.engine
    monkeypatch.setattr(long_span,'ROOT',base.ROOT)
    monkeypatch.setattr(long_span,'opening',base.opening)
    monkeypatch.setattr(long_span,'preview',base.integrated_remote_request_preview)
    with long_span.configured():
        assert base.PAIRS==(('山信','山音'),)
        assert base.derive_feedback(dict(subject='候车室',composition='没有目标字。',focus='手势')) is None
        assert base.next_stage(report)==2
        with pytest.raises(RuntimeError):base.next_stage(report)
        assert base.inspect(report)['inspection_requests']==0
    assert sum(c.total for c in captures)==1 and report['status']=='bounded-terminal'

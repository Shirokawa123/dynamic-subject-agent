import json
import pytest
from dynamic_subject_agent.natural_experience import (NaturalExperience, visible_experience,
    selection_projection, adjudicate_experience, encode_experience, decode_experience)


def proposal(action='remember', duration='today', reason='temporary'):
    return dict(action=action, duration=duration, reason_code=reason)


def test_temporary_source_survives_serialization_but_expires_without_becoming_permanent():
    text='仅今天想自己先比较，明天不一定。'
    value=adjudicate_experience(proposal(),current_text=text,previous=None,source_head_sequence=1,local_day='2026-10-29')
    restored=decode_experience(json.loads(json.dumps(encode_experience(value))))
    assert selection_projection(restored,'2026-10-29')==dict(quote=text,duration='today')
    assert visible_experience(restored,'2026-10-30') is None
    with pytest.raises(ValueError):visible_experience(restored,'2026-10-28')
    assert set(selection_projection(restored,'2026-10-29'))=={'quote','duration'}


def test_correction_replaces_source_keep_does_not_rewrite_and_forget_disables():
    old=NaturalExperience('我一直喜欢对比观察。','until_changed',1,'2026-10-29')
    new=adjudicate_experience(proposal(reason='correction'),current_text='刚才说错了，只限今天。',previous=old,source_head_sequence=2,local_day='2026-10-30')
    assert new.quote=='刚才说错了，只限今天。' and new.source_head_sequence==2
    assert visible_experience(new,'2026-10-31') is None
    kept=adjudicate_experience(proposal('keep',None,'irrelevant'),current_text='按钮在哪？',previous=old,source_head_sequence=3,local_day='2026-10-30')
    assert kept==old
    assert adjudicate_experience(proposal('forget',None,'explicit-forget'),current_text='不用记这件事了。',previous=old,source_head_sequence=4,local_day='2026-10-30') is None
    assert old.quote=='我一直喜欢对比观察。'


@pytest.mark.parametrize('value,text',[(dict(proposal(),quote='模型杜撰'),'今天想休息'),(proposal(duration='until_changed'),'今天想休息'),(proposal(),'字'*401)])
def test_rejects_rewritten_quotes_oversize_and_temporary_promotion(value,text):
    with pytest.raises(ValueError):adjudicate_experience(value,current_text=text,previous=None,source_head_sequence=1,local_day='2026-10-29')

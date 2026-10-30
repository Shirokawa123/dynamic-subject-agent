from copy import deepcopy
import pytest
from dynamic_subject_agent.activity_reply_review import adjudicate_review, outbound_bytes
from dynamic_subject_agent.reply_review_diagnostics import ReviewValidationFailure


def payload(text='我想把这两个想法放在一起比较，你愿意吗？'):
    return dict(character=dict(name='合成人物',stage='已有相处',knowledge=[]),
        current_message='你现在想做什么？',exchange=[],activity_evidence=None,candidate_text=text)


def test_acceptance_preserves_free_wording_and_does_not_create_state():
    source=payload();before=deepcopy(source)
    result=adjudicate_review(source,dict(verdict='supported',issues=[]),request_digest='local')
    assert result.status=='candidate' and result.reply_text==source['candidate_text']
    assert source==before


@pytest.mark.parametrize('verdict',['unsupported','uncertain'])
def test_rejected_or_uncertain_review_never_returns_text_for_publication(verdict):
    source=payload('我刚完成了一个观察实验。接下来想休息。')
    issues=[dict(quote='我刚完成了一个观察实验',kind='unsupported_event',basis_labels=[])] if verdict=='unsupported' else []
    result=adjudicate_review(source,dict(verdict=verdict,issues=issues),request_digest='local')
    assert result.status=='rejected' and result.reply_text==''


def test_phantom_evidence_or_changed_quote_is_not_accepted():
    source=payload('我刚完成了观察实验。')
    issue=dict(quote='刚完成了观察实验',kind='unsupported_event',basis_labels=['A1'])
    with pytest.raises(ReviewValidationFailure,match='review-label'):
        adjudicate_review(source,dict(verdict='unsupported',issues=[issue]),request_digest='local')
    issue.update(quote='模型改写过的片段',basis_labels=[])
    with pytest.raises(ReviewValidationFailure,match='review-quote'):
        adjudicate_review(source,dict(verdict='unsupported',issues=[issue]),request_digest='local')


def test_reviewer_cannot_rewrite_reply_or_add_unapproved_fields():
    source=payload()
    with pytest.raises(ReviewValidationFailure):
        adjudicate_review(source,dict(verdict='supported',issues=[],reply_text='替换正文'),request_digest='local')
    source['raw_game_assets']='not allowed'
    with pytest.raises(ValueError,match='exact activity-review'):
        outbound_bytes(source)

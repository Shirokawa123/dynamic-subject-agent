"""The proposed data use is reviewable but cannot change approved delivery."""
import json
from copy import deepcopy
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send
from test_integrated_character import integrated_fixture, start, MESSAGE
from test_living_activity import act
from dynamic_subject_agent.integrated_character_change_preview import current_change_request_preview
from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview


def test_change_candidate_preserves_old_wire_and_has_no_choice_use(integrated_fixture):
    product, adapter = start(integrated_fixture)
    assert send(product, MESSAGE, 'change-preview-edit-1').status == 'terminal'
    assert act(product, 'share', 'change-preview-share-1').status == 'committed'
    change = dict(action='revise', changes=[dict(field='focus', before='左手', after='右手')], unexpanded_fields=[])
    calls = len(adapter.calls)
    for task in adapter.calls[1:]:
        original = deepcopy(task.payload)
        baseline = integrated_remote_request_preview(task)
        proposed = current_change_request_preview(task, change, technical_variant='baseline')
        assert proposed['status'] == 'unapproved-change-preview-only'
        payload = json.loads(proposed['body']['messages'][1]['content'])
        assert payload.pop('current_result_change') == change
        assert payload == json.loads(baseline['body']['messages'][1]['content'])
        assert task.payload == original
        assert integrated_remote_request_preview(task) == baseline
        assert proposed['body']['max_tokens'] == 4096
        assert proposed['automatic_retries'] == 0 and proposed['requests_per_action'] == 1
        assert proposed['output_contract'] == baseline['output_contract']
        assert proposed['wire_sha256'] != baseline['wire_sha256']
        with pytest.raises(ValueError):
            current_change_request_preview(task, dict(change, source_id='private'), technical_variant='baseline')
    with pytest.raises(ValueError, match='reply and share only'):
        current_change_request_preview(adapter.calls[0], change, technical_variant='baseline')
    assert len(adapter.calls) == calls


def test_history_off_review_cannot_add_changes(integrated_fixture):
    product, adapter = start(integrated_fixture)
    product.application.set_reviewed_character_history(False)
    assert send(product, '现在聊点别的。', 'change-preview-history-off').status == 'terminal'
    task = adapter.calls[-1]
    change = dict(action='revise', changes=[], unexpanded_fields=['composition'])
    with pytest.raises(ValueError, match='history-off'):
        current_change_request_preview(task, change, technical_variant='baseline')
    preview = current_change_request_preview(task, None, technical_variant='baseline')
    assert json.loads(preview['body']['messages'][1]['content'])['current_result_change'] is None

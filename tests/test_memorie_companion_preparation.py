from dataclasses import asdict, replace
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.memorie_companion_preparation import MemoriePreparationRequest


@pytest.fixture
def memorie_preparation(tmp_path):
    line = '合成来源人物已经完成一段旅程，仍在继续学习。'
    nodes = [{'name': 'scenario_Story_055', 'instructions': [
        dict(kind='line', value='line:synthetic', text_zh_hans=line)]}]
    source = tmp_path / 'nodes.json'
    source.write_text(canonical_json(nodes), encoding='utf-8')
    claim = dict(id='synthetic-identity', dimension='identity', kind='fact',
        statement='合成测试人物梅莫莉，仍在学习。', support=[dict(node='scenario_Story_055',
            line_id='line:synthetic', text_sha256=sha256(line.encode()).hexdigest())])
    organization = dict(version='character-chat-organization-1', subject_id='memorie',
        anchor_id='postgame-story-055', core=[dict(id='core', title='合成核心',
            content=claim['statement'], claim_ids=[claim['id']], cues=[])], episodes=[], details=[])
    profile = dict(version='memorie-postgame-profile-1', subject_id='memorie', anchor_id='postgame-story-055',
        name='梅莫莉', stage='合成测试的旅程后起点。', source_nodes_sha256=sha256(source.read_bytes()).hexdigest(),
        claims=[claim], chat_organization=organization)
    path = tmp_path / 'profile.json'
    path.write_text(canonical_json(profile), encoding='utf-8')
    profile_sha = sha256(path.read_bytes()).hexdigest()
    personality = dict(version='character-personality-draft-1', status='local-interpretation-candidates',
        base_reviewed_digest=profile_sha, subject_id='memorie', anchor_id='postgame-story-055', items=[
            dict(id='synthetic', title='合成解释', interpretation='可对新事物好奇。', when='闲聊时。',
                choice='提出问题。', expression='简短表达。', limits='不补造经历。', claim_ids=[claim['id']])])
    sidecar = tmp_path / 'personality.json'
    sidecar.write_text(canonical_json(personality), encoding='utf-8')
    request = MemoriePreparationRequest(path, profile_sha, source, sidecar, sha256(sidecar.read_bytes()).hexdigest())
    return request, profile, nodes


def test_facade_prepares_exact_existing_definition_and_two_wires_without_writes(memorie_preparation):
    request, _, _ = memorie_preparation
    before = {p.name: p.read_bytes() for p in request.profile_path.parent.iterdir()}
    view = ApplicationFacade.preview_memorie_companion_preparation(request)
    assert view.status == 'prepared', view
    assert not view.remote_authorized and not view.identity_created
    definition = json.loads(view.definition_json)
    assert definition['source_declaration']['rights_confirmed'] is False
    assert definition['definition_version'] == 'character-definition-approval-2'
    assert definition['execution_ready'] is False
    # The existing freezer can validate the candidate after explicit confirmation.
    from dynamic_subject_agent.reviewed_character_definition import _character_preparation_envelope
    assert _character_preparation_envelope(view.definition_json, view.definition_basis,
        rights_confirmation=True)['definition_basis'] == view.definition_basis
    for exchange in ((), ({'user_text': '合成已提交问题。', 'assistant_text': '合成已提交回复。'},)):
        wire = ApplicationFacade.preview_memorie_companion_message(view, '一个合成问题。', exchange)
        body = json.loads(wire)
        projection = json.loads(body['messages'][1]['content'])
        assert set(projection) == {'character', 'personality', 'exchange', 'current_message'}
        assert body['thinking'] == {'type': 'disabled'} and body['max_tokens'] == 4096
        for forbidden in ('synthetic-identity', 'line:synthetic', 'source_nodes_sha256', 'claim_ids',
                          'scenario_Story', '系统按兴趣推荐', '插画', str(request.profile_path)):
            assert forbidden not in wire.decode()
    assert before == {p.name: p.read_bytes() for p in request.profile_path.parent.iterdir()}


@pytest.mark.parametrize('change', ['profile', 'source', 'personality', 'missing', 'null-digest'])
def test_changed_or_unbound_sources_cannot_be_prepared(memorie_preparation, change):
    request, _, _ = memorie_preparation
    if change == 'null-digest':
        request = replace(request, profile_sha256=None)
    elif change == 'missing':
        request = replace(request, nodes_path=request.nodes_path.with_name('missing.json'))
    else:
        path = {'profile': request.profile_path, 'source': request.nodes_path,
                'personality': request.personality_path}[change]
        path.write_text('{}', encoding='utf-8')
    assert ApplicationFacade.preview_memorie_companion_preparation(request).status in (
        'rejected', 'failed-closed', 'unavailable')


@pytest.mark.parametrize('exchange', [({'user_text': '不完整'},), tuple(
    {'user_text': '合成问题', 'assistant_text': '合成回复'} for _ in range(3)),
    ({'user_text': '字' * 4000, 'assistant_text': '超界'},)])
def test_preview_rejects_incomplete_or_oversized_exchange(memorie_preparation, exchange):
    view = ApplicationFacade.preview_memorie_companion_preparation(memorie_preparation[0])
    with pytest.raises(ValueError):
        ApplicationFacade.preview_memorie_companion_message(view, '问题', exchange)


def test_changed_preparation_witness_is_not_a_request(memorie_preparation):
    view = ApplicationFacade.preview_memorie_companion_preparation(memorie_preparation[0])
    with pytest.raises(ValueError):
        ApplicationFacade.preview_memorie_companion_message(replace(view, review_basis='0' * 64), '问题')


def test_changed_asset_cannot_keep_old_freeze_basis_even_with_rehashed_labels(memorie_preparation):
    view = ApplicationFacade.preview_memorie_companion_preparation(memorie_preparation[0])
    definition = json.loads(view.definition_json)
    asset = json.loads(definition['runtime_asset_json'])
    asset['eligible'][0]['statement'] = '伪造的另一份定义。'
    definition['runtime_asset_json'] = canonical_json(asset)
    definition['runtime_asset_sha'] = sha256(canonical_json(asset).encode()).hexdigest()
    scope = json.loads(view.scope_json)
    scope['runtime_asset_sha'] = definition['runtime_asset_sha']
    altered = replace(view, definition_json=canonical_json(definition), scope_json=canonical_json(scope),
        review_basis=sha256(canonical_json(dict(definition_basis=view.definition_basis, scope=scope)).encode()).hexdigest())
    with pytest.raises(ValueError):
        ApplicationFacade.preview_memorie_companion_message(altered, '问题')

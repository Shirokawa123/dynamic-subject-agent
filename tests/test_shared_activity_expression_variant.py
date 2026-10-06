"""The closed same-use candidate changes expression, never source projection."""
from copy import deepcopy
from hashlib import sha256

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_shared_activity import LocalAdapter, select, step_request
from test_shared_activity_live import live_fixture, SharedTransport
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from dynamic_subject_agent.local_product import (
    open_shared_activity_product_live, open_shared_activity_product_local, validate_shared_activity_entry)
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING, contract_variant, whole_publication_key
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.shared_activity import (
    shared_contract, shared_reply_policy, build_reply_preview, digest, SHARED_EXPRESSION_POLICY_SHA)
from dynamic_subject_agent.shared_activity_live import (
    ApprovedSharedActivityGrant, APPROVED_SHARED_REVIEW, POLICY_HASHES,
    shared_live_contract, open_shared_activity_audit, SharedActivityDelivery)
from dynamic_subject_agent.shared_activity_remote_preview import shared_remote_request_preview


def candidate_options(options):
    return dict(options, grant=ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True, 'natural-expression'),
        technical_variant='natural-expression')


def test_old_exact_contract_policy_and_wire_pins_are_unchanged():
    baseline = shared_live_contract(APPROVED_BINDING)
    assert digest(baseline) == 'f37edb00aec3e999fc0ed0c09c5b30a9535a5e882054a3fc9c75db40e4666f66'
    assert digest(shared_contract(APPROVED_BINDING)) == '0b60787ec732c7c35b5e124497b0600f94d146b28d8a17aea049594163dba7e5'
    assert sha256(shared_reply_policy().encode()).hexdigest() == POLICY_HASHES[1]
    candidate = shared_live_contract(APPROVED_BINDING, technical_variant='natural-expression')
    assert contract_variant(candidate) == 'shared-live'
    assert whole_publication_key(candidate) != whole_publication_key(baseline)
    assert candidate['policy_sha'] == candidate['technical_variant']['chat_policy_sha'] == SHARED_EXPRESSION_POLICY_SHA
    assert candidate['technical_variant']['expression_variant'] == 'natural-expression'
    for field in ('max_current_chars', 'max_complete_turns', 'max_exchange_chars', 'max_reply_chars',
        'provider', 'credential_use', 'max_requests_per_turn', 'automatic_retries'):
        assert candidate[field] == baseline[field]
    task = ModelTask(ModelTaskKind.SHARED_ACTIVITY_REPLY, dict(policy=shared_reply_policy(), payload={}))
    # A selected candidate cannot fall back to a caller's baseline policy.
    with pytest.raises(ValueError, match='exact local execution policy'):
        shared_remote_request_preview(task, technical_variant='natural-expression')


def test_candidate_facade_builds_exact_wire_with_identical_material_and_activity_fields(live_fixture):
    _, config, options, binding = live_fixture
    transport = SharedTransport(); observations = []
    product = open_shared_activity_product_live(config, **candidate_options(options), _transport=transport, observations=observations)
    try:
        snapshot = LocalIdentityAuthority(config).try_whole_scope_snapshot(product.profile_id, product.timeline_id)
        initial = product.application.query_shared_activity().view
        message = '合成SOURCE桌边留白。'
        args = (snapshot['envelope'], snapshot['identity'], message, CharacterDialogueBasis('available'), True, initial)
        baseline = build_reply_preview(*args, shared_live_contract(binding))
        candidate = build_reply_preview(*args, snapshot['contract'])
        assert candidate['payload'] == baseline['payload']
        assert candidate['policy'] != baseline['policy']
        assert set(candidate['payload']) == {'turn', 'background', 'exchange', 'evidence'}
        assert send(product, message, 'candidate-source').status == 'terminal'
        wire = shared_remote_request_preview(ModelTask(ModelTaskKind.SHARED_ACTIVITY_REPLY, candidate), technical_variant='natural-expression')
        assert transport.calls[0] == wire['body'] and observations[0]['wire_sha256'] == wire['wire_sha256']
        validate_shared_activity_entry(config, profile_id=product.profile_id, timeline_id=product.timeline_id,
            technical_variant='natural-expression')
        with pytest.raises(RuntimeError, match='entry-identity-unverified'):
            validate_shared_activity_entry(config, profile_id=product.profile_id, timeline_id=product.timeline_id)
        assert select(product, 'SOURCE桌边留白').status == 'committed'
        preview = product.application.preview_shared_activity_step().view
        request = step_request(product)
        assert product.application.advance_shared_activity(request).status == 'committed'
        old_wire = shared_remote_request_preview(ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE, preview))
        new_wire = shared_remote_request_preview(ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE, preview), technical_variant='natural-expression')
        assert old_wire == new_wire and transport.calls[-1] == old_wire['body']
        saved, record = history(product), product.application.query_shared_activity().view
    finally:
        product.close()
    fresh = SharedTransport()
    product = open_shared_activity_product_live(config, **candidate_options(options), _transport=fresh)
    try:
        assert history(product) == saved and product.application.query_shared_activity().view == record
        assert product.application.query_shared_activity(request).status == 'replayed'
        assert not fresh.calls
    finally:
        product.close()


def test_unknown_conflicting_and_existing_variant_selection_is_closed_before_side_effects(live_fixture):
    opening, config, options, _ = live_fixture
    transport = SharedTransport()
    with pytest.raises(ValueError):
        ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True, 'unknown')
    before = config.state_path.read_bytes()
    for overrides in (dict(technical_variant='unknown'), dict(technical_variant='natural-expression')):
        with pytest.raises(ValueError):
            open_shared_activity_product_live(config, **dict(options, **overrides), _transport=transport)
    assert config.state_path.read_bytes() == before and not options['audit_path'].exists() and not transport.calls
    product = opening(transport)
    assert send(product, '原baseline已提交消息。', 'baseline-source').status == 'terminal'
    saved = history(product); product.close()
    before = config.state_path.read_bytes(); audit = open_shared_activity_audit(options['audit_path']).snapshot()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        open_shared_activity_product_live(config, **candidate_options(options), _transport=transport)
    assert config.state_path.read_bytes() == before and open_shared_activity_audit(options['audit_path']).snapshot() == audit
    fresh = SharedTransport(); product = opening(fresh)
    assert history(product) == saved
    result = send(product, '原baseline已提交消息。', 'baseline-source')
    assert result.status == 'terminal' and result.replayed and not fresh.calls


def test_local_preparation_identity_cannot_be_upgraded_to_candidate(live_fixture):
    _, config, options, binding = live_fixture
    adapter = LocalAdapter()
    product = open_shared_activity_product_local(config, gateway=ModelGateway(adapter), identity_id=options['identity_id'], binding=binding)
    product.close(); before = config.state_path.read_bytes(); transport = SharedTransport()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        open_shared_activity_product_live(config, **candidate_options(options), _transport=transport)
    assert config.state_path.read_bytes() == before and not options['audit_path'].exists() and not transport.calls


def test_candidate_policy_source_mutation_is_rejected_before_admission(live_fixture, monkeypatch):
    _, config, options, _ = live_fixture
    transport = SharedTransport()
    product = open_shared_activity_product_live(config, **candidate_options(options), _transport=transport)
    try:
        import dynamic_subject_agent.shared_activity as module
        with monkeypatch.context() as changed:
            changed.setattr(module, 'NATURAL_EXPRESSION_SCOPE_PARAGRAPH', module.NATURAL_EXPRESSION_SCOPE_PARAGRAPH + 'changed')
            rejected = send(product, '尚未准入的合成文字。', 'candidate-mutated-policy')
        assert rejected.status == 'failed-closed' and rejected.operation_ref is None
        assert not transport.calls and not history(product)
        assert open_shared_activity_audit(options['audit_path']).snapshot() == ()
    finally:
        product.close()


def test_caller_policy_mutation_cannot_replace_canonical_candidate(live_fixture, monkeypatch):
    _, config, options, _ = live_fixture
    transport = SharedTransport()
    product = open_shared_activity_product_live(config, **candidate_options(options), _transport=transport)
    original = SharedActivityDelivery.claim
    def change(self, operation, task, rebuild):
        payload = deepcopy(task.payload)
        payload['policy'] = shared_reply_policy('baseline')
        return original(self, operation, ModelTask(task.kind, payload), rebuild)
    try:
        with monkeypatch.context() as changed:
            changed.setattr(SharedActivityDelivery, 'claim', change)
            result = send(product, '同材料的合成提问。', 'candidate-caller-policy')
        assert result.status == 'failed-closed' and result.projection.failure_code == 'original-whole-delivery-unverified'
        assert not transport.calls and not history(product)
        assert open_shared_activity_audit(options['audit_path']).snapshot() == ()
    finally:
        product.close()

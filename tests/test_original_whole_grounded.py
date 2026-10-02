from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.original_whole_chat import (APPROVED_BINDING, WHOLE_USE_POLICY, JSON_EXAMPLE_SUFFIX,
    GROUNDED_SCOPE_PARAGRAPH, whole_contract, digest, policy_for_contract, projection_for_contract,
    whole_publication_key, contract_variant)
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
from test_original_whole_chat import whole_fixture, approved, personality_fixture, model_fixture, WholeTransport, send, history


def test_grounded_replaces_only_one_scope_paragraph_and_binds_existing_components():
    baseline = whole_contract(APPROVED_BINDING)
    followup = whole_contract(APPROVED_BINDING, technical_variant="followup")
    example = whole_contract(APPROVED_BINDING, technical_variant="json-example")
    grounded = whole_contract(APPROVED_BINDING, technical_variant="grounded")
    old_scope = "当前可以提出意见或新设想，不补造过去、近期活动、画作完成、外部反馈或持续心理活动。"
    policy = policy_for_contract(grounded)
    assert policy == WHOLE_USE_POLICY.replace(old_scope, GROUNDED_SCOPE_PARAGRAPH, 1) + JSON_EXAMPLE_SUFFIX
    assert policy.count(GROUNDED_SCOPE_PARAGRAPH) == 1 and old_scope not in policy
    assert grounded["policy_sha"] == sha256(policy.encode()).hexdigest()
    assert grounded["technical_variant"]["selector_version"] == followup["technical_variant"]["selector_version"]
    assert grounded["technical_variant"]["selector_digest"] == followup["technical_variant"]["selector_digest"]
    assert grounded["technical_variant"]["json_example_version"] == example["technical_variant"]["version"]
    assert "-s130-" in whole_publication_key(grounded) and len(whole_publication_key(grounded)) <= 256
    assert digest(baseline) == "764d47ab726959464aae403d809843f0ed624c07bc4bc1ff32016243d2c73731"
    assert policy_for_contract(baseline) == policy_for_contract(followup) == WHOLE_USE_POLICY
    assert policy_for_contract(example) == WHOLE_USE_POLICY + JSON_EXAMPLE_SUFFIX
    assert example["policy_sha"] == "248599e8253f3f674c46afb24a60785d273ae94f029b5c2a24a5f431836536f5"


def test_grounded_gateway_uses_exact_v2_selection_and_existing_protocol(whole_fixture):
    opening, options, config, _ = whole_fixture
    opening().close()
    loaded = LocalIdentityAuthority(config).load_active()
    binding = {key: loaded.qri.reviewed_chat_contract[key] for key in APPROVED_BINDING}
    followup = whole_contract(binding, technical_variant="followup")
    grounded = whole_contract(binding, technical_variant="grounded")
    dialogue = CharacterDialogueBasis("available", True, (RecentDialogueTurn("你小时候怎么学画的？", "无据的旧助手细节。"),))
    projection = projection_for_contract(loaded.reviewed_definition, loaded.runtime_identity, "当时是什么样？", dialogue, True, grounded)
    old_projection = projection_for_contract(loaded.reviewed_definition, loaded.runtime_identity, "当时是什么样？", dialogue, True, followup)
    assert projection == old_projection and len(projection.background["self_knowledge"]) == 1
    assert set(asdict(projection)) == {"turn", "background", "exchange", "evidence"}
    from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, open_original_whole_audit
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind
    transport = WholeTransport()
    delivery = OriginalWholeDelivery(open_original_whole_audit(options["audit_path"]), contract=grounded, state_path=config.state_path)
    gateway = ModelGateway(DeepSeekOriginalWholeAdapter(transport=transport, delivery=delivery, envelope=loaded.reviewed_definition,
        credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    delivery.claim("d" * 64, "e" * 64, digest(asdict(projection)))
    result = gateway.execute(ModelTask(ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY, projection))
    delivery.record("complete", value=result.value)
    body = transport.calls[0]
    assert body["messages"][0]["content"] == policy_for_contract(grounded)
    assert json.loads(body["messages"][1]["content"]) == json.loads(json.dumps(asdict(projection)))
    assert body["thinking"] == {"type": "enabled"} and body["reasoning_effort"] == "high" and body["max_tokens"] == 4096
    assert body["response_format"] == {"type": "json_object"} and body["stream"] is False
    assert set(result.value) == {"reply_text", "language"} and len(transport.calls) == 1


def test_grounded_facade_continuity_noop_history_off_and_reopen(whole_fixture):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport()
    product = opening(transport, technical_variant="grounded")
    first = send(product, "你小时候怎么学画的？", "ground-first")
    assert first.status == "terminal" and first.projection.living_memory_status == "no-op"
    assert first.projection.relationship_event is None and first.projection.committed_effect_count == 0
    assert send(product, "当时是什么样？", "ground-followup").status == "terminal"
    assert len(json.loads(transport.calls[-1]["messages"][1]["content"])["background"]["self_knowledge"]) == 1
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert send(product, "为什么呢？", "ground-off").status == "terminal"
    payload = json.loads(transport.calls[-1]["messages"][1]["content"])
    assert payload["exchange"] == [] and payload["background"]["self_knowledge"] == []
    saved = history(product)
    product.close()
    transport2 = WholeTransport()
    reopened = opening(transport2, technical_variant="grounded")
    assert history(reopened) == saved and not transport2.calls
    assert send(reopened, "你小时候怎么学画的？", "ground-first").replayed and not transport2.calls


def test_grounded_witness_cannot_change_policy_selector_or_bound_root(whole_fixture):
    opening, options, config, _ = whole_fixture
    before = config.state_path.read_bytes()
    with pytest.raises(ValueError):
        opening(technical_variant="grounded-with-extra-checker")
    assert config.state_path.read_bytes() == before and not options["audit_path"].exists()
    opening(technical_variant="json-example").close()
    before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError, match="activation-conflict"):
        opening(technical_variant="grounded")
    assert config.state_path.read_bytes() == before
    loaded = LocalIdentityAuthority(config).load_active()
    binding = {key: loaded.qri.reviewed_chat_contract[key] for key in APPROVED_BINDING}
    grounded = whole_contract(binding, technical_variant="grounded")
    for key in ("selector_digest", "json_example_version", "policy_sha"):
        forged = deepcopy(grounded)
        forged["technical_variant"][key] = "unapproved"
        with pytest.raises(ValueError):
            contract_variant(forged)
    forged = deepcopy(grounded)
    forged["policy"] = "PRIVATE_CALLER_POLICY"
    with pytest.raises(ValueError):
        policy_for_contract(forged)

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.original_whole_chat import (APPROVED_BINDING, WHOLE_USE_POLICY, JSON_EXAMPLE_SUFFIX,
    whole_contract, contract_variant, policy_for_contract, whole_publication_key, whole_projection,
    projection_for_contract, digest, _legacy_followup_contract)
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from test_original_whole_chat import whole_fixture, approved, personality_fixture, model_fixture, WholeTransport, send, history


def test_json_example_is_closed_format_only_and_preserves_all_old_contracts():
    baseline = whole_contract(APPROVED_BINDING)
    followup = whole_contract(APPROVED_BINDING, technical_variant="followup")
    example = whole_contract(APPROVED_BINDING, technical_variant="json-example")
    assert digest(baseline) == "764d47ab726959464aae403d809843f0ed624c07bc4bc1ff32016243d2c73731"
    assert followup["technical_variant"]["selector_digest"] == "d43da99fa070ed3d3e27e40f59b15297854eaecbd6243d101f9dfbae1532bc87"
    assert policy_for_contract(baseline) == policy_for_contract(followup) == WHOLE_USE_POLICY
    assert policy_for_contract(example) == WHOLE_USE_POLICY + JSON_EXAMPLE_SUFFIX
    assert example["policy_sha"] == sha256(policy_for_contract(example).encode()).hexdigest()
    assert example["technical_variant"]["selector"] == "baseline"
    literal = JSON_EXAMPLE_SUFFIX.split("：", 1)[1].split("\n", 1)[0]
    assert json.loads(literal) == dict(reply_text="按当前话题自然回答。", language="zh")
    assert "不是人物台词" in JSON_EXAMPLE_SUFFIX and "不要复述" in JSON_EXAMPLE_SUFFIX
    assert whole_publication_key(example) != whole_publication_key(baseline)
    assert "-s129-" in whole_publication_key(example) and len(whole_publication_key(example)) <= 256
    assert contract_variant(_legacy_followup_contract(APPROVED_BINDING)) == "followup-legacy"
    with pytest.raises(ValueError, match="receipt-only"):
        policy_for_contract(_legacy_followup_contract(APPROVED_BINDING))


def test_gateway_example_changes_only_system_policy_and_keeps_baseline_selection(whole_fixture):
    opening, options, config, _ = whole_fixture
    opening().close()
    loaded = LocalIdentityAuthority(config).load_active()
    binding = {key: loaded.qri.reviewed_chat_contract[key] for key in APPROVED_BINDING}
    example_contract = whole_contract(binding, technical_variant="json-example")
    dialogue = CharacterDialogueBasis("available", True, (RecentDialogueTurn("你小时候怎么学画的？", "合成历史回复。"),))
    baseline_projection = whole_projection(loaded.reviewed_definition, loaded.runtime_identity, "当时是什么样？", dialogue, True)
    example_projection = projection_for_contract(loaded.reviewed_definition, loaded.runtime_identity, "当时是什么样？", dialogue, True, example_contract)
    assert canonical(example_projection) == canonical(baseline_projection)
    assert example_projection.background["self_knowledge"] == ()
    from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, open_original_whole_audit
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind
    bodies = []
    for number, contract in enumerate((loaded.qri.reviewed_chat_contract, example_contract)):
        transport = WholeTransport()
        delivery = OriginalWholeDelivery(open_original_whole_audit(options["audit_path"]), contract=contract, state_path=config.state_path)
        adapter = DeepSeekOriginalWholeAdapter(transport=transport, delivery=delivery, envelope=loaded.reviewed_definition,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
        delivery.claim("a" * 64, str(number) * 64, digest(asdict(example_projection)))
        value = ModelGateway(adapter).execute(ModelTask(ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY, example_projection)).value
        delivery.record("complete", value=value)
        assert value == dict(reply_text="合成单阶段回复。", language="zh")
        bodies.append(transport.calls[0])
    first, second = deepcopy(bodies[0]), deepcopy(bodies[1])
    assert second["messages"][0]["content"] == first["messages"][0]["content"] + JSON_EXAMPLE_SUFFIX
    second["messages"][0]["content"] = first["messages"][0]["content"]
    assert second == first


def canonical(value):
    from dynamic_subject_agent.frozen_attempt import canonical_json
    return canonical_json(asdict(value))


def test_json_example_facade_continuity_history_off_and_reopen(whole_fixture):
    opening, _, _, _ = whole_fixture
    transport, rows = WholeTransport(), []
    product = opening(transport, rows, technical_variant="json-example")
    assert not transport.calls
    first = send(product, "你小时候怎么学画的？", "example-first")
    assert first.status == "terminal" and first.projection.expression_text != "按当前话题自然回答。"
    assert send(product, "当时是什么样？", "example-second").status == "terminal"
    payload = json.loads(transport.calls[-1]["messages"][1]["content"])
    assert payload["background"]["self_knowledge"] == [] and len(payload["exchange"]) == 1
    assert payload["evidence"] == dict(current_activity=None, current_plan=None, related_event=None)
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert send(product, "换个话题。", "example-off").status == "terminal"
    assert json.loads(transport.calls[-1]["messages"][1]["content"])["exchange"] == []
    saved = history(product)
    product.close()
    transport2 = WholeTransport()
    reopened = opening(transport2, technical_variant="json-example")
    assert history(reopened) == saved and not transport2.calls
    assert send(reopened, "你小时候怎么学画的？", "example-first").replayed and not transport2.calls
    assert all("payload" not in row and "value" not in row and "final_content" not in row for row in rows)


def test_unknown_policy_mixing_or_bound_root_switch_is_rejected(whole_fixture):
    opening, _, config, _ = whole_fixture
    before = config.state_path.read_bytes()
    with pytest.raises(ValueError):
        opening(technical_variant="json-example+followup")
    assert config.state_path.read_bytes() == before
    product = opening(technical_variant="json-example")
    product.close()
    before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError, match="activation-conflict"):
        opening(technical_variant="followup")
    assert config.state_path.read_bytes() == before
    loaded = LocalIdentityAuthority(config).load_active()
    for field, text in (("policy", "PRIVATE_CALLER_POLICY"), ("policy_sha", "0" * 64)):
        forged = deepcopy(loaded.qri.reviewed_chat_contract)
        forged[field] = text
        with pytest.raises(ValueError):
            policy_for_contract(forged)
    forged = deepcopy(loaded.qri.reviewed_chat_contract)
    forged["technical_variant"]["selector"] = "followup"
    with pytest.raises(ValueError):
        policy_for_contract(forged)


def test_gateway_rejects_mutated_caller_policy_before_transport(whole_fixture):
    opening, options, config, _ = whole_fixture
    opening(technical_variant="json-example").close()
    loaded = LocalIdentityAuthority(config).load_active()
    from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, open_original_whole_audit
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind, ModelGatewayFailure
    projection = projection_for_contract(loaded.reviewed_definition, loaded.runtime_identity, "普通合成问题。",
        CharacterDialogueBasis("available"), True, loaded.qri.reviewed_chat_contract)
    delivery = OriginalWholeDelivery(open_original_whole_audit(options["audit_path"]), contract=deepcopy(loaded.qri.reviewed_chat_contract),
        state_path=config.state_path)
    transport = WholeTransport()
    adapter = DeepSeekOriginalWholeAdapter(transport=transport, delivery=delivery, envelope=loaded.reviewed_definition,
        credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
    delivery.contract["policy"] = "PRIVATE_CALLER_POLICY"
    delivery.claim("b" * 64, "c" * 64, digest(asdict(projection)))
    with pytest.raises(ModelGatewayFailure):
        ModelGateway(adapter).execute(ModelTask(ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY, projection))
    delivery.record("failed-closed")
    assert not transport.calls and delivery.counts() == (None, 1, None)

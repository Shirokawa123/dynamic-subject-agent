import json
from dataclasses import replace

import pytest

from test_conversation_basis import local_basis
from test_character_dialogue import Adapter, Transport, request
from dynamic_subject_agent.character_dialogue import (
    GROUNDED_POLICY, grounded_plan_digest, grounded_plan_payload, plan_digest, DialogueProjection,
)
from dynamic_subject_agent.character_dialogue_provider import DeepSeekCharacterDialogueAdapter
from dynamic_subject_agent.local_product import open_character_dialogue_lab
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID


def test_material_reaches_one_reply_task_without_source_details(local_basis):
    create, _, _, _ = local_basis
    adapter = Adapter()
    product, _ = create(adapter=adapter)
    app = product.application
    first = request(app, "谁教你画画的？")
    result = app.character_dialogue_send(first)
    assert result.status == "replied" and result.material_mode == "bounded"
    assert result.plan_digest == grounded_plan_digest()
    assert app.character_dialogue_send(first) == result
    assert len(adapter.calls) == 1
    payload = adapter.calls[0]
    assert set(payload) == {"character", "current_message", "recent_dialogue", "selected_character_material"}
    assert payload["selected_character_material"] == [{"content": "最初是母亲教她画画。"}]
    assert "synthetic.epub" not in json.dumps(payload)
    assert "citations" not in json.dumps(payload)
    app.character_dialogue_send(request(app, "接着聊吧"))
    assert adapter.calls[1]["selected_character_material"] == []
    assert adapter.calls[1]["recent_dialogue"] == [{"user_text": first.message, "assistant_text": "收到。"}]
    assert app.character_dialogue_send(replace(first, message="changed")).code == "key-conflict"


def test_bad_source_stops_generation_consumes_attempt_and_honors_history_control(local_basis):
    create, _, book, _ = local_basis
    adapter = Adapter()
    product, _ = create(adapter=adapter)
    app = product.application
    app.character_dialogue_send(request(app, "谁教你画画的？"))
    original = book.read_bytes()
    book.write_bytes(original + b"changed")
    bad = request(app, "最初是谁教你画画的？")
    result = app.character_dialogue_send(bad)
    assert result.status == "failed-closed" and result.code == "basis-integrity-failed"
    assert result.attempts == 2 and not result.history_enabled
    assert len(adapter.calls) == 1
    book.write_bytes(original)
    assert app.character_dialogue_send(bad) == result  # No automatic retry after repair.
    app.character_dialogue_send(request(app, "你画画多久了？"))
    assert len(adapter.calls) == 2 and adapter.calls[-1]["recent_dialogue"] == []
    assert len(adapter.calls[-1]["selected_character_material"]) == 1


def test_missing_source_cannot_silently_fall_back_for_matched_request(local_basis):
    create, _, book, _ = local_basis
    adapter = Adapter()
    product, _ = create(adapter=adapter)
    book.rename(book.with_suffix(".held"))
    result = product.application.character_dialogue_send(request(product.application, "你画画多久了？"))
    assert result.status == "unavailable" and result.attempts == 1
    assert adapter.calls == []


def test_grounded_wire_has_only_bounded_content_and_new_policy(local_basis):
    create, _, _, _ = local_basis
    transport = Transport({"reply_text": "这是合成响应。", "language": "zh"})
    adapter = DeepSeekCharacterDialogueAdapter(transport=transport, credential_ref=CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
    product, _ = create(adapter=adapter)
    app = product.application
    assert app.character_dialogue_send(request(app, "你是怎么开始画画的？")).status == "replied"
    wire = json.loads(transport.calls[0]["body"])
    assert wire["messages"][0]["content"] == GROUNDED_POLICY
    payload = json.loads(wire["messages"][1]["content"])
    assert len(payload["selected_character_material"]) == 2
    assert all(set(x) == {"content"} for x in payload["selected_character_material"])
    assert "synthetic" not in json.dumps(wire)
    assert wire["max_tokens"] == 400
    for contents in (("not-reviewed",), ("最初是母亲教她画画。",) * 3):
        with pytest.raises(ValueError):
            DeepSeekCharacterDialogueAdapter.outbound_bytes(DialogueProjection("你好", selected_material=contents))


def test_old_plan_cannot_activate_grounded_mode_and_offline_never_reads_key(tmp_path, monkeypatch):
    from dynamic_subject_agent.credentials import WindowsCredentialStore
    monkeypatch.setattr(WindowsCredentialStore, "load", lambda *args: pytest.fail("no real credentials"))
    with pytest.raises(ValueError, match="approval"):
        open_character_dialogue_lab(tmp_path / "labs", basis_workspace=tmp_path, grounded=True, approved_plan=plan_digest())
    with pytest.raises(ValueError, match="workspace"):
        open_character_dialogue_lab(tmp_path / "labs", grounded=True)
    with open_character_dialogue_lab(tmp_path / "labs", basis_workspace=tmp_path, grounded=True) as product:
        app = product.application
        assert app.character_dialogue_status().mode == "offline"
        assert app.character_dialogue_send(request(app, "谁教你画画的？")).status == "unavailable"
    assert plan_digest() == "e2e01984ef27017754a81571c9a5f73857f4818809cbcd030c93bd3b6d59e7d0"
    assert grounded_plan_payload()["trial_attempts"] == 8
    assert grounded_plan_payload()["remaining_user_attempts"] == 12


def test_twenty_attempts_shared_between_fixed_checks_and_user_chat(local_basis):
    create, _, _, _ = local_basis
    adapter = Adapter()
    product, _ = create(adapter=adapter)
    app = product.application
    from dynamic_subject_agent.character_dialogue import GROUNDED_TEST_MESSAGES
    for message in GROUNDED_TEST_MESSAGES:
        assert app.character_dialogue_send(request(app, message)).status == "replied"
    current = app.start_character_dialogue_interactive()
    assert current.attempts == 8 and current.history_enabled and current.revision == 9
    assert app.start_character_dialogue_interactive() == current
    for _ in range(12):
        assert app.character_dialogue_send(request(app, "现在聊聊画画吧")).status == "replied"
    assert adapter.calls[8]["recent_dialogue"] == []
    assert len(adapter.calls[9]["recent_dialogue"]) == 1
    assert app.character_dialogue_send(request(app)).code == "attempt-budget-exhausted"
    assert len(adapter.calls) == 20


def test_failed_trial_cannot_start_interactive_or_reset_budget(local_basis):
    create, _, _, _ = local_basis
    adapter = Adapter()
    product, _ = create(adapter=adapter)
    app = product.application
    assert app.start_character_dialogue_interactive().code == "trial-not-complete"
    adapter.fail = True
    for _ in range(8):
        app.character_dialogue_send(request(app, "你好"))
    assert app.start_character_dialogue_interactive().code == "trial-not-complete"
    assert app.character_dialogue_status().attempts == 8


def test_eight_arbitrary_successes_are_not_the_reviewed_trial(local_basis):
    create, _, _, _ = local_basis
    product, _ = create(adapter=Adapter())
    app = product.application
    for _ in range(8):
        assert app.character_dialogue_send(request(app, "你好")).status == "replied"
    assert app.start_character_dialogue_interactive().code == "trial-not-complete"
    assert app.character_dialogue_status().attempts == 8

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.character_dialogue import (
    CAPSULE, POLICY, MAX_ATTEMPTS, CharacterDialogueSession, DialogueProjection,
    DialogueReply, DialogueRequest, plan_digest, plan_payload,
)
from dynamic_subject_agent.character_dialogue_provider import DeepSeekCharacterDialogueAdapter
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import (
    DeepSeekTransport, DeepSeekHttpResponse, DEEPSEEK_MODEL, DEEPSEEK_ENDPOINT,
    DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID,
)
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_character_dialogue_lab
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelResult, ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
)


class Adapter(ProviderAdapter):
    capabilities = ProviderCapabilities("test", "test", True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls = []
        self.reply = "收到。"
        self.fail = False

    def invoke(self, task):
        self.calls.append(task.payload.payload())
        if self.fail:
            raise RuntimeError("private transport detail must never reach the UI")
        return ModelResult(task.kind, DialogueReply(self.reply))


@pytest.fixture
def lab(tmp_path):
    opened = []

    def create(adapter=None, enabled=True):
        adapter = adapter or Adapter()
        root = tmp_path / str(len(opened))
        product = open_local_product(LocalProductConfig(root / "experiments", root / "state.json"),
                                    cognition=DormantDeepSeekCognition(),
                                    _character_dialogue=CharacterDialogueSession(ModelGateway(adapter)) if enabled else None)
        opened.append(product)
        return product.application, adapter, root, product

    yield create
    for product in opened:
        product.close()


def request(app, text="你好", key=None, history=None):
    current = app.character_dialogue_status()
    return DialogueRequest(current.lab_id, current.revision, key or f"k{current.revision}", text,
                           current.history_enabled if history is None else history)


def test_default_product_has_no_character_dialogue(lab):
    app, adapter, _, _ = lab(enabled=False)
    assert app.character_dialogue_status().status == "unavailable"
    assert app.character_dialogue_send(request(app)).status == "unavailable"
    assert not adapter.calls


def test_exact_projection_and_canonical_files_unchanged(lab):
    app, adapter, root, _ = lab()

    def snapshot():
        return {p.relative_to(root): sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file()}

    before = snapshot()
    assert app.character_dialogue_send(request(app, "我是新网友")).status == "replied"
    assert app.character_dialogue_send(request(app, "刚才说的是什么？")).status == "replied"
    assert adapter.calls == [
        dict(character=CAPSULE, current_message="我是新网友", recent_dialogue=[]),
        dict(character=CAPSULE, current_message="刚才说的是什么？",
             recent_dialogue=[dict(user_text="我是新网友", assistant_text="收到。")]),
    ]
    assert snapshot() == before


def test_idempotency_conflict_stale_and_cross_lab(lab):
    app, adapter, _, _ = lab()
    other, other_adapter, _, _ = lab()
    first = request(app)
    result = app.character_dialogue_send(first)
    assert app.character_dialogue_send(first) == result
    assert app.character_dialogue_send(replace(first, message="不同内容")).code == "key-conflict"
    assert app.character_dialogue_send(replace(first, use_history=False)).code == "key-conflict"
    assert app.character_dialogue_send(replace(first, idempotency_key="new")).code == "stale-revision"
    assert other.character_dialogue_send(first).code == "wrong-lab"
    other.character_dialogue_send(request(other))
    assert other_adapter.calls[0]["recent_dialogue"] == []
    assert len(adapter.calls) == 1


def test_failed_attempts_are_counted_sanitized_and_never_retried(lab):
    app, adapter, _, _ = lab()
    adapter.fail = True
    first = request(app)
    failure = app.character_dialogue_send(first)
    assert failure.status == "failed-closed" and failure.attempts == 1
    assert "private" not in repr(failure)
    adapter.fail = False
    assert app.character_dialogue_send(first) == failure
    app.character_dialogue_send(request(app, "新消息"))
    assert len(adapter.calls) == 2
    assert adapter.calls[1]["recent_dialogue"] == []


def test_attempt_budget_and_invalid_requests_do_not_call_provider(lab):
    app, adapter, _, _ = lab()
    for bad in (None, replace(request(app), message="x" * 1001),
                replace(request(app), revision=True), replace(request(app), use_history="yes")):
        assert app.character_dialogue_send(bad).code == "invalid-request"
    assert not adapter.calls
    for _ in range(MAX_ATTEMPTS):
        assert app.character_dialogue_send(request(app)).status == "replied"
    assert app.character_dialogue_send(request(app)).code == "attempt-budget-exhausted"
    assert len(adapter.calls) == MAX_ATTEMPTS


def test_history_window_is_complete_and_character_bounded(lab):
    app, adapter, _, _ = lab()
    adapter.reply = "答" * 1200
    for index in range(4):
        app.character_dialogue_send(request(app, str(index) * 1000))
    # Two 2200-character rounds do not fit; only the newest complete round leaves.
    assert adapter.calls[-1]["recent_dialogue"] == [dict(user_text="2" * 1000, assistant_text="答" * 1200)]
    adapter.reply = "短答"
    for text in ("甲", "乙", "丙", "丁"):
        app.character_dialogue_send(request(app, text))
    assert [x["user_text"] for x in adapter.calls[-1]["recent_dialogue"]] == ["乙", "丙"]


@pytest.mark.parametrize("control", ["不要再使用前面的聊天记录。", "删除以前的记忆", "please forget that"])
def test_withdrawal_latches_off_even_on_failure_and_explicit_on_starts_fresh(lab, control):
    app, adapter, _, _ = lab()
    app.character_dialogue_send(request(app, "旧消息"))
    adapter.fail = True
    result = app.character_dialogue_send(request(app, control))
    assert not result.history_enabled
    assert adapter.calls[-1]["recent_dialogue"] == []
    adapter.fail = False
    app.character_dialogue_send(request(app, "关闭后的消息"))
    app.character_dialogue_send(request(app, "明确重新开启", history=True))
    assert adapter.calls[-1]["recent_dialogue"] == []
    app.character_dialogue_send(request(app, "接着聊"))
    assert [x["user_text"] for x in adapter.calls[-1]["recent_dialogue"]] == ["明确重新开启"]


def test_manual_history_off_and_close(lab):
    app, adapter, _, product = lab()
    old = request(app, "旧消息")
    app.character_dialogue_send(old)
    app.character_dialogue_send(request(app, "本轮关闭", history=False))
    app.character_dialogue_send(request(app, "现在开启", history=True))
    assert adapter.calls[-1]["recent_dialogue"] == []
    product.close()
    assert app.character_dialogue_status().status == "unavailable"
    assert app.character_dialogue_send(old).status == "unavailable"


class Transport(DeepSeekTransport):
    def __init__(self, value):
        self.value = value
        self.calls = []

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        return DeepSeekHttpResponse(status_code=200, body=json.dumps(dict(
            model=DEEPSEEK_MODEL, choices=[dict(index=0, finish_reason="stop", message=dict(
                role="assistant", content=json.dumps(self.value, ensure_ascii=False)))],
            usage=dict(prompt_tokens=50, completion_tokens=20, total_tokens=70))).encode())


@pytest.mark.parametrize("value,expected", [
    ({"reply_text": "嗯，看得到。", "language": "zh"}, "replied"),
    ({"reply_text": "嗯", "language": "zh", "memory": "new"}, "failed-closed"),
    ({"reply_text": "x" * 1201, "language": "zh"}, "failed-closed"),
    ({"reply_text": "hello", "language": "en"}, "failed-closed"),
])
def test_wire_contract_through_facade(lab, value, expected):
    transport = Transport(value)
    adapter = DeepSeekCharacterDialogueAdapter(transport=transport, credential_ref=CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
    app, _, _, _ = lab(adapter)
    assert app.character_dialogue_send(request(app)).status == expected
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["endpoint"] == plan_payload()["endpoint"] == DEEPSEEK_ENDPOINT
    wire = json.loads(call["body"])
    assert wire == dict(model=plan_payload()["model"], messages=[dict(role="system", content=POLICY),
        dict(role="user", content=json.dumps(DialogueProjection("你好").payload(), ensure_ascii=False,
                                           sort_keys=True, separators=(",", ":")))],
        max_tokens=400, temperature=0.7, stream=False, thinking={"type": "disabled"},
        response_format={"type": "json_object"})


def test_offline_root_and_wrong_approval_never_touch_credentials(tmp_path, monkeypatch):
    from dynamic_subject_agent.credentials import WindowsCredentialStore

    def forbidden(*args):
        raise AssertionError("credential must not be read")

    monkeypatch.setattr(WindowsCredentialStore, "load", forbidden)
    with pytest.raises(ValueError, match="approval"):
        open_character_dialogue_lab(tmp_path, approved_plan="wrong")
    with open_character_dialogue_lab(tmp_path) as product:
        app = product.application
        assert app.character_dialogue_status().mode == "offline"
        assert app.character_dialogue_send(request(app)).status == "replied"
        assert app.character_dialogue_status().plan_digest == plan_digest()


@pytest.mark.parametrize("backend_failure", [False, True])
def test_missing_secure_credential_is_unavailable_without_network(tmp_path, monkeypatch, backend_failure):
    import dynamic_subject_agent.local_product as root
    from dynamic_subject_agent.credentials import WindowsCredentialStore, CredentialStoreUnavailable
    from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport

    reads = []

    def missing(*args):
        reads.append(True)
        if backend_failure:
            raise CredentialStoreUnavailable("secure-backend-unavailable")
        return None

    # Exercise the real transport's lazy resolver while forbidding an HTTP opener.
    original_init = DeepSeekUrlLibTransport.__init__

    def no_network(*args, **kwargs):
        pytest.fail("credential failure must prevent all network access")

    def initialize(self, **kwargs):
        original_init(self, **kwargs, _opener=no_network)

    monkeypatch.setattr(root, "_REMOTE_LAB_OPENED", False)
    monkeypatch.setattr(WindowsCredentialStore, "load", missing)
    monkeypatch.setattr(DeepSeekUrlLibTransport, "__init__", initialize)
    with root.open_character_dialogue_lab(tmp_path, approved_plan=plan_digest()) as product:
        app = product.application
        assert app.character_dialogue_status().mode == "remote"
        assert not reads
        first = request(app)
        result = app.character_dialogue_send(first)
        assert result.status == "unavailable" and result.code == "credential-unavailable"
        assert result.attempts == 1
        assert app.character_dialogue_send(first) == result
        assert len(reads) == 1
    with pytest.raises(ValueError, match="one remote lab"):
        root.open_character_dialogue_lab(tmp_path, approved_plan=plan_digest())


def test_http_adapter_rejects_foreign_send_and_uses_facade(lab):
    import importlib.util
    from threading import Thread
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    import re

    spec = importlib.util.spec_from_file_location("character_lab", Path(__file__).resolve().parents[1]
                                                / "app/desktop/character_dialogue_lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app, adapter, _, _ = lab()
    server = module.make_server(app)
    thread = Thread(target=server.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base) as response:
            page = response.read().decode()
            assert response.headers["Cache-Control"] == "no-store"
        token = re.search("const token='([^']+)'", page)[1]
        from dataclasses import asdict
        body = json.dumps(asdict(request(app))).encode()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/send", data=body, headers={"Content-Type": "application/json"}))
        assert error.value.code == 403 and not adapter.calls
        with urlopen(Request(base + "/send", data=body, headers={"Content-Type": "application/json",
                                                                "X-Lab-Token": token})) as response:
            assert json.loads(response.read())["status"] == "replied"
        assert len(adapter.calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

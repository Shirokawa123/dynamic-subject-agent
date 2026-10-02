"""Thin entry lifecycle, async HTTP and draft recovery; no real model or account."""
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from dynamic_subject_agent.application import (ApplicationOperationResponse, ApplicationOperationStatus,
    ApplicationProblemView, SubjectRequestLookupResponse, SubjectRequestLookupStatus)
from dynamic_subject_agent.reviewed_character_chat import ReviewedCharacterChatStatus
from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryResponse
from dynamic_subject_agent.character_basis import (CharacterBasisView, CharacterBasisKnowledge,
    CharacterBasisUnit, CharacterBasisInterpretation)
from dynamic_subject_agent.whole_message_scope import WholeMessageScopePreviewView
from dynamic_subject_agent.character_chat_context import SelfKnowledge
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn

ROOT = Path(__file__).resolve().parents[1]


def synthetic_basis():
    fact = CharacterBasisKnowledge("biography", "合成小时候学画的概括。", "fact", "direct", "before", "before")
    belief = CharacterBasisKnowledge("work", "我相信交稿有压力。<img src=x onerror=alert(1)>", "belief", "linked-evidence", "at", "at")
    persona = CharacterBasisInterpretation("合成解释", "可对构图取舍感兴趣。", "讨论画面时", "比较方案", "说本轮理由",
        "不补造过去细节。", "author-interpretation", False)
    return CharacterBasisView("available", subject_name="合成测试人物", subject_identity="合成有限身份。", canon_start="合成起点。",
        stage_description="合成初次交流。", knowledge=(fact, belief), core=(CharacterBasisUnit("合成核心", "核心概括。", (fact,)),),
        details=(CharacterBasisUnit("工作关注", "对压力的信念。", (belief,)),), personality=(persona,),
        source_note="当前封存的已审依据，聊天不是依据。", trace_note="原小说逐段定位尚未接入。", limitations=("不是本轮全部选材或模型推理。",))


def synthetic_scope(text="当前合成草稿。", history=True):
    core = SelfKnowledge("core", "合成人物有限核心。", "fact", "direct", "before", "before")
    related = SelfKnowledge("episode", "已审学习概括。", "fact", "linked-evidence", "before", "before")
    return WholeMessageScopePreviewView("available", current_message=text, history_enabled=history,
        has_prior_committed_exchange=True, character_core=(core,), self_knowledge=(related,), personality_count=4,
        recent_dialogue=(RecentDialogueTurn("先前合成消息。", "先前合成回复。"),) if history else (),
        projection_digest="a"*64, snapshot_fingerprint="b"*64, limitations=("发送前仍重新核对，不增加本轮权限。",))


class FakeWholeFacade:
    def __init__(self):
        self.state = ReviewedCharacterChatStatus("active", "合成测试人物", True, None, 0, None)
        self.turns, self.submissions, self.waits, self.operations, self.finished = [], [], [], {}, set()
        self.lookups, self.outcomes = [], {}

    def reviewed_character_chat_status(self):
        return self.state

    def query(self, query):
        return SimpleNamespace(status=SimpleNamespace(value="available"),
            projection=SimpleNamespace(turns=tuple(self.turns)))

    def submit(self, command, *, idempotency_key):
        self.submissions.append((command, idempotency_key))
        ref = self.operations.setdefault(idempotency_key, object())
        if ref in self.finished:
            return self.result("terminal", ref)
        return self.result("pending", ref)

    def complete(self, ref):
        if ref not in self.finished:
            self.finished.add(ref)
            command = next(command for command, key in self.submissions if self.operations[key] == ref)
            self.turns.append(SimpleNamespace(user_text=command.utterance, assistant_text="合成回复。"))
        return self.result("terminal", ref)

    def wait(self, ref, *, timeout_seconds):
        raise AssertionError("request lookup must not wait, follow or resume")

    def lookup_subject_request(self, request):
        self.lookups.append(request)
        ref = self.operations.get(request.idempotency_key)
        if ref is None:
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.NOT_FOUND)
        original = next(command for command, key in self.submissions if key == request.idempotency_key)
        if original.payload_fingerprint != request.command.payload_fingerprint:
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.UNAVAILABLE,
                problem=ApplicationProblemView("subject-request-payload-mismatch"))
        result = self.outcomes.get(ref) or self.result("terminal" if ref in self.finished else "pending", ref)
        return SubjectRequestLookupResponse(SubjectRequestLookupStatus.FOUND, operation=result)

    def set_reviewed_character_history(self, enabled):
        self.state = replace(self.state, history_enabled=enabled)
        return self.state

    @staticmethod
    def result(status, ref=None, *, text="合成回复。", failure=None):
        projection = SimpleNamespace(expression_text=text, failure_code=failure) if status != "pending" else None
        return ApplicationOperationResponse(ApplicationOperationStatus(status), ref, projection, None)


class FakeBoundaryFacade(FakeWholeFacade):
    def __init__(self):
        super().__init__()
        self.context_revision, self.boundaries, self.boundary_calls = 0, {}, []

    def query_whole_context_boundary(self, original_request=None):
        pending = any(ref not in self.finished and ref not in self.outcomes for ref in self.operations.values())
        value = dict(status="available", context_revision=self.context_revision,
            cutoff_sequence=self.context_revision * 3, has_prior_committed_exchange=bool(self.turns),
            pending=pending, basis={})
        if original_request is not None:
            stored = self.boundaries.get(original_request.request_id)
            if stored is None:
                value["request_status"] = "busy" if pending else "not-found"
            elif stored[0] != original_request.request_digest:
                value["request_status"] = "conflict"
            else:
                value.update(request_status="replayed", receipt=stored[1])
        return value

    def apply_whole_context_boundary(self, request):
        self.boundary_calls.append(request)
        if not request.confirmed:
            return WholeContextBoundaryResponse("unavailable", problem_code="confirmation-required")
        stored = self.boundaries.get(request.request_id)
        if stored is not None:
            return WholeContextBoundaryResponse("replayed", stored[1]) if stored[0] == request.request_digest else WholeContextBoundaryResponse("conflict")
        if request.expected_revision != self.context_revision:
            return WholeContextBoundaryResponse("conflict")
        self.context_revision += 1
        receipt = dict(context_revision=self.context_revision, cutoff_sequence=self.context_revision * 3,
            request_digest=request.request_digest, operation_ref=dict(kind="system", operation_id=str(uuid4())))
        self.boundaries[request.request_id] = request.request_digest, receipt
        return WholeContextBoundaryResponse("committed", receipt)


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "app/desktop"))
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import original_whole_chat
    spec = importlib.util.spec_from_file_location("original_whole_entry_script", ROOT / "scripts/serve_original_whole_chat.py")
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    return original_whole_chat, entry


def fake_product(facade=None):
    return SimpleNamespace(application=facade or FakeWholeFacade(), profile_id=str(uuid4()), timeline_id=str(uuid4()))


def test_http_async_exact_input_nonce_read_only_status_and_no_extra_permissions(modules):
    desktop, _ = modules
    product, reopens = fake_product(), []
    def reopen():
        reopens.append(True)
        return product
    server = desktop.original_whole_server(product, reopen=reopen)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            page = response.read().decode()
        token = re.search(r"TOKEN='([^']+)'", page).group(1)
        def get(path):
            with urlopen(base + path, timeout=5) as response:
                return json.load(response)
        def post(path, payload, **headers):
            with urlopen(Request(base + path, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Chat-Token": token, **headers}), timeout=5) as response:
                return json.load(response)
        assert get("/health") == dict(application=desktop.APPLICATION_ID)
        assert get("/status")["history"]["turns"] == []
        nonce = str(uuid4())
        for payload in ({}, dict(text="消息", request_id=nonce, attachment="file"),
            dict(text="", request_id=nonce), dict(text="a\x00b", request_id=nonce),
            dict(text="字" * 1001, request_id=nonce), dict(text=True, request_id=nonce),
            dict(text="消息", request_id="invalid")):
            with pytest.raises(HTTPError) as error:
                post("/send", payload)
            assert error.value.code == 400
        assert not product.application.submissions
        payload = dict(text="  明确提交的合成消息\n", request_id=nonce)
        first = post("/send", payload)
        assert first["ok"] and first["pending"] and not first["settled"] and first["request_id"] == nonce
        assert product.application.submissions[0][0].utterance == payload["text"]
        status = get("/status")
        assert status["pending_handle"] == first["pending"] and status["pending_request_id"] == nonce
        assert not product.application.waits and len(product.application.operations) == 1
        assert not post("/reload", {})["ok"] and not reopens
        repeated = post("/send", payload)
        assert repeated["pending"] == first["pending"] and len(product.application.operations) == 1
        for handle in (None, {}, "foreign-operation"):
            with pytest.raises(HTTPError) as error:
                post("/operation", dict(handle=handle))
            assert error.value.code == 400
        observed = post("/operation", dict(handle=first["pending"]))
        assert observed["pending"] == first["pending"] and observed["request_verified"]
        assert not product.application.finished and len(product.application.submissions) == 2
        ref = product.application.operations["original-whole-" + nonce]
        product.application.complete(ref)
        terminal = post("/operation", dict(handle=first["pending"]))
        assert terminal["ok"] and terminal["settled"] and terminal["request_id"] == nonce and not terminal["state"]["presentation_pending"]
        assert terminal["query_status"] == "found" and terminal["request_verified"] and not product.application.waits
        assert all(request.command == product.application.submissions[0][0] for request in product.application.lookups)
        assert post("/send", payload)["ok"] and len(product.application.operations) == 1
        saved = terminal["state"]["history"]
        recovered = post("/request-result", payload)
        assert recovered["ok"] and recovered["state"]["history"] == saved and len(product.application.submissions) == 3
        assert post("/history", dict(enabled=False))["state"]["character"]["history_enabled"] is False
        assert post("/reload", {})["state"]["history"] == saved and reopens == [True]
        for path in ("/context-reset", "/simulate", "/heartbeat", "/controls", "/attachments"):
            with pytest.raises(HTTPError) as error:
                post(path, {})
            assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            post("/send", payload, Origin="https://untrusted.example")
        assert error.value.code == 403 and len(product.application.operations) == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_terminal_failure_clears_duplicate_handles_without_disclosing_unverified_history(modules):
    desktop, _ = modules
    product = fake_product()
    adapter = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product)
    first = adapter.send(dict(text="合成消息。", request_id=str(uuid4())))
    ref = adapter.pending[first["pending"]]
    adapter.pending["legacy-duplicate"] = ref
    adapter.inflight.add("legacy-duplicate")
    result = adapter._result(product.application.result("failed-closed", ref, text=None, failure="whole-history-unverified"),
        first["pending"], first["request_id"])
    assert not result["ok"] and result["settled"] and not result["pending"] and not adapter.inflight
    assert "上下文" in result["message"] and "草稿" in result["message"]
    product.application.query = lambda query: SimpleNamespace(status=SimpleNamespace(value="failed-closed"),
        projection=SimpleNamespace(turns=[SimpleNamespace(user_text="不可核实", assistant_text="不可核实")]))
    assert adapter.snapshot()["history"] == dict(status="failed-closed", turns=[])


def test_lookup_after_adapter_restart_distinguishes_unknown_from_query_failure(modules):
    desktop, _ = modules
    product = fake_product()
    original = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product)
    payload = dict(text="  合成原消息\n", request_id=str(uuid4()))
    first = original.send(payload)
    ref = product.application.operations["original-whole-" + payload["request_id"]]
    product.application.outcomes[ref] = product.application.result("unknown", ref, text=None,
        failure="original-whole-transport-timeout")
    restarted = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product)
    result = restarted.lookup(payload)
    assert result["query_status"] == "found" and result["can_abandon"] and not result["settled"]
    assert result["request_id"] == first["request_id"] and len(product.application.submissions) == 1
    mismatch = restarted.lookup(dict(payload, text="不是原消息。"))
    assert mismatch["query_status"] == "unavailable" and not mismatch["request_verified"] and not mismatch["can_abandon"]
    absent = restarted.lookup(dict(text="合成未提交消息。", request_id=str(uuid4())))
    assert absent["query_status"] == "not-found" and not absent["can_abandon"] and not absent["settled"]
    product.application.lookup_subject_request = lambda request: SubjectRequestLookupResponse(
        SubjectRequestLookupStatus.FAILED_CLOSED, problem=ApplicationProblemView("synthetic-integrity-failed"))
    failed = restarted.lookup(payload)
    assert failed["query_status"] == "failed-closed" and not failed["settled"] and not failed["request_verified"]
    assert not failed["can_abandon"] and len(product.application.submissions) == 1 and not product.application.waits


def test_boundary_http_preview_confirmation_replay_and_history_are_separate_from_chat(modules):
    desktop, _ = modules
    facade = FakeBoundaryFacade()
    facade.turns = [SimpleNamespace(user_text="先前合成消息。", assistant_text="先前合成回复。")]
    facade.state = replace(facade.state, history_enabled=False)
    product = fake_product(facade)
    server = desktop.original_whole_server(product, reopen=lambda: product)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            token = re.search(r"TOKEN='([^']+)'", response.read().decode()).group(1)
        def post(path, payload):
            with urlopen(Request(base + path, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Chat-Token": token}), timeout=5) as response:
                return json.load(response)
        preview = post("/context-boundary-query", {})
        assert preview["ok"] and preview["context_boundary"]["context_revision"] == 0
        assert not facade.boundary_calls and not facade.submissions
        payload = dict(request_id=str(uuid4()), expected_revision=0, confirmed=False)
        assert not post("/context-boundary", payload)["ok"] and facade.context_revision == 0
        with pytest.raises(HTTPError) as error:
            post("/context-boundary", dict(payload, text="不能夹带草稿"))
        assert error.value.code == 400
        payload["confirmed"] = True
        committed = post("/context-boundary", payload)
        assert committed["ok"] and committed["boundary_settled"] and committed["boundary_status"] == "committed"
        assert "request_id" not in committed  # A control response never clears a chat draft nonce.
        assert committed["state"]["history"] == preview["state"]["history"]
        assert committed["state"]["character"]["history_enabled"] is False
        assert facade.boundary_calls[-1].target_profile_id == product.profile_id
        assert facade.boundary_calls[-1].target_timeline_id == product.timeline_id
        replayed = post("/context-boundary", payload)
        assert replayed["boundary_status"] == "replayed" and replayed["boundary_receipt"] == committed["boundary_receipt"]
        assert facade.context_revision == 1
        lookup = post("/context-boundary-query", {key: payload[key] for key in ("request_id", "expected_revision")})
        assert lookup["boundary_settled"] and lookup["context_boundary"]["receipt"] == committed["boundary_receipt"]
        assert len(facade.boundary_calls) == 3 and not facade.submissions and not facade.waits
        conflict = post("/context-boundary-query", dict(request_id=payload["request_id"], expected_revision=1))
        assert conflict["boundary_failed"] and not conflict["boundary_settled"] and facade.context_revision == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_boundary_capability_and_inflight_never_borrow_old_scope_or_wait(modules):
    desktop, _ = modules
    old_product = fake_product()
    old = desktop.OriginalWholeChatAdapter(old_product, reopen=lambda: old_product)
    assert old.snapshot()["context_boundary"]["status"] == "unavailable"
    assert not old.boundary_apply(dict(request_id=str(uuid4()), expected_revision=0, confirmed=True))["ok"]
    facade = FakeBoundaryFacade()
    product = fake_product(facade)
    adapter = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product)
    adapter.send(dict(text="合成在途请求。", request_id=str(uuid4())))
    result = adapter.boundary_apply(dict(request_id=str(uuid4()), expected_revision=0, confirmed=True))
    assert result["boundary_status"] == "busy" and not result["ok"]
    assert not facade.boundary_calls and facade.context_revision == 0
    assert not adapter.boundary_query({})["ok"] and adapter.snapshot()["context_boundary"]["pending"]


def test_basis_http_only_reads_facade_and_never_returns_failed_cached_body(modules):
    desktop, _ = modules
    facade = FakeWholeFacade(); reads = []; view = synthetic_basis()
    def query_basis():
        reads.append(True)
        return view
    facade.query_character_basis = query_basis
    def forbid(*args):
        raise AssertionError("basis viewing must not fetch history or settings")
    facade.query = forbid
    product = fake_product(facade)
    server = desktop.original_whole_server(product, reopen=lambda: product)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            token = re.search(r"TOKEN='([^']+)'", response.read().decode()).group(1)
        def post(payload):
            with urlopen(Request(base + "/character-basis", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Chat-Token": token}), timeout=5) as response:
                return json.load(response)
        response = post({})
        assert response["ok"] and len(response["basis"]["knowledge"]) == 2
        assert response["basis"]["knowledge"][1]["kind"] == "belief"
        assert response["basis"]["personality"][0]["basis"] == "author-interpretation"
        assert response["basis"]["core"][0]["support"][0]["event_scope"] == "before"
        with pytest.raises(HTTPError) as error:
            post(dict(path="unrequested-file"))
        assert error.value.code == 400 and len(reads) == 1
        facade.query_character_basis = lambda: replace(view, status="failed-closed")
        failed = post({})
        assert not failed["ok"] and failed["basis"] == {"status": "failed-closed"}
        assert not facade.submissions and not facade.lookups and not facade.waits and facade.state.history_enabled is True
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_scope_http_is_nonce_free_read_only_and_preserves_exact_local_draft(modules):
    desktop, _ = modules
    facade = FakeWholeFacade(); requests = []
    def preview(request):
        requests.append(request)
        return synthetic_scope(request.text)
    facade.preview_whole_message_scope = preview
    facade.query = lambda *args: (_ for _ in ()).throw(AssertionError("scope route must not fetch UI history"))
    product = fake_product(facade)
    server = desktop.original_whole_server(product, reopen=lambda: product)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            token = re.search(r"TOKEN='([^']+)'", response.read().decode()).group(1)
        def post(payload):
            with urlopen(Request(base + "/message-scope", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Chat-Token": token}), timeout=5) as response:
                return json.load(response)
        text = "  本地合成草稿\n"
        response = post(dict(text=text))
        assert response["ok"] and response["message_scope"]["current_message"] == text
        assert requests[0].text == text and requests[0].target_profile_id == product.profile_id
        assert requests[0].target_timeline_id == product.timeline_id and "request_id" not in response
        with pytest.raises(HTTPError) as error:
            post(dict(text=text, request_id=str(uuid4())))
        assert error.value.code == 400 and len(requests) == 1
        facade.preview_whole_message_scope = lambda request: replace(synthetic_scope(request.text), status="failed-closed")
        assert post(dict(text=text))["message_scope"] == {"status": "failed-closed"}
        assert not facade.submissions and not facade.operations and not facade.lookups and facade.state.history_enabled
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


@pytest.mark.parametrize("status,settled", [("terminal", True), ("failed-closed", True),
    ("unavailable", True), ("unknown", False)])
def test_http_reports_known_failure_settlement_without_retrying(modules, status, settled):
    desktop, _ = modules
    product = fake_product()
    calls = []
    def fail(command, *, idempotency_key):
        calls.append(idempotency_key)
        return product.application.result(status, text=None, failure="synthetic-failure")
    product.application.submit = fail
    server = desktop.original_whole_server(product, reopen=lambda: product)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            token = re.search(r"TOKEN='([^']+)'", response.read().decode()).group(1)
        nonce = str(uuid4())
        with urlopen(Request(base + "/send", data=json.dumps(dict(text="合成失败草稿。", request_id=nonce)).encode(),
            headers={"Content-Type": "application/json", "X-Chat-Token": token}), timeout=5) as response:
            result = json.load(response)
        assert not result["ok"] and result["settled"] is settled and result["request_id"] == nonce
        with urlopen(base + "/status", timeout=5) as response:
            assert not json.load(response)["presentation_pending"]
        assert calls == ["original-whole-" + nonce] and not product.application.waits
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


@pytest.fixture
def fake_entry(modules, monkeypatch, tmp_path):
    _, script = modules
    package = tmp_path / "owned-synthetic-package.json"
    package.write_text("synthetic-package-only", encoding="utf-8")
    facade, calls, closed = FakeWholeFacade(), [], []
    identity = str(uuid4()), str(uuid4())
    def open_author(config, **kwargs):
        calls.append("author-open")
        config.state_path.write_text("synthetic-state", encoding="utf-8")
        class Author:
            def freeze_source_identity(self, request):
                calls.append(("freeze", request))
                return SimpleNamespace(status="created", view=SimpleNamespace(identity_id=identity[0]))
            def select_local_identity(self, request):
                calls.append(("select", request))
                return SimpleNamespace(status="selected")
            def __enter__(self):
                return SimpleNamespace(application=self)
            def __exit__(self, *args):
                closed.append("author")
        return Author()
    def open_whole(config, **kwargs):
        calls.append(("whole-open", kwargs))
        return SimpleNamespace(application=facade, profile_id=identity[0], timeline_id=identity[1], close=lambda: closed.append("whole"))
    def review(request):
        calls.append(("review", request))
        return SimpleNamespace(status="previewed", review_basis=script.APPROVED_BINDING["review_basis"])
    monkeypatch.setattr(script, "open_local_product", open_author)
    monkeypatch.setattr(script, "open_original_whole_product", open_whole)
    monkeypatch.setattr(script.ApplicationFacade, "preview_original_character_whole_use_preparation", staticmethod(review))
    options = dict(live=False, package_path=package, transport=object(), audit_path=tmp_path / "isolated-audit")
    return script, tmp_path / "entry", options, facade, calls, closed


def test_entry_freezes_only_first_open_and_recovers_without_package_or_messages(fake_entry):
    script, root, options, facade, calls, closed = fake_entry
    entry = script.OriginalWholeChatEntry(root, **options)
    assert facade.turns == facade.submissions == []
    pointer = (root / "current.json").read_bytes()
    request = next(item[1] for item in calls if type(item) is tuple and item[0] == "freeze")
    assert request.confirmed and request.rights_confirmed and request.preparation_json == "synthetic-package-only"
    assert "synthetic-package-only" not in pointer.decode()
    options["package_path"].unlink()  # Our own synthetic fixture, never product data.
    entry.reopen()
    entry.close()
    recovered = script.OriginalWholeChatEntry(root, **options)
    assert (root / "current.json").read_bytes() == pointer and not facade.submissions
    assert sum(item == "author-open" for item in calls) == 1
    assert sum(type(item) is tuple and item[0] == "review" for item in calls) == 1
    recovered.close()


def test_partial_entry_and_stale_binding_stop_without_recreating_or_opening_author(fake_entry):
    script, root, options, _, calls, _ = fake_entry
    partial = root.with_name("partial-entry")
    partial.mkdir(); (partial / "initialized").mkdir()
    with pytest.raises(ValueError, match="incomplete"):
        script.OriginalWholeChatEntry(partial, **options)
    assert not calls and not (partial / "current.json").exists()
    entry = script.OriginalWholeChatEntry(root, **options); entry.close()
    pointer = root / "current.json"
    value = json.loads(pointer.read_text(encoding="utf-8")); value["binding"]["review_basis"] = "0" * 64
    pointer.write_text(json.dumps(value), encoding="utf-8")
    before, count = pointer.read_bytes(), len(calls)
    with pytest.raises(ValueError, match="pointer changed"):
        script.OriginalWholeChatEntry(root, **options)
    assert pointer.read_bytes() == before and len(calls) == count


def test_page_draft_nonce_recovery_ime_scope_and_read_only_refresh(modules):
    desktop, _ = modules
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the repository's desktop JavaScript checks")
    product = fake_product()
    state = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product).snapshot()
    page = (ROOT / "app/desktop/static/original_whole_chat.html").read_text(encoding="utf-8")
    script = re.search(r"<script>([\s\S]*?)</script>", page).group(1)
    harness = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage=new Map(),calls=[],waiting=[],nodes=new Map();let status=input.state,nextId=0;
const element=()=>({value:'',textContent:'',disabled:false,children:[],handlers:{},
 append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},
 addEventListener(name,handler){this.handlers[name]=handler},focus(){throw Error('no focus')}});
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
function start(){nodes.clear();const sandbox={document:{getElementById:get,createElement:element},
 sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 crypto:{randomUUID:()=> '00000000-0000-4000-8000-'+String(++nextId).padStart(12,'0')},
 setTimeout:callback=>setImmediate(callback),fetch:async(path,options)=>{
  if(path==='/status')return {ok:true,json:async()=>status};
  calls.push({path,body:JSON.parse(options.body)});
  return new Promise((resolve,reject)=>waiting.push({ok:value=>resolve({ok:true,json:async()=>value}),fail:()=>reject(Error('network'))}));
 }};vm.createContext(sandbox);vm.runInContext(input.script,sandbox);
 get('composer').requestSubmit=()=>get('composer').handlers.submit({preventDefault(){}})}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const draft=text=>{get('draft').value=text;get('draft').handlers.input()};
const submit=()=>get('composer').requestSubmit();
const key=extra=>get('draft').handlers.keydown({key:'Enter',preventDefault(){},...extra});
const outcome=(id,ok=true,settled=true)=>({ok,settled,pending:null,request_id:id,state:input.state,can_abandon:false});
const found=(id,ok=true,settled=true)=>({...outcome(id,ok,settled),query_status:'found',request_verified:true});
const failure=id=>({...outcome(id,false,false),query_status:'failed-closed',request_verified:false});
const unknown=id=>({...found(id,false,false),can_abandon:true});
(async()=>{
 start();await flush();draft('合成未发送草稿');
 key({shiftKey:true});key({isComposing:true});key({keyCode:229});
 get('draft').handlers.compositionstart();key({});await submit();get('draft').handlers.compositionend();
 assert.equal(calls.length,0);await get('refresh').handlers.click();assert.equal(get('draft').value,'合成未发送草稿');
 const first=submit();const id=calls.at(-1).body.request_id;waiting.shift().fail();await first;
 assert.equal(get('draft').value,'合成未发送草稿');assert.equal(get('send').disabled,false);assert.equal(get('send').textContent,'读取原结果');
 start();await flush();assert.equal(calls.at(-1).path,'/request-result');
 assert.deepEqual(calls.at(-1).body,{request_id:id,text:'合成未发送草稿'});
 assert.equal(calls.filter(row=>row.path==='/send').length,1);
 draft('后来的草稿');waiting.shift().ok(found(id));await flush();await flush();
 assert.equal(get('draft').value,'后来的草稿');
 const changed=submit(),changedId=calls.at(-1).body.request_id;assert.notEqual(changedId,id);
 assert.equal(calls.at(-1).path,'/send');
 waiting.shift().ok(outcome(changedId));await changed;assert.equal(get('draft').value,'');
 draft('已知失败保留草稿');const known=submit(),knownId=calls.at(-1).body.request_id;
 waiting.shift().ok(outcome(knownId,false));await known;
 assert.equal(get('draft').value,'已知失败保留草稿');assert.equal(get('send').textContent,'发送');
 const beforeNew=calls.length;await flush();assert.equal(calls.length,beforeNew);
 const explicitNew=submit(),newId=calls.at(-1).body.request_id;assert.notEqual(newId,knownId);
 waiting.shift().ok(outcome(newId));await explicitNew;assert.equal(get('draft').value,'');
 // An UNKNOWN from send is not a verified lookup and cannot be abandoned yet.
 draft('不确定原草稿');const uncertain=submit(),uncertainId=calls.at(-1).body.request_id;
 waiting.shift().ok(outcome(uncertainId,false,false));await uncertain;
 assert.equal(get('abandon').hidden,true);assert.equal(get('send').textContent,'读取原结果');
 const blockedRead=submit();assert.equal(calls.at(-1).path,'/request-result');
 waiting.shift().ok(failure(uncertainId));await blockedRead;
 assert.equal(get('abandon').hidden,true);assert.equal(get('send').textContent,'读取原结果');
 const verifiedRead=submit();waiting.shift().ok(unknown(uncertainId));await verifiedRead;
 assert.equal(get('abandon').hidden,false);
 const beforeAbandon=calls.length;
 get('abandon-start').handlers.click();get('abandon-cancel').handlers.click();
 assert.equal(get('send').textContent,'读取原结果');assert.equal(calls.length,beforeAbandon);
 draft('不确定后编辑的草稿');get('abandon-start').handlers.click();get('abandon-confirm').handlers.click();
 assert.equal(get('draft').value,'不确定后编辑的草稿');assert.equal(get('send').textContent,'发送');
 assert.equal(calls.length,beforeAbandon);
 const userNew=submit(),userNewId=calls.at(-1).body.request_id;
 assert.equal(calls.at(-1).path,'/send');assert.notEqual(userNewId,uncertainId);
 waiting.shift().ok(outcome(userNewId));await userNew;assert.equal(get('draft').value,'');
 // A verified missing nonce is not an implicit send; only the next click sends.
 draft('合成尚未admit草稿');const missingSend=submit(),missingId=calls.at(-1).body.request_id;
 waiting.shift().fail();await missingSend;const beforeMissing=calls.filter(row=>row.path==='/send').length;
 start();await flush();assert.equal(calls.at(-1).path,'/request-result');
 waiting.shift().ok({...failure(missingId),query_status:'not-found',request_verified:true});await flush();await flush();
 assert.equal(calls.filter(row=>row.path==='/send').length,beforeMissing);
 assert.equal(get('draft').value,'合成尚未admit草稿');assert.equal(get('send').textContent,'发送');
 const explicitMissing=submit(),newMissingId=calls.at(-1).body.request_id;assert.equal(newMissingId,missingId);
 waiting.shift().ok(outcome(newMissingId));await explicitMissing;assert.equal(get('draft').value,'');
 draft('合成等待回复');const pending=submit(),pendingId=calls.at(-1).body.request_id;
 const pendingState={...input.state,presentation_pending:true,pending_handle:'owned-handle',pending_request_id:pendingId};
 waiting.shift().ok({ok:true,pending:'owned-handle',request_id:pendingId,state:pendingState});
 await flush();await flush();assert.equal(calls.at(-1).path,'/operation');waiting.shift().fail();await pending;
 // After restart no process-local handle is needed: saved original text is queried.
 status=input.state;const sends=calls.filter(row=>row.path==='/send').length;start();await flush();await flush();
 assert.equal(calls.filter(row=>row.path==='/send').length,sends);assert.equal(calls.at(-1).path,'/request-result');
 assert.equal(calls.at(-1).body.request_id,pendingId);assert.equal(calls.at(-1).body.text,'合成等待回复');
 waiting.shift().ok({...found(pendingId,true,false),pending:'restored-handle',state:pendingState});await flush();await flush();
 assert.equal(calls.at(-1).path,'/operation');
 assert.equal(get('draft').value,'合成等待回复');waiting.shift().ok(found(pendingId,false));await flush();await flush();
 assert.equal(get('draft').value,'合成等待回复');assert.equal(get('send').textContent,'发送');
 const retryKnownPending=submit(),afterPendingId=calls.at(-1).body.request_id;assert.notEqual(afterPendingId,pendingId);
 waiting.shift().ok(outcome(afterPendingId));await retryKnownPending;assert.equal(get('draft').value,'');
 draft('旧范围草稿');status={...input.state,scope_key:'another-owned-scope'};start();await flush();
 assert.equal(get('draft').value,'');status=input.state;start();await flush();assert.equal(get('draft').value,'旧范围草稿');
 const history=get('history').handlers.change();assert.equal(calls.at(-1).path,'/history');
 waiting.shift().ok({...outcome(null),request_id:null});await flush();await flush();
 assert.equal(get('draft').value,'旧范围草稿');
 process.stdout.write('original-whole-page-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run([node, "-e", harness], input=json.dumps(dict(script=script, state=state)).encode(),
        capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stdout == b"original-whole-page-complete"


def test_boundary_page_cancel_lost_response_and_failed_confirmation_preserve_draft(modules):
    desktop, _ = modules
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the repository's desktop JavaScript checks")
    facade = FakeBoundaryFacade(); facade.state = replace(facade.state, history_enabled=False)
    product = fake_product(facade)
    state = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product).snapshot()
    page = (ROOT / "app/desktop/static/original_whole_chat.html").read_text(encoding="utf-8")
    script = re.search(r"<script>([\s\S]*?)</script>", page).group(1)
    harness = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage=new Map(),calls=[],waiting=[],nodes=new Map();let status=input.state,nextId=0;
const element=()=>({value:'',textContent:'',disabled:false,hidden:true,children:[],handlers:{},
 append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},
 addEventListener(name,handler){this.handlers[name]=handler},focus(){throw Error('no focus')}});
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
const atRevision=rev=>({...input.state,context_boundary:{...input.state.context_boundary,context_revision:rev,cutoff_sequence:rev*3}});
function start(){nodes.clear();const sandbox={document:{getElementById:get,createElement:element},
 sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 crypto:{randomUUID:()=> '00000000-0000-4000-8000-'+String(++nextId).padStart(12,'0')},
 setTimeout:callback=>setImmediate(callback),fetch:async(path,options)=>{
  if(path==='/status')return {ok:true,json:async()=>status};calls.push({path,body:JSON.parse(options.body)});
  return new Promise((resolve,reject)=>waiting.push({ok:value=>resolve({ok:true,json:async()=>value}),fail:()=>reject(Error('network'))}));
 }};vm.createContext(sandbox);vm.runInContext(input.script,sandbox);}
const flush=()=>new Promise(resolve=>setImmediate(resolve)),click=id=>get(id).handlers.click();
const query=(rev,id=null,requestStatus=null)=>({ok:!id||requestStatus==='replayed',boundary_request_id:id,
 boundary_settled:requestStatus==='replayed',boundary_failed:['failed-closed','conflict'].includes(requestStatus),
 context_boundary:{...atRevision(rev).context_boundary,...(requestStatus?{request_status:requestStatus}:{}),
 receipt:requestStatus==='replayed'?{context_revision:rev}:null},state:atRevision(rev),message:''});
(async()=>{
 start();await flush();get('draft').value='确认以后仍保留的合成草稿';get('draft').handlers.input();
 assert.equal(get('boundary-start').disabled,false);assert.equal(get('history').checked,false);
 let preview=click('boundary-start');assert.equal(calls.at(-1).path,'/context-boundary-query');
 waiting.shift().ok(query(0));await preview;assert.equal(get('boundary-panel').hidden,false);
 click('boundary-cancel');assert.equal(calls.filter(row=>row.path==='/context-boundary').length,0);
 assert.equal(get('draft').value,'确认以后仍保留的合成草稿');
 preview=click('boundary-start');waiting.shift().ok(query(0));await preview;
 const lost=click('boundary-confirm'),originalId=calls.at(-1).body.request_id;
 assert.deepEqual(calls.at(-1).body,{request_id:originalId,expected_revision:0,confirmed:true});
 waiting.shift().fail();await lost;click('boundary-cancel');
 status=atRevision(1);start();await flush();assert.equal(calls.at(-1).path,'/context-boundary-query');
 assert.deepEqual(calls.at(-1).body,{request_id:originalId,expected_revision:0});
 waiting.shift().ok(query(1,originalId,'replayed'));await flush();await flush();
 assert.equal(calls.filter(row=>row.path==='/context-boundary').length,1);
 assert.equal(calls.filter(row=>row.path==='/send').length,0);assert.equal(get('history').checked,false);
 assert.equal(get('draft').value,'确认以后仍保留的合成草稿');
 preview=click('boundary-start');waiting.shift().ok(query(1));await preview;
 const failed=click('boundary-confirm'),failedId=calls.at(-1).body.request_id;assert.notEqual(failedId,originalId);
 waiting.shift().ok({ok:false,boundary_status:'failed-closed',boundary_settled:false,boundary_request_id:failedId,state:atRevision(1)});
 await flush();await flush();assert.equal(calls.at(-1).path,'/context-boundary-query');
 waiting.shift().ok(query(1,failedId,'failed-closed'));await failed;
 assert.equal(get('boundary-release').hidden,false);assert.equal(get('boundary-confirm').disabled,true);
 const beforeRelease=calls.filter(row=>row.path==='/context-boundary').length;
 const release=click('boundary-release');assert.equal(calls.at(-1).path,'/context-boundary-query');
 assert.deepEqual(calls.at(-1).body,{});waiting.shift().ok(query(1));await release;
 assert.equal(calls.filter(row=>row.path==='/context-boundary').length,beforeRelease);
 assert.equal(get('boundary-confirm').disabled,false);assert.equal(get('boundary-confirm').textContent,'确认新交流边界');
 const next=click('boundary-confirm'),nextId=calls.at(-1).body.request_id;assert.notEqual(nextId,failedId);
 assert.equal(calls.at(-1).body.expected_revision,1);
 waiting.shift().ok({ok:true,boundary_status:'committed',boundary_settled:true,boundary_request_id:nextId,state:atRevision(2)});await next;
 assert.equal(get('boundary-panel').hidden,true);assert.equal(get('draft').value,'确认以后仍保留的合成草稿');
 assert.equal(calls.filter(row=>row.path==='/send').length,0);
 status={...input.state,context_boundary:{status:'unavailable',pending:false}};start();await flush();
 assert.equal(get('boundary-start').disabled,true);assert.equal(get('draft').value,'确认以后仍保留的合成草稿');
 process.stdout.write('whole-boundary-page-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run([node, "-e", harness], input=json.dumps(dict(script=script, state=state)).encode(),
        capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stdout == b"whole-boundary-page-complete"


def test_basis_page_search_close_failure_and_late_scope_keep_chat_untouched(modules):
    desktop, _ = modules
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the repository's desktop JavaScript checks")
    product = fake_product()
    state = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product).snapshot()
    page = (ROOT / "app/desktop/static/original_whole_chat.html").read_text(encoding="utf-8")
    script = re.search(r"<script>([\s\S]*?)</script>", page).group(1)
    harness = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage=new Map(),calls=[],waiting=[],nodes=new Map();let status=input.state;
const element=tag=>{const item={tag,value:'',textContent:'',disabled:false,hidden:true,children:[],handlers:{},
 append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},
 addEventListener(name,handler){this.handlers[name]=handler},focus(){throw Error('no focus')}};
 Object.defineProperty(item,'innerHTML',{set(){throw Error('unsafe HTML')}});return item};
const get=id=>{if(!nodes.has(id))nodes.set(id,element('div'));return nodes.get(id)};
const sandbox={document:{getElementById:get,createElement:element},
 sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 crypto:{randomUUID:()=> '00000000-0000-4000-8000-000000000001'},setTimeout:callback=>setImmediate(callback),
 fetch:async(path,options)=>{if(path==='/status')return {ok:true,json:async()=>status};calls.push({path,body:JSON.parse(options.body)});
 return new Promise(resolve=>waiting.push(value=>resolve({ok:true,json:async()=>value})))}};
vm.createContext(sandbox);vm.runInContext(input.script,sandbox);
const flush=()=>new Promise(resolve=>setImmediate(resolve)),click=id=>get(id).handlers.click();
const text=item=>item.textContent+item.children.map(text).join('');
const available={ok:true,scope_key:input.state.scope_key,basis:input.basis};
(async()=>{
 await flush();get('draft').value='仍未提交的合成草稿';get('draft').handlers.input();const before=new Map(storage);
 let opening=click('basis-open');assert.equal(calls.at(-1).path,'/character-basis');waiting.shift()(available);await opening;
 assert.equal(get('basis-panel').hidden,false);assert(text(get('basis-content')).includes('人物信念'));
 assert(text(get('basis-content')).includes('作者解释'));assert(text(get('basis-content')).includes('onerror=alert(1)'));
 const count=calls.length;get('basis-search').value='压力';get('basis-search').handlers.input();assert.equal(calls.length,count);
 assert.equal(get('basis-status').textContent.includes('1项认识'),true);
 assert.equal(get('draft').value,'仍未提交的合成草稿');assert.deepEqual(storage,before);
 let refreshing=click('basis-refresh');waiting.shift()({ok:false,scope_key:input.state.scope_key,basis:{status:'unavailable'}});await refreshing;
 assert.equal(text(get('basis-content')),'');assert.equal(get('basis-search').disabled,true);
 click('basis-close');assert.equal(get('basis-panel').hidden,true);assert.deepEqual(storage,before);
 opening=click('basis-open');click('basis-close');waiting.shift()(available);await opening;
 assert.equal(text(get('basis-content')),'');assert.equal(get('basis-panel').hidden,true);
 opening=click('basis-open');status={...input.state,scope_key:'another-owned-scope'};
 await click('refresh');waiting.shift()(available);await opening;
 assert.equal(text(get('basis-content')),'');assert.equal(get('basis-panel').hidden,true);
 assert.deepEqual(storage,before);assert.equal(calls.some(row=>row.path==='/send'||row.path==='/history'||row.path==='/context-boundary'),false);
 process.stdout.write('character-basis-page-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run([node, "-e", harness], input=json.dumps(dict(script=script, state=state, basis=asdict(synthetic_basis()))).encode(),
        capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stdout == b"character-basis-page-complete"


def test_scope_page_edit_settings_state_and_late_response_never_send_or_change_nonce(modules):
    desktop, _ = modules
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the repository's desktop JavaScript checks")
    product = fake_product()
    state = desktop.OriginalWholeChatAdapter(product, reopen=lambda: product).snapshot()
    page = (ROOT / "app/desktop/static/original_whole_chat.html").read_text(encoding="utf-8")
    script = re.search(r"<script>([\s\S]*?)</script>", page).group(1)
    harness = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage=new Map(),calls=[],waiting=[],nodes=new Map();let status=input.state;
const element=()=>({value:'',textContent:'',disabled:false,hidden:true,children:[],handlers:{},
 append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},
 addEventListener(name,handler){this.handlers[name]=handler},focus(){throw Error('no focus')}});
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
const sandbox={document:{getElementById:get,createElement:element},
 sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 crypto:{randomUUID:()=> {throw Error('preview cannot generate nonce')}},setTimeout:callback=>setImmediate(callback),
 fetch:async(path,options)=>{if(path==='/status')return {ok:true,json:async()=>status};calls.push({path,body:JSON.parse(options.body)});
 return new Promise(resolve=>waiting.push(value=>resolve({ok:true,json:async()=>value})))}};
vm.createContext(sandbox);vm.runInContext(input.script,sandbox);
const flush=()=>new Promise(resolve=>setImmediate(resolve)),click=id=>get(id).handlers.click();
const text=item=>item.textContent+item.children.map(text).join('');
const draft=value=>{get('draft').value=value;get('draft').handlers.input()};
const available=value=>({ok:true,scope_key:input.state.scope_key,message_scope:{...input.preview,current_message:value}});
(async()=>{
 await flush();draft('当前合成草稿。');const before=new Map(storage);
 let preview=click('scope-open');assert.deepEqual(calls.at(-1),{path:'/message-scope',body:{text:'当前合成草稿。'}});
 waiting.shift()(available('当前合成草稿。'));await preview;
 assert(text(get('scope-content')).includes('先前合成消息。'));assert(text(get('scope-content')).includes('已审学习概括。'));
 assert.equal(text(get('scope-content')).includes(input.preview.projection_digest),false);
 assert.deepEqual(storage,before);assert.equal(get('draft').value,'当前合成草稿。');
 draft('编辑后的草稿。');assert.equal(text(get('scope-content')),'');
 preview=click('scope-refresh');draft('再次编辑的草稿。');waiting.shift()(available('编辑后的草稿。'));await preview;
 assert.equal(text(get('scope-content')),'');assert.equal(get('draft').value,'再次编辑的草稿。');
 preview=click('scope-refresh');waiting.shift()(available('再次编辑的草稿。'));await preview;
 get('history').checked=false;get('history').handlers.change();assert.equal(text(get('scope-content')),'');
 const off={...input.state,character:{...input.state.character,history_enabled:false}};
 waiting.shift()({ok:true,state:off});await flush();await flush();
 preview=click('scope-refresh');waiting.shift()({ok:true,scope_key:input.state.scope_key,message_scope:{...input.preview,current_message:'再次编辑的草稿。',history_enabled:false,recent_dialogue:[]}});await preview;
 assert.equal(text(get('scope-content')).includes('先前合成消息。'),false);assert(text(get('scope-content')).includes('历史参考已关闭'));
 status=off;await click('refresh');assert.equal(text(get('scope-content')),'');
 preview=click('scope-refresh');waiting.shift()({ok:false,scope_key:input.state.scope_key,message_scope:{status:'unavailable'}});await preview;
 assert.equal(text(get('scope-content')),'');assert.equal(get('draft').value,'再次编辑的草稿。');
 click('scope-close');assert.equal(get('scope-panel').hidden,true);
 assert.equal(calls.some(row=>row.path==='/send'||row.path==='/context-boundary'),false);
 process.stdout.write('whole-message-scope-page-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run([node, "-e", harness], input=json.dumps(dict(script=script, state=state, preview=asdict(synthetic_scope()))).encode(),
        capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stdout == b"whole-message-scope-page-complete"

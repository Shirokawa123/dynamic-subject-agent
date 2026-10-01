"""Exercise the trial over HTTP and real Facade/canonical recovery, no remote I/O."""
import importlib.util
import json
from pathlib import Path
import re
import sys
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from test_s117_continuous_comparison import SyntheticTransport

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("s118_entry", ROOT / "scripts/serve_s118_whole_reply.py")
entry_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry_module)


def test_background_http_send_restore_reset_and_scope_rejection(tmp_path):
    transport = SyntheticTransport()
    entry = entry_module.TrialEntry(tmp_path / "entry", live=False, transport=transport)
    server = entry_module.trial_server(entry.products, choices=entry.choices,
        scope_key=entry.trial.manifest_digest, reopen=entry.reopen, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    case = "objects-and-versions"
    try:
        with urlopen(base + "/", timeout=10) as response:
            page = response.read().decode()
        token = re.search(r"TOKEN='([^']+)'", page).group(1)
        headers = {"Content-Type":"application/json", "X-Chat-Token":token}
        def get():
            with urlopen(base + "/status", timeout=20) as response:
                return json.load(response)
        def post(path, value):
            with urlopen(Request(base+path, data=json.dumps(value).encode(), headers=headers), timeout=20) as response:
                return json.load(response)
        def settle(result):
            deadline = time.monotonic() + 30
            while result.get("pending"):
                assert time.monotonic() < deadline
                result = post("/operation",dict(case_id=case,handle=result["pending"]))
            return result
        state = get()
        selected = next(row for row in state["cases"] if row["case_id"] == case)
        assert selected["state"]["character"]["budget_remaining"] is None
        assert len(selected["state"]["messages"]) == 2  # programmed intro and share
        assert not transport.calls and entry.trial.shared_budget().counts() == (None,0,None)
        for payload in (dict(case_id=case,text="PRIVATE_TEXT_NOT_AUTHORIZED",request_id=str(uuid4())),
            dict(case_id=case,choice_id="new-message",request_id=str(uuid4())),
            dict(case_id=case,choice_id="1",text="PRIVATE_TEXT_NOT_AUTHORIZED",request_id=str(uuid4()))):
            with pytest.raises(HTTPError) as error:
                post("/send",payload)
            assert error.value.code == 400
        assert not transport.calls
        payload = dict(case_id=case,choice_id="1",request_id=str(uuid4()))
        result = settle(post("/send",payload))
        assert result["ok"] and len(transport.calls)==1
        assert result["state"]["messages"][-1]["assistant_text"] == "合成独立回复1。"
        saved = result["state"]["messages"]
        again = settle(post("/send",payload))
        assert again["ok"] and len(transport.calls)==1 and again["state"]["messages"] == saved
        reopened = post("/reload",dict(case_id=case))
        assert reopened["ok"] and reopened["state"]["messages"] == saved and len(transport.calls)==1
        reset = settle(post("/context-reset",dict(case_id=case,request_id=str(uuid4()),confirmed=True)))
        assert reset["ok"] and len(transport.calls)==1
        assert reset["state"]["character"]["context_start_sequence"] > 0
        following = settle(post("/send",dict(case_id=case,choice_id="7",request_id=str(uuid4()))))
        assert following["ok"] and len(transport.calls)==2
        assert not json.loads(transport.calls[-1]["messages"][1]["content"])["exchange"]["dialogue_sources"]
        for path in ("/simulate","/heartbeat","/controls"):
            with pytest.raises(HTTPError) as error:
                post(path,dict(case_id=case,request_id=str(uuid4())))
            assert error.value.code==403
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base+"/send",data=json.dumps(payload).encode(),headers={**headers,"Origin":"https://untrusted.example"}),timeout=5)
        assert error.value.code==403 and len(transport.calls)==2
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        entry.close()
    restored = entry_module.TrialEntry(tmp_path / "entry", live=False, transport=transport)
    try:
        assert len(transport.calls)==2
        history = entry_module.read_history(restored.products[case])
        assert history[-1].assistant_text=="合成独立回复2。" and len(history)==3
    finally:
        restored.close()


def test_partial_entry_cannot_silently_reinitialize(tmp_path):
    root=tmp_path/"entry"
    root.mkdir()
    (root/"initialized").mkdir()
    with pytest.raises(ValueError,match="incomplete"):
        entry_module.TrialEntry(root,live=False,transport=SyntheticTransport())
    assert not (root/"current.json").exists()


def test_duplicate_pending_handles_share_one_operation_and_terminal_clears_the_cached_state():
    from types import SimpleNamespace
    from test_first_life_context_adapter import FakeFacade, response
    from whole_reply_trial import TrialConversationAdapter
    product=SimpleNamespace(application=FakeFacade(),profile_id="profile",timeline_id="timeline")
    adapter=TrialConversationAdapter(product)
    ref=object()
    pending=response("pending",pending=ref)
    first=adapter._result(pending)
    adapter._request_ids[first["pending"]]="opaque-client-request"
    assert adapter.snapshot()["pending_request_id"]=="opaque-client-request"
    again=adapter._result(pending)
    assert first["pending"]==again["pending"] and len(adapter.inflight)==1
    # Also remove duplicate legacy handles if the same operation is observed.
    adapter.pending["duplicate-handle"]=ref
    adapter.inflight.add("duplicate-handle")
    terminal=adapter._result(response("terminal",pending=ref))
    assert terminal["ok"] and not terminal["state"]["presentation_pending"]
    assert not adapter.inflight


def test_blank_reply_has_honest_feedback_and_does_not_create_a_reply():
    from types import SimpleNamespace
    from dataclasses import replace
    from test_first_life_context_adapter import FakeFacade, response
    from whole_reply_trial import TrialConversationAdapter
    product=SimpleNamespace(application=FakeFacade(),profile_id="profile",timeline_id="timeline")
    adapter=TrialConversationAdapter(product)
    before=adapter.snapshot()["messages"]
    failed=replace(response("failed-closed"),projection=SimpleNamespace(failure_code="first-life-response-content-empty"))
    result=adapter._result(failed)
    assert not result["ok"] and "空白" in result["message"] and "保留" in result["message"]
    assert result["state"]["messages"]==before

"""Thin Adapter checks with a fake Facade; no real Provider or user state."""
from dataclasses import replace
from pathlib import Path
import importlib.util
import json
import re
import shutil
import subprocess
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from dynamic_subject_agent.application import (
    ApplicationOperationResponse, ApplicationOperationStatus, ApplicationProblemView,
)
from dynamic_subject_agent.first_life import (
    CONTEXT_RESET_CONFIRMATION, FirstLifeContextResetRequest, FirstLifeQuery, FirstLifeStatus,
)


ROOT = Path(__file__).resolve().parents[1]


def response(status="terminal", *, code=None, pending=None):
    return ApplicationOperationResponse(ApplicationOperationStatus(status), pending, None,
        ApplicationProblemView(code) if code else None)


class FakeFacade:
    def __init__(self):
        self.resets = []
        self.waits = []
        self.state = FirstLifeStatus("paused", subject_name="测试人物", history_enabled=True,
            budget_total=200, budget_used=200, budget_remaining=0,
            today_decisions_used=0, today_share_calls_used=0,
            development_run=True, development_calls_remaining=0)
        self.next_response = response()

    def first_life_status(self):
        return self.state

    def query_first_life(self):
        return FirstLifeQuery("available")

    def query(self, query):
        return SimpleNamespace(status=SimpleNamespace(value="available"),
            projection=SimpleNamespace(turns=(SimpleNamespace(head_sequence=1,
                user_text="先前消息", assistant_text="先前回复"),)))

    def reset_first_life_context(self, request):
        self.resets.append(request)
        if request.confirmed is not True:
            return response("unavailable", code="confirmed-chat-context-reset-required")
        if self.next_response.status.value == "terminal":
            self.state = replace(self.state, context_start_sequence=2)
        return self.next_response

    def wait(self, ref, *, timeout_seconds):
        self.waits.append((ref, timeout_seconds))
        return response()


@pytest.fixture
def desktop(monkeypatch):
    directory = ROOT / "app" / "desktop"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("first_life_context_desktop", directory / "first_life.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def product():
    return SimpleNamespace(application=FakeFacade(), profile_id="fake-profile", timeline_id="fake-timeline")


def test_read_only_snapshot_and_exact_confirmed_delegation_with_no_budget(desktop, product):
    adapter = desktop.FirstLifeAdapter(product)
    before = adapter.snapshot()
    assert before["context_reset_confirmation"] == CONTEXT_RESET_CONFIRMATION
    assert before["character"]["budget_remaining"] == 0
    assert not product.application.resets
    request_id = str(uuid4())
    result = adapter.reset_context(dict(request_id=request_id, confirmed=True))
    assert product.application.resets == [FirstLifeContextResetRequest(request_id, True)]
    assert result["ok"] and result["state"]["character"]["context_start_sequence"] == 2
    assert result["state"]["messages"] == before["messages"]
    assert result["state"]["character"]["budget_remaining"] == 0


@pytest.mark.parametrize("payload", [
    None, [], {}, {"request_id": str(uuid4())}, {"confirmed": True},
    {"request_id": str(uuid4()), "confirmed": 1},
    {"request_id": str(uuid4()), "confirmed": "true"},
    {"request_id": str(uuid4()), "confirmed": True, "text": "不能夹带草稿"},
    {"request_id": "not-a-uuid", "confirmed": True},
])
def test_context_reset_rejects_non_exact_payload_before_facade(desktop, product, payload):
    with pytest.raises(ValueError):
        desktop.FirstLifeAdapter(product).reset_context(payload)
    assert not product.application.resets


def test_unconfirmed_and_history_failures_have_readable_recovery_path(desktop, product):
    adapter = desktop.FirstLifeAdapter(product)
    result = adapter.reset_context(dict(request_id=str(uuid4()), confirmed=False))
    assert not result["ok"] and "尚未确认" in result["message"]
    assert product.application.state.context_start_sequence == 0
    # The production failure code is in the authorized projection, not the generic problem.
    failed = response("failed-closed", code="operation-failed-closed")
    failed = replace(failed, projection=SimpleNamespace(failure_code="first-life-history-unverified"))
    result = adapter._result(failed)
    assert not result["ok"]
    assert "使用范围" in result["message"] and "从新消息继续" in result["message"]
    assert "完整性" in result["message"] and "草稿保留" in result["message"]


def test_pending_reset_remains_pending_until_facade_poll(desktop, product):
    operation = object()
    product.application.next_response = response("pending", pending=operation)
    adapter = desktop.FirstLifeAdapter(product)
    result = adapter.reset_context(dict(request_id=str(uuid4()), confirmed=True))
    assert result["pending"] and result["state"]["presentation_pending"]
    polled = adapter.poll(dict(handle=result["pending"]))
    assert polled["ok"] and not polled["pending"]
    assert not polled["state"]["presentation_pending"]
    assert product.application.waits == [(operation, 0)]
    assert len(product.application.resets) == 1


def test_http_status_cannot_reset_and_post_uses_exact_route(desktop, product):
    server = desktop.life_server(product, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as result:
            page = result.read().decode()
        token = re.search(r"TOKEN='([^']+)'", page).group(1)
        with urlopen(base + "/status", timeout=5) as result:
            assert json.load(result)["context_reset_confirmation"] == CONTEXT_RESET_CONFIRMATION
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/context-reset", timeout=5)
        assert error.value.code == 404 and not product.application.resets
        payload = dict(request_id=str(uuid4()), confirmed=True)
        headers = {"Content-Type": "application/json", "X-Chat-Token": token}
        with urlopen(Request(base + "/context-reset", data=json.dumps(payload).encode(), headers=headers), timeout=5) as result:
            assert json.load(result)["ok"]
        assert product.application.resets == [FirstLifeContextResetRequest(**payload)]
        invalid = dict(payload, draft="不能夹带草稿")
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/context-reset", data=json.dumps(invalid).encode(), headers=headers), timeout=5)
        assert error.value.code == 400 and len(product.application.resets) == 1
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_page_two_steps_cancel_pending_failure_and_success_preserve_draft(desktop, product):
    """Execute the page JS in a small DOM double without opening or focusing a browser."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the existing desktop JavaScript test approach")
    page = (ROOT / "app/desktop/static/first_life.html").read_text(encoding="utf-8")
    script = re.search(r"<script>([\s\S]*?)</script>", page).group(1)
    state = desktop.FirstLifeAdapter(product).snapshot()
    harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const nodes = new Map(), calls = [], waiting = [];
const element = () => ({value:'',textContent:'',disabled:false,hidden:true,children:[],handlers:{},
  append(...items){this.children.push(...items);},replaceChildren(){this.children=[];},
  setAttribute(name,value){this[name]=value;},
  addEventListener(name,handler){this.handlers[name]=handler;},
  focus(){throw new Error('must not steal focus');}});
const get = id => {if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
const sandbox = {document:{hidden:false,getElementById:get,createElement:element},
  crypto:{randomUUID:()=> '10000000-0000-4000-8000-000000000001'},
  setInterval:()=>0,setTimeout:callback=>setImmediate(callback),
  fetch:async(path,options)=>{
    if(path==='/status')return {ok:true,json:async()=>input.state};
    calls.push({path,body:JSON.parse(options.body)});
    return new Promise(resolve=>waiting.push(value=>resolve({ok:true,json:async()=>value})));
  }};
vm.createContext(sandbox);vm.runInContext(input.script,sandbox);
const flush = () => new Promise(resolve=>setImmediate(resolve));
const click = id => get(id).handlers.click();
(async()=>{
  await flush();
  get('draft').value='仍未提交的草稿';
  assert.equal(get('send').disabled,true); // Zero model budget does not block local recovery.
  assert.equal(get('context-reset').disabled,false);
  assert.equal(get('context-reset-copy').textContent,input.confirmation);
  await click('context-reset-confirm'); // Cannot confirm before showing the explanation.
  await click('context-reset');
  assert.equal(get('context-reset-explanation').hidden,false);
  assert.equal(get('context-reset-confirm').disabled,false);
  await get('composer').handlers.submit({preventDefault(){}});
  await click('context-reset-cancel');
  assert.equal(get('context-reset-explanation').hidden,true);
  assert.equal(calls.length,0);
  assert.equal(get('draft').value,'仍未提交的草稿');
  await click('context-reset');
  const failed = click('context-reset-confirm');
  assert.equal(get('context-reset-confirm').disabled,true);
  assert.equal(get('context-reset-cancel').disabled,true);
  await click('context-reset-confirm');
  assert.equal(calls.length,1);
  assert.deepEqual(calls[0],{path:'/context-reset',body:{confirmed:true,request_id:'10000000-0000-4000-8000-000000000001'}});
  waiting.shift()({ok:false,pending:null,state:input.state,message:'当前记录完整性尚未确认，草稿保留。'});
  await failed;
  assert.equal(get('context-reset-explanation').hidden,false);
  assert.match(get('feedback').textContent,/完整性/);
  assert.equal(get('draft').value,'仍未提交的草稿');
  const succeeded = click('context-reset-confirm');
  waiting.shift()({ok:true,pending:'pending-reset',state:{...input.state,presentation_pending:true,pending_handle:'pending-reset'}});
  await flush();await flush();
  assert.equal(get('context-reset-confirm').disabled,true);
  assert.equal(calls.at(-1).path,'/operation');
  waiting.shift()({ok:true,pending:null,state:{...input.state,character:{...input.state.character,context_start_sequence:2}}});
  await succeeded;
  assert.equal(calls.filter(c=>c.path==='/context-reset').length,2);
  assert.equal(get('context-reset-explanation').hidden,true);
  assert.equal(get('context-reset').disabled,false);
  assert.equal(get('draft').value,'仍未提交的草稿');
  assert.match(get('context-note').textContent,/此前记录仍可查看/);
  assert.match(get('feedback').textContent,/草稿未发送/);
  assert.deepEqual(calls.map(c=>c.path),['/context-reset','/context-reset','/operation']);
  process.stdout.write('context-reset-page-complete');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run([node, "-e", harness], input=json.dumps(dict(script=script, state=state,
        confirmation=CONTEXT_RESET_CONFIRMATION)).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stdout == b"context-reset-page-complete"

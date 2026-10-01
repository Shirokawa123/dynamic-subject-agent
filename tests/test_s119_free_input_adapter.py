"""Free-input HTTP and browser recovery behavior, with no remote I/O or UI focus."""
from dataclasses import replace
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

from test_first_life_context_adapter import FakeFacade, response


ROOT = Path(__file__).resolve().parents[1]


class ChatFacade(FakeFacade):
    def __init__(self):
        super().__init__()
        self.submissions = []
        self.operations = {}
        self.completed = set()

    def submit(self, command, *, idempotency_key):
        self.submissions.append((command, idempotency_key))
        ref = self.operations.setdefault(idempotency_key, object())
        return response("terminal" if ref in self.completed else "pending", pending=ref)

    def wait(self, ref, *, timeout_seconds):
        self.waits.append((ref, timeout_seconds))
        self.completed.add(ref)
        return response("terminal", pending=ref)

    def set_reviewed_character_history(self, enabled):
        self.state = replace(self.state, status="active", history_enabled=enabled)
        return self.state


@pytest.fixture
def adapter_module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "app/desktop"))
    import whole_reply_chat
    return whole_reply_chat


@pytest.fixture
def presentation():
    facade = ChatFacade()
    product = SimpleNamespace(application=facade, profile_id=str(uuid4()), timeline_id=str(uuid4()))
    choices = {"scene":dict(title="文字构图", choices=[dict(id="1", text="建议消息")])}
    return facade, product, choices


@pytest.mark.parametrize("text", [None, True, 123, [], {}, "", " \n\t", "a\x00b", "字"*1001])
def test_invalid_text_never_reaches_admission(adapter_module, presentation, text):
    facade, product, choices = presentation
    adapter = adapter_module.WholeReplyChatAdapter({"scene":product}, choices=choices,
        scope_key="new-free-input-scope", reopen=lambda _:product)
    with pytest.raises(ValueError):
        adapter.send(dict(case_id="scene", text=text, request_id=str(uuid4())))
    assert not facade.submissions


def test_background_http_exact_input_pending_nonce_and_read_only_refresh(adapter_module, presentation):
    facade, product, choices = presentation
    reopened = []
    def reopen(case):
        reopened.append(case)
        return product
    server = adapter_module.chat_server({"scene":product}, choices=choices,
        scope_key="new-free-input-scope", reopen=reopen)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        def get(path):
            with urlopen(base+path, timeout=5) as result:
                return json.load(result)
        with urlopen(base+"/", timeout=5) as result:
            page = result.read().decode()
        token = re.search(r"TOKEN='([^']+)'", page).group(1)
        def post(path, value, **extra_headers):
            headers = {"Content-Type":"application/json", "X-Chat-Token":token, **extra_headers}
            with urlopen(Request(base+path, data=json.dumps(value).encode(), headers=headers), timeout=5) as result:
                return json.load(result)
        assert get("/health") == dict(application="whole-reply-free-input-chat-s119")
        assert get("/status")["mode"] == "free-input"
        nonce = str(uuid4())
        for payload in (None, {}, dict(case_id="unknown",text="消息",request_id=nonce),
                dict(case_id="scene",choice_id="1",request_id=nonce),
                dict(case_id="scene",text="消息",request_id=None),
                dict(case_id="scene",text="消息",request_id="not-a-uuid"),
                dict(case_id="scene",text="消息",request_id=nonce,attachment="file")):
            with pytest.raises(HTTPError) as error:
                post("/send", payload)
            assert error.value.code == 400
        assert not facade.submissions
        text = "  自己写的新问法\n" + "🙂"*990
        payload = dict(case_id="scene",text=text,request_id=nonce)
        first = post("/send",payload)
        assert first["ok"] and first["pending"] and first["request_id"] == nonce
        assert facade.submissions[0][0].utterance == text
        state = get("/status")["cases"][0]["state"]
        assert state["pending_handle"] == first["pending"] and state["pending_request_id"] == nonce
        assert len(facade.submissions) == 1 and not facade.waits
        blocked_reload = post("/reload",dict(case_id="scene"))
        assert not blocked_reload["ok"] and not reopened
        repeated = post("/send",payload)
        assert repeated["pending"] == first["pending"] and len(facade.operations) == 1
        terminal = post("/operation",dict(case_id="scene",handle=first["pending"]))
        assert terminal["ok"] and terminal["request_id"] == nonce
        assert not terminal["state"]["presentation_pending"]
        assert post("/reload",dict(case_id="scene"))["ok"] and reopened == ["scene"]
        assert post("/history",dict(case_id="scene",enabled=False))["ok"]
        assert post("/context-reset",dict(case_id="scene",confirmed=True,request_id=str(uuid4())))["ok"]
        assert len(facade.submissions) == 2
        for path in ("/simulate", "/heartbeat", "/controls", "/attachments"):
            with pytest.raises(HTTPError) as error:
                post(path, dict(case_id="scene"))
            assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            post("/send",dict(payload,text="拒绝跨来源请求"), Origin="https://untrusted.example")
        assert error.value.code == 403 and len(facade.operations) == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_page_draft_nonce_refresh_ime_and_terminal_matching(adapter_module, presentation):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the existing desktop JavaScript test approach")
    _, product, choices = presentation
    adapter = adapter_module.WholeReplyChatAdapter({"scene":product}, choices=choices,
        scope_key="scope", reopen=lambda _:product)
    page = (ROOT / "app/desktop/static/whole_reply_chat.html").read_text(encoding="utf-8")
    script = re.search(r"<script>([\s\S]*?)</script>", page).group(1)
    harness = r"""
const assert = require('node:assert/strict'), vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage = new Map(), calls = [], waiting = [], nodes = new Map();
let nextId=0, status=input.state;
const terminalState=JSON.parse(JSON.stringify(input.state.cases[0].state));
const element=()=>({value:'',textContent:'',disabled:false,hidden:true,children:[],handlers:{},dataset:{},
  append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
  get firstChild(){return this.children[0];},querySelectorAll(){return this.children;},
  setAttribute(name,value){this[name]=value;},addEventListener(name,handler){this.handlers[name]=handler;},
  focus(){throw Error('must not steal focus');}});
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
function start(){nodes.clear();const sandbox={document:{getElementById:get,createElement:element},location:{hash:''},
  sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
  crypto:{randomUUID:()=> '00000000-0000-4000-8000-'+String(++nextId).padStart(12,'0')},
  setTimeout:callback=>setImmediate(callback),fetch:async(path,options)=>{
    if(path==='/status')return {ok:true,json:async()=>status};
    calls.push({path,body:JSON.parse(options.body)});
    return new Promise((resolve,reject)=>waiting.push({ok:value=>resolve({ok:true,json:async()=>value}),fail:()=>reject(Error('network'))}));
  }};vm.createContext(sandbox);vm.runInContext(input.script,sandbox);
  get('composer').requestSubmit=()=>get('composer').handlers.submit({preventDefault(){}});
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const draft=text=>{get('draft').value=text;get('draft').handlers.input();};
const submit=()=>get('composer').requestSubmit();
const key=(extra={})=>get('draft').handlers.keydown({key:'Enter',preventDefault(){},...extra});
const outcome=(nonce,ok=true)=>({case_id:'scene',request_id:nonce,ok,pending:null,state:terminalState});
(async()=>{
  start();await flush();draft('还没提交');
  key({shiftKey:true});key({isComposing:true});key({keyCode:229});
  get('draft').handlers.compositionstart();key();await submit();get('draft').handlers.compositionend();
  assert.equal(calls.length,0);
  await get('refresh').handlers.click();assert.equal(get('draft').value,'还没提交');assert.equal(calls.length,0);
  get('suggestion').value='1';get('suggestion').handlers.change();assert.equal(get('draft').value,'还没提交');
  key();assert.equal(calls.length,1);const first=calls[0].body.request_id;
  await submit();assert.equal(calls.length,1);waiting.shift().fail();await flush();await flush();
  assert.equal(get('draft').value,'还没提交');assert.equal(get('send').disabled,true);
  start();await flush();assert.equal(get('draft').value,'还没提交');assert.equal(calls.length,1);
  const retry=submit();assert.equal(calls.at(-1).body.request_id,first);
  waiting.shift().ok(outcome(first,false));await retry;
  assert.equal(get('draft').value,'还没提交');assert.equal(get('send').textContent,'继续上次发送');
  // A later edited draft must survive a result for the old submitted text.
  const old=submit();draft('后来编辑的草稿');waiting.shift().ok(outcome(first));await old;
  assert.equal(get('draft').value,'后来编辑的草稿');
  const changed=submit(), changedId=calls.at(-1).body.request_id;assert.notEqual(changedId,first);
  waiting.shift().ok(outcome(changedId));await changed;assert.equal(get('draft').value,'');
  // Pending reload reads status/operation only, retaining the draft until matching success.
  draft('等待回复');const pending=submit(), pendingId=calls.at(-1).body.request_id;
  const pendingState={...terminalState,presentation_pending:true,pending_handle:'handle',pending_request_id:pendingId};
  waiting.shift().ok({case_id:'scene',ok:true,pending:'handle',request_id:pendingId,state:pendingState});
  await flush();await flush();assert.equal(calls.at(-1).path,'/operation');
  waiting.shift().fail();await pending;status={...input.state,cases:[{...input.state.cases[0],state:pendingState}]};
  const sends=calls.filter(c=>c.path==='/send').length;start();await flush();await flush();
  assert.equal(calls.at(-1).path,'/operation');assert.equal(calls.filter(c=>c.path==='/send').length,sends);
  assert.equal(get('draft').value,'等待回复');waiting.shift().ok(outcome(pendingId));await flush();await flush();
  assert.equal(get('draft').value,'');
  draft('重置后仍保留');assert.equal(get('context-reset').disabled,false);get('context-reset').handlers.click();
  const reset=get('reset-confirm').handlers.click();assert.equal(calls.at(-1).path,'/context-reset');
  waiting.shift().ok({...outcome(null),request_id:null});await reset;
  assert.equal(get('draft').value,'重置后仍保留');
  process.stdout.write('free-input-page-complete');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run([node, "-e", harness], input=json.dumps(dict(script=script,
        state=adapter.snapshot())).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stdout == b"free-input-page-complete"

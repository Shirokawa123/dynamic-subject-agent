"""S147 independent entry and user loop with synthetic HTTPS, never real keys."""
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from threading import Event, Thread
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from test_shared_activity_chat_entry import entry_setup, chat
from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_working_understanding_live import WorkingTransport
from test_whole_chat_archive import canonical_path
from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.working_understanding import working_contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def working_entry_setup(entry_setup, monkeypatch):
    shared, _, root, options, reviews, request = entry_setup
    script = importlib.import_module('serve_working_understanding_chat')
    desktop = importlib.import_module('working_understanding_chat')
    live = importlib.import_module('dynamic_subject_agent.working_understanding_live')
    binding = shared.APPROVED_BINDING
    monkeypatch.setattr(script, 'APPROVED_BINDING', binding)
    monkeypatch.setattr(live, 'APPROVED_WORKING_MATERIAL_DIGEST', live.digest(binding))
    monkeypatch.setattr(live, 'APPROVED_WORKING_LOCAL_CONTRACT_SHA', live.digest(working_contract(binding)))
    options.update(transport=WorkingTransport(), audit_path=root.with_name('working-entry-audit'))
    return script, desktop, root.with_name('working-entry'), options, reviews, request


@contextmanager
def http_entry(entry, desktop):
    server = desktop.working_understanding_server(entry.product, reopen=entry.reopen)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    with urlopen(base + '/', timeout=5) as response:
        page = response.read().decode('utf-8')
    token = re.search(r"TOKEN='([^']+)'", page).group(1)
    def get(path):
        with urlopen(base + path, timeout=5) as response:
            return json.load(response)
    def post(path, payload):
        with urlopen(Request(base + path, data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json', 'X-Chat-Token': token}), timeout=10) as response:
            return json.load(response)
    try:
        yield SimpleNamespace(get=get, post=post, page=page, base=base)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


@contextmanager
def owned_fake_http(root):
    """Temporary hidden-page probe using only this module's synthetic fixtures.

    The caller owns an empty absolute root beneath its TEMP parent and closes
    this context after inspection. No production root or credential is used.
    """
    root = Path(root)
    if not root.is_absolute() or not root.is_dir() or any(root.iterdir()):
        raise ValueError('empty owned absolute fixture root required')
    patch = pytest.MonkeyPatch()
    generators = []
    entry = None
    try:
        generator = model_fixture.__wrapped__(root, patch); generators.append(generator); model = next(generator)
        generator = personality_fixture.__wrapped__(model); generators.append(generator); personality = next(generator)
        generator = approved.__wrapped__(personality, root); generators.append(generator); approval = next(generator)
        setup = entry_setup.__wrapped__(approval, patch, root)
        script, desktop, entry_root, options, _, _ = working_entry_setup.__wrapped__(setup, patch)
        entry = script.WorkingUnderstandingChatEntry(entry_root, **options)
        with http_entry(entry, desktop) as http:
            yield http
    finally:
        if entry is not None:
            entry.close()
        for generator in reversed(generators):
            generator.close()
        patch.undo()


def sources(http):
    chat(http, '这一次构图试少量暖色。')
    chat(http, '桌边留白可以帮助看清主体。')
    archive = http.post('/chat-archive', dict(query='', before_sequence=None))['archive']['rows']
    rows = sorted((row for row in archive if row['kind'] == 'turn'), key=lambda row: row['head_sequence'])
    return [dict(source_head_sequence=row['head_sequence'], quote=row['user_text']) for row in rows[-2:]]


def form_payload(http, quotes):
    return dict(request_id=str(uuid4()), expected_revision=http.get('/status')['working_understanding']['view']['revision'],
        sources=quotes, confirmed=True)


def manual(http, kind, payload):
    route = {'form': '/working-understanding-form', 'disable': '/working-understanding-disable', 'advance': '/working-activity-advance'}[kind]
    result = http.post(route, payload)
    deadline = time.monotonic() + 30
    while result['shared_status'] == 'busy' and time.monotonic() < deadline:
        time.sleep(.02)
        result = http.post('/working-understanding-request', dict(kind=kind, request=payload))
    assert result['shared_status'] != 'busy', 'synthetic operation did not settle within the test deadline'
    return result


def advance(http):
    payload = dict(request_id=str(uuid4()), expected_revision=http.get('/status')['working_understanding']['view']['revision'])
    return manual(http, 'advance', payload), payload


def test_entry_schema7_empty_exact_pointer_and_reopen_zero_model(working_entry_setup):
    script, desktop, root, options, reviews, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        assert entry.product._qri.provider_authority == 'original-working-fact-faithful-deepseek-s147-1'
        with sqlite3.connect(canonical_path(entry.product)) as db:
            assert db.execute('PRAGMA user_version').fetchone() == (7,)
            assert db.execute('SELECT COUNT(*) FROM timeline_outcome').fetchone() == (0,)
        marker, registry = (root/'current.json').read_bytes(), entry.config.state_path.read_bytes()
        pointer = json.loads(marker)
        assert pointer['version'] == script.ENTRY_VERSION and pointer['technical_variant'] == 'fact-faithful'
        with http_entry(entry, desktop) as http:
            assert http.get('/health') == dict(application=desktop.APPLICATION_ID)
            assert http.page.count('id="working-panel"') == 1
            for _ in range(3):
                state = http.get('/status')
                assert state['history']['turns'] == [] and not state['presentation_pending']
                assert state['working_understanding']['view']['formation_status'] == 'initial'
                assert state['working_understanding']['view']['visible_understanding'] is None
                assert http.post('/working-understanding', {})['ok']
                assert http.post('/working-activity-preview', {})['ok']
            assert http.post('/reload', {})['ok']
        entry.reopen()
        assert (root/'current.json').read_bytes() == marker and entry.config.state_path.read_bytes() == registry
        assert not options['transport'].calls and options['transport'].credential.reads == 0
        assert len(reviews) == 1
    finally:
        entry.close()
    reopened = script.WorkingUnderstandingChatEntry(root, **dict(options, package_path=root/'absent-owned-package.json'))
    reopened.close()
    assert len(reviews) == 1 and not options['transport'].calls


def test_partial_wrong_pointer_and_old_roots_never_activate_or_recreate(working_entry_setup, monkeypatch):
    script, _, root, options, _, _ = working_entry_setup
    partial = root.with_name('partial-working-entry'); partial.mkdir(); (partial/'initialized').mkdir()
    with pytest.raises(ValueError, match='incomplete'):
        script.WorkingUnderstandingChatEntry(partial, **options)
    assert list(partial.iterdir()) == [partial/'initialized']
    for protected in (script.default_entry_root(), script.final_text_entry_root(), script.context_entry_root()):
        with pytest.raises(ValueError, match='independent'):
            script.WorkingUnderstandingChatEntry(protected, **options)
    entry = script.WorkingUnderstandingChatEntry(root, **options); entry.close()
    pointer = json.loads((root/'current.json').read_text(encoding='utf-8'))
    pointer['technical_variant'] = 'baseline'
    (root/'current.json').write_text(json.dumps(pointer), encoding='utf-8')
    before = entry.config.state_path.read_bytes()
    def forbidden(*a, **kw):
        raise AssertionError('bad pointer cannot activate or cold recover')
    monkeypatch.setattr(script, 'open_working_understanding_product_live', forbidden)
    with pytest.raises(ValueError, match='pointer'):
        script.WorkingUnderstandingChatEntry(root, **options)
    assert entry.config.state_path.read_bytes() == before and not options['transport'].calls


def test_wrong_active_scope_is_purely_rejected_before_opener(working_entry_setup, monkeypatch):
    script, _, root, options, _, request = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options); config = entry.config; entry.close()
    alternate = LocalProductConfig(config.product_parent, root/'alternate-owned-state.json')
    with open_local_product(alternate, cognition=DormantDeepSeekCognition()) as author:
        frozen = author.application.freeze_source_identity(request)
        assert frozen.status in ('created', 'replayed')
    other = json.loads(alternate.state_path.read_text(encoding='utf-8'))
    record = next(row for row in other['identities'] if row['identity_id'] == frozen.view.identity_id)
    state = json.loads(config.state_path.read_text(encoding='utf-8'))
    state['identities'] = [row for row in state['identities'] if row['identity_id'] != record['identity_id']] + [record]
    state['active_identity_id'] = record['identity_id']; state['chat_identity_revision'] += 1
    config.state_path.write_text(json.dumps(state), encoding='utf-8')
    before, pointer = config.state_path.read_bytes(), (root/'current.json').read_bytes()
    monkeypatch.setattr(script, 'open_working_understanding_product_live', lambda *a, **kw: pytest.fail('unverified scope cannot open'))
    with pytest.raises(RuntimeError):
        script.WorkingUnderstandingChatEntry(root, **options)
    assert config.state_path.read_bytes() == before and (root/'current.json').read_bytes() == pointer
    assert not options['transport'].calls


def test_http_two_quotes_form_window_reopen_activity_reply_disable_and_reform(working_entry_setup):
    script, desktop, root, options, _, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            quotes = sources(http)
            first, _ = advance(http); assert first['ok']
            payload = form_payload(http, quotes)
            count = len(options['transport'].calls)
            preview = http.post('/working-understanding-preview', dict(payload, confirmed=False))
            assert preview['ok'] and preview['working_preview']['activity_result'] is not None
            assert [x['quote'] for x in preview['working_preview']['exchanges']] == [x['quote'] for x in quotes]
            assert len(options['transport'].calls) == count
            formed = manual(http, 'form', payload)
            assert formed['ok'] and formed['shared_settled'] and len(options['transport'].calls) == count + 1, formed
            saved = formed['state']['working_understanding']['view']['visible_understanding']
            assert saved['sources'] == quotes and saved['activity_result']['plan'] == first['state']['working_understanding']['view']['current_plan']
            for _ in range(2):
                assert http.post('/working-understanding-request', dict(kind='form', request=payload))['shared_status'] == 'replayed'
                assert http.post('/working-understanding-form', payload)['shared_status'] == 'replayed'
            assert len(options['transport'].calls) == count + 1
            for message in ('说说线条。', '换个话题聊光线。', '再谈画面节奏。'):
                chat(http, message)
            assert http.post('/reload', {})['ok']
            choice, request = advance(http); assert choice['ok']
            scope = http.post('/message-scope', dict(text='说说这一版的具体取舍。'))
            assert scope['ok'] and scope['message_scope']['working_understanding']['statement'] == saved['statement']
            assert scope['message_scope']['activity_result']['plan'] == choice['state']['working_understanding']['view']['current_plan']
            chat(http, '说说这一版的具体取舍。')
            body = json.loads(options['transport'].calls[-1]['messages'][1]['content'])
            assert body['evidence']['working_understanding'] is not None and body['evidence']['shared_experience'] is None
            count = len(options['transport'].calls)
            disable = dict(request_id=str(uuid4()), expected_revision=http.get('/status')['working_understanding']['view']['revision'], sources=[], confirmed=True)
            stopped = manual(http, 'disable', disable)
            assert stopped['ok'] and len(options['transport'].calls) == count
            assert stopped['state']['working_understanding']['view']['formation_status'] == 'disabled'
            scope = http.post('/message-scope', dict(text='现在接着聊一个新构图。'))['message_scope']
            assert scope['working_understanding'] is None and scope['activity_result'] is None
            new_quotes = sources(http)
            # Supply a genuinely different synthetic proposal: the Python
            # adjudicator correctly refuses an identical old plan as revise.
            options['transport'].form_override = dict(status='formed', scope='composition-text',
                statement='本次将少量暖色集中在桌边，留白用来突出主体轮廓。', basis_refs=['U1', 'U2'])
            rebuilt = manual(http, 'form', form_payload(http, new_quotes)); assert rebuilt['ok']
            assert rebuilt['state']['working_understanding']['view']['visible_understanding']['sources'] == new_quotes
            assert advance(http)[0]['ok']
            chat(http, '这一版的留白如何？')
            assert http.post('/reload', {})['ok']
            assert http.post('/working-understanding-request', dict(kind='advance', request=request))['shared_status'] == 'replayed'
    finally:
        entry.close()


def test_source_bounds_canonical_preview_revision_and_history_cutoff_zero_model(working_entry_setup):
    script, desktop, root, options, _, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            quotes = sources(http); payload = form_payload(http, quotes); count = len(options['transport'].calls)
            with pytest.raises(HTTPError) as error:
                http.post('/working-understanding-preview', dict(payload, sources=[quotes[0], quotes[0]]))
            assert error.value.code == 400
            for quote in ('暖色和主体拼接', '不属于已提交原话'):
                bad = [dict(quotes[0], quote=quote), quotes[1]]
                assert not http.post('/working-understanding-preview', dict(payload, sources=bad))['ok']
            assert not http.post('/working-understanding-preview', dict(payload, expected_revision=payload['expected_revision'] + 1))['ok']
            assert http.post('/history', dict(enabled=False))['ok']
            assert not http.post('/working-understanding-preview', payload)['ok']
            assert http.post('/history', dict(enabled=True))['ok']
            boundary = http.post('/context-boundary-query', {})['context_boundary']
            assert http.post('/context-boundary', dict(request_id=str(uuid4()), expected_revision=boundary['context_revision'], confirmed=True))['ok']
            payload['expected_revision'] = http.get('/status')['working_understanding']['view']['revision']
            assert not http.post('/working-understanding-preview', payload)['ok']
            assert len(options['transport'].calls) == count
    finally:
        entry.close()


def test_form_pending_duplicate_exact_nonce_and_other_actions_do_not_send(working_entry_setup):
    script, desktop, root, options, _, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    entered, release = Event(), Event()
    try:
        with http_entry(entry, desktop) as http:
            payload = form_payload(http, sources(http)); count = len(options['transport'].calls)
            options['transport'].callback = lambda: (entered.set(), release.wait(5))
            result = http.post('/working-understanding-form', payload); assert entered.wait(3)
            assert result['shared_status'] == 'busy' and result['state']['working_pending']
            assert http.get('/status')['presentation_pending']
            assert http.post('/working-understanding-form', payload)['shared_status'] == 'busy'
            assert http.post('/working-understanding-request', dict(kind='form', request=payload))['shared_status'] == 'busy'
            assert not http.post('/send', dict(text='尚未发送的下一稿。', request_id=str(uuid4())))['ok']
            assert not http.post('/reload', {})['ok']
            assert not http.post('/history', dict(enabled=False))['ok']
            altered = dict(payload, sources=[dict(payload['sources'][0], quote='暖色'), payload['sources'][1]])
            assert http.post('/working-understanding-form', altered)['shared_status'] == 'conflict'
            assert len(options['transport'].calls) == count + 1
            release.set()
            result = manual(http, 'form', payload)
            assert result['ok'] and len(options['transport'].calls) == count + 1
    finally:
        release.set(); entry.close()


@pytest.mark.parametrize('fault,expected', [('timeout', 'unknown'), ('blank', 'failed-closed'), ('credential', 'unavailable')])
def test_form_failures_lookup_and_reopen_never_retry(working_entry_setup, fault, expected):
    script, desktop, root, options, _, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            payload = form_payload(http, sources(http)); count = len(options['transport'].calls)
            options['transport'].fault = fault
            result = manual(http, 'form', payload)
            assert result['shared_status'] == expected
            calls = len(options['transport'].calls)
            assert calls == count + (0 if fault == 'credential' else 1)
            for _ in range(2):
                result = http.post('/working-understanding-request', dict(kind='form', request=payload))
                assert result['shared_status'] == expected
            assert http.post('/reload', {})['ok']
            assert http.post('/working-understanding-request', dict(kind='form', request=payload))['shared_status'] == expected
            assert len(options['transport'].calls) == calls
    finally:
        entry.close()


def test_insufficient_typed_noop_keeps_understanding_and_exact_nonce(working_entry_setup):
    script, desktop, root, options, _, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            quotes = sources(http); assert manual(http, 'form', form_payload(http, quotes))['ok']
            old = http.get('/status')['working_understanding']['view']['understanding']
            options['transport'].form_override = dict(status='insufficient', scope='composition-text', statement='', basis_refs=[])
            payload = form_payload(http, quotes); result = manual(http, 'form', payload)
            assert result['ok'] and result['shared_status'] == 'no-op' and result['shared_settled']
            assert result['state']['working_understanding']['view']['understanding'] == old
            count = len(options['transport'].calls)
            assert http.post('/working-understanding-request', dict(kind='form', request=payload))['shared_status'] == 'no-op'
            assert manual(http, 'form', payload)['shared_status'] == 'no-op'
            assert len(options['transport'].calls) == count
    finally:
        entry.close()


def test_entry_cold_prepared_form_recovers_exact_nonce_without_new_model(working_entry_setup, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    from dynamic_subject_agent.working_understanding import WorkingSourceQuote, WorkingUnderstandingRequest
    script, desktop, root, options, _, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            payload = form_payload(http, sources(http))
        request = WorkingUnderstandingRequest(entry.product.profile_id, entry.product.timeline_id,
            payload['request_id'], payload['expected_revision'],
            tuple(WorkingSourceQuote(**source) for source in payload['sources']), 'form', True)
        original = TimelineEngine._hit
        def crash(engine, point):
            if point is FaultPoint.AFTER_PLAN_CLAIM:
                raise OSError('synthetic interruption after immutable preparation')
            return original(engine, point)
        with monkeypatch.context() as patch:
            patch.setattr(TimelineEngine, '_hit', crash)
            entry.product.application.apply_working_understanding(request)
        assert len(options['transport'].calls) == 3
    finally:
        entry.close()
    reopened = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        with http_entry(reopened, desktop) as http:
            result = http.post('/working-understanding-request', dict(kind='form', request=payload))
            assert result['ok'] and result['shared_status'] == 'replayed' and result['shared_settled']
            assert result['state']['working_understanding']['view']['visible_understanding']['sources'] == payload['sources']
            assert len(options['transport'].calls) == 3
    finally:
        reopened.close()


def test_launcher_health_reuse_wrong_or_uncertain_port_never_creates_or_focuses(working_entry_setup, monkeypatch):
    script, desktop, root, options, _, _ = working_entry_setup
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(ROOT/'scripts/start_working_understanding_chat.ps1'), '-Python', sys.executable, '-NoBrowser', '-Port', http.base.rsplit(':', 1)[1]],
                env=dict(os.environ, HTTP_PROXY='http://127.0.0.1:1', HTTPS_PROXY='http://127.0.0.1:1', NO_PROXY=''), capture_output=True, timeout=20)
            assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
            assert not options['transport'].calls
    finally:
        entry.close()
    opened = []; monkeypatch.setattr(script.webbrowser, 'open', opened.append)
    monkeypatch.setattr(script, 'WorkingUnderstandingChatEntry', lambda *a, **kw: pytest.fail('occupied or unverified port cannot create'))
    monkeypatch.setattr(sys, 'argv', ['working-entry'])
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return json.dumps(dict(application='living-final-text-chat-s144')).encode()
    monkeypatch.setattr(script, 'urlopen', lambda *a, **kw: Response())
    with pytest.raises(SystemExit, match='其他服务'):
        script.main()
    monkeypatch.setattr(script, 'urlopen', lambda *a, **kw: (_ for _ in ()).throw(URLError(TimeoutError())))
    with pytest.raises(SystemExit, match='不能确认'):
        script.main()
    assert not opened


def test_page_exact_two_quotes_preview_pending_draft_nonce_and_stale_scope(working_entry_setup):
    script, desktop, root, options, _, _ = working_entry_setup
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for desktop page behavior checks')
    entry = script.WorkingUnderstandingChatEntry(root, **options)
    try:
        state = desktop.WorkingUnderstandingChatAdapter(entry.product, reopen=entry.reopen).snapshot()
    finally:
        entry.close()
    source = re.search(r'<script>([\s\S]*?)</script>', (ROOT/'app/desktop/static/working_understanding_chat.html').read_text(encoding='utf-8')).group(1)
    harness = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage=new Map([['s140-draft:old-user-scope','UNTOUCHED_OLD_USER_DRAFT']]),calls=[],waiting=[],nodes=new Map();let nextId=0,status=input.state;
const element=()=>({value:'',textContent:'',disabled:false,children:[],handlers:{},append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},addEventListener(name,handler){this.handlers[name]=handler},focus(){throw Error('no focus')}});
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
function start(){nodes.clear();const sandbox={document:{getElementById:get,createElement:element},sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},crypto:{randomUUID:()=> '00000000-0000-4000-8000-'+String(++nextId).padStart(12,'0')},setTimeout:callback=>setImmediate(callback),fetch:async(path,options)=>{if(path==='/status')return {ok:true,json:async()=>status};calls.push({path,body:JSON.parse(options.body)});return new Promise(resolve=>waiting.push(value=>resolve({ok:true,json:async()=>value})))}};vm.createContext(sandbox);vm.runInContext(input.source,sandbox);get('composer').requestSubmit=()=>get('composer').handlers.submit({preventDefault(){}});return sandbox;}
const flush=()=>new Promise(resolve=>setImmediate(resolve)),draft=text=>{get('draft').value=text;get('draft').handlers.input()},saved=()=>JSON.parse(storage.get('s147-draft:'+input.state.scope_key)||'null'),manual=()=>JSON.parse(storage.get('s147-manual-request:'+input.state.scope_key)||'null');
const textTree=element=>[element.textContent,...element.children.map(textTree)].join(' ');
(async()=>{
 let sandbox=start();await flush();draft('尚未发送的聊天草稿。');
 vm.runInContext('chooseWorking({head_sequence:1,user_text:"逐字<img src=x>原话一。"},0);chooseWorking({head_sequence:1,user_text:"逐字<img src=x>原话一。"},1)',sandbox);
 assert.equal(get('working-preview-open').disabled,true);
 vm.runInContext('chooseWorking({head_sequence:2,user_text:"另一条已提交原话二。"},1)',sandbox);
 get('working-quote-0').value='改写原话';get('working-quote-0').handlers.input();assert.equal(get('working-preview-open').disabled,true);
 get('working-quote-0').value='<img src=x>';get('working-quote-0').handlers.input();assert.equal(get('working-preview-open').disabled,false);
 const previewing=get('working-preview-open').handlers.click(),previewRequest=calls.at(-1).body;
 assert.equal(calls.at(-1).path,'/working-understanding-preview');assert.equal(previewRequest.confirmed,false);assert.deepEqual(previewRequest.sources,[{source_head_sequence:1,quote:'<img src=x>'},{source_head_sequence:2,quote:'另一条已提交原话二。'}]);
 waiting.shift()({ok:true,working_preview:{scope:'composition-text',exchanges:[{label:'U1',quote:'<img src=x>'},{label:'U2',quote:'另一条已提交原话二。'}],activity_result:null},state:input.state});await previewing;
 assert.equal(get('working-form-confirm').disabled,false);assert.equal(manual(),null);assert(textTree(get('working-preview-content')).includes('<img src=x>'));
 const forming=get('working-form-confirm').handlers.click(),original=manual(),id=original.request.request_id;
 assert.equal(calls.at(-1).path,'/working-understanding-form');assert.equal(original.request.confirmed,true);assert.equal(id,previewRequest.request_id);assert.equal(get('draft').disabled,false);
 const pending={...input.state,presentation_pending:true,shared_pending:true,working_pending:true,shared_request_id:id,pending_handle:null,pending_request_id:null,context_boundary:{...input.state.context_boundary,pending:true}};
 waiting.shift()({ok:true,shared_status:'busy',shared_request_id:id,shared_settled:false,state:pending});await flush();await flush();
 assert.equal(calls.at(-1).path,'/working-understanding-request');draft('形成理解时写的下一稿。');await get('composer').requestSubmit();assert.equal(calls.filter(row=>row.path==='/send').length,0);
 const understanding={scope:'composition-text',statement:'当次试少量暖色。',sources:original.request.sources,activity_result:null,basis_refs:['U1','U2'],dependencies:[],revision:1};
 const formed={...input.state,shared_activity:{...input.state.shared_activity,view:{...input.state.shared_activity.view,revision:1}},working_understanding:{status:'available',view:{...input.state.working_understanding.view,revision:1,formation_status:'formed',understanding,visible_understanding:understanding}}};
 waiting.shift()({ok:true,shared_status:'replayed',shared_request_id:id,shared_settled:true,state:formed});await forming;
 assert.equal(manual(),null);assert.equal(get('draft').value,'形成理解时写的下一稿。');assert.equal(saved().text,'形成理解时写的下一稿。');assert(textTree(get('working-sources-view')).includes('<img src=x>'));
 // Browser refresh reads only the saved exact request, including NOT_FOUND.
 storage.set('s147-manual-request:'+input.state.scope_key,JSON.stringify(original));status=formed;sandbox=start();await flush();
 assert.deepEqual(calls.at(-1),{path:'/working-understanding-request',body:original});
 waiting.shift()({ok:false,shared_status:'not-found',shared_request_id:id,shared_settled:false,state:formed});await flush();await flush();
 assert.equal(calls.filter(row=>row.path==='/working-understanding-form').length,1);assert.equal(get('send').disabled,true);assert.equal(get('shared-resume').hidden,false);
 get('shared-release').handlers.click();assert.equal(manual(),null);assert.equal(get('draft').value,'形成理解时写的下一稿。');
 // A changed scope/revision invalidates a prepared source preview.
 vm.runInContext('chooseWorking({head_sequence:3,user_text:"新的原话一。"},0);chooseWorking({head_sequence:4,user_text:"新的原话二。"},1)',sandbox);
 const stale=get('working-preview-open').handlers.click();
 const changed={...formed,shared_activity:{...formed.shared_activity,view:{...formed.shared_activity.view,revision:2}},working_understanding:{...formed.working_understanding,view:{...formed.working_understanding.view,revision:2}}};
 vm.runInContext('render('+JSON.stringify(changed)+')',sandbox);
 waiting.shift()({ok:true,working_preview:{scope:'composition-text',exchanges:[],activity_result:null},state:formed});await stale;
 assert.equal(get('working-form-confirm').disabled,true);assert.equal(get('working-preview').hidden,true);assert.equal(get('draft').value,'形成理解时写的下一稿。');
 // Ordinary send stays explicit, uses its own nonce, and keeps a later draft.
 const chatting=get('composer').requestSubmit();assert.equal(calls.at(-1).path,'/send');const chatId=calls.at(-1).body.request_id;
 waiting.shift()({ok:true,pending:'chat-handle',settled:false,request_id:chatId,state:{...changed,presentation_pending:true,pending_handle:'chat-handle',pending_request_id:chatId}});await flush();await flush();
 assert.equal(get('draft').disabled,false);draft('回复等待时的新草稿。');
 waiting.shift()({ok:true,pending:null,settled:true,request_id:chatId,query_status:'found',request_verified:true,state:changed});await chatting;
 assert.equal(get('draft').value,'回复等待时的新草稿。');assert.equal(saved().text,'回复等待时的新草稿。');
 assert.equal(storage.get('s140-draft:old-user-scope'),'UNTOUCHED_OLD_USER_DRAFT');
 assert.equal(calls.filter(row=>row.path==='/working-understanding-form').length,1);assert.equal(calls.filter(row=>row.path==='/send').length,1);
 process.stdout.write('working-page-exact-source-pending-draft-recovery-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run([node, '-e', harness], input=json.dumps(dict(source=source, state=state)).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    assert result.stdout == b'working-page-exact-source-pending-draft-recovery-complete'

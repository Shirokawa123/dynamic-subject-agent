"""The independent user entry and complete HTTP loop, using synthetic delivery."""
from contextlib import contextmanager
from dataclasses import replace
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
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.shared_activity import SharedActivityStepRequest, SharedExperienceRequest, SHARED_LIVE_AUTHORITY
from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_shared_activity_live import SharedTransport, live_fixture
from test_whole_chat_archive import canonical_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def entry_setup(approved, monkeypatch, tmp_path):
    _, _, request, view = approved
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    base = importlib.import_module('serve_original_whole_chat')
    entry_module = importlib.import_module('serve_shared_activity_chat')
    desktop = importlib.import_module('shared_activity_chat')
    import dynamic_subject_agent.original_whole_chat as contract
    import dynamic_subject_agent.shared_activity_live as live
    asset = json.loads(view.runtime_asset_json)
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    for module in (base, entry_module, contract):
        monkeypatch.setattr(module, 'APPROVED_BINDING', binding)
    monkeypatch.setattr(live, 'APPROVED_SHARED_MATERIAL_DIGEST', live.digest(binding))
    reviews = []
    def review(value):
        reviews.append(value)
        return SimpleNamespace(status='previewed', review_basis=binding['review_basis'])
    monkeypatch.setattr(ApplicationFacade, 'preview_original_character_whole_use_preparation', staticmethod(review))
    def no_select(*a, **kw):
        raise AssertionError('new shared entry must never serve a schema1/old identity')
    monkeypatch.setattr(ApplicationFacade, 'select_local_identity', no_select)
    package = tmp_path / 'owned-package.json'
    package.write_text(request.preparation_json, encoding='utf-8')
    options = dict(live=False, package_path=package, transport=SharedTransport(), audit_path=tmp_path / 'entry-audit')
    return entry_module, desktop, tmp_path / 'shared-entry', options, reviews, request


@contextmanager
def http_entry(entry, desktop):
    server = desktop.shared_activity_server(entry.product, reopen=entry.reopen,
        technical_variant=entry.technical_variant)
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


def chat(http, text):
    payload = dict(text=text, request_id=str(uuid4()))
    result = http.post('/send', payload)
    for _ in range(300):
        if not result.get('pending'):
            break
        time.sleep(.01)
        result = http.post('/request-result', payload)
    assert result['settled'] and result['ok'], result
    return result, payload


def select_source(http, quote=None):
    state = http.get('/status')
    archive = http.post('/chat-archive', dict(query='', before_sequence=None))
    assert archive['ok'], json.dumps(archive, ensure_ascii=False)
    row = next(row for row in archive['archive']['rows'] if row['kind'] == 'turn')
    payload = dict(request_id=str(uuid4()), expected_revision=state['shared_activity']['view']['revision'],
        source_head_sequence=row['head_sequence'], quote=quote or row['user_text'], confirmed=True)
    result = http.post('/shared-experience', payload)
    assert result['ok'] and result['shared_settled'], result
    return result, payload


def advance(http):
    payload = dict(request_id=str(uuid4()), expected_revision=http.get('/status')['shared_activity']['view']['revision'])
    result = http.post('/shared-activity-advance', payload)
    for _ in range(300):
        if result['shared_status'] != 'busy':
            break
        time.sleep(.01)
        result = http.post('/shared-activity-request', dict(kind='advance', request=payload))
    return result, payload


@pytest.mark.parametrize('variant', ['baseline', 'natural-expression', 'self-directed-activity'])
def test_entry_starts_empty_schema5_and_reopens_without_package_or_model(entry_setup, variant):
    script, desktop, root, options, reviews, _ = entry_setup
    entry = script.SharedActivityChatEntry(root, **options, technical_variant=variant)
    try:
        assert entry.product._qri.provider_authority == SHARED_LIVE_AUTHORITY
        with sqlite3.connect(canonical_path(entry.product)) as db:
            assert db.execute('PRAGMA user_version').fetchone() == (5,)
            assert db.execute('SELECT COUNT(*) FROM timeline_outcome').fetchone() == (0,)
        pointer = (root / 'current.json').read_bytes(); identity = entry.identity
        assert json.loads(pointer)['technical_variant'] == variant
        with http_entry(entry, desktop) as http:
            assert http.get('/health') == dict(application=desktop.shared_activity_application_id(variant))
            assert '从已提交原话选一段' in http.page and '明确推进这一步' in http.page
            for _ in range(3):
                assert http.get('/status')['shared_activity']['view']['revision'] == 0
            assert http.post('/reload', {})['ok']
            assert http.post('/shared-activity-preview', {})['shared_preview']['current_plan'] is None
        options['package_path'].unlink()  # Owned synthetic package only.
        entry.reopen()
        assert not options['transport'].calls
    finally:
        entry.close()
    reopened = script.SharedActivityChatEntry(root, **options, technical_variant=variant)
    try:
        assert reopened.identity == identity and (root / 'current.json').read_bytes() == pointer
        assert len(reviews) == 1 and not options['transport'].calls
    finally:
        reopened.close()


def test_entry_partial_pointer_wrong_variant_and_dormant_identity_do_not_activate(entry_setup, monkeypatch):
    script, _, root, options, _, request = entry_setup
    options['package_path'].unlink()
    with pytest.raises(FileNotFoundError):
        script.SharedActivityChatEntry(root, **options)
    assert not root.exists()
    root.mkdir(); (root / 'initialized').mkdir()
    before = tuple(root.iterdir())
    with pytest.raises(ValueError, match='incomplete'):
        script.SharedActivityChatEntry(root, **options)
    assert tuple(root.iterdir()) == before and not options['transport'].calls
    fresh_root = root.with_name('second-owned-entry')
    options['package_path'].write_text(request.preparation_json, encoding='utf-8')
    entry = script.SharedActivityChatEntry(fresh_root, **options)
    config = entry.config; entry.close()
    with pytest.raises(ValueError, match='pointer changed'):
        script.SharedActivityChatEntry(fresh_root, **options, technical_variant='natural-expression')
    alternate = LocalProductConfig(config.product_parent, fresh_root / 'alternate-state.json')
    with open_local_product(alternate, cognition=DormantDeepSeekCognition()) as author:
        frozen = author.application.freeze_source_identity(request)
        assert frozen.status in ('created', 'replayed')
    other = json.loads(alternate.state_path.read_text(encoding='utf-8'))
    record = next(row for row in other['identities'] if row['identity_id'] == frozen.view.identity_id)
    state = json.loads(config.state_path.read_text(encoding='utf-8'))
    state['identities'] = [row for row in state['identities'] if row['identity_id'] != record['identity_id']] + [record]
    state['active_identity_id'] = record['identity_id']; state['chat_identity_revision'] += 1
    config.state_path.write_text(json.dumps(state), encoding='utf-8')
    registry, marker = config.state_path.read_bytes(), (fresh_root / 'current.json').read_bytes()
    def forbidden(*a, **kw):
        raise AssertionError('invalid active identity must not reach activation or cold recovery')
    monkeypatch.setattr(script, 'open_shared_activity_product_live', forbidden)
    with pytest.raises(RuntimeError, match='identity-unverified'):
        script.SharedActivityChatEntry(fresh_root, **options)
    assert config.state_path.read_bytes() == registry and (fresh_root / 'current.json').read_bytes() == marker
    assert not options['transport'].calls


def test_http_complete_experience_activity_followup_restart_and_duplicates(entry_setup):
    script, desktop, root, options, _, _ = entry_setup
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            chat(http, '合成用户原话：我喜欢让桌边留白。')
            selected, selection = select_source(http, '让桌边留白')
            assert http.post('/shared-experience', selection)['shared_status'] == 'replayed'
            for i in range(3):
                chat(http, '合成换题：数字顺序' + str(i))
            count = len(options['transport'].calls)
            assert http.post('/reload', {})['ok']
            assert len(options['transport'].calls) == count
            preview = http.post('/shared-activity-preview', {})
            assert preview['shared_preview']['shared_experience'] == dict(label='E1', quote='让桌边留白')
            result, request = advance(http)
            assert result['ok'] and result['shared_status'] == 'replayed', json.dumps(result, ensure_ascii=False)
            view = result['state']['shared_activity']['view']
            assert view['activity_revision'] == 1 and view['phase'] == 'drafted'
            assert view['decision']['decision_note'] == '合成可见取舍。'
            assert view['result']['kind'] == 'composition-text' and view['result']['plan'] == view['current_plan']
            calls = len(options['transport'].calls)
            for _ in range(3):
                assert http.post('/shared-activity-advance', request)['shared_status'] == 'replayed'
                assert http.post('/shared-activity-request', dict(kind='advance', request=request))['shared_settled']
            assert len(options['transport'].calls) == calls
            assert http.post('/reload', {})['ok']
            assert http.post('/shared-activity-request', dict(kind='advance', request=request))['shared_status'] == 'replayed'
            chat(http, '能说说刚才提交的文字方案吗？')
            payload = json.loads(options['transport'].calls[-1]['messages'][1]['content'])
            assert payload['evidence']['activity_result']['plan'] == view['current_plan']
            assert len(options['transport'].calls) == 6
    finally:
        entry.close()


@pytest.mark.parametrize('control', ['disable', 'history', 'boundary', 'replace'])
def test_http_privacy_controls_filter_experience_plan_and_derived_dialogue(entry_setup, control):
    script, desktop, root, options, _, _ = entry_setup
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            chat(http, '原有合成依据TOKEN，留白。'); select_source(http, 'TOKEN')
            result, _ = advance(http); assert result['ok']
            chat(http, '依赖活动结果的合成回聊。')
            count = len(options['transport'].calls)
            if control == 'history':
                assert http.post('/history', dict(enabled=False))['ok']
            elif control == 'boundary':
                basis = http.post('/context-boundary-query', {})['context_boundary']
                boundary = http.post('/context-boundary', dict(request_id=str(uuid4()), expected_revision=basis['context_revision'], confirmed=True))
                assert boundary['ok']
                scope = http.post('/message-scope', dict(text='当前预览草稿。'))
                assert scope['ok']
                assert scope['message_scope']['context_revision'] == basis['context_revision'] + 1
                assert scope['message_scope']['cutoff_sequence'] == boundary['boundary_receipt']['cutoff_sequence']
                assert scope['message_scope']['recent_dialogue'] == []
                assert scope['message_scope']['shared_experience'] is None and scope['message_scope']['activity_result'] is None
            elif control == 'replace':
                chat(http, '新独立依据NEXT。')
                select_source(http, 'NEXT')
                count += 1
            else:
                revision = http.get('/status')['shared_activity']['view']['revision']
                assert http.post('/shared-experience', dict(request_id=str(uuid4()), expected_revision=revision,
                    source_head_sequence=None, quote='', confirmed=True))['ok']
            assert len(options['transport'].calls) == count
            state = http.get('/status')['shared_activity']['view']
            assert state['visible_result'] is None and state['current_plan'] is None
            assert state['result'] is not None  # Historical outcome is preserved.
            assert http.post('/reload', {})['ok']
            preview = http.post('/shared-activity-preview', {})['shared_preview']
            assert preview['current_plan'] is None and 'TOKEN' not in json.dumps(preview)
            chat(http, '从当前范围接着聊。')
            wire = json.loads(options['transport'].calls[-1]['messages'][1]['content'])
            assert wire['evidence']['activity_result'] is None
            assert 'TOKEN' not in json.dumps(wire) and '依赖活动结果' not in json.dumps(wire)
    finally:
        entry.close()


def test_http_rejects_uncommitted_or_rewritten_quote_and_unread_nonce_never_executes(entry_setup):
    script, desktop, root, options, _, _ = entry_setup
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            missing = dict(request_id=str(uuid4()), expected_revision=0)
            for _ in range(3):
                assert http.post('/shared-activity-request', dict(kind='advance', request=missing))['shared_status'] == 'not-found'
            chat(http, '逐字依据ABC。')
            state = http.get('/status')['shared_activity']['view']
            for quote, head in [('改写ABC', 1), ('逐字依据ABC。', 999)]:
                result = http.post('/shared-experience', dict(request_id=str(uuid4()), expected_revision=state['revision'],
                    source_head_sequence=head, quote=quote, confirmed=True))
                assert result['shared_status'] == 'unavailable'
            with pytest.raises(HTTPError) as error:
                http.post('/shared-experience', dict(request_id=str(uuid4()), expected_revision=state['revision'],
                    source_head_sequence=1, quote='ABC', confirmed=False))
            assert error.value.code == 400
            assert len(options['transport'].calls) == 1
    finally:
        entry.close()


def test_http_pending_duplicate_and_new_draft_have_no_second_delivery(entry_setup):
    script, desktop, root, options, _, _ = entry_setup
    entered, release = Event(), Event()
    class SlowTransport(SharedTransport):
        def post_json(self, **kwargs):
            entered.set()
            assert release.wait(8)
            return super().post_json(**kwargs)
    options['transport'] = SlowTransport()
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            payload = dict(request_id=str(uuid4()), expected_revision=0)
            first = http.post('/shared-activity-advance', payload)
            assert first['shared_status'] == 'busy' and entered.wait(5)
            assert http.get('/status')['shared_pending'] is True
            assert http.post('/shared-activity-advance', payload)['shared_status'] == 'busy'
            assert http.post('/shared-activity-request', dict(kind='advance', request=payload))['shared_status'] == 'busy'
            assert not http.post('/reload', {})['ok']
            assert not http.post('/send', dict(text='未提交新草稿。', request_id=str(uuid4())))['ok']
            assert not http.post('/history', dict(enabled=False))['ok']
            release.set()
            for _ in range(300):
                result = http.post('/shared-activity-request', dict(kind='advance', request=payload))
                if result['shared_status'] != 'busy':
                    break
                time.sleep(.01)
            assert result['ok'] and len(options['transport'].calls) == 1
    finally:
        release.set(); entry.close()


@pytest.mark.parametrize('fault,status', [('blank', 'failed-closed'), ('timeout', 'unknown')])
def test_http_first_failure_is_preserved_and_never_retried(entry_setup, fault, status):
    script, desktop, root, options, _, _ = entry_setup
    options['transport'] = SharedTransport(fault)
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            result, payload = advance(http)
            assert not result['ok'] and result['shared_status'] == status
            shared = result['state']['shared_activity']
            assert shared['status'] in ('available', 'failed-closed')
            if shared['status'] == 'available':
                assert shared['view']['result'] is None
            for _ in range(3):
                assert http.post('/shared-activity-request', dict(kind='advance', request=payload))['shared_status'] == status
                assert http.post('/shared-activity-advance', payload)['shared_status'] == status
            assert http.post('/reload', {})['ok']
            assert http.post('/shared-activity-request', dict(kind='advance', request=payload))['shared_status'] == status
            assert len(options['transport'].calls) == 1
    finally:
        entry.close()


def test_readonly_request_observation_does_not_claim_or_recover_and_checks_exact_payload(live_fixture, monkeypatch):
    opening, _, _, _ = live_fixture
    transport = SharedTransport(); product = opening(transport)
    request = SharedActivityStepRequest(product.profile_id, product.timeline_id, str(uuid4()), 0)
    assert product.application.query_shared_activity(request).status == 'not-found'
    assert not transport.calls
    before = canonical_path(product).read_bytes()
    for _ in range(3):
        assert product.application.query_shared_activity(request).status == 'not-found'
    assert canonical_path(product).read_bytes() == before
    assert product.application.query_shared_activity(replace(request, target_profile_id=str(uuid4()))).status == 'unavailable'
    assert product.application.query_shared_activity(object()).status == 'unavailable'
    original = TimelineEngine._hit
    def crash(self, point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError('synthetic prepared interruption')
        return original(self, point)
    with monkeypatch.context() as patch:
        patch.setattr(TimelineEngine, '_hit', crash)
        product.application.advance_shared_activity(request)
    assert len(transport.calls) == 1
    assert product.application.query_shared_activity(request).status == 'busy'
    assert product.application.query_shared_activity(replace(request, expected_revision=1)).status == 'conflict'
    product.close(); product = opening(transport)
    assert product.application.query_shared_activity(request).status == 'replayed'
    assert len(transport.calls) == 1 and product.application.query_shared_activity().view['activity_revision'] == 1


def test_entry_cold_recovers_prepared_action_and_reads_same_receipt_without_second_request(entry_setup, monkeypatch):
    script, desktop, root, options, _, _ = entry_setup
    entry = script.SharedActivityChatEntry(root, **options)
    request = SharedActivityStepRequest(entry.product.profile_id, entry.product.timeline_id, str(uuid4()), 0)
    original = TimelineEngine._hit
    def crash(self, point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError('synthetic interruption after exact prepared plan')
        return original(self, point)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(TimelineEngine, '_hit', crash)
            entry.product.application.advance_shared_activity(request)
        assert entry.product.application.query_shared_activity(request).status == 'busy'
        assert len(options['transport'].calls) == 1
    finally:
        entry.close()
    reopened = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(reopened, desktop) as http:
            payload = dict(request_id=request.request_id, expected_revision=request.expected_revision)
            result = http.post('/shared-activity-request', dict(kind='advance', request=payload))
            assert result['shared_status'] == 'replayed' and result['shared_receipt'] is not None
            assert result['state']['shared_activity']['view']['activity_revision'] == 1
            assert http.post('/shared-activity-advance', payload)['shared_status'] == 'replayed'
            assert len(options['transport'].calls) == 1
    finally:
        reopened.close()


def test_activity_archive_preserves_verified_origins_and_rejects_corrupt_shared_record(entry_setup):
    script, desktop, root, options, _, _ = entry_setup
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            chat(http, '合成已提交用户原话。'); select_source(http)
            result, _ = advance(http); assert result['ok']
            archive = http.post('/chat-archive', dict(query='', before_sequence=None))
            assert archive['ok'] and len(archive['archive']['rows']) == 1
            assert archive['archive']['rows'][0]['user_text'] == '合成已提交用户原话。'
            calls = len(options['transport'].calls)
            with sqlite3.connect(canonical_path(entry.product)) as db:
                db.execute("UPDATE shared_activity_record SET record_json='{}'")
            bad = http.post('/chat-archive', dict(query='', before_sequence=None))
            assert not bad['ok'] and bad['archive'] == dict(status='failed-closed')
            assert len(options['transport'].calls) == calls
    finally:
        entry.close()


def test_entry_health_variant_conflict_never_initializes_or_focuses(entry_setup, monkeypatch):
    script, _, _, _, _, _ = entry_setup
    opened = []
    monkeypatch.setattr(script.webbrowser, 'open', opened.append)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return json.dumps(dict(application=script.APPLICATION_ID)).encode()
    monkeypatch.setattr(script, 'urlopen', lambda *a, **kw: Response())
    def forbidden(*a, **kw): raise AssertionError('occupied port must never initialize a new root')
    monkeypatch.setattr(script, 'SharedActivityChatEntry', forbidden)
    monkeypatch.setattr('sys.argv', ['entry'])
    script.main(); assert not opened
    monkeypatch.setattr('sys.argv', ['entry', '--technical-variant', 'natural-expression'])
    with pytest.raises(SystemExit, match='其他服务'):
        script.main()
    assert not opened


def test_launcher_validates_existing_interpreter_and_reuses_exact_health_without_focus(entry_setup):
    script, desktop, root, options, _, _ = entry_setup
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            port = int(http.base.rsplit(':', 1)[1])
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(ROOT / 'scripts/start_shared_activity_chat.ps1'), '-Python', sys.executable, '-NoBrowser', '-Port', str(port)],
                env=dict(os.environ, HTTP_PROXY='http://127.0.0.1:1', HTTPS_PROXY='http://127.0.0.1:1', NO_PROXY=''),
                capture_output=True, timeout=20)
            assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
            assert not options['transport'].calls
    finally:
        entry.close()


def test_shared_page_keeps_new_draft_after_pending_and_refresh_never_resubmits(entry_setup):
    script, desktop, root, options, _, _ = entry_setup
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the desktop JavaScript behavior checks')
    entry = script.SharedActivityChatEntry(root, **options)
    try:
        state = desktop.SharedActivityChatAdapter(entry.product, reopen=entry.reopen).snapshot()
    finally:
        entry.close()
    source = re.search(r'<script>([\s\S]*?)</script>', (ROOT / 'app/desktop/static/shared_activity_chat.html').read_text(encoding='utf-8')).group(1)
    harness = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage=new Map(),calls=[],waiting=[],nodes=new Map();let nextId=0,status=input.state;
const element=()=>({value:'',textContent:'',disabled:false,children:[],handlers:{},append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},addEventListener(name,handler){this.handlers[name]=handler},focus(){throw Error('no focus')}});
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
function start(){nodes.clear();const sandbox={document:{getElementById:get,createElement:element},sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},crypto:{randomUUID:()=> '00000000-0000-4000-8000-'+String(++nextId).padStart(12,'0')},setTimeout:callback=>setImmediate(callback),fetch:async(path,options)=>{if(path==='/status')return {ok:true,json:async()=>status};calls.push({path,body:JSON.parse(options.body)});return new Promise(resolve=>waiting.push(value=>resolve({ok:true,json:async()=>value})))}};vm.createContext(sandbox);vm.runInContext(input.source,sandbox);get('composer').requestSubmit=()=>get('composer').handlers.submit({preventDefault(){}});return sandbox;}
const flush=()=>new Promise(resolve=>setImmediate(resolve)),draft=text=>{get('draft').value=text;get('draft').handlers.input()},saved=()=>JSON.parse(storage.get('s140-draft:'+input.state.scope_key)||'null'),manual=()=>JSON.parse(storage.get('s140-shared-request:'+input.state.scope_key)||'null');
(async()=>{
 let sandbox=start();await flush();draft('活动前的未发送草稿。');
 const next=get('shared-next').handlers.click();assert.equal(calls.at(-1).path,'/shared-activity-preview');
 waiting.shift()({ok:true,shared_preview:{shared_experience:null,current_activity:{phase:'unstarted',allowed_actions:['start','defer']},current_plan:null},state:input.state});await next;
 const advancing=get('shared-advance-confirm').handlers.click(),original=manual(),id=original.request.request_id;
 assert.equal(calls.at(-1).path,'/shared-activity-advance');assert.equal(get('draft').disabled,false);
 const pending={...input.state,presentation_pending:true,shared_pending:true,shared_request_id:id,pending_handle:null,pending_request_id:null,context_boundary:{...input.state.context_boundary,pending:true}};
 waiting.shift()({ok:true,shared_status:'busy',shared_request_id:id,shared_settled:false,state:pending});await flush();await flush();
 assert.equal(calls.at(-1).path,'/shared-activity-request');assert.equal(get('draft').disabled,false);assert.equal(get('send').disabled,true);
 draft('等待活动时写的下一稿。');await get('composer').requestSubmit();assert.equal(calls.filter(row=>row.path==='/send').length,0);
 waiting.shift()({ok:true,shared_status:'replayed',shared_request_id:id,shared_settled:true,state:input.state});await advancing;
 assert.equal(get('draft').value,'等待活动时写的下一稿。');assert.equal(saved().text,'等待活动时写的下一稿。');assert.equal(manual(),null);
 // Restored unknown attempt only reads its original request, even if absent.
 storage.set('s140-shared-request:'+input.state.scope_key,JSON.stringify(original));sandbox=start();await flush();
 assert.deepEqual(calls.at(-1),{path:'/shared-activity-request',body:original});
 waiting.shift()({ok:false,shared_status:'not-found',shared_request_id:id,shared_settled:false,state:input.state});await flush();await flush();
 assert.equal(calls.filter(row=>row.path==='/shared-activity-advance').length,1);assert.equal(get('draft').value,'等待活动时写的下一稿。');
 assert.equal(get('shared-resume').hidden,false);assert.equal(get('send').disabled,true);
 get('shared-release').handlers.click();assert.equal(manual(),null);assert.equal(get('draft').value,'等待活动时写的下一稿。');
 // New normal chat remains explicit and does not inherit the manual nonce.
 const chatting=get('composer').requestSubmit();assert.equal(calls.at(-1).path,'/send');const chatId=calls.at(-1).body.request_id;
 waiting.shift()({ok:true,settled:true,pending:null,request_id:chatId,state:input.state});await chatting;
 assert.equal(calls.filter(row=>row.path==='/shared-activity-advance').length,1);assert.equal(get('draft').value,'');
 // Local text rendering, exact quote selection, and no focus or HTML execution.
 vm.runInContext('chooseShared({head_sequence:1,user_text:"逐字<img src=x>原话。"})',sandbox);
 get('shared-quote').value='改写原话';get('shared-quote').handlers.input();assert.equal(get('shared-select-confirm').disabled,true);
 get('shared-quote').value='<img src=x>';get('shared-quote').handlers.input();assert.equal(get('shared-select-confirm').disabled,false);
 // Actual local differences show only current after values. An unavailable
 // source can leave before values in the saved record, never in this view.
 const plan={subject:'窗边静物',composition:'减少背景线条<img src=x>',focus:'轮廓'},result={kind:'composition-text',plan,differences:[{field:'composition',before:'STOPPED_PRIVATE_OLD_SOURCE',after:plan.composition}]};
 const revised={...input.state,shared_activity:{status:'available',view:{...input.state.shared_activity.view,phase:'revised',activity_revision:2,decision:{action:'revise',reason_code:'improve-readability',basis_refs:[],decision_note:'本次突出轮廓。'},result,visible_result:result}}};
 vm.runInContext('render('+JSON.stringify(revised)+')',sandbox);
 const textTree=element=>[element.textContent,...element.children.map(textTree)].join(' ');
 assert(textTree(get('shared-changes')).includes('本次已提交变化'));assert(textTree(get('shared-changes')).includes('构图'));assert(textTree(get('shared-changes')).includes(plan.composition));
 assert(!textTree(get('shared-changes')).includes('STOPPED_PRIVATE_OLD_SOURCE'));
 vm.runInContext('render('+JSON.stringify({...revised,shared_activity:{status:'available',view:{...revised.shared_activity.view,visible_result:null}}})+')',sandbox);
 assert.equal(get('shared-changes').children.length,0);
 const deferred={...input.state,shared_activity:{status:'available',view:{...input.state.shared_activity.view,phase:'deferred',decision:{action:'defer',reason_code:'defer-comparison',basis_refs:[],decision_note:'本次先不形成方案。'},result:{kind:'composition-text',plan:null},visible_result:{kind:'composition-text',plan:null}}}};
 vm.runInContext('render('+JSON.stringify(deferred)+')',sandbox);
 assert(get('shared-plan').children.some(row=>row.textContent.includes('没有形成新文字方案')));
 assert(textTree(get('shared-changes')).includes('暂缓 · 本次没有提交新方案。'));
 process.stdout.write('shared-page-pending-draft-recovery-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run([node, '-e', harness], input=json.dumps(dict(source=source, state=state)).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    assert result.stdout == b'shared-page-pending-draft-recovery-complete'

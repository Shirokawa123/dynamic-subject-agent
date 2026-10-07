"""S143 user entry: synthetic delivery, exact HTTP recovery and page behavior."""
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
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_shared_activity_chat_entry import entry_setup, chat, select_source
from test_living_activity_live import LivingTransport
from test_whole_chat_archive import canonical_path
from dynamic_subject_agent.living_activity import LivingClock, LivingPresenceRequest, living_contract
from dynamic_subject_agent.shared_activity import LIVING_LIVE_AUTHORITY
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def living_entry_setup(entry_setup, monkeypatch):
    shared_script, _, root, options, reviews, request = entry_setup
    script = importlib.import_module('serve_living_activity_chat')
    desktop = importlib.import_module('living_activity_chat')
    live = importlib.import_module('dynamic_subject_agent.living_activity_live')
    binding = shared_script.APPROVED_BINDING
    monkeypatch.setattr(script, 'APPROVED_BINDING', binding)
    monkeypatch.setattr(live, 'APPROVED_LIVING_MATERIAL_DIGEST', live.digest(binding))
    monkeypatch.setattr(live, 'APPROVED_LIVING_LOCAL_CONTRACT_SHA', live.digest(living_contract(binding)))
    now = [0.0]
    options.update(transport=LivingTransport(), clock=LivingClock(lambda: now[0]), day=lambda: '2026-10-07')
    return script, desktop, root.with_name('living-entry'), options, reviews, request, now


@contextmanager
def http_entry(entry, desktop, *, simulation=False):
    server = desktop.living_activity_server(entry.product, reopen=entry.reopen, allow_simulation=simulation)
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
    from types import SimpleNamespace
    try:
        yield SimpleNamespace(get=get, post=post, page=page, base=base)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def control(http, *, paused=None, sharing=None):
    permission = http.get('/status')['living_controls']['view']
    payload = dict(request_id=str(uuid4()), expected_permission_revision=permission['revision'],
        paused=paused, sharing_enabled=sharing, confirmed=True)
    result = http.post('/living-controls', payload)
    assert result['ok'], result
    return result, payload


def action(http, kind, session=None, payload=None):
    if payload is None:
        payload = dict(request_id=str(uuid4()), expected_revision=http.get('/status')['living_activity']['view']['revision'])
        if kind == 'online':
            payload['session_id'] = session
    route = {'online': '/living-heartbeat', 'simulation': '/living-simulation', 'share': '/living-share'}[kind]
    result = http.post(route, payload)
    for _ in range(400):
        if result['living_status'] != 'busy':
            break
        time.sleep(.005)
        result = http.post('/living-request', dict(kind=kind, request=payload))
    return result, payload


def test_new_entry_exact_schema6_empty_defaults_and_readonly_reopen(living_entry_setup):
    script, desktop, root, options, reviews, _, now = living_entry_setup
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        assert entry.product._qri.provider_authority == LIVING_LIVE_AUTHORITY
        with sqlite3.connect(canonical_path(entry.product)) as db:
            assert db.execute('PRAGMA user_version').fetchone() == (6,)
            assert db.execute('SELECT COUNT(*) FROM timeline_outcome').fetchone() == (0,)
        marker, registry = (root / 'current.json').read_bytes(), entry.config.state_path.read_bytes()
        with http_entry(entry, desktop) as http:
            assert http.get('/health') == dict(application=desktop.APPLICATION_ID)
            assert http.page.count('id="living-panel"') == 1
            for _ in range(3):
                state = http.get('/status')
                assert state['living_controls']['view'] == dict(paused=True, sharing_enabled=False,
                    revision=0, needs_attention=False, source_blocked=False)
                assert state['history']['turns'] == state['chat_messages'] == []
                assert http.post('/living-controls-query', {})['ok']
                assert http.post('/shared-activity', {})['ok']
            blocked, _ = action(http, 'simulation')
            assert blocked['living_status'] == 'unavailable'
            assert '生活已暂停' not in blocked['message']
            assert http.post('/reload', {})['ok']
        options['package_path'].unlink()  # This fixture owns only this synthetic source.
        now[0] = 10000
        entry.reopen()
        assert not options['transport'].calls and options['clock'].owner is None
        assert (root / 'current.json').read_bytes() == marker and entry.config.state_path.read_bytes() == registry
    finally:
        entry.close()
    reopened = script.LivingActivityChatEntry(root, **options)
    reopened.close()
    assert len(reviews) == 1 and not options['transport'].calls


def test_partial_or_wrong_active_entry_preserves_data_before_any_activation(living_entry_setup, monkeypatch):
    script, _, root, options, _, request, _ = living_entry_setup
    partial = root.with_name('partial-owned-living-entry')
    partial.mkdir(); (partial/'initialized').mkdir()
    with pytest.raises(ValueError, match='incomplete'):
        script.LivingActivityChatEntry(partial, **options)
    assert list(partial.iterdir()) == [partial/'initialized']
    entry = script.LivingActivityChatEntry(root, **options)
    config = entry.config; entry.close()
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
    def forbidden(*args, **kwargs):
        raise AssertionError('unverified identity cannot activate or cold recover')
    monkeypatch.setattr(script, 'open_living_activity_product_live', forbidden)
    with pytest.raises(RuntimeError):
        script.LivingActivityChatEntry(root, **options)
    assert config.state_path.read_bytes() == before and (root/'current.json').read_bytes() == pointer
    assert not options['transport'].calls


def test_http_distinct_choice_share_origin_followup_and_nonce_recovery(living_entry_setup):
    script, desktop, root, options, _, _, _ = living_entry_setup
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop, simulation=True) as http:
            control(http, paused=False, sharing=True)
            choice, request = action(http, 'simulation')
            assert choice['ok'] and choice['living_status'] == 'replayed'
            assert len(options['transport'].calls) == 1 and choice['state']['chat_messages'] == []
            assert choice['state']['living_activity']['view']['share_gate'] == ''
            shared, sharing = action(http, 'share')
            assert shared['ok'] and len(options['transport'].calls) == 2
            messages = shared['state']['chat_messages']; assert len(messages) == 1
            assert messages[0]['kind'] == 'assistant-share' and messages[0]['user_text'] == ''
            assert messages[0]['assistant_text'] == shared['state']['living_activity']['view']['shares'][0]['text']
            assert shared['state']['history']['turns'] == []
            archive = http.post('/chat-archive', dict(query='合成分享', before_sequence=None))
            assert archive['ok'] and archive['archive']['rows'] == messages
            for _ in range(3):
                assert http.post('/living-request', dict(kind='share', request=sharing))['living_status'] == 'replayed'
                assert http.post('/living-share', sharing)['living_status'] == 'replayed'
            assert len(options['transport'].calls) == 2
            assert http.post('/reload', {})['ok']
            assert http.post('/living-request', dict(kind='simulation', request=request))['living_status'] == 'replayed'
            for index in range(3):
                preview = http.post('/message-scope', dict(text='说说这个安排。'))
                assert preview['ok'] and bool(preview['message_scope']['latest_share']) is (index < 2)
                if index == 2:
                    assert preview['message_scope']['recent_dialogue'] == []
                    assert preview['message_scope']['has_prior_committed_exchange'] is True
                chat(http, '说说这个安排。' if index < 2 else '换个话题聊线条。')
                payload = json.loads(options['transport'].calls[-1]['messages'][1]['content'])
                assert bool(payload['evidence']['latest_share']) is (index < 2)
                if index == 2:
                    assert payload['exchange'] == []
                    assert payload['turn']['has_prior_committed_exchange'] is True
            state = http.get('/status')
            assert [row['kind'] for row in state['chat_messages']] == ['assistant-share', 'turn', 'turn', 'turn']
            assert len(state['history']['turns']) == 3 and len(options['transport'].calls) == 5
    finally:
        entry.close()


def test_online_owner_queries_do_not_renew_and_restart_discards_time(living_entry_setup):
    script, desktop, root, options, _, _, now = living_entry_setup
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            control(http, paused=False)
            session, other = str(uuid4()), str(uuid4())
            first, original = action(http, 'online', session)
            assert first['living_problem_code'] == 'online-baseline'
            now[0] += 10
            assert action(http, 'online', other)[0]['living_problem_code'] == 'another-life-window'
            for _ in range(3):
                assert http.post('/living-request', dict(kind='online', request=original))['living_status'] == 'no-op'
                http.get('/status'); http.post('/living-controls-query', {})
            now[0] += 6
            # Queries and a competing page have not renewed the old owner.
            assert http.get('/status')['living_activity']['view']['online_seconds'] == 0
            assert action(http, 'online', other)[0]['living_problem_code'] == 'online-baseline'
            for _ in range(89):
                now[0] += 10
                assert action(http, 'online', other)[0]['living_status'] == 'no-op'
            assert not options['transport'].calls
            now[0] += 10
            choice, request = action(http, 'online', other)
            assert choice['living_status'] == 'replayed' and len(options['transport'].calls) == 1
            assert choice['state']['living_activity']['view']['visible_result']['event']['simulated'] is False
            assert not choice['state']['living_activity']['view']['shares']
            # The same nonce cannot accrue or request a second opportunity.
            assert action(http, 'online', other, request)[0]['living_status'] == 'replayed'
            now[0] += 10
            action(http, 'online', other)
            assert http.post('/reload', {})['ok']
            assert options['clock'].owner is None
            assert action(http, 'online', other)[0]['living_problem_code'] == 'online-baseline'
            now[0] += 10000
            assert action(http, 'online', session)[0]['living_problem_code'] == 'online-baseline'
            assert len(options['transport'].calls) == 1
    finally:
        entry.close()


def test_presence_during_long_pending_chat_keeps_prior_seconds_without_any_publication(living_entry_setup):
    script, desktop, root, options, _, _, now = living_entry_setup
    entered, release = Event(), Event()
    class PendingTransport(LivingTransport):
        def post_json(self, **kwargs):
            response = super().post_json(**kwargs)
            entered.set(); assert release.wait(10)
            return response
    options['transport'] = PendingTransport()
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            control(http, paused=False)
            session = str(uuid4())
            first = http.post('/living-presence', dict(session_id=session))
            assert first['ok'] and first['presence_problem_code'] == 'online-baseline'
            now[0] += 10
            assert http.post('/living-presence', dict(session_id=session))['presence']['online_seconds'] == 10
            store_path = canonical_path(entry.product)
            pending = dict(text='合成普通用户原话，回复等待中。', request_id=str(uuid4()))
            assert http.post('/send', pending)['pending']
            assert entered.wait(5)
            canonical, registry = store_path.read_bytes(), entry.config.state_path.read_bytes()
            # The page remains present for an injected 20-second pending
            # interval. The previous 10 seconds must remain in the opportunity.
            for expected in (20, 30):
                now[0] += 10
                result = http.post('/living-presence', dict(session_id=session))
                assert result['ok'] and result['presence']['session_owner'] is True, result
                assert result['presence']['online_seconds'] == expected and result['presence']['opportunity_due'] is False
            assert store_path.read_bytes() == canonical
            assert entry.config.state_path.read_bytes() == registry and len(options['transport'].calls) == 1
            assert http.get('/status')['presentation_pending'] is True
            release.set()
            for _ in range(300):
                result = http.post('/request-result', pending)
                if not result.get('pending'):
                    break
                time.sleep(.01)
            assert result['ok'] and result['settled']
            assert result['state']['living_activity']['view']['online_seconds'] == 30
            assert len(options['transport'].calls) == 1
    finally:
        release.set(); entry.close()


def test_presence_due_never_consumes_and_idle_choice_claims_once_with_owner_and_pause_fences(living_entry_setup):
    script, desktop, root, options, _, _, now = living_entry_setup
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            control(http, paused=False)
            session, other = str(uuid4()), str(uuid4())
            assert http.post('/living-presence', dict(session_id=session))['presence']['online_seconds'] == 0
            canonical, registry = canonical_path(entry.product).read_bytes(), entry.config.state_path.read_bytes()
            for _ in range(89):
                now[0] += 10
                result = http.post('/living-presence', dict(session_id=session))
                assert result['ok'] and result['presence']['opportunity_due'] is False
            now[0] += 10
            for _ in range(2):
                result = http.post('/living-presence', dict(session_id=session))
                assert result['presence_problem_code'] == 'online-ready'
                assert result['presence']['opportunity_due'] is True and result['presence']['online_seconds'] == 900
            assert not options['transport'].calls
            assert canonical_path(entry.product).read_bytes() == canonical and entry.config.state_path.read_bytes() == registry
            wrong = LivingPresenceRequest(str(uuid4()), entry.product.timeline_id, session)
            assert entry.product.application.heartbeat_living_presence(wrong).status == 'unavailable'
            assert entry.product.application.heartbeat_living_presence(object()).status == 'unavailable'
            assert options['clock'].seconds == 900
            conflict, _ = action(http, 'online', session, dict(request_id=str(uuid4()), expected_revision=99, session_id=session))
            assert conflict['living_status'] == 'conflict' and options['clock'].seconds == 900 and not options['transport'].calls
            chosen, original = action(http, 'online', session)
            assert chosen['ok'] and len(options['transport'].calls) == 1
            assert options['clock'].seconds == 0
            assert action(http, 'online', session, original)[0]['living_status'] == 'replayed'
            assert action(http, 'online', session)[0]['living_status'] == 'no-op'
            now[0] += 10
            assert http.post('/living-presence', dict(session_id=session))['presence']['online_seconds'] == 10
            contested = http.post('/living-presence', dict(session_id=other))
            assert contested['presence_problem_code'] == 'another-life-window'
            assert contested['presence']['session_owner'] is False and contested['presence']['opportunity_due'] is False
            now[0] += 16
            assert http.post('/living-presence', dict(session_id=other))['presence']['online_seconds'] == 0
            control(http, paused=True)
            paused = http.post('/living-presence', dict(session_id=other))
            assert paused['presence_problem_code'] == 'paused' and paused['presence']['online_seconds'] == 0
            assert paused['presence']['session_owner'] is False and paused['presence']['opportunity_due'] is False
            control(http, paused=False)
            assert http.post('/living-presence', dict(session_id=session))['presence']['online_seconds'] == 0
            now[0] += 10
            assert http.post('/living-presence', dict(session_id=session))['presence']['online_seconds'] == 10
            assert http.post('/reload', {})['ok']
            assert http.post('/living-presence', dict(session_id=session))['presence']['online_seconds'] == 0
            assert len(options['transport'].calls) == 1
    finally:
        entry.close()


@pytest.mark.parametrize('fault,status', [('blank', 'failed-closed'), ('timeout', 'unknown'), ('credential', 'unavailable')])
def test_technical_failure_preserves_typed_original_and_pure_controls(living_entry_setup, fault, status):
    script, desktop, root, options, _, _, _ = living_entry_setup
    options['transport'] = LivingTransport(fault)
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop, simulation=True) as http:
            control(http, paused=False, sharing=True)
            result, original = action(http, 'simulation')
            assert result['living_status'] == status and not result['ok']
            for _ in range(3):
                observed = http.post('/living-request', dict(kind='simulation', request=original))
                assert observed['living_status'] == status
                assert action(http, 'simulation', payload=original)[0]['living_status'] == status
            state = http.post('/living-controls-query', {})['state']
            assert state['living_controls']['status'] == 'available'
            assert state['living_controls']['view']['needs_attention'] is True
            assert state['living_controls']['view']['paused'] is True
            if status == 'unknown':
                assert state['living_activity'] == dict(status='failed-closed')
                assert state['chat_messages_status'] == 'failed-closed' and state['chat_messages'] == []
            assert http.post('/reload', {})['ok']
            assert http.post('/living-request', dict(kind='simulation', request=original))['living_status'] == status
            assert len(options['transport'].calls) == 1
    finally:
        entry.close()
    reopened = script.LivingActivityChatEntry(root, **options)
    try:
        state = desktop.LivingActivityChatAdapter(reopened.product, reopen=reopened.reopen).snapshot()
        assert state['living_controls']['view']['needs_attention'] is True
        if status == 'unknown':
            assert state['living_activity'] == dict(status='failed-closed')
            assert state['presentation_blocked'] is True and state['chat_messages'] == []
        assert len(options['transport'].calls) == 1
    finally:
        reopened.close()


def test_pause_during_choice_rejects_changed_permission_and_keeps_drafts_unsent(living_entry_setup):
    script, desktop, root, options, _, _, _ = living_entry_setup
    entered, release = Event(), Event()
    class SlowTransport(LivingTransport):
        def post_json(self, **kwargs):
            entered.set(); assert release.wait(10)
            return super().post_json(**kwargs)
    options['transport'] = SlowTransport()
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop, simulation=True) as http:
            control(http, paused=False, sharing=True)
            original = dict(request_id=str(uuid4()), expected_revision=0)
            assert http.post('/living-simulation', original)['living_status'] == 'busy'
            assert entered.wait(5)
            assert http.get('/status')['living_pending'] is True
            other = dict(request_id=str(uuid4()), expected_revision=0, session_id=str(uuid4()))
            assert http.post('/living-heartbeat', other)['living_status'] == 'busy'
            assert http.post('/living-request', dict(kind='online', request=other))['living_status'] == 'busy'
            assert not http.post('/message-scope', dict(text='另一页尚未提交的草稿。'))['ok']
            paused, _ = control(http, paused=True)
            assert paused['state']['living_controls']['view']['paused'] is True
            assert not http.post('/send', dict(text='没有提交的下一稿。', request_id=str(uuid4())))['ok']
            assert not http.post('/reload', {})['ok']
            release.set()
            result, _ = action(http, 'simulation', payload=original)
            assert result['living_status'] == 'failed-closed'
            assert result['state']['living_activity']['view']['visible_result'] is None
            assert len(options['transport'].calls) == 1
    finally:
        release.set(); entry.close()


def test_false_share_no_message_and_unanswered_daily_and_source_controls(living_entry_setup):
    script, desktop, root, options, _, _, _ = living_entry_setup
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop, simulation=True) as http:
            def new_plan():
                # The synthetic model respects the real phase progression;
                # revised -> keep -> revise is not fabricated into one stage.
                for _ in range(2):
                    result, _ = action(http, 'simulation')
                    assert result['ok'], result
                    visible = result['state']['living_activity']['view']['visible_result']
                    if visible is not None and visible['event']['kind'] in ('start', 'revise') and visible['plan'] is not None:
                        return
                raise AssertionError('synthetic allowed actions did not form a new plan')
            control(http, paused=False, sharing=True)
            chat(http, '合成用户原话：我想试试窗边留白。'); select_source(http, '窗边留白')
            action(http, 'simulation')
            options['transport'].override = dict(share=False, reply_text='', language='zh')
            false, _ = action(http, 'share')
            assert false['ok'] and false['state']['living_activity']['view']['shares'] == []
            assert all(row['kind'] != 'assistant-share' for row in false['state']['chat_messages'])
            count = len(options['transport'].calls)
            assert action(http, 'share')[0]['living_status'] == 'no-op'
            assert len(options['transport'].calls) == count
            options['transport'].override = None
            for index in range(2):
                if index:
                    chat(http, '我看到你刚才的分享了。')
                new_plan(); shared, _ = action(http, 'share')
                assert shared['ok'] and len(shared['state']['living_activity']['view']['shares']) == index+1
                new_plan()
                count = len(options['transport'].calls)
                assert action(http, 'share')[0]['living_problem_code'] == 'living-awaiting-reply'
                assert len(options['transport'].calls) == count
            chat(http, '我看到第二次分享了。'); new_plan()
            count = len(options['transport'].calls)
            assert action(http, 'share')[0]['living_problem_code'] == 'living-daily-topic-limit'
            assert len(options['transport'].calls) == count
            source = dict(request_id=str(uuid4()), expected_revision=http.get('/status')['shared_activity']['view']['revision'],
                source_head_sequence=None, quote='', confirmed=True)
            assert http.post('/shared-experience', source)['ok']
            assert http.post('/message-scope', dict(text='现在参考什么？'))['message_scope']['shared_experience'] is None
            assert http.get('/status')['living_activity']['view']['visible_result'] is None
            # Local archived shares remain accurately attributed after disable.
            assert sum(row['kind']=='assistant-share' for row in http.get('/status')['chat_messages']) == 2
    finally:
        entry.close()


def test_launcher_exact_health_is_zero_calls_and_never_focuses(living_entry_setup, monkeypatch):
    script, desktop, root, options, _, _, _ = living_entry_setup
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        with http_entry(entry, desktop) as http:
            port = int(http.base.rsplit(':', 1)[1])
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(ROOT/'scripts/start_living_activity_chat.ps1'), '-Python', sys.executable, '-NoBrowser', '-Port', str(port)],
                env=dict(os.environ, HTTP_PROXY='http://127.0.0.1:1', HTTPS_PROXY='http://127.0.0.1:1', NO_PROXY=''),
                capture_output=True, timeout=20)
            assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
            assert not options['transport'].calls
    finally:
        entry.close()


def test_page_visible_lifecycle_distinct_stages_draft_and_refresh_recovery(living_entry_setup):
    script, desktop, root, options, _, _, _ = living_entry_setup
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the desktop JavaScript behavior checks')
    entry = script.LivingActivityChatEntry(root, **options)
    try:
        state = desktop.LivingActivityChatAdapter(entry.product, reopen=entry.reopen).snapshot()
    finally:
        entry.close()
    source = re.search(r'<script>([\s\S]*?)</script>', (ROOT/'app/desktop/static/living_activity_chat.html').read_text(encoding='utf-8')).group(1)
    harness = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const storage=new Map(),calls=[],waiting=[],nodes=new Map();let nextId=0,status=input.state,timers=[];
const element=()=>({value:'',textContent:'',disabled:false,children:[],handlers:{},append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},addEventListener(name,handler){this.handlers[name]=handler},focus(){throw Error('no focus')}});
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
function start(){nodes.clear();timers=[];const doc={hidden:false,handlers:{},getElementById:get,createElement:element,addEventListener(name,handler){this.handlers[name]=handler}},win={handlers:{},addEventListener(name,handler){this.handlers[name]=handler}};
 const sandbox={document:doc,window:win,sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},crypto:{randomUUID:()=> '00000000-0000-4000-8000-'+String(++nextId).padStart(12,'0')},setTimeout:(callback,ms)=>ms>=5000?(timers.push(callback),timers.length):setImmediate(callback),clearTimeout:()=>{timers=[]},fetch:async(path,options)=>{if(path==='/status')return {ok:true,json:async()=>status};calls.push({path,body:JSON.parse(options.body)});return new Promise(resolve=>{const finish=value=>resolve({ok:true,json:async()=>value});finish.path=path;waiting.push(finish)})}};
 vm.createContext(sandbox);vm.runInContext(input.source,sandbox);get('composer').requestSubmit=()=>get('composer').handlers.submit({preventDefault(){}});return sandbox;}
const flush=()=>new Promise(resolve=>setImmediate(resolve)),draft=text=>{get('draft').value=text;get('draft').handlers.input()},savedLife=()=>JSON.parse(storage.get('s143-living-request:'+input.state.scope_key)||'null');
const complete=value=>{status=value.state||status;waiting.shift()(value)};
const completePresence=value=>{const index=waiting.findIndex(finish=>finish.path==='/living-presence');assert(index>=0);waiting.splice(index,1)[0](value)};
const enabled={...input.state,living_controls:{status:'available',view:{...input.state.living_controls.view,paused:false,sharing_enabled:true}},living_activity:{status:'available',view:{...input.state.living_activity.view,permission:{...input.state.living_controls.view,paused:false,sharing_enabled:true}}}};
const plan={subject:'窗边',composition:'留白<img src=x>',focus:'光线'},result={kind:'composition-text',plan,differences:[]};
const chosen={...enabled,shared_activity:{status:'available',view:{...enabled.shared_activity.view,revision:1,phase:'drafted',activity_revision:1,result,visible_result:result}},living_activity:{status:'available',view:{...enabled.living_activity.view,revision:1,share_gate:'',visible_result:result,current_plan:plan}}};
const shared={...chosen,living_activity:{status:'available',view:{...chosen.living_activity.view,revision:2,share_gate:'living-awaiting-reply',shares:[{text:'已提交分享<img src=x>'}]}},chat_messages:[{kind:'assistant-share',head_sequence:2,user_text:'',assistant_text:'已提交分享<img src=x>'}]};
(async()=>{
 let sandbox=start();await flush();await flush();assert.equal(calls.length,0);assert.equal(get('life-sharing').checked,false);
 draft('活动前没有提交的草稿。');
 const setting=get('life-toggle').handlers.click();assert.equal(calls.at(-1).path,'/living-controls');assert(!JSON.stringify(calls.at(-1).body).includes('草稿'));
 complete({ok:true,state:enabled});await setting;
 const pulse=vm.runInContext('lifePulse()',sandbox);assert.equal(calls.at(-1).path,'/living-presence');assert.deepEqual(Object.keys(calls.at(-1).body),['session_id']);
 completePresence({ok:true,presence_status:'available',presence_problem_code:'online-ready',presence:{session_owner:true,opportunity_due:true,online_seconds:900,permission:enabled.living_controls.view},scope_key:input.state.scope_key});await pulse;
 const online=savedLife();assert.equal(calls.at(-1).path,'/living-heartbeat');assert.deepEqual(Object.keys(calls.at(-1).body).sort(),['expected_revision','request_id','session_id']);
 const pending={...enabled,presentation_pending:true,shared_pending:true,living_pending:true,living_kind:'online',context_boundary:{...enabled.context_boundary,pending:true}};
 complete({ok:true,living_status:'busy',living_started:true,living_request_id:online.request.request_id,living_settled:false,state:pending});await flush();await flush();
 assert.equal(get('draft').disabled,false);draft('活动等待期间写的下一稿。');await get('composer').requestSubmit();assert.equal(calls.filter(row=>row.path==='/send').length,0);
 assert.equal(calls.at(-1).path,'/living-request');assert(timers.length>0);
 const continuing=vm.runInContext('lifePulse()',sandbox);assert.equal(calls.at(-1).path,'/living-presence');assert.equal(calls.at(-1).body.session_id,online.request.session_id);assert(!JSON.stringify(calls.at(-1).body).includes('下一稿'));
 completePresence({ok:true,presence_status:'available',presence_problem_code:'online-ready',presence:{session_owner:true,opportunity_due:true,online_seconds:900,permission:enabled.living_controls.view},scope_key:input.state.scope_key});await continuing;
 assert.equal(calls.filter(row=>row.path==='/living-heartbeat').length,1);assert.equal(savedLife().request.request_id,online.request.request_id);assert(timers.length>0);
 complete({ok:true,living_status:'replayed',living_request_id:online.request.request_id,living_settled:true,state:chosen});await flush();await flush();
 assert.equal(calls.at(-1).path,'/living-share');const sharing=savedLife();assert.notEqual(sharing.request.request_id,online.request.request_id);
 complete({ok:true,living_status:'replayed',living_request_id:sharing.request.request_id,living_settled:true,state:shared});await flush();await flush();
 assert.equal(get('draft').value,'活动等待期间写的下一稿。');assert.equal(savedLife(),null);
 const textTree=element=>[element.className,element.textContent,...element.children.map(textTree)].join(' ');
 assert(textTree(get('messages')).includes('纱雾 · 主动分享'));assert(textTree(get('messages')).includes('已提交分享<img src=x>'));assert(!textTree(get('messages')).includes('message user'));
 const count=calls.length; sandbox.document.hidden=true;sandbox.document.handlers.visibilitychange();await vm.runInContext('lifePulse()',sandbox);assert.equal(calls.length,count);assert.equal(timers.length,0);
 sandbox.document.hidden=false;await sandbox.document.handlers.visibilitychange();await flush();assert.equal(calls.length,count);
 // Reloading an exact saved choice only queries; it never auto-shares again.
 storage.set('s143-living-request:'+input.state.scope_key,JSON.stringify(online));status=chosen;sandbox=start();await flush();await flush();
 assert.deepEqual(calls.at(-1),{path:'/living-request',body:online});complete({ok:true,living_status:'replayed',living_request_id:online.request.request_id,living_settled:true,state:chosen});await flush();await flush();
 assert.equal(calls.filter(row=>row.path==='/living-heartbeat').length,1);assert.equal(calls.filter(row=>row.path==='/living-share').length,1);assert.equal(get('draft').value,'活动等待期间写的下一稿。');
 // Unknown results keep the nonce, then query controls; no full stale message.
 storage.set('s143-living-request:'+input.state.scope_key,JSON.stringify(sharing));sandbox=start();await flush();await flush();
 const unknown={...input.state,presentation_blocked:true,living_activity:{status:'failed-closed'},chat_messages:[],chat_messages_status:'failed-closed',living_controls:{status:'available',view:{...input.state.living_controls.view,needs_attention:true,paused:true}}};
 complete({ok:false,living_status:'unknown',living_request_id:sharing.request.request_id,living_settled:false,state:unknown});await flush();await flush();
 assert.equal(savedLife().request.request_id,sharing.request.request_id);assert(get('life-summary').textContent.includes('需要检查'));assert(!textTree(get('messages')).includes('已提交分享'));
 get('life-release').handlers.click();assert.equal(savedLife(),null);assert.equal(get('send').disabled,true);assert.equal(get('life-toggle').disabled,true);
 assert.equal(calls.filter(row=>row.path==='/living-share').length,1);assert.equal(calls.filter(row=>row.path==='/send').length,0);
 process.stdout.write('living-page-lifecycle-draft-recovery-complete');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run([node, '-e', harness], input=json.dumps(dict(source=source,state=state)).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    assert result.stdout == b'living-page-lifecycle-draft-recovery-complete'

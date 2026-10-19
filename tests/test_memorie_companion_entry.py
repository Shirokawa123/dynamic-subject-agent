from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from test_original_whole_chat_entry import FakeWholeFacade

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/desktop'))
entry = importlib.import_module('memorie_companion')


class CompletedOnLookupFacade(FakeWholeFacade):
    def __init__(self):
        super().__init__()
        self.state = replace(self.state, subject_name='梅莫莉')

    def lookup_subject_request(self, request):
        ref = self.operations.get(request.idempotency_key)
        if ref is not None:
            self.complete(ref)
        return super().lookup_subject_request(request)


@pytest.fixture
def memorie_http():
    facade = CompletedOnLookupFacade()
    product = SimpleNamespace(application=facade, profile_id=str(uuid4()), timeline_id=str(uuid4()))
    from dynamic_subject_agent.memorie_companion_contract import contract, DEFINITION, ASSET, SCOPE, USE_REVIEW
    product._memorie_composition_witness = contract(dict(definition_basis=DEFINITION, runtime_asset_sha=ASSET), SCOPE, USE_REVIEW)
    server = entry.memorie_companion_server(product, reopen=lambda: product)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f'http://127.0.0.1:{server.server_port}/'
    yield facade, root
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def call(root, route, payload=None, token='', **headers):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = Request(root + route, data=body, headers={
        **({'Content-Type': 'application/json', 'X-Chat-Token': token} if body else {}), **headers})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def test_native_interface_one_send_and_same_request_lookup_after_client_reopen(memorie_http):
    facade, root = memorie_http
    session = call(root, 'session')
    from dynamic_subject_agent.memorie_companion_contract import VERSION
    health = call(root, 'health')
    assert health['contract_version'] == VERSION and health['entry_key'] == ''
    assert session['application'] == entry.APPLICATION_ID
    assert call(root, 'status')['ready']
    assert not facade.submissions
    message = dict(text='合成普通交流。', request_id=str(uuid4()), scope_key=call(root, 'status')['scope_key'])
    sent = call(root, 'send', message, session['token'])
    assert sent['pending'] and len(facade.submissions) == 1
    looked_up = call(root, 'result', message, call(root, 'session')['token'])
    assert looked_up['settled'] and looked_up['ok']
    assert looked_up['state']['turns'] == [dict(user_text=message['text'], assistant_text='合成回复。')]
    assert len(facade.submissions) == 1 and not facade.waits


def test_wrong_subject_or_unavailable_history_cannot_leak_or_send(memorie_http):
    facade, root = memorie_http
    scope = call(root, 'status')['scope_key']
    facade.state = replace(facade.state, subject_name='其他人物')
    facade.turns = [SimpleNamespace(user_text='其他人物秘密', assistant_text='其他人物回答')]
    state = call(root, 'status')
    assert not state['ready'] and state['turns'] == [] and not state['scope_key']
    value = call(root, 'send', dict(text='草稿不能发送', request_id=str(uuid4()), scope_key=scope), call(root, 'session')['token'])
    assert not value['ok'] and not facade.submissions


def test_stale_game_scope_rejected_before_submit_without_new_history(memorie_http):
    facade, root = memorie_http
    facade.turns = [SimpleNamespace(user_text='新人物秘密', assistant_text='新人物回答')]
    value = call(root, 'send', dict(text='旧草稿', request_id=str(uuid4()), scope_key='0' * 64),
        call(root, 'session')['token'])
    assert not value['ok'] and value['state']['turns'] == [] and not facade.submissions


@pytest.mark.parametrize('headers', [{}, {'Origin': 'https://unrelated.example'}])
def test_native_post_rejects_missing_token_or_foreign_origin(memorie_http, headers):
    facade, root = memorie_http
    token = call(root, 'session')['token'] if headers else ''
    with pytest.raises(HTTPError) as error:
        call(root, 'send', dict(text='合成', request_id=str(uuid4())), token, **headers)
    assert error.value.code == 403 and not facade.submissions


def test_compiled_native_client_contract_against_interface(memorie_http, tmp_path):
    harness = os.environ.get('MEMORIE_CLIENT_HARNESS')
    runtime = os.environ.get('MEMORIE_DOTNET')
    if not harness or not runtime:
        pytest.skip('explicit local compiled client contract runtime not selected')
    facade, root = memorie_http
    result = subprocess.run([runtime, harness, root, str(tmp_path / 'draft.json')],
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'client-contract:' in result.stdout
    assert len(facade.submissions) == 2 and len(facade.lookups) == 3 and not facade.waits


def test_compiled_harness_unknown_mode_cannot_fall_through_to_submission(memorie_http, tmp_path):
    harness, runtime = os.environ.get('MEMORIE_CLIENT_HARNESS'), os.environ.get('MEMORIE_DOTNET')
    if not harness or not runtime:
        pytest.skip('explicit local compiled client contract runtime not selected')
    facade, root = memorie_http
    path = tmp_path / 'must-not-write.json'
    result = subprocess.run([runtime, harness, root, str(path), 'unknown-mode'],
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0 and 'Unknown client contract mode' in result.stderr
    assert not facade.submissions and not path.exists()


def test_compiled_client_accepts_legal_python_unicode_history_boundary(memorie_http, tmp_path):
    harness, runtime = os.environ.get('MEMORIE_CLIENT_HARNESS'), os.environ.get('MEMORIE_DOTNET')
    if not harness or not runtime:
        pytest.skip('explicit local compiled client contract runtime not selected')
    facade, root = memorie_http
    facade.turns = [SimpleNamespace(user_text='甲' * 999 + '🌿', assistant_text='甲' * 1199 + '🌿')]
    result = subprocess.run([runtime, harness, root, str(tmp_path / 'draft.json'), 'unicode-history'],
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not facade.submissions


def test_compiled_client_failed_reconnect_does_not_submit_with_new_token(memorie_http, tmp_path):
    harness, runtime = os.environ.get('MEMORIE_CLIENT_HARNESS'), os.environ.get('MEMORIE_DOTNET')
    if not harness or not runtime:
        pytest.skip('explicit local compiled client contract runtime not selected')
    facade, original_root = memorie_http
    counts = dict(session=0, status=0, posts=0)

    class ChangingSession(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/session':
                counts['session'] += 1
                value = dict(application=entry.APPLICATION_ID, protocol=1, token=str(counts['session']) * 43)
                status = 200
            else:
                counts['status'] += 1
                status = 200 if counts['status'] == 1 else 503
                value = call(original_root, 'status') if status == 200 else dict(error='temporary-unavailable')
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            counts['posts'] += 1
            self.send_error(500)

    server = ThreadingHTTPServer(('127.0.0.1', 0), ChangingSession)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([runtime, harness, f'http://127.0.0.1:{server.server_port}/',
            str(tmp_path / 'draft.json'), 'reconnect-failure'],
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert counts == dict(session=2, status=2, posts=0) and not facade.submissions
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

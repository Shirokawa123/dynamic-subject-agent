"""Independent S144 entry inherits the proven draft and nonce lifecycle."""
import importlib
import json
from types import SimpleNamespace

import pytest

from test_living_final_text import FinalTextTransport, RAW
from test_living_activity_chat_entry import (living_entry_setup, http_entry, control, action,
    approved, personality_fixture, model_fixture, entry_setup)
from test_shared_activity_chat_entry import chat
from dynamic_subject_agent.shared_activity import LIVING_FINAL_TEXT_AUTHORITY


def test_independent_empty_entry_http_exact_raw_share_nonce_reload_and_old_marker_closed(living_entry_setup):
    baseline, desktop, root, options, _, _, _ = living_entry_setup
    candidate = importlib.import_module('serve_living_final_text_chat')
    transport = FinalTextTransport(); options['transport'] = transport
    root = root.with_name('final-text-entry')
    entry = candidate.FinalTextLivingActivityChatEntry(root, **options)
    original_marker = (root / 'current.json').read_bytes()
    assert json.loads(original_marker)['version'] == candidate.ENTRY_VERSION
    assert entry.product._qri.provider_authority == LIVING_FINAL_TEXT_AUTHORITY
    assert not transport.calls
    factory = SimpleNamespace(living_activity_server=lambda *args, **kwargs:
        desktop.living_activity_server(*args, **kwargs, application_id=desktop.FINAL_TEXT_APPLICATION_ID))
    try:
        with http_entry(entry, factory, simulation=True) as http:
            assert http.get('/health') == dict(application=candidate.APPLICATION_ID)
            initial = http.get('/status')
            assert initial['chat_messages'] == [] and initial['living_controls']['view']['paused'] is True
            chat(http, '合成首次当前话题。')
            assert http.get('/status')['chat_messages'][0]['assistant_text'] == RAW
            control(http, paused=False, sharing=True)
            chosen, request = action(http, 'simulation')
            assert chosen['ok']
            shared, sharing = action(http, 'share')
            assert shared['ok'] and shared['state']['chat_messages'][-1]['kind'] == 'assistant-share'
            assert len(transport.calls) == 3
            assert http.post('/reload', {})['ok']
            assert http.post('/living-request', dict(kind='simulation', request=request))['living_status'] == 'replayed'
            assert http.post('/living-share', sharing)['living_status'] == 'replayed'
            assert len(transport.calls) == 3
        assert (root / 'current.json').read_bytes() == original_marker
        entry.reopen()
        assert len(transport.calls) == 3
    finally:
        entry.close()
    before = (root / 'state.json').read_bytes()
    with pytest.raises(ValueError, match='changed'):
        baseline.LivingActivityChatEntry(root, **options)
    assert (root / 'state.json').read_bytes() == before and (root / 'current.json').read_bytes() == original_marker
    assert len(transport.calls) == 3


def test_final_text_launcher_existing_exact_health_does_not_open_browser_or_root(monkeypatch):
    script = importlib.import_module('serve_living_final_text_chat')
    class Healthy:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, *args): return json.dumps(dict(application=script.APPLICATION_ID)).encode()
    monkeypatch.setattr(script, 'urlopen', lambda *a, **kw: Healthy())
    def forbidden(*args, **kwargs):
        raise AssertionError('healthy launcher cannot create entry or take browser focus')
    monkeypatch.setattr(script, 'FinalTextLivingActivityChatEntry', forbidden)
    monkeypatch.setattr(script.webbrowser, 'open', forbidden)
    monkeypatch.setattr('sys.argv', ['serve_living_final_text_chat.py'])
    assert script.main() is None

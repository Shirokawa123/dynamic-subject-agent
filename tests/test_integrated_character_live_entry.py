"""Independent LIVE entry uses synthetic transport only; no real credentials."""
import importlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_shared_activity_chat_entry import entry_setup, chat
from test_living_activity_chat_entry import http_entry, control, action
from test_integrated_character import MESSAGE, PLAN, LocalAdapter
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind


class EntryTransport(DeepSeekTransport):
    """Exercise the LIVE wire with the already shared synthetic LOCAL replies."""
    def __init__(self):
        self.calls = []
        self.fixture = LocalAdapter()

    def post_json(self, **kwargs):
        body = json.loads(kwargs['body']); self.calls.append(body)
        payload = json.loads(body['messages'][1]['content'])
        kind = (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK if 'turn' in payload else
            ModelTaskKind.LIVING_ACTIVITY_CHOICE if 'current_activity' in payload else ModelTaskKind.LIVING_ACTIVITY_SHARE)
        result = self.fixture.invoke(ModelTask(kind, dict(policy=body['messages'][0]['content'], payload=payload)))
        return DeepSeekHttpResponse(200, canonical_json(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop', message=dict(role='assistant', content=canonical_json(result.value)))],
            usage=dict(prompt_tokens=100, completion_tokens=80, total_tokens=180))).encode())


@pytest.fixture
def integrated_live_entry_setup(entry_setup, monkeypatch):
    shared, _, root, options, reviews, _ = entry_setup
    script = importlib.import_module('serve_integrated_character_chat')
    desktop = importlib.import_module('integrated_character_chat')
    monkeypatch.setattr(script, 'APPROVED_BINDING', shared.APPROVED_BINDING)
    import dynamic_subject_agent.integrated_character_live as live
    from dynamic_subject_agent.integrated_character import integrated_contract
    monkeypatch.setattr(live, 'APPROVED_INTEGRATED_MATERIAL', live.digest(shared.APPROVED_BINDING))
    monkeypatch.setattr(live, 'APPROVED_INTEGRATED_LOCAL_CONTRACT', live.digest(integrated_contract(shared.APPROVED_BINDING)))
    transport = EntryTransport()
    return script, desktop, root.with_name('integrated-live-entry'), dict(options,
        transport=transport, audit_path=root.with_name('integrated-live-audit')), transport, reviews


def test_initialize_only_empty_pause_readonly_scope_and_reopen(integrated_live_entry_setup, monkeypatch, capsys):
    script, desktop, root, options, transport, reviews = integrated_live_entry_setup
    entry = script.IntegratedCharacterChatEntry(root, **options)
    identity = entry.identity
    pointer = (root / 'current.json').read_bytes()
    registry = entry.config.state_path.read_bytes()
    try:
        def no_server(*args, **kwargs):
            raise AssertionError('initialize-only cannot start an HTTP server')
        with monkeypatch.context() as patch:
            patch.setattr(script, 'integrated_character_server', no_server)
            patch.setattr(script, 'IntegratedCharacterChatEntry', lambda *args: entry)
            patch.setattr(script, 'default_entry_root', lambda: root)
            patch.setattr(script.argparse.ArgumentParser, 'parse_args',
                lambda self: SimpleNamespace(initialize_only=True, port=8797))
            script.main()
        result = json.loads(capsys.readouterr().out)
        assert result['status'] == 'initialized' and result['audit_attempts'] == result['chat_turns'] == result['activity_revision'] == 0
        assert not transport.calls
    finally:
        entry.close()
    # Package was reviewed once; cold opening needs the verified saved identity.
    reopened = script.IntegratedCharacterChatEntry(root, **dict(options, package_path=root / 'absent.json'))
    try:
        assert reopened.identity == identity and not transport.calls and len(reviews) == 1
    finally:
        reopened.close()
    assert (root / 'current.json').read_bytes() == pointer
    assert (root / 'state.json').read_bytes() == registry


def test_live_http_share_feedback_and_recovery_preserve_identity(integrated_live_entry_setup):
    script, desktop, root, options, transport, _ = integrated_live_entry_setup
    entry = script.IntegratedCharacterChatEntry(root, **options)
    bridge = SimpleNamespace(living_activity_server=lambda *args, **kwargs:
        desktop.integrated_character_server(*args, **kwargs, live=True))
    try:
        with http_entry(entry, bridge, simulation=True) as http:
            assert http.get('/health') == dict(application=desktop.LIVE_APPLICATION_ID)
            assert '本地准备 · 合成回复' not in http.page and "'s158-live-draft:'" in http.page
            state = http.get('/status')
            assert state['living_controls']['view']['paused'] and not state['living_controls']['view']['sharing_enabled']
            assert state['chat_messages'] == [] and not transport.calls
            assert http.post('/message-scope', dict(text='未发送草稿。'))['ok'] and not transport.calls
            control(http, paused=False, sharing=True)
            assert action(http, 'simulation')[0]['living_status'] == 'replayed'
            assert action(http, 'share')[0]['living_status'] == 'replayed'
            before = http.get('/status')['shared_activity']['view']['current_plan']
            assert before == PLAN
            scope = http.post('/message-scope', dict(text=MESSAGE))['message_scope']
            assert scope['latest_share'] and scope['current_plan'] == before
            _, original = chat(http, MESSAGE)
            updated = http.get('/status')['shared_activity']['view']['current_plan']
            assert updated == {key: text.replace('松架', '杉架') for key, text in PLAN.items()}
            calls = len(transport.calls)
            assert http.post('/reload', {})['ok']
            assert http.get('/status')['scope_key'] == state['scope_key'] and len(transport.calls) == calls
            assert http.post('/request-result', original)['ok'] and len(transport.calls) == calls
            assert http.post('/history', dict(enabled=False))['ok']
            scope = http.post('/message-scope', dict(text='当前新话题。'))['message_scope']
            assert scope['current_plan'] is None and scope['current_feedback'] is None and scope['latest_share'] is None
            assert len(transport.calls) == calls
    finally:
        entry.close()


def test_partial_pointer_audit_and_production_paths_are_preserved(integrated_live_entry_setup, monkeypatch):
    script, _, root, options, transport, _ = integrated_live_entry_setup
    root.mkdir()
    marker = root / 'keep.txt'; marker.write_text('keep', encoding='utf-8')
    with pytest.raises(ValueError, match='partial'):
        script.IntegratedCharacterChatEntry(root, **options)
    assert marker.read_text(encoding='utf-8') == 'keep'
    for path in (script.default_entry_root(), script.ROOT / '.artifacts/s155/experience-entry'):
        with pytest.raises(ValueError, match='independent'):
            script.IntegratedCharacterChatEntry(path, **options)
    audit = options['audit_path']; audit.mkdir()
    note = audit / 'keep.txt'; note.write_text('audit', encoding='utf-8')
    with pytest.raises(ValueError, match='orphan audit'):
        script.IntegratedCharacterChatEntry(root.with_name('orphan-entry'), **options)
    assert note.read_text(encoding='utf-8') == 'audit'
    fresh = root.with_name('complete-entry')
    opts = dict(options, audit_path=root.with_name('complete-audit'))
    entry = script.IntegratedCharacterChatEntry(fresh, **opts); entry.close()
    pointer = fresh / 'current.json'
    value = json.loads(pointer.read_text(encoding='utf-8')); value['timeline_id'] = str(uuid4())
    pointer.write_text(json.dumps(value), encoding='utf-8'); saved = pointer.read_bytes()
    called = []
    monkeypatch.setattr(script.IntegratedCharacterChatEntry, '_open', lambda self: called.append(True))
    with pytest.raises(RuntimeError):
        script.IntegratedCharacterChatEntry(fresh, **opts)
    assert pointer.read_bytes() == saved and not called and not transport.calls

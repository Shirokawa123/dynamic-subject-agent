"""One HTTP entry over the integrated Facade, with explicit synthetic output."""
from contextlib import contextmanager
import importlib
from pathlib import Path
from types import SimpleNamespace

from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_integrated_character import integrated_fixture, LocalAdapter, MESSAGE, PLAN
from test_living_activity_chat_entry import http_entry, control, action
from test_shared_activity_chat_entry import chat


@contextmanager
def integrated_http(integrated_fixture, monkeypatch, *, simulation=False):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'app' / 'desktop'))
    desktop = importlib.import_module('integrated_character_chat')
    fake = LocalAdapter()
    product = integrated_fixture(fake)
    entry = SimpleNamespace(product=product)
    def reopen():
        entry.product.close()
        entry.product = integrated_fixture(fake)
        return entry.product
    entry.reopen = reopen
    # The existing HTTP test helper owns and closes its temporary loopback server.
    bridge = SimpleNamespace(living_activity_server=desktop.integrated_character_server)
    with http_entry(entry, bridge, simulation=simulation) as http:
        yield http, fake, desktop


def test_local_entry_reads_and_reopens_without_calls_and_previews_exact_feedback(integrated_fixture, monkeypatch):
    with integrated_http(integrated_fixture, monkeypatch) as (http, fake, desktop):
        assert http.get('/health') == dict(application=desktop.APPLICATION_ID)
        initial = http.get('/status')
        assert initial['living_controls']['view']['paused'] is True
        assert initial['living_controls']['view']['sharing_enabled'] is False
        assert initial['chat_messages'] == []
        preview = http.post('/message-scope', dict(text='还未发送的本地草稿。'))
        assert preview['ok'] and preview['scope_key'] == initial['scope_key']
        assert preview['message_scope']['current_message'] == '还未发送的本地草稿。'
        assert preview['message_scope']['current_plan'] is None
        assert preview['message_scope']['latest_share'] is None
        assert preview['message_scope']['current_feedback'] is None
        blocked, _ = action(http, 'simulation')
        assert blocked['living_status'] == 'unavailable'
        assert http.post('/reload', {})['ok']
        assert http.get('/status')['scope_key'] == initial['scope_key']
        assert not fake.calls
        assert '本地准备 · 合成回复' in http.page
        assert "'s158-draft:'" in http.page and "'s143-draft:'" not in http.page
        assert '每次发送使用现有DeepSeek' not in http.page


def test_same_http_entry_share_feedback_topics_reopen_and_next_choice(integrated_fixture, monkeypatch):
    with integrated_http(integrated_fixture, monkeypatch, simulation=True) as (http, fake, _):
        control(http, paused=False, sharing=True)
        initial = http.get('/status')['scope_key']
        choice, _ = action(http, 'simulation')
        assert choice['living_status'] == 'replayed'
        shared, share_request = action(http, 'share')
        assert shared['living_status'] == 'replayed'
        rows = http.get('/status')['chat_messages']
        assert len(rows) == 1 and rows[0]['kind'] == 'assistant-share'
        scope = http.post('/message-scope', dict(text=MESSAGE))['message_scope']
        assert scope['current_plan'] == PLAN and scope['latest_share']['text'].startswith('合成分享')
        _, original_request = chat(http, MESSAGE)
        updated = http.get('/status')['living_activity']['view']['current_plan']
        assert updated == {key: value.replace('松架', '杉架') for key, value in PLAN.items()}
        scope = http.post('/message-scope', dict(text='接着聊。'))['message_scope']
        assert scope['current_feedback'] == dict(label='F1', quote=MESSAGE)
        for index in range(3):
            chat(http, '另一个合成话题' + str(index))
        scope = http.post('/message-scope', dict(text='继续刚才的安排。'))['message_scope']
        assert scope['latest_share'] is None and scope['current_plan'] == updated
        calls = len(fake.calls)
        assert http.post('/reload', {})['ok']
        assert http.get('/status')['scope_key'] == initial and len(fake.calls) == calls
        recovered = http.post('/request-result', original_request)
        assert recovered['ok'] and recovered['settled'] and len(fake.calls) == calls
        control(http, paused=False)
        preview = http.post('/shared-activity-preview', {})
        assert preview['ok'] and preview['shared_preview']['current_feedback']['quote'] == MESSAGE
        choice, _ = action(http, 'simulation')
        assert choice['living_status'] == 'replayed'
        state = http.get('/status')['shared_activity']['view']
        assert state['activity_revision'] == 3 and state['current_plan']['composition'] == updated['composition']
        calls = len(fake.calls)
        recovered = http.post('/living-request', dict(kind='share', request=share_request))
        assert recovered['living_status'] == 'replayed' and len(fake.calls) == calls

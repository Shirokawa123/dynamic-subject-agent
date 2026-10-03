import json
from threading import Event
import sqlite3

import pytest

from test_whole_context_boundary import context_fixture
from test_original_whole_chat import approved, personality_fixture, model_fixture, WholeTransport, send, history
from dynamic_subject_agent.timeline import SubjectCommand, TimelineEngine
from dynamic_subject_agent.runtime import CognitionFailedClosed
from dynamic_subject_agent.whole_message_scope import WholeMessageScopePreviewRequest
from test_whole_chat_archive import canonical_path


def test_correction_clarification_new_topic_and_reopen_resume_without_permission_loss(context_fixture):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    messages = ('聊聊蓝色构图。', '你说错了，刚才那不是我想问的。我只是想谈构图。',
                '我的意思是本轮配色，不是在要求撤回聊天。', '换个话题，聊聊绿色。')
    observed = []
    for index, text in enumerate(messages):
        result = send(product, text, 'correction-scope-' + str(index))
        observed.append((result.status.value, None if result.projection is None else result.projection.failure_code))
    saved = history(product); product.close()
    restarted_transport = WholeTransport(); restarted = opening(restarted_transport)
    assert history(restarted) == saved and not restarted_transport.calls
    result = send(restarted, '现在继续聊当前的绿色配色。', 'correction-scope-reopened')
    observed.append((result.status.value, None if result.projection is None else result.projection.failure_code))
    assert observed == [('terminal', None)] * 5, observed
    assert len(transport.calls) == 4 and len(restarted_transport.calls) == 1


def test_legacy_miscorrection_and_cascade_failures_resume_only_with_original_receipts_preserved(context_fixture, monkeypatch):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '正常合成开场。', 'diagnostic-normal').status == 'terminal'
    import dynamic_subject_agent.original_whole_chat_cognition as cognition
    def legacy_history_gate(self, **kwargs):
        raise CognitionFailedClosed('history', 'original-whole-history-unverified', 'History and exact whole disclosure are unavailable.')
    # Emulate old binary decisions through the real Admission/frozen attempt
    # and failure writer, rather than editing the immutable legacy failures.
    with monkeypatch.context() as legacy:
        legacy.setattr(cognition.OriginalWholeChatCognition, 'propose', legacy_history_gate)
        old = send(product, '你说错了。', 'diagnostic-correction')
        cascade = send(product, '澄清一下，本轮只聊配色。', 'diagnostic-current-only')
    assert old.projection.failure_code == cascade.projection.failure_code == 'original-whole-history-unverified'
    assert len(transport.calls) == 1
    path = canonical_path(product)
    with sqlite3.connect(path) as reader:
        original_failures = reader.execute('SELECT * FROM operation_failure ORDER BY operation_id').fetchall()
    assert send(product, '换个话题，聊聊绿色。', 'diagnostic-prefix').status == 'terminal'
    exchange = json.loads(transport.calls[-1]['messages'][1]['content'])['exchange']
    assert len(transport.calls) == 2 and len(exchange) == 1 and exchange[0]['user_text'] == '正常合成开场。'
    for response in (old, cascade):
        followed = product.application.follow(response.operation_ref)
        assert followed.operation_ref == response.operation_ref and followed.projection.failure_code == response.projection.failure_code
    with sqlite3.connect(path) as reader:
        assert reader.execute('SELECT * FROM operation_failure ORDER BY operation_id').fetchall() == original_failures
    saved = history(product); product.close()
    restarted_transport = WholeTransport(); restarted = opening(restarted_transport)
    assert history(restarted) == saved and not restarted_transport.calls
    assert send(restarted, '继续当前绿色配色。', 'legacy-prefix-reopened').status == 'terminal'
    assert restarted.application.follow(old.operation_ref).projection.failure_code == 'original-whole-history-unverified'


def test_correction_quotes_and_discussion_are_conversation_but_actual_operations_are_unavailable(context_fixture):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    for index, text in enumerate(('纠正一下，配色应该是绿色。', '你刚才说“不要再用之前的聊天”，这句话是什么意思？',
                                  '我昨天说，别再提那段聊天。现在只想聊配色。', '你觉得保存方案和完成目标有什么区别？',
                                  '不要用“已经完成”来描述这个想法，刚才说错了。',
                                  '我们不要用“撤回历史”这种说法，我们是在纠正措辞。', '旧聊天并不会删除。',
                                  '不要用蓝色来画。', '不要用“蓝色”来画。',
                                  '他昨天说：不要再引用之前的聊天。',
                                  '请解释保存资料和删除资料的区别。', '请告诉我保存聊天意味着什么。')):
        assert send(product, text, 'scope-discussion-' + str(index)).status == 'terminal'
    assert len(transport.calls) == 12
    unavailable = send(product, '请把这份方案保存到文件。', 'scope-unsupported')
    assert unavailable.status == 'unavailable' and unavailable.operation_ref is None
    assert len(transport.calls) == 12
    assert send(product, '接着说当前配色吧。', 'scope-after-unsupported').status == 'terminal'
    assert len(json.loads(transport.calls[-1]['messages'][1]['content'])['exchange']) == 2


def test_actual_withdrawal_never_sends_current_or_old_window_and_continues_after_safe_cutoff(context_fixture):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '合成旧口令是蓝桥。', 'scope-sensitive-prior').status == 'terminal'
    withdrawn = send(product, '你说错了，请不要再使用之前的聊天。', 'scope-withdrawal')
    assert withdrawn.status == 'failed-closed' and withdrawn.projection.failure_code == 'original-whole-history-withdrawn'
    assert len(transport.calls) == 1
    for index, text in enumerate(('你说错了，删除刚才的聊天。', '请忘记“合成旧口令蓝桥”。', 'Please forget the previous chat.',
                                 '不要再用“合成旧口令蓝桥”。', '请不要再使用聊天记录。', '请不要再引用我的聊天记录。',
                                 '我撤回刚才这段话。', '别把之前的聊天发给模型。', '不要把刚才的聊天发给模型。')):
        actual = send(product, text, 'scope-quoted-withdrawal-' + str(index))
        assert actual.status == 'failed-closed' and actual.projection.failure_code == 'original-whole-history-withdrawn'
    assert len(transport.calls) == 1
    assert send(product, '换个话题，聊聊绿色。', 'scope-after-withdrawal').status == 'terminal'
    payload = json.loads(transport.calls[-1]['messages'][1]['content'])
    assert payload['exchange'] == [] and payload['turn']['has_prior_committed_exchange'] is True
    assert send(product, '再谈谈青色。', 'scope-new-window').status == 'terminal'
    assert len(json.loads(transport.calls[-1]['messages'][1]['content'])['exchange']) == 1
    assert history(product)[0].user_text == '合成旧口令是蓝桥。'
    product.close(); restarted_transport = WholeTransport(); restarted = opening(restarted_transport)
    assert send(restarted, '继续当前话题。', 'scope-withdrawal-reopened').status == 'terminal'
    exchange = json.loads(restarted_transport.calls[0]['messages'][1]['content'])['exchange']
    assert len(exchange) == 2 and all('蓝桥' not in row['user_text'] for row in exchange)


@pytest.mark.parametrize('unknown', ['unrecognised-history-code', 'original-whole-transport-delivery-ambiguous'])
def test_unknown_failure_cannot_be_overridden_by_later_plain_message(context_fixture, monkeypatch, unknown):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '正常开场。', 'unknown-prior').status == 'terminal'
    import dynamic_subject_agent.original_whole_chat_cognition as cognition
    def fail(self, **kwargs):
        raise CognitionFailedClosed('history' if unknown.startswith('unrecognised') else 'whole-reply', unknown, 'Synthetic uncertain failure.')
    with monkeypatch.context() as uncertain:
        uncertain.setattr(cognition.OriginalWholeChatCognition, 'propose', fail)
        send(product, '尚不明确的合成输入。', 'unknown-failure')
    assert send(product, '换个话题，聊聊绿色。', 'unknown-followup').status == 'failed-closed'
    assert len(transport.calls) == 1


@pytest.mark.parametrize('message', ['不要再用“合成旧口令蓝桥。', '请忘记“合成旧口令蓝桥。', '别把“合成旧口令蓝桥发给模型。'])
def test_unclosed_literal_withdrawal_does_not_disclose_or_release_history(context_fixture, message):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '合成旧口令蓝桥。', 'unclosed-prior').status == 'terminal'
    result = send(product, message, 'unclosed-withdrawal')
    assert result.status == 'failed-closed'
    assert result.projection.failure_code == 'original-whole-history-control-unresolved'
    assert send(product, '继续当前配色。', 'unclosed-followup').status == 'failed-closed'
    assert len(transport.calls) == 1


def test_pending_and_corrupt_prefix_still_close_whole_disclosure(context_fixture):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '正常开场。', 'scope-pending-prior').status == 'terminal'
    path = canonical_path(product)
    entered, release = Event(), Event()
    def blocking(): entered.set(); assert release.wait(10)
    transport.callback = blocking
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status', utterance='在途原消息。', language='zh', provenance='project-original')
    pending = product.application.submit(command, idempotency_key='whole-scope-pending')
    assert entered.wait(5)
    try:
        view = product.application.preview_whole_message_scope(WholeMessageScopePreviewRequest(product.profile_id, product.timeline_id, '你说错了。'))
        assert view.status == 'unavailable' and view.recent_dialogue == () and len(transport.calls) == 2
    finally: release.set()
    assert product.application.wait(pending.operation_ref, timeout_seconds=30).status == 'terminal'
    db = sqlite3.connect(path, autocommit=True)
    try: db.execute("UPDATE expression_record SET expression_text='TAMPERED_SYNTHETIC_TEXT'")
    finally: db.close()
    assert send(product, '换个话题，聊聊绿色。', 'scope-corrupt-followup').status == 'failed-closed'
    assert len(transport.calls) == 2


def test_unfrozen_legacy_history_failure_cannot_release_a_window(context_fixture, monkeypatch):
    opening, _, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '正常开场。', 'unfrozen-prior').status == 'terminal'
    import dynamic_subject_agent.original_whole_chat_cognition as cognition
    def legacy(self, **kwargs):
        raise CognitionFailedClosed('history', 'original-whole-history-unverified', 'History and exact whole disclosure are unavailable.')
    with monkeypatch.context() as old_binary:
        old_binary.setattr(cognition.OriginalWholeChatCognition, 'propose', legacy)
        failed = send(product, '你说错了。', 'unfrozen-legacy')
    path = canonical_path(product)
    from uuid import UUID
    db = sqlite3.connect(path, autocommit=True)
    try: db.execute('DELETE FROM attempt_cycle_basis WHERE operation_id=?', (UUID(failed.operation_ref.operation_id).bytes,))
    finally: db.close()
    assert send(product, '澄清一下，只是讨论配色。', 'unfrozen-followup').status == 'failed-closed'
    assert len(transport.calls) == 1

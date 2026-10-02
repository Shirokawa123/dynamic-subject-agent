from dataclasses import replace
from threading import Event
from time import monotonic
import sqlite3

from dynamic_subject_agent.whole_chat_archive import WholeChatArchiveRequest
from dynamic_subject_agent.timeline import SubjectCommand, TimelineEngine
from test_whole_context_boundary import context_fixture, request_for
from test_original_whole_chat import whole_fixture, approved, personality_fixture, model_fixture, WholeTransport, send, history
from test_subject_request_lookup import counts


def archive(product, query='', before=None):
    return product.application.query_whole_chat_archive(WholeChatArchiveRequest(product.profile_id, product.timeline_id, before, query))


def canonical_path(product):
    # Test-only access to this synthetic fixture's known store for invariants
    # and intentional corruption; application behavior stays at the Facade.
    binding = product._composition._host.query_binding(profile_id=product.profile_id, timeline_id=product.timeline_id)
    return binding.timeline_root.timeline_database


def test_complete_archive_over_twenty_turns_search_boundaries_and_append_stable_pages(context_fixture, monkeypatch):
    opening, config, _ = context_fixture
    transport = WholeTransport(); product = opening(transport)
    for index in range(21):
        transport.reply = '合成第' + str(index) + '回回复。' + ('松果%_字面' if index == 0 else '')
        assert send(product, '合成第' + str(index) + '回原话。', 'archive-' + str(index)).status == 'terminal'
        if index in (3, 14):
            revision = 0 if index == 3 else 1
            assert product.application.apply_whole_context_boundary(request_for(product, 'archive-boundary-' + str(index), revision)).status == 'committed'
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    saved = history(product); path = canonical_path(product)
    registry = config.state_path.read_bytes(); before_counts = counts(path)
    def forbidden(*a, **kw): raise AssertionError('archive entered an admission or runtime execution path')
    from dynamic_subject_agent.host import RuntimeHost
    from dynamic_subject_agent.runtime import SubjectRuntime
    with monkeypatch.context() as readonly:
        readonly.setattr(RuntimeHost, 'lease', forbidden)
        readonly.setattr(TimelineEngine, 'admit', forbidden)
        readonly.setattr(SubjectRuntime, 'resume', forbidden)
        first = archive(product)
        found = archive(product, '松果%_')
        spaced = archive(product, ' 松果')
    assert first.status == 'available' and len(first.rows) == 20 and first.has_more and first.snapshot_head_sequence == 23
    assert first.next_before_sequence == first.rows[-1].head_sequence
    assert found.status == 'available' and len(found.rows) == 1 and found.rows[0].head_sequence == 1
    assert found.rows[0].context_revision == 0 and found.rows[0].assistant_text.endswith('松果%_字面')
    assert spaced.status == 'available' and spaced.query == ' 松果' and spaced.rows == ()
    assert counts(path) == before_counts and config.state_path.read_bytes() == registry and len(transport.calls) == 21
    # Append after the first page. Its stable key still reaches every older
    # item exactly once, without shifting an OFFSET under the caller.
    transport.reply = '新增合成回复。'
    assert send(product, '新增合成原话。', 'archive-appended').status == 'terminal'
    second = archive(product, before=first.next_before_sequence)
    combined = first.rows + second.rows
    assert [row.head_sequence for row in combined] == list(range(23, 0, -1))
    assert not second.has_more and second.next_before_sequence is None
    boundaries = [row for row in combined if row.kind == 'context-boundary']
    assert [(row.head_sequence, row.context_revision) for row in boundaries] == [(17, 2), (5, 1)]
    assert all(not row.user_text and not row.assistant_text for row in boundaries)
    assert {row.context_revision for row in combined if row.kind == 'turn'} == {0, 1, 2}
    assert history(product)[:-1] == saved[-19:]
    product.close()
    reopened = opening(transport)
    assert archive(reopened, '松果%_').rows == found.rows and len(transport.calls) == 22


def test_pending_new_turn_does_not_hide_verified_archive_or_wait_for_model(whole_fixture):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '已经提交的合成原话。', 'archive-old').status == 'terminal'
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    path = canonical_path(product)
    entered, release = Event(), Event()
    def blocking(): entered.set(); assert release.wait(10)
    transport.callback = blocking
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status', utterance='尚未提交的合成原话。', language='zh', provenance='project-original')
    pending = product.application.submit(command, idempotency_key='whole-archive-inflight-chat')
    assert entered.wait(5)
    before_counts = counts(path)
    try:
        start = monotonic(); page = archive(product)
        assert monotonic() - start < 3
        assert page.status == 'available' and page.pending and len(page.rows) == 1
        assert page.rows[0].user_text == '已经提交的合成原话。' and page.snapshot_head_sequence == 1
        assert counts(path) == before_counts and len(transport.calls) == 2
    finally: release.set()
    assert product.application.wait(pending.operation_ref, timeout_seconds=30).status == 'terminal'
    assert not archive(product).pending


def test_wrong_scope_changed_authority_and_bad_canonical_never_return_cached_body(whole_fixture, monkeypatch):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport(); product = opening(transport)
    assert send(product, '仅属于当前人物的合成原话。', 'archive-private').status == 'terminal'
    request = WholeChatArchiveRequest(product.profile_id, product.timeline_id)
    for invalid in (replace(request, target_profile_id='foreign'), replace(request, before_sequence=True),
                    replace(request, before_sequence=1000), replace(request, query='\x00')):
        result = product.application.query_whole_chat_archive(invalid)
        assert result.status != 'available' and result.rows == () and result.target_profile_id == ''
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    original = LocalIdentityAuthority.whole_archive_authorization
    calls = [0]
    def changed(self, *args):
        value = original(self, *args); calls[0] += 1
        if calls[0] == 1: self.set_reviewed_character_history(False)
        return value
    with monkeypatch.context() as changing:
        changing.setattr(LocalIdentityAuthority, 'whole_archive_authorization', changed)
        result = archive(product)
        assert result.status == 'unavailable' and result.rows == ()
    path = canonical_path(product)
    db = sqlite3.connect(path, autocommit=True)
    try: db.execute("UPDATE expression_record SET expression_text='TAMPERED_SYNTHETIC_TEXT'")
    finally: db.close()
    result = archive(product)
    assert result.status == 'failed-closed' and result.rows == () and not result.has_more
    assert len(transport.calls) == 1

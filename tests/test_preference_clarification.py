"""A short answer authorizes only its current, committed preference question."""
import pytest
from test_scoped_preferences import BroadMemory, COVER, QUERY, records
from test_memory_write_receipts import open_composite
from test_recent_dialogue import submit
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind

NEW = '我做封面时偏爱浅杏色。'

@pytest.mark.parametrize('reply,colors', [('是补充。', ('雾紫色', '浅杏色')), ('替换。', ('浅杏色',)), ('算了。', ('雾紫色',))])
def test_short_answer_completes_or_cancels_exact_question(tmp_path, reply, colors):
    provider = BroadMemory()
    opened = open_composite(tmp_path, provider)
    try:
        submit(opened, COVER)
        question = submit(opened, NEW)
        assert question.projection.expression_text, question
        assert '是补充还是替换' in question.projection.expression_text
        response = submit(opened, reply)
        if reply != '算了。':
            assert response.projection.living_memory_status == 'accepted'
            new_record = next(r for r in records(opened) if '浅杏色' in r.content)
            assert new_record.content == NEW
            assert new_record.source_user_message_id == question.operation_ref.operation_id
        actual = [r for r in records(opened) if r.status == 'active']
        assert len(actual) == len(colors)
        for color in colors:
            assert any(color in r.content for r in actual)
        if reply.startswith('是补充'):
            assert next(r for r in actual if '浅杏色' in r.content).preference_additive
        answer = submit(opened, QUERY)
        assert all(color in answer.projection.expression_text for color in colors)
        assert '同时喜欢，还是' not in answer.projection.expression_text
        assert provider.proposals == [] and provider.replies == []
    finally:
        opened.app.close()


@pytest.mark.parametrize('intervening', ['我们聊点别的。', '算了。', QUERY])
def test_other_turn_consumes_question_and_cannot_be_revisited(tmp_path, intervening):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, COVER); submit(opened, NEW)
        submit(opened, intervening)
        before = records(opened)
        response = submit(opened, '是补充。')
        assert response.projection.living_memory_status == 'no-op'
        assert '当前没有可确认' in response.projection.expression_text
        assert records(opened) == before
    finally:
        opened.app.close()


def test_success_is_consumed_and_repeated_answer_does_not_write_again(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, COVER); submit(opened, NEW)
        submit(opened, '是补充。')
        before = records(opened)
        submit(opened, '是补充。')
        assert records(opened) == before
    finally:
        opened.app.close()


def test_restart_restores_pending_question_and_confirmed_relation(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    submit(opened, COVER); submit(opened, NEW)
    opened.app.close()
    reopened = open_composite(tmp_path, BroadMemory(), saved=opened)
    result = submit(reopened, '是补充。')
    assert result.projection.living_memory_status == 'accepted'
    reopened.app.close()
    again = open_composite(tmp_path, BroadMemory(), saved=opened)
    try:
        answer = submit(again, QUERY)
        assert '补充保留' in answer.projection.expression_text
        assert any(r.preference_additive for r in records(again))
    finally:
        again.app.close()


@pytest.mark.parametrize('delta', [31 * 60 * 1_000_000, -1_000_000])
def test_expired_or_backwards_clock_question_does_not_write(tmp_path, monkeypatch, delta):
    import dynamic_subject_agent.timeline as timeline
    now = [1_800_000_000_000_000]
    monkeypatch.setattr(timeline, '_utc_microseconds', lambda: now[0])
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, COVER); submit(opened, NEW)
        before = records(opened)
        now[0] += delta
        response = submit(opened, '是补充。')
        assert '过期或时间无法核实' in response.projection.expression_text
        assert records(opened) == before
    finally:
        opened.app.close()


def test_unpublished_question_cannot_authorize_confirmation(tmp_path):
    from dynamic_subject_agent.runtime import RuntimeFaultPoint
    opened = open_composite(tmp_path, BroadMemory())
    submit(opened, COVER)
    opened.app.close()
    interrupted = open_composite(tmp_path, BroadMemory(), saved=opened, _runtime_interrupt_at=RuntimeFaultPoint.BEFORE_PUBLICATION)
    submit(interrupted, NEW)
    interrupted.app.close()
    resumed = open_composite(tmp_path, BroadMemory(), saved=opened)
    try:
        before = records(resumed)
        submit(resumed, '是补充。')
        assert records(resumed) == before
    finally:
        resumed.app.close()


@pytest.mark.parametrize('mode', ['identity', 'prefix', 'records', 'unreadable', 'incomplete'])
def test_changed_or_unverifiable_confirmation_context_cannot_write(tmp_path, mode):
    from dataclasses import replace
    from uuid import uuid4
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from test_recent_dialogue import open_app
    class Changed(ControlledLivingMemoryCognition):
        def propose(self, **kwargs):
            if kwargs['command'].utterance == '是补充。':
                context = kwargs['context']
                original = context.load_preference_question
                def load():
                    if mode == 'unreadable':
                        raise OSError('synthetic read failure')
                    pending = original()
                    if mode == 'identity':
                        return replace(pending, question=replace(pending.question, profile_id=str(uuid4())))
                    if mode == 'prefix':
                        return replace(pending, prefix_digest='wrong')
                    return pending
                kwargs['context'] = replace(context, load_preference_question=load,
                    memory_control_complete=mode != 'incomplete',
                    canonical_memory_history=() if mode == 'records' else context.canonical_memory_history)
            return super().propose(**kwargs)
    provider = BroadMemory()
    opened = open_app(tmp_path, provider, cognition=Changed(provider=provider))
    try:
        submit(opened, COVER); submit(opened, NEW)
        before = records(opened)
        result = submit(opened, '是补充。')
        assert result.projection.living_memory_status != 'accepted'
        assert records(opened) == before
    finally:
        opened.app.close()


def test_replace_cannot_drop_other_details_from_the_old_record(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, '我做封面时偏爱雾紫色，排版喜欢留白。')
        submit(opened, NEW)
        before = records(opened)
        result = submit(opened, '替换。')
        assert '完整旧原文' in result.projection.expression_text
        assert records(opened) == before
    finally:
        opened.app.close()


def test_controlled_source_does_not_advertise_a_resumable_question(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, COVER)
        before = records(opened)
        question = submit(opened, '请记住：' + NEW)
        assert '无法保留待确认' in question.projection.expression_text
        submit(opened, '是补充。')
        assert records(opened) == before
    finally:
        opened.app.close()


def test_confirmation_interrupted_before_publication_does_not_write(tmp_path):
    from dynamic_subject_agent.runtime import RuntimeFaultPoint
    opened = open_composite(tmp_path, BroadMemory())
    submit(opened, COVER); submit(opened, NEW)
    before = records(opened)
    opened.app.close()
    interrupted = open_composite(tmp_path, BroadMemory(), saved=opened, _runtime_interrupt_at=RuntimeFaultPoint.BEFORE_PUBLICATION)
    response = submit(interrupted, '是补充。')
    assert response.projection is None or not response.projection.expression_text
    interrupted.app.close()
    restored = open_composite(tmp_path, BroadMemory(), saved=opened)
    try:
        assert records(restored) == before
        submit(restored, '是补充。')
        assert records(restored) == before
    finally:
        restored.app.close()

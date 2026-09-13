"""A fresh committed draft remains editable after earlier goal discussion."""
from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
from test_compound_requests import NoopGoal
import pytest
from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalClassificationResult, ParticipantGoalReplyResult

POEM = '灯光落在纸上。晚风经过窗边。'
REVISED = '灯光落在纸上。窗边停着一缕风。'
SECOND_REVISION = '月光落在纸上。窗边停着一缕风。'

class DraftProvider(DialogueProvider):
    def reply(self, request):
        self.replies.append(request)
        text = SECOND_REVISION if request.current_user_message.startswith('第一句') else REVISED if request.current_user_message.startswith('第二句') else POEM
        return LivingMemoryReplyResult(text, 'zh', 'creative')

@pytest.mark.parametrize('goal_failure', ['none', 'classification-failed', 'classification-invalid', 'selection-invalid', 'reply-failed', 'reply-invalid'])
def test_fresh_draft_after_goal_query_can_be_edited(tmp_path, goal_failure):
    class Goal(NoopGoal):
        def classify(self, request):
            if goal_failure == 'classification-failed':
                raise OSError('synthetic unrelated goal failure')
            if goal_failure == 'classification-invalid':
                return None
            if goal_failure == 'selection-invalid':
                return ParticipantGoalClassificationResult(None, ('unknown',), '处理目标。', 'zh')
            if goal_failure.startswith('reply-'):
                return ParticipantGoalClassificationResult(None, (request.active_records[0].turn_ref,), '读取目标。', 'zh')
            return super().classify(request)
        def reply(self, request):
            if goal_failure == 'reply-failed':
                raise OSError('synthetic unrelated reply failure')
            return None if goal_failure == 'reply-invalid' else ParticipantGoalReplyResult('收到。', 'zh')
    provider = DraftProvider()
    opened = open_composite(tmp_path, provider, goal=Goal())
    try:
        submit(opened, '我的目标是今年完成四篇随笔。')
        submit(opened, '我的目标是什么？')
        draft = submit(opened, '请给这本小刊物写两句关于慢慢完成的短诗。')
        assert POEM in draft.projection.expression_text
        if goal_failure != 'none':
            assert draft.projection.participant_goal_commitment_status == 'failed-closed'
        edited = submit(opened, '第二句我想改成带窗的意象。')
        assert REVISED in edited.projection.expression_text
        assert len(provider.replies[-1].recent_dialogue) == 1
        assert provider.replies[-1].recent_dialogue[0].assistant_text == draft.projection.expression_text
        assert '目标' not in provider.replies[-1].recent_dialogue[0].user_text
        again = submit(opened, '第一句我想改成带月的意象。')
        assert SECOND_REVISION in again.projection.expression_text
        assert provider.replies[-1].recent_dialogue[0].assistant_text == edited.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('malformation', [None, 'missing', 'reason', 'action', 'extra', 'unknown', 'memory-null'])
def test_only_complete_known_goal_failure_proves_no_memory_revision(tmp_path, malformation):
    import json
    from dataclasses import replace
    from dynamic_subject_agent.timeline import TimelineEngine
    from test_atomic_publication import _authority, _command, _commit_plan
    code = 'participant-goal-classification-failed'
    goal = {'status': 'failed-closed', 'action': 'noop', 'reason_code': code}
    reason = {'code': code, 'participant_goal_commitment': goal}
    if malformation == 'missing':
        reason.pop('participant_goal_commitment')
    elif malformation == 'reason':
        goal['reason_code'] = 'participant-goal-reply-failed'
    elif malformation == 'action':
        goal['action'] = 'create'
    elif malformation == 'extra':
        goal['terms'] = 'unknown'
    elif malformation == 'unknown':
        reason['code'] = goal['reason_code'] = 'participant-goal-future-failure'
    elif malformation == 'memory-null':
        reason['living_memory'] = None
    engine = TimelineEngine.create_test(tmp_path, _authority())
    try:
        first = engine.admit(_command(), idempotency_key='known-goal-failure')
        plan = _commit_plan(engine, first.operation_ref, first.attempt_id)
        experience = plan.experience_outcome
        engine.publish(replace(plan, experience_outcome=replace(experience,
            decision=replace(experience.decision, rule_version='experience-1.0', reason=json.dumps(reason)))))
        current = engine.admit(_command(), idempotency_key='read-known-goal-failure')
        engine.freeze_attempt_basis(current.operation_ref)
        assert len(engine.recent_dialogue_before(current.operation_ref, expected_head=1)) == (1 if malformation is None else 0)
    finally:
        engine.close()


def test_goal_failure_does_not_override_explicit_history_control(tmp_path):
    class Goal(NoopGoal):
        def classify(self, request):
            raise OSError('synthetic unrelated goal failure')
    provider = DraftProvider()
    opened = open_composite(tmp_path, provider, goal=Goal())
    try:
        submit(opened, '我的目标是今年完成四篇随笔。')
        draft = submit(opened, '请写两句关于灯光的短诗。不要再提旧话题。')
        assert POEM in draft.projection.expression_text
        edited = submit(opened, '第二句我想改成带窗的意象。')
        assert REVISED not in edited.projection.expression_text
        assert provider.replies[-1].recent_dialogue == ()
    finally:
        opened.app.close()


def test_one_replacement_sentence_does_not_discard_the_rest_of_the_draft(tmp_path):
    class Partial(DraftProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult('窗边停着一缕风。' if request.current_user_message.startswith('第二句') else POEM, 'zh', 'creative')
    opened = open_composite(tmp_path, Partial(), goal=NoopGoal())
    try:
        submit(opened, '请写两句关于灯光的短诗。')
        edited = submit(opened, '第二句我想改成带窗的意象。')
        assert '灯光落在纸上。' in edited.projection.expression_text
        assert '窗边停着一缕风。' in edited.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('reply,accepted', [
    ('擅自改动了第一句。窗边停着一缕风。', True),
    ('窗边停着一缕风。额外的一句。还有另一句。', False),
    ('晚风经过窗边。', False),
])
def test_numbered_edit_changes_only_its_target_or_reports_failure(tmp_path, reply, accepted):
    class Partial(DraftProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult(reply if request.current_user_message.startswith('第二句') else POEM, 'zh', 'creative')
    opened = open_composite(tmp_path, Partial(), goal=NoopGoal())
    try:
        submit(opened, '请写两句关于灯光的短诗。')
        result = submit(opened, '第二句我想改成带窗的意象。')
        if accepted:
            assert REVISED in result.projection.expression_text
            assert '擅自改动' not in result.projection.expression_text
        else:
            assert '没有形成新的改写版本' in result.projection.expression_text
    finally:
        opened.app.close()


def test_current_supplied_multi_paragraph_draft_retains_all_other_sentences(tmp_path):
    class Partial(DraftProvider):
        def reply(self, request):
            return LivingMemoryReplyResult('窗边停着一缕风。', 'zh', 'creative')
    opened = open_composite(tmp_path, Partial(), goal=NoopGoal())
    try:
        result = submit(opened, '原文是：「灯光落在纸上。晚风经过窗边。\n\n远山仍然安静。」第二句我想改成带窗的意象。')
        assert '灯光落在纸上。' in result.projection.expression_text
        assert '窗边停着一缕风。' in result.projection.expression_text
        assert '远山仍然安静。' in result.projection.expression_text
        assert '\n\n远山仍然安静。' in result.projection.expression_text
    finally:
        opened.app.close()

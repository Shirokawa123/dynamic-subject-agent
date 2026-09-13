"""Current direct compound requests retain each independent result."""
from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult
from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalClassificationResult, ParticipantGoalReplyResult
from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentCandidate
from test_memory_write_receipts import open_composite
from test_recent_dialogue import DialogueProvider, submit
import pytest
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind

PLAN = '我周六整理苔桥笔记，但如果样张没到就顺延。'
POEM = '晨光落在草叶。鸟声越过山岗。'

class CompoundMemory(DialogueProvider):
    def propose(self, request):
        self.proposals.append(request)
        initial = PLAN in request.current_user_message
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.CREATE if initial else LivingMemoryAction.NONE,
            PLAN if initial else ''), '处理当前请求。', '收到。', 'zh')

    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult(POEM, 'zh', 'creative')

class NoopGoal:
    def __init__(self):
        self.requests = []

    def classify(self, request):
        self.requests.append(request)
        return ParticipantGoalClassificationResult(None, (), '没有目标变化。', 'zh')

    def reply(self, request):
        return ParticipantGoalReplyResult('没有目标变化。', 'zh')

def test_memory_and_two_sentence_creation_are_both_visible(tmp_path):
    opened = open_composite(tmp_path, CompoundMemory())
    try:
        result = submit(opened, PLAN + '请写两句关于清晨的短诗。')
        assert result.projection.living_memory_status == 'accepted'
        assert PLAN in result.projection.expression_text
        assert POEM in result.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('creation', ['请写两句关于清晨的短诗。', '请给清晨写2句短诗。', '给我一版两句短诗。'])
@pytest.mark.parametrize('text,valid', [(POEM, True), ('晨光落在草叶。', False)])
def test_creation_permission_and_count_share_the_request(tmp_path, creation, text, valid):
    class Response(CompoundMemory):
        def reply(self, request):
            return LivingMemoryReplyResult(text, 'zh', 'creative')
    opened = open_composite(tmp_path, Response())
    try:
        result = submit(opened, PLAN + creation)
        assert PLAN in result.projection.expression_text
        assert (text in result.projection.expression_text) is valid
        assert ('没有完成你请求的创作' in result.projection.expression_text) is (not valid)
    finally:
        opened.app.close()


@pytest.mark.parametrize('order', [0, 1, 2])
@pytest.mark.parametrize('goal_clause', ['我的目标是今年读完两本书', '我给自己定个目标：今年读完两本书'])
def test_goal_position_does_not_require_a_model_or_change_other_results(tmp_path, order, goal_clause):
    goal = NoopGoal()
    provider = CompoundMemory()
    clauses = [PLAN, '请写两句关于清晨的短诗。']
    clauses.insert(order, goal_clause + '。')
    message = ''.join(clauses)
    opened = open_composite(tmp_path, provider, goal=goal)
    try:
        result = submit(opened, message)
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert PLAN in result.projection.expression_text and POEM in result.projection.expression_text
        records = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.PARTICIPANT_GOALS,
            opened.qri.profile_id, opened.timeline)).projection.records
        assert [record.terms for record in records] == ['今年读完两本书']
        assert goal.requests == []
        assert len(provider.proposals) == len(provider.replies) == 1
        assert provider.proposals[0].current_user_message == message
        assert provider.replies[0].current_user_message == message
    finally:
        opened.app.close()


@pytest.mark.parametrize('mode', ['noop', 'failure', 'rejected'])
def test_memory_non_success_does_not_hide_goal_or_creation_result(tmp_path, mode):
    class Memory(CompoundMemory):
        def propose(self, request):
            if mode == 'failure':
                raise OSError('synthetic memory failure')
            return LivingMemoryProviderResult(LivingMemoryProposal(
                LivingMemoryAction.NONE if mode == 'noop' else LivingMemoryAction.CREATE,
                '' if mode == 'noop' else '未出现在消息中的内容'), '处理当前请求。', '收到。', 'zh')
    opened = open_composite(tmp_path, Memory(), goal=NoopGoal())
    try:
        result = submit(opened, '请记住：' + PLAN + '我的目标是今年读完两本书。请写两句关于清晨的短诗。')
        text = result.projection.expression_text
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert '已记录你的目标' in text and '已记录你的原话' not in text
        assert '记忆' in text
        if mode == 'failure':
            assert '没有完成你请求的创作' in text
        else:
            assert POEM in text
    finally:
        opened.app.close()


@pytest.mark.parametrize('goal_clause', [
    '朋友说：“我的目标是今年读完两本书。”',
    '如果我的目标是今年读完两本书，你怎么看？',
    '我之前说过：我的目标是今年读完两本书。',
    '我的目标是今年读完两本书？',
])
def test_reported_hypothetical_or_question_goal_is_not_promoted(tmp_path, goal_clause):
    # Even a provider trying to promote a quoted substring must not gain write authority.
    class Claimed(NoopGoal):
        def classify(self, request):
            return ParticipantGoalClassificationResult(ParticipantGoalCommitmentCandidate(
                'create', 'goal', '今年读完两本书', None, 'active', '我的目标是今年读完两本书'), (), '提议目标。', 'zh')
    opened = open_composite(tmp_path, CompoundMemory(), goal=Claimed())
    try:
        result = submit(opened, PLAN + goal_clause + '请写两句关于清晨的短诗。')
        assert result.projection.participant_goal_commitment_status != 'accepted'
        assert '已记录你的目标' not in result.projection.expression_text
        assert PLAN in result.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('tail', ['不要保存这个目标。', '我的目标改为练习写作。'])
def test_full_message_withdrawal_or_second_operation_still_rejects(tmp_path, tail):
    opened = open_composite(tmp_path, CompoundMemory(), goal=NoopGoal())
    try:
        result = submit(opened, PLAN + '我的目标是今年读完两本书。' + tail + '请写两句关于清晨的短诗。')
        assert result.projection.participant_goal_commitment_status == 'rejected'
        assert '已记录你的目标' not in result.projection.expression_text
        if tail.startswith('不要'):
            # Existing withdrawal routing stops Memory generation; disclose it.
            assert '没有完成你请求的创作' in result.projection.expression_text
        else:
            assert POEM in result.projection.expression_text
    finally:
        opened.app.close()


def test_two_distinct_creative_requests_are_not_silently_reduced_to_one(tmp_path):
    opened = open_composite(tmp_path, CompoundMemory())
    try:
        result = submit(opened, PLAN + '请写两句关于清晨的短诗。请写一句生日祝福。')
        assert POEM not in result.projection.expression_text
        assert '多个创作要求' in result.projection.expression_text
        assert PLAN in result.projection.expression_text
    finally:
        opened.app.close()


def test_followup_edit_uses_published_poem_not_receipt(tmp_path):
    revised = '晨光落在草叶。远山接住鸟声。'
    class Revision(CompoundMemory):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult(revised if request.current_user_message.startswith('第二句') else POEM, 'zh', 'creative')
    provider = Revision()
    opened = open_composite(tmp_path, provider)
    try:
        first = submit(opened, PLAN + '请写两句关于清晨的短诗。')
        second = submit(opened, '第二句我想改成带山的意象。')
        assert revised in second.projection.expression_text
        assert '已记录' not in second.projection.expression_text
        assert provider.replies[-1].recent_dialogue[-1].assistant_text == first.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('valid', [True, False])
def test_goal_and_creation_do_not_require_a_memory_write(tmp_path, valid):
    class Response(CompoundMemory):
        def reply(self, request):
            return LivingMemoryReplyResult(POEM if valid else '收到。', 'zh', 'creative' if valid else 'conversation')
    opened = open_composite(tmp_path, Response(), goal=NoopGoal())
    try:
        result = submit(opened, '我的目标是今年读完两本书。请写两句关于清晨的短诗。')
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert '已记录你的原话' not in result.projection.expression_text
        assert (POEM in result.projection.expression_text) is valid
        assert ('没有完成你请求的创作' in result.projection.expression_text) is (not valid)
    finally:
        opened.app.close()


@pytest.mark.parametrize('tail', ['朋友说：“请写两句关于清晨的短诗。”', '请写两句关于清晨的短诗。算了，不要写了。'])
def test_quoted_or_withdrawn_creation_is_not_a_missing_requirement(tmp_path, tail):
    opened = open_composite(tmp_path, CompoundMemory(), goal=NoopGoal())
    try:
        result = submit(opened, PLAN + '我的目标是今年读完两本书。' + tail)
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert POEM not in result.projection.expression_text
        assert '没有完成你请求的创作' not in result.projection.expression_text
    finally:
        opened.app.close()

def test_explicit_goal_clause_is_processed_with_memory_and_creation(tmp_path):
    opened = open_composite(tmp_path, CompoundMemory(), goal=NoopGoal())
    try:
        result = submit(opened, PLAN + '我的目标是今年读完两本书。请写一句关于清晨的短诗。')
        assert result.projection.living_memory_status == 'accepted'
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert '今年读完两本书' in result.projection.expression_text
        assert POEM in result.projection.expression_text
    finally:
        opened.app.close()

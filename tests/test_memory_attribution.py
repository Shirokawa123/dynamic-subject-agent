"""A verbatim substring must retain its quotation/report/condition scope."""
import pytest

from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
from test_scoped_preferences import records
from test_compound_requests import NoopGoal

REPORTED = '小夏说：“我给自己定个目标：把桌布叠整齐。”'
EXCERPT = '我给自己定个目标：把桌布叠整齐。'
OWN = '我周六带两块桌布去旧书交换会。'

class ExcerptProvider(DialogueProvider):
    def __init__(self, message, evidence, revise=False):
        super().__init__()
        self.message, self.evidence, self.revise = message, evidence, revise

    def propose(self, request):
        targeted = request.current_user_message == self.message
        revise = targeted and self.revise
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.REVISE if revise else LivingMemoryAction.CREATE,
            self.evidence if targeted else request.current_user_message,
            request.active_memories[0].memory_id if revise else None, memory_kind='plan'),
            '提出记忆候选。', '已记录。', 'zh')

@pytest.mark.parametrize('revise', [False, True])
def test_original_reported_first_person_cannot_be_written_or_replace_own_plan(tmp_path, revise):
    provider = ExcerptProvider(REPORTED, EXCERPT, revise)
    opened = open_composite(tmp_path, provider, goal=NoopGoal())
    try:
        submit(opened, OWN)
        before = records(opened)
        result = submit(opened, REPORTED)
        assert result.projection.living_memory_status == 'rejected'
        assert records(opened) == before
        assert '已记录你的原话' not in result.projection.expression_text
    finally:
        opened.app.close()

@pytest.mark.parametrize('message,evidence', [
    ('小夏说：「小林说：‘我周六会带蛋糕。’」', '我周六会带蛋糕。'),
    ('如果下雨，我周六会留在家里。', '我周六会留在家里。'),
    ('小夏说：我周六会带蛋糕。', '我周六会带蛋糕。'),
])
def test_nested_report_and_condition_do_not_lose_qualifiers(tmp_path, message, evidence):
    opened = open_composite(tmp_path, ExcerptProvider(message, evidence), goal=NoopGoal())
    try:
        result = submit(opened, message)
        assert result.projection.living_memory_status == 'rejected'
        assert records(opened) == ()
    finally:
        opened.app.close()

@pytest.mark.parametrize('message,evidence', [
    ('小夏说：“我周六会带蛋糕。”', '“我周六会带蛋糕。”'),
    ('“我周六会带蛋糕。”小夏说。', '“我周六会带蛋糕。”'),
    ('小夏说：“我周六会带蛋糕。', '我周六会带蛋糕。'),
    ('小夏说："我周六会带蛋糕。"', '我周六会带蛋糕。'),
    ('小夏说：「我周六会带蛋糕。」', '我周六会带蛋糕。'),
    ('小夏说：“我周六会带蛋糕。”我周六会带蛋糕。', '我周六会带蛋糕。'),
    ('请记住：如果下雨，我周六会留在家里。', '我周六会留在家里。'),
])
def test_partial_quotation_duplicate_or_wrapped_condition_is_not_authoritative(tmp_path, message, evidence):
    opened = open_composite(tmp_path, ExcerptProvider(message, evidence), goal=NoopGoal())
    try:
        assert submit(opened, message).projection.living_memory_status == 'rejected'
        assert records(opened) == ()
    finally:
        opened.app.close()

@pytest.mark.parametrize('message,evidence', [
    (REPORTED, REPORTED),
    ('如果下雨，我周六会留在家里。', '如果下雨，我周六会留在家里。'),
    ('小夏说：我周六会带蛋糕。', '小夏说：我周六会带蛋糕。'),
    (OWN, OWN),
    (REPORTED + OWN, OWN),
    (OWN + REPORTED, OWN),
    ('请记住：我抄了一句“风会经过”用于稿件。', '我抄了一句“风会经过”用于稿件。'),
    ('我给纸箱起名“松风”。我周六带桌布。', '我给纸箱起名“松风”。'),
    ('小夏说：“我周六会带蛋糕。”；我给纸箱起名“松风”。', '我给纸箱起名“松风”。'),
    ('小夏说：“我周六会带蛋糕。”；我周六带桌布。', '小夏说：“我周六会带蛋糕。”'),
])
def test_complete_context_and_independent_current_self_statement_survive_restart(tmp_path, message, evidence):
    provider = ExcerptProvider(message, evidence)
    opened = open_composite(tmp_path, provider, goal=NoopGoal())
    try:
        result = submit(opened, message)
        assert result.projection.living_memory_status == 'accepted'
        assert [r.content for r in records(opened)] == [evidence]
        before = records(opened)
        opened.app.close()
        opened = open_composite(tmp_path, provider, goal=NoopGoal(), saved=opened)
        assert records(opened) == before
    finally:
        opened.app.close()

def test_literal_correction_shape_alone_does_not_license_arbitrary_quote_extraction(tmp_path):
    message = '更正记忆：把「旧内容」改成「小夏说：我周六会带蛋糕。」'
    excerpt = '我周六会带蛋糕。'
    opened = open_composite(tmp_path, ExcerptProvider(message, excerpt, revise=True), goal=NoopGoal())
    try:
        submit(opened, OWN)
        before = records(opened)
        assert submit(opened, message).projection.living_memory_status == 'rejected'
        assert records(opened) == before
    finally:
        opened.app.close()

def test_existing_exact_preference_correction_with_spacing_keeps_its_authority(tmp_path):
    from test_scoped_preferences import BroadMemory
    old = '我做封面时喜欢墨绿色，排版喜欢留白。'
    new = '我做封面时喜欢浅杏色，排版喜欢留白。'
    opened = open_composite(tmp_path, BroadMemory(), goal=NoopGoal())
    try:
        submit(opened, old)
        result = submit(opened, f'  更正记忆：把「{old}」改成「{new}」  ')
        assert result.projection.living_memory_status == 'accepted'
        assert [r.content for r in records(opened) if r.status == 'active'] == [new]
    finally:
        opened.app.close()

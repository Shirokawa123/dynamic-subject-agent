"""Natural scenario declarations feed only the existing explicit choice flow."""
import pytest

from test_scoped_preferences import BroadMemory, records
from test_memory_write_receipts import open_composite
from test_recent_dialogue import submit

OLD = '给展台贴纸挑颜色时，我通常喜欢砖红色，远看也不冷。'
NEW = '最近展台贴纸用米白色也不错，我拿不准这算添一种还是换掉原来的。'
QUERY = '我做展台贴纸时喜欢什么颜色？'

@pytest.mark.parametrize('restart', [False, True])
def test_original_natural_preference_question_and_supplement(tmp_path, restart):
    provider = BroadMemory()
    opened = open_composite(tmp_path, provider)
    try:
        submit(opened, OLD)
        submit(opened, '我做工具标签时偏爱海军蓝色。')
        before = records(opened)
        question = submit(opened, NEW)
        assert '是补充还是替换' in question.projection.expression_text
        assert records(opened) == before
        if restart:
            opened.app.close()
            opened = open_composite(tmp_path, provider, saved=opened)
        response = submit(opened, '是补充。')
        assert response.projection.living_memory_status == 'accepted'
        saved = next(r for r in records(opened) if r.content == NEW)
        assert saved.source_user_message_id == question.operation_ref.operation_id
        assert saved.preference_additive
        answer = submit(opened, QUERY)
        assert OLD in answer.projection.expression_text and NEW in answer.projection.expression_text
        assert '海军蓝' not in answer.projection.expression_text
        assert '补充保留' in answer.projection.expression_text
        assert provider.proposals == [] and provider.replies == []
    finally:
        opened.app.close()

def test_natural_scene_declaration_keeps_entire_original(tmp_path):
    provider = BroadMemory()
    opened = open_composite(tmp_path, provider)
    try:
        submit(opened, OLD)
        assert [r.content for r in records(opened)] == [OLD]
        assert OLD in submit(opened, QUERY).projection.expression_text
        assert provider.proposals == []
    finally:
        opened.app.close()

def test_legacy_unconfirmed_option_does_not_become_a_confirmed_preference(tmp_path, monkeypatch):
    import dynamic_subject_agent.scoped_preferences as preferences
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, OLD)
        with monkeypatch.context() as legacy:
            legacy.setattr(preferences, 'route_preference', lambda *args, **kwargs: None)
            legacy.setattr(preferences, 'preference_change_allowed', lambda *args, **kwargs: True)
            submit(opened, NEW)
        result = submit(opened, QUERY)
        assert OLD in result.projection.expression_text
        assert NEW not in result.projection.expression_text
        question = submit(opened, NEW)
        assert '是补充还是替换' in question.projection.expression_text
    finally:
        opened.app.close()

def test_control_prefix_cannot_turn_uncertain_option_into_direct_replacement(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, '我做展台贴纸时喜欢砖红色。')
        before = records(opened)
        submit(opened, '更正记忆：' + NEW)
        assert records(opened) == before
    finally:
        opened.app.close()

@pytest.mark.parametrize('answer', ['替换。', '算了。'])
def test_natural_question_replace_or_cancel_and_restart(tmp_path, answer):
    provider = BroadMemory()
    opened = open_composite(tmp_path, provider)
    old = '给展台贴纸挑颜色时，我通常喜欢砖红色。'
    try:
        submit(opened, old)
        question = submit(opened, NEW)
        submit(opened, answer)
        before = records(opened)
        active = [r for r in before if r.status == 'active']
        assert [r.content for r in active] == ([NEW] if answer == '替换。' else [old])
        if answer == '替换。':
            assert active[0].preference_confirmed and not active[0].preference_additive
            assert active[0].source_user_message_id == question.operation_ref.operation_id
        submit(opened, answer)
        assert records(opened) == before
        opened.app.close()
        opened = open_composite(tmp_path, provider, saved=opened)
        assert records(opened) == before
        result = submit(opened, QUERY)
        assert (NEW if answer == '替换。' else old) in result.projection.expression_text
        assert provider.proposals == [] and provider.replies == []
    finally:
        opened.app.close()

def test_original_old_tail_cannot_be_discarded_by_short_replace(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, OLD)
        submit(opened, NEW)
        before = records(opened)
        result = submit(opened, '替换。')
        assert '完整旧原文' in result.projection.expression_text
        assert records(opened) == before
    finally:
        opened.app.close()

@pytest.mark.parametrize('intervening', ['我们换个话题。', QUERY])
def test_natural_question_cannot_be_revived_after_another_turn(tmp_path, intervening):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, OLD)
        submit(opened, NEW)
        submit(opened, intervening)
        before = records(opened)
        result = submit(opened, '是补充。')
        assert '当前没有可确认' in result.projection.expression_text
        assert records(opened) == before
    finally:
        opened.app.close()

def test_undecided_option_without_known_scene_is_not_saved_or_confirmable(tmp_path):
    provider = BroadMemory()
    opened = open_composite(tmp_path, provider)
    try:
        result = submit(opened, NEW)
        assert '旧偏好' in result.projection.expression_text
        submit(opened, '是补充。')
        assert records(opened) == ()
        assert provider.proposals == [] and provider.replies == []
    finally:
        opened.app.close()

@pytest.mark.parametrize('message', [
    '朋友说：“' + NEW + '”',
    '如果' + NEW,
    '我昨天说，' + NEW,
    NEW + '算了，不要保存。',
])
def test_provider_cannot_lift_an_undecided_option_out_of_noncurrent_or_withdrawn_text(tmp_path, message):
    from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult
    class Lifted(BroadMemory):
        def propose(self, request):
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE, NEW), '候选。', '已保存。', 'zh')
    opened = open_composite(tmp_path, Lifted())
    try:
        submit(opened, OLD)
        before = records(opened)
        submit(opened, message)
        assert records(opened) == before
        submit(opened, '是补充。')
        assert records(opened) == before
    finally:
        opened.app.close()

@pytest.mark.parametrize('scope,color', [('书套', '浅杏色'), ('花盆标签', '淡紫色')])
def test_other_scenes_use_same_confirmation_path(tmp_path, scope, color):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, f'给{scope}挑颜色时，我喜欢墨绿色。')
        candidate = f'{scope}用{color}也不错，我不确定是补充还是替换。'
        result = submit(opened, candidate)
        assert '是补充还是替换' in result.projection.expression_text
        submit(opened, '是补充。')
        result = submit(opened, f'我做{scope}时喜欢什么颜色？')
        assert '墨绿色' in result.projection.expression_text and candidate in result.projection.expression_text
    finally:
        opened.app.close()

def test_natural_declaration_with_withdrawal_is_not_saved(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        result = submit(opened, '给展台贴纸挑颜色时，我通常喜欢砖红色，先不要保存。')
        assert records(opened) == ()
        assert result.projection.living_memory_status != 'accepted'
    finally:
        opened.app.close()

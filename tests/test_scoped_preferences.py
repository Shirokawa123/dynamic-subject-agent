"""Preferences are answered and changed within their declared scenario."""
from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
import pytest

COVER = '我做封面时偏爱雾紫色。'
POSTER = '我做海报时偏爱墨绿色。'
GENERAL = '我喜欢柔和的蓝色。'
QUERY = '我做封面时偏爱什么颜色？'

class BroadMemory(DialogueProvider):
    def propose(self, request):
        self.proposals.append(request)
        question = request.current_user_message.endswith('？')
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.NONE if question else LivingMemoryAction.CREATE,
            '' if question else request.current_user_message,
            recalled_memory_ids=tuple(m.memory_id for m in request.active_memories) if question else ()),
            '处理偏好。', '收到。', 'zh')
    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult('', 'zh', 'memory')

def records(opened):
    return opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
        opened.qri.profile_id, opened.timeline)).projection.memories

def test_preference_query_does_not_mix_other_scenarios(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        for text in (GENERAL, POSTER, COVER):
            submit(opened, text)
        result = submit(opened, QUERY)
        assert COVER in result.projection.expression_text
        assert '海报' not in result.projection.expression_text
        assert '蓝色' not in result.projection.expression_text
    finally:
        opened.app.close()

def test_explicit_change_revises_only_the_unique_scenario(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, POSTER)
        submit(opened, COVER)
        result = submit(opened, '封面改用浅杏色。')
        assert result.projection.living_memory_status == 'accepted'
        active = [m.content for m in records(opened) if m.status == 'active']
        assert COVER not in active and POSTER in active
        result = submit(opened, QUERY)
        assert '浅杏色' in result.projection.expression_text and '雾紫色' not in result.projection.expression_text
    finally:
        opened.app.close()


def test_addition_coexists_but_a_bare_new_preference_requires_clarification(tmp_path):
    provider = BroadMemory()
    opened = open_composite(tmp_path, provider)
    try:
        submit(opened, COVER)
        before = records(opened)
        ambiguous = submit(opened, '我做封面时偏爱浅杏色。')
        assert records(opened) == before
        assert '补充还是替换' in ambiguous.projection.expression_text
        submit(opened, '我做封面时也喜欢浅杏色。')
        answer = submit(opened, QUERY)
        assert '雾紫色' in answer.projection.expression_text and '浅杏色' in answer.projection.expression_text
        assert '补充保留' in answer.projection.expression_text
        assert provider.proposals == [] and provider.replies == []
    finally:
        opened.app.close()


def test_legacy_conflicting_values_are_not_resolved_by_recency(tmp_path, monkeypatch):
    import dynamic_subject_agent.scoped_preferences as preferences
    opened = open_composite(tmp_path, BroadMemory())
    try:
        with monkeypatch.context() as legacy:
            legacy.setattr(preferences, 'route_preference', lambda *args, **kwargs: None)
            legacy.setattr(preferences, 'preference_change_allowed', lambda *args, **kwargs: True)
            submit(opened, COVER)
            submit(opened, '我做封面时偏爱浅杏色。')
            submit(opened, GENERAL)
        before = records(opened)
        answer = submit(opened, QUERY)
        assert '雾紫色' in answer.projection.expression_text and '浅杏色' in answer.projection.expression_text
        assert '同时喜欢' in answer.projection.expression_text
        assert '蓝色' not in answer.projection.expression_text
        ambiguous = submit(opened, '封面改用玫瑰色。')
        assert records(opened) == before
        assert '无法唯一' in ambiguous.projection.expression_text
    finally:
        opened.app.close()


def test_short_change_cannot_discard_other_record_content(tmp_path):
    old = '我做封面时偏爱雾紫色，排版喜欢留白。'
    new = '我做封面时偏爱浅杏色，排版喜欢留白。'
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, old)
        before = records(opened)
        refused = submit(opened, '封面改用浅杏色。')
        assert records(opened) == before
        assert '完整新原文' in refused.projection.expression_text
        accepted = submit(opened, f'更正记忆：把「{old}」改成「{new}」')
        assert accepted.projection.living_memory_status == 'accepted'
        assert [m.content for m in records(opened) if m.status == 'active'] == [new]
        answer = submit(opened, QUERY)
        assert new in answer.projection.expression_text and '雾紫色' not in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', ['朋友说：“封面改用浅杏色。”', '如果封面改用浅杏色，你怎么看？',
    '我之前说过：封面改用浅杏色。', '封面改用浅杏色。算了，不要保存。'])
def test_quoted_hypothetical_or_withdrawn_change_does_not_supersede_preference(tmp_path, message):
    class Malicious(BroadMemory):
        def propose(self, request):
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.REVISE,
                '封面改用浅杏色。' if '封面改用浅杏色。' in request.current_user_message else request.current_user_message,
                request.active_memories[0].memory_id), '试图修改。', '已更正。', 'zh')
    opened = open_composite(tmp_path, Malicious())
    try:
        submit(opened, COVER)
        old = records(opened)[0]
        submit(opened, message)
        assert any(m.memory_id == old.memory_id and m.status == 'active' for m in records(opened))
    finally:
        opened.app.close()


def test_unknown_scenario_does_not_fall_back_to_general_color(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, GENERAL)
        answer = submit(opened, '我做书签时偏爱什么颜色？')
        assert '蓝色' not in answer.projection.expression_text
        assert '没有能明确对应' in answer.projection.expression_text
    finally:
        opened.app.close()


def test_forgetting_preference_keeps_it_out_of_scoped_answer(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, COVER)
        submit(opened, f'请忘记「{COVER}」')
        answer = submit(opened, QUERY)
        assert '雾紫色' not in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('mode', ['incomplete', 'unreadable', 'pending'])
def test_uncertain_inventory_does_not_answer_or_change_preference(tmp_path, mode):
    from dataclasses import replace
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from test_recent_dialogue import open_app
    class Limited(ControlledLivingMemoryCognition):
        limited = False
        def propose(self, **kwargs):
            if self.limited:
                context = kwargs['context']
                def unreadable():
                    raise OSError('synthetic inventory failure')
                kwargs['context'] = (replace(context, memory_control_complete=False) if mode == 'incomplete' else
                    replace(context, load_withheld_memory_ids=unreadable if mode == 'unreadable' else lambda: ('unknown',)))
            return super().propose(**kwargs)
    provider = BroadMemory()
    cognition = Limited(provider=provider)
    opened = open_app(tmp_path, provider, cognition=cognition)
    try:
        submit(opened, COVER)
        before = records(opened)
        cognition.limited = True
        answer = submit(opened, QUERY)
        assert '无法核实' in answer.projection.expression_text and '雾紫色' not in answer.projection.expression_text
        submit(opened, '封面改用浅杏色。')
        assert records(opened) == before
        assert provider.proposals == []
    finally:
        opened.app.close()


def test_bare_followup_does_not_infer_a_state_target_from_chat_history(tmp_path):
    opened = open_composite(tmp_path, BroadMemory())
    try:
        submit(opened, COVER)
        before = records(opened)
        reply = submit(opened, '也喜欢浅杏色。')
        assert '哪个场景' in reply.projection.expression_text
        assert records(opened) == before
    finally:
        opened.app.close()


def test_compound_message_can_still_save_an_independent_preference(tmp_path):
    class Compound(BroadMemory):
        def propose(self, request):
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE, COVER), '记录偏好。', '收到。', 'zh')
        def reply(self, request):
            return LivingMemoryReplyResult('灯光落在纸上。', 'zh', 'creative')
    opened = open_composite(tmp_path, Compound())
    try:
        result = submit(opened, '请记住：' + COVER + '请写一句关于灯光的短诗。')
        assert result.projection.living_memory_status == 'accepted'
        assert '灯光落在纸上。' in result.projection.expression_text
        assert [m.content for m in records(opened)] == [COVER]
    finally:
        opened.app.close()

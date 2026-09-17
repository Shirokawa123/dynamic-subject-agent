"""Mixed-scene writing requests reach the existing bounded edit path."""
import pytest

from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from dynamic_subject_agent.runtime_identity_reply import CREATIVE_REPLY_PREFIX
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
from test_compound_requests import NoopGoal

ORIGINAL_REQUEST = '原文是：「路过的人，留一小段空白。把今天的颜色带走。」第二句请改得更像邀请，不要命令口气。'
NEXT_REQUEST = '第一句再改成有风吹过纸边的感觉，别用“路过”。'
DRAFT = '路过的人，留一小段空白。要不要把今天的颜色带走？'
REPLACEMENT = '风轻轻翻过纸边。'

class WritingProvider(DialogueProvider):
    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult(REPLACEMENT if request.current_user_message == NEXT_REQUEST else DRAFT, 'zh', 'creative')

@pytest.mark.parametrize('restart', [False, True])
def test_original_mixed_scene_second_edit_retains_other_sentence(tmp_path, restart):
    provider = WritingProvider()
    opened = open_composite(tmp_path, provider, goal=NoopGoal())
    try:
        first = submit(opened, ORIGINAL_REQUEST)
        assert DRAFT in first.projection.expression_text
        if restart:
            opened.app.close()
            opened = open_composite(tmp_path, provider, goal=NoopGoal(), saved=opened)
        second = submit(opened, NEXT_REQUEST)
        assert second.projection.expression_text == CREATIVE_REPLY_PREFIX + REPLACEMENT + '要不要把今天的颜色带走？'
        assert len(provider.replies[-1].recent_dialogue) == 1
        assert provider.replies[-1].recent_dialogue[0].assistant_text == first.projection.expression_text
    finally:
        opened.app.close()

def test_original_mixed_scene_first_draft_request(tmp_path):
    opened = open_composite(tmp_path, WritingProvider(), goal=NoopGoal())
    try:
        result = submit(opened, '那就请写两句吧：一行像邀请，一行像留给路人的空白，不要太像宣传语。')
        assert result.projection.expression_text == CREATIVE_REPLY_PREFIX + DRAFT
    finally:
        opened.app.close()

@pytest.mark.parametrize('message', [
    '第二句请再换成轻声邀请。',
    '第二句我想再改得更简短。',
    '第二句再改为一句问候。',
])
def test_repeated_edit_is_bound_to_one_sentence(tmp_path, message):
    class Partial(WritingProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult('来坐坐吧。' if request.current_user_message == message else DRAFT, 'zh', 'creative')
    opened = open_composite(tmp_path, Partial(), goal=NoopGoal())
    try:
        submit(opened, ORIGINAL_REQUEST)
        answer = submit(opened, message)
        assert answer.projection.expression_text == CREATIVE_REPLY_PREFIX + '路过的人，留一小段空白。来坐坐吧。'
    finally:
        opened.app.close()

@pytest.mark.parametrize('message', [
    '朋友说：“第一句再改成有风吹过纸边的感觉。”',
    '如果第一句再改成有风吹过纸边的感觉，你怎么看？',
    '我昨天说，第一句再改成有风吹过纸边的感觉。',
    NEXT_REQUEST + '算了，不要改了。',
    '第一句再改成风。第二句再改成雨。',
    '朋友说：“那就请写两句吧。”',
    '如果那就请写两句吧，你会怎样回答？',
    '我昨天说，那就请写两句吧。',
    '那就请写两句吧。算了，不要写了。',
])
def test_new_forms_do_not_license_report_condition_withdrawal_or_ambiguous_edit(tmp_path, message):
    opened = open_composite(tmp_path, WritingProvider(), goal=NoopGoal())
    try:
        submit(opened, ORIGINAL_REQUEST)
        answer = submit(opened, message)
        assert not answer.projection.expression_text.startswith(CREATIVE_REPLY_PREFIX)
    finally:
        opened.app.close()

def test_repeated_edit_keeps_history_control_and_requires_current_draft(tmp_path):
    provider = WritingProvider()
    opened = open_composite(tmp_path, provider, goal=NoopGoal())
    try:
        submit(opened, ORIGINAL_REQUEST)
        result = submit(opened, '第一句再改成风吹过的感觉，别再提旧词。')
        assert '可安全用于修改' in result.projection.expression_text
        assert provider.replies[-1].recent_dialogue == ()
        result = submit(opened, NEXT_REQUEST)
        assert '可安全用于修改' in result.projection.expression_text
        assert provider.replies[-1].recent_dialogue == ()
    finally:
        opened.app.close()

def test_new_creation_leadin_still_requires_two_sentences(tmp_path):
    class One(WritingProvider):
        def reply(self, request):
            return LivingMemoryReplyResult('只有一句。', 'zh', 'creative')
    opened = open_composite(tmp_path, One(), goal=NoopGoal())
    try:
        result = submit(opened, '那就请写两句吧。')
        assert '只有一句。' not in result.projection.expression_text
    finally:
        opened.app.close()

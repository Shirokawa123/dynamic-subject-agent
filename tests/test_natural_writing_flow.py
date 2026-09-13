"""Original independent acceptance prompts must deliver complete writing."""
import pytest
from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite

FIRST = '我们顺手给周六的餐桌写两句小卡片吧，要明亮一点，不要像广告。'
SUPPLIED = '那张餐桌卡片我先自己写了两句：「雨停以后，桌上有光。愿周六的早晨慢一点。」第二句想换得更像邀请，但别太郑重。'
FOLLOWUP = '第一句也别再提雨，换成窗边有光的感觉。'
POEM = '窗边留着光。周六一起吃早餐吧。'

class Writer(DialogueProvider):
    def reply(self, request):
        self.replies.append(request)
        text = '周六一起吃早餐吧。' if request.current_user_message == SUPPLIED else '窗边留着光。' if FOLLOWUP in request.current_user_message else POEM
        return LivingMemoryReplyResult(text, 'zh', 'creative')

def test_original_natural_first_draft(tmp_path):
    opened = open_composite(tmp_path, Writer())
    try:
        result = submit(opened, FIRST)
        assert POEM in result.projection.expression_text
    finally:
        opened.app.close()

def test_original_supplied_draft_then_controlled_followup_requires_reposting(tmp_path):
    provider = Writer()
    opened = open_composite(tmp_path, provider)
    try:
        result = submit(opened, SUPPLIED)
        assert '雨停以后，桌上有光。' in result.projection.expression_text
        assert '周六一起吃早餐吧。' in result.projection.expression_text
        result = submit(opened, FOLLOWUP)
        assert '可安全用于修改' in result.projection.expression_text
        assert provider.replies[-1].recent_dialogue == ()
        result = submit(opened, '原文是：「雨停以后，桌上有光。周六一起吃早餐吧。」' + FOLLOWUP)
        assert '窗边留着光。' in result.projection.expression_text
        assert '周六一起吃早餐吧。' in result.projection.expression_text
        assert '雨停' not in result.projection.expression_text
        assert provider.replies[-1].recent_dialogue == ()
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', [
    '咱们一起给读书角写两句短笺，轻松一点。',
    '我们先为新邻居写两句欢迎语吧。',
    '顺手给窗台写两句短诗。',
])
def test_unseen_collaborative_creation_forms(tmp_path, message):
    opened = open_composite(tmp_path, Writer())
    try:
        assert POEM in submit(opened, message).projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', [
    '朋友说：“我们顺手给餐桌写两句卡片吧。”',
    '如果我们一起给餐桌写两句卡片，你怎么看？',
    '我们昨天给餐桌写两句卡片了。',
    FIRST + '算了，不要写了。',
])
def test_reported_conditional_or_withdrawn_creation_remains_unlicensed(tmp_path, message):
    opened = open_composite(tmp_path, Writer())
    try:
        assert POEM not in submit(opened, message).projection.expression_text
    finally:
        opened.app.close()


def test_fresh_natural_edit_without_privacy_control_continues(tmp_path):
    class Edit(Writer):
        def reply(self, request):
            self.replies.append(request)
            text = '月光落在书页上。' if '第一句' in request.current_user_message else '一起坐在窗边读书吧。' if '第二句' in request.current_user_message else POEM
            return LivingMemoryReplyResult(text, 'zh', 'creative')
    opened = open_composite(tmp_path, Edit())
    try:
        first = submit(opened, '我刚写了两句：「窗边留着光。愿早晨慢一点。」第二句想改得像邀请。')
        assert '窗边留着光。' in first.projection.expression_text and '一起坐在窗边读书吧。' in first.projection.expression_text
        second = submit(opened, '第一句也想换成月光的感觉。')
        assert '月光落在书页上。' in second.projection.expression_text and '一起坐在窗边读书吧。' in second.projection.expression_text
    finally:
        opened.app.close()


def test_mixed_multiple_drafts_are_not_silently_selected(tmp_path):
    opened = open_composite(tmp_path, Writer())
    try:
        submit(opened, FIRST)
        result = submit(opened, '原文是：“甲。乙。”我写了两句：“丙。丁。”我写了两句：“戊。己。”第二句想换得轻一点。')
        assert '可安全用于修改' in result.projection.expression_text
        assert POEM not in result.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('source', ['我刚写了一句：「只有一句。」', '我刚写了两句：「光落下来。「风吹过。」其他句子。」'])
def test_unusable_current_draft_does_not_fall_back_to_old_work(tmp_path, source):
    provider = Writer()
    opened = open_composite(tmp_path, provider)
    try:
        submit(opened, FIRST)
        result = submit(opened, source + '第二句想换得更轻一点。')
        assert '可安全用于修改' in result.projection.expression_text
        assert provider.replies[-1].recent_dialogue == ()
    finally:
        opened.app.close()

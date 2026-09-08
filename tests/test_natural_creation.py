from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from test_grounded_role_expression import MemoryProvider, turn
import pytest


CAPTION = '这个“注脚”的说法我喜欢。帮我给这张票的照片配一句话吧，像发给朋友的消息，别写成感伤散文。'
SHORTEN = '这位老板话还是有点多，我想让他省话一点。能缩到十个字以内吗？'


def test_caption_with_style_restriction_is_an_explicit_creation(tmp_path):
    text = '今天的注脚，是这张票。'
    result = turn(tmp_path, CAPTION, MemoryProvider('基础回复。', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text
    assert '即兴创作' in result.expression_text


@pytest.mark.parametrize('message', [
    '给照片配一句话。不要写。',
    '给照片配一句话是什么意思？',
    '朋友说：“帮我给照片配一句话。”你怎么看？',
    '我昨天给照片配一句话了。',
    '如果我请你给照片配一句话，你会怎么做？',
])
def test_caption_mention_or_actual_prohibition_does_not_license_creation(tmp_path, message):
    text = '冒充获得许可的创作。'
    result = turn(tmp_path, message, MemoryProvider('请具体说明你的需求。', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text not in result.expression_text


def test_counted_shortening_uses_nearest_safe_reply(tmp_path):
    from test_recent_dialogue import DialogueProvider, open_app, submit, pairs
    class Shortener(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult('进来，面热着。' if request.current_user_message == SHORTEN else '客官请进，热面已经为你准备好了。', 'zh', 'creative')
    provider = Shortener()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '请写一句旧话题的诗。')
        latest = submit(opened, '请给面馆老板写一句欢迎客人的话。')
        result = submit(opened, SHORTEN)
        assert '进来，面热着。' in result.projection.expression_text
        assert pairs(provider.replies[-1]) == [('请给面馆老板写一句欢迎客人的话。', latest.projection.expression_text)]
        assert len(provider.replies) == len(provider.proposals) == 3
    finally:
        opened.app.close()


@pytest.mark.parametrize('limit,text,accepted', [
    ('十', '进来，面热着。', True), ('10', '“进来，面热着。”', True),
    ('一', '来', True), ('两', '来。', True), ('十九', '甲' * 19, True),
    ('九十九', '甲' * 99, True), ('十', '客官请进来坐下吃碗热面吧。', False), ('一', '来。', False),
])
def test_counted_rewrite_checks_body_instead_of_claiming_success(tmp_path, limit, text, accepted):
    from test_recent_dialogue import DialogueProvider, open_app, submit
    class Shortener(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult(text if len(self.replies) > 1 else '老板请客人坐下来吃面。', 'zh', 'creative')
    provider = Shortener()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '请写一句老板招呼客人的话。')
        result = submit(opened, f'能缩到{limit}个字以内吗？')
        if accepted:
            assert text in result.projection.expression_text
            assert '即兴创作' in result.projection.expression_text
        else:
            assert text not in result.projection.expression_text
            assert '没有形成新的改写版本' in result.projection.expression_text
        assert len(provider.replies) == len(provider.proposals) == 2
    finally:
        opened.app.close()


def test_counted_rewrite_after_control_cannot_reuse_old_text(tmp_path):
    from test_recent_dialogue import DialogueProvider, open_app, submit, pairs
    provider = DialogueProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '请写一句关于虚构暗号青舟的话。')
        submit(opened, '不要再说这个暗号。')
        result = submit(opened, SHORTEN)
        assert pairs(provider.replies[-1]) == []
        assert '青舟' not in result.projection.expression_text
        assert '前文' in result.projection.expression_text
    finally:
        opened.app.close()

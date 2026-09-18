"""Explicit numbered style feedback reuses the current bounded edit path."""
import pytest
from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from dynamic_subject_agent.runtime_identity_reply import CREATIVE_REPLY_PREFIX
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
from test_compound_requests import NoopGoal

FIRST = '请写两句关于书页的短诗。'
DRAFT = '故事停在书页间。愿你慢慢翻开。'
EDIT = '第一句我想更轻一点，别用“故事”这个词。'

class Writer(DialogueProvider):
    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult(DRAFT if request.current_user_message == FIRST else '风停在书页间。', 'zh', 'creative')

@pytest.mark.parametrize('restart', [False, True])
def test_original_softening_keeps_other_sentence(tmp_path, restart):
    provider = Writer()
    opened = open_composite(tmp_path, provider, goal=NoopGoal())
    try:
        first = submit(opened, FIRST)
        if restart:
            opened.app.close()
            opened = open_composite(tmp_path, provider, goal=NoopGoal(), saved=opened)
        result = submit(opened, EDIT)
        assert result.projection.expression_text == CREATIVE_REPLY_PREFIX + '风停在书页间。愿你慢慢翻开。'
        assert len(provider.replies[-1].recent_dialogue) == 1
        assert provider.replies[-1].recent_dialogue[0].assistant_text == first.projection.expression_text
    finally:
        opened.app.close()

@pytest.mark.parametrize('message', ['第二句请更口语一些。', '第二句我希望更含蓄一点。', '第二句也想再更简短点。'])
def test_style_has_a_single_numbered_target(tmp_path, message):
    opened = open_composite(tmp_path, Writer(), goal=NoopGoal())
    try:
        submit(opened, FIRST)
        assert submit(opened, message).projection.expression_text == CREATIVE_REPLY_PREFIX + '故事停在书页间。风停在书页间。'
    finally:
        opened.app.close()

@pytest.mark.parametrize('message', [
    '小夏说：“第一句我想更轻一点。”', '小夏说，第一句我想更轻一点。',
    '如果第一句我想更轻一点，你怎么看？', '我昨天说，第一句我想更轻一点。',
    EDIT + '算了，不要改了。', '第一句我想更轻一点。第二句我想更短一点。',
])
def test_report_condition_withdrawal_and_multiple_targets_are_not_edit_permission(tmp_path, message):
    opened = open_composite(tmp_path, Writer(), goal=NoopGoal())
    try:
        submit(opened, FIRST)
        assert not submit(opened, message).projection.expression_text.startswith(CREATIVE_REPLY_PREFIX)
    finally:
        opened.app.close()

def test_missing_or_controlled_draft_requests_reposting(tmp_path):
    provider = Writer()
    opened = open_composite(tmp_path, provider, goal=NoopGoal())
    try:
        assert '可安全用于修改' in submit(opened, EDIT).projection.expression_text
        submit(opened, FIRST)
        assert '可安全用于修改' in submit(opened, '第一句我想更轻一点，别再提旧词。').projection.expression_text
        assert provider.replies[-1].recent_dialogue == ()
    finally:
        opened.app.close()

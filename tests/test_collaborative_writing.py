import pytest
from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from test_grounded_role_expression import MemoryProvider, turn


FIRST = '好，那就把不知道的部分留白。你先给我一版不煽情、像傍晚窗边的明信片短句。'
RETURN = '那就给我一版明亮一点、但仍然克制的两句祝福。'
REVISION = '第二句我想保留“窗”这个意象，不过不要再提薄荷。'


@pytest.mark.parametrize('message', [FIRST, RETURN])
def test_direct_request_for_a_version_delivers_creation(tmp_path, message):
    text = '愿新窗接住晨光。愿你在新家自在安稳。'
    result = turn(tmp_path, message, MemoryProvider('（无记忆相关内容）',
        refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text
    assert '即兴创作' in result.expression_text


def test_background_citation_cannot_replace_valid_creation(tmp_path):
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
    entry = KnowledgeEntry(ENTRY.entry_id, '合作偏好', '愿意一起把小事写成祝福。', ENTRY.source_ref)
    text = '愿新窗接住晨光。愿你在新家自在安稳。'
    result = turn(tmp_path, RETURN, KnowledgeProvider('未说明的内容不能确定。', entry=entry), knowledge=True, entry=entry,
        also_memory=MemoryProvider('（无记忆相关内容）', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text
    assert entry.content in result.expression_text


def test_existing_two_sentence_creation_can_be_revised_and_restart(tmp_path):
    from test_recent_dialogue import DialogueProvider, open_app, submit, pairs
    class Writer(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult('愿你安稳。愿新窗接住晨光。', 'zh', 'creative')
    provider = Writer()
    original = open_app(tmp_path, provider)
    first = submit(original, RETURN)
    original.app.close()
    restarted = open_app(tmp_path, provider, saved=original)
    try:
        provider.reply = lambda request: (provider.replies.append(request) or LivingMemoryReplyResult('愿新家的窗常有暖光。', 'zh', 'creative'))
        result = submit(restarted, '第二句我想保留“窗”这个意象。')
        assert '愿新家的窗常有暖光。' in result.projection.expression_text
        assert pairs(provider.replies[-1]) == [(RETURN, first.projection.expression_text)]
    finally:
        restarted.app.close()


@pytest.mark.parametrize('message', [
    '我昨天对他说，那就给我一版明亮一点的两句祝福。',
    '那就给我一版两句祝福。算了，不用写了。',
    '你觉得“给我一版两句祝福”是什么意思？',
])
def test_version_request_does_not_bypass_permission(tmp_path, message):
    result = turn(tmp_path, message, MemoryProvider('请说明需求。', refined=LivingMemoryReplyResult('未经允许的文字。', 'zh', 'creative')))
    assert '未经允许的文字' not in result.expression_text


def test_reposted_original_can_resume_creation_without_history(tmp_path):
    text = '愿你在新家安心。愿窗边常有暖光。'
    result = turn(tmp_path, '原文是：“愿你安稳。愿薄荷常绿。”请给我写一个新版本，保留窗这个意象。',
        MemoryProvider('基础回复。', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text
    assert result.knowledge_status == 'accepted'


def test_missing_second_sentence_requests_original_without_history_disclosure(tmp_path):
    from test_recent_dialogue import DialogueProvider, open_app, submit, pairs
    class Writer(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult('捏造的第二句。', 'zh', 'creative')
    provider = Writer()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '普通话题。')
        result = submit(opened, REVISION)
        assert pairs(provider.replies[-1]) == []
        assert '完整原文' in result.projection.expression_text
        assert '捏造的第二句' not in result.projection.expression_text
    finally:
        opened.app.close()


def test_missing_sentence_recovery_survives_background_source(tmp_path):
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
    entry = KnowledgeEntry(ENTRY.entry_id, '保留意象', '喜欢保留窗边的光。', ENTRY.source_ref)
    result = turn(tmp_path, REVISION, KnowledgeProvider('资料未说明。', entry=entry), knowledge=True, entry=entry,
        also_memory=MemoryProvider('（无记忆相关内容）', refined=LivingMemoryReplyResult('捏造第二句。', 'zh', 'creative')))
    assert result.knowledge_status == 'accepted'
    assert '完整原文' in result.expression_text
    assert entry.content in result.expression_text

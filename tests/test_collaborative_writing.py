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


def test_two_creative_capabilities_deliver_one_unambiguous_draft(tmp_path):
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    from dynamic_subject_agent.knowledge import KnowledgeReplyResult
    from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
    entry = KnowledgeEntry(ENTRY.entry_id, '合作偏好', '愿意一起把小事写成祝福。', ENTRY.source_ref)
    result = turn(tmp_path, RETURN, KnowledgeProvider('基础回复。', entry=entry,
        refined=KnowledgeReplyResult('另外一份冲突稿。还有另一个句子。', 'zh', 'creative')), knowledge=True, entry=entry,
        also_memory=MemoryProvider('（无记忆相关内容）', refined=LivingMemoryReplyResult('愿你安稳。愿新窗有光。', 'zh', 'creative')))
    assert '愿你安稳。愿新窗有光。' in result.expression_text
    assert '另外一份冲突稿' not in result.expression_text
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


def test_pasted_original_supports_same_numbered_edit_request(tmp_path):
    text = '愿窗边常有暖光。'
    result = turn(tmp_path, '原文是：“愿你安稳。愿薄荷常绿。”第二句我想保留“窗”这个意象，不过不要再提薄荷。',
        MemoryProvider('基础回复。', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text


@pytest.mark.parametrize('control', ['', '不过不要再提薄荷。'])
def test_supplied_original_failure_does_not_claim_original_is_missing(tmp_path, control):
    result = turn(tmp_path, '原文是：“愿你安稳。愿薄荷常绿。”第二句我想保留“窗”这个意象。' + control,
        MemoryProvider('（无记忆相关内容）', fail=True))
    assert '没有形成新的改写版本' in result.expression_text
    assert '请贴出' not in result.expression_text
    assert '没有可以可靠使用的前文' not in result.expression_text


def test_source_background_note_is_not_a_second_creative_sentence(tmp_path):
    from test_recent_dialogue import DialogueProvider, open_app, submit
    class Writer(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            text = '愿你安稳。\n引用仅作为创作背景。' if len(self.replies) == 1 else '凭空补出第二句。'
            return LivingMemoryReplyResult(text, 'zh', 'creative')
    opened = open_app(tmp_path, Writer())
    try:
        submit(opened, RETURN)
        result = submit(opened, '第二句我想保留“窗”这个意象。')
        assert '完整原文' in result.projection.expression_text
        assert '凭空补出' not in result.projection.expression_text
    finally:
        opened.app.close()


def test_state_receipt_is_not_a_second_creative_sentence(tmp_path):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter
    from test_situated_integration import _SituatedProvider, _NoopKnowledgeProvider, _NoopRelationshipProvider
    from test_recent_dialogue import open_app, submit
    class Writer(MemoryProvider):
        def propose(self, request):
            self.evidence = '我喜欢深蓝色' if request.current_user_message.startswith('我喜欢') else ''
            return super().propose(request)
    memory = Writer('基础回复。', refined=LivingMemoryReplyResult('愿你安稳。', 'zh', 'creative'))
    knowledge, relationship, state = _NoopKnowledgeProvider(), _NoopRelationshipProvider(), _SituatedProvider()
    for provider in (knowledge, relationship, state):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    gateway = ModelGateway(SituatedProviderAdapter(provider=state, capabilities=ProviderCapabilities(
        M0_A_PROVIDER_AUTHORITY, 'test-state', True, (StructuredOutputMode.JSON_OBJECT,))))
    opened = open_app(tmp_path, memory, cognition=ControlledCompositeCognition(memory_provider=memory,
        knowledge_provider=knowledge, relationship_provider=relationship, situated_gateway=gateway))
    try:
        first = submit(opened, '我喜欢深蓝色。请写一句祝福。你现在的姿态是什么？')
        assert '愿你安稳。' in first.projection.expression_text
        assert '姿态' in first.projection.expression_text
        result = submit(opened, '第二句请改成“愿窗边常有暖光。”')
        assert '完整原文' in result.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('kind', ['creative', 'conversation'])
def test_requested_two_sentences_cannot_be_delivered_as_one(tmp_path, kind):
    text = '愿你的日子像晨光一样透亮，也像薄雾一样温柔。'
    result = turn(tmp_path, RETURN, MemoryProvider('（无记忆相关内容）',
        refined=LivingMemoryReplyResult(text, 'zh', kind)))
    assert text not in result.expression_text


@pytest.mark.parametrize('message', [
    '他刚给了我两句祝福。请给我写一句回复。',
    '这两句祝福里，第二句请改成更明亮一点的祝福。请写一个新版本。原文是：“愿你安稳。愿你快乐。”',
])
def test_mentioned_two_sentences_do_not_set_current_output_count(tmp_path, message):
    text = '愿窗边常有暖光。'
    result = turn(tmp_path, message, MemoryProvider('基础回复。', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text

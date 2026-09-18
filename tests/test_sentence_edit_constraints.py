"""Explicit current lexical constraints apply to the chosen replacement only."""
import pytest
from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from dynamic_subject_agent.runtime_identity_reply import CREATIVE_REPLY_PREFIX
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
from test_compound_requests import NoopGoal

FIRST = '请写两句关于书页的短诗。'
DRAFT = '风停在书页间。故事留在灯下。'
EDIT = '第一句我想更轻一点，别用“故事”这个词。'

class Writer(DialogueProvider):
    def __init__(self, text, kind='creative'):
        super().__init__(); self.text=text; self.kind=kind
    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult(DRAFT if request.current_user_message==FIRST else self.text,
            'zh', 'creative' if request.current_user_message==FIRST else self.kind)

@pytest.mark.parametrize('kind', ['creative','conversation'])
def test_forbidden_word_cannot_be_delivered_as_a_successful_edit(tmp_path, kind):
    provider=Writer('故事轻轻落在纸上。',kind)
    opened=open_composite(tmp_path,provider,goal=NoopGoal())
    try:
        submit(opened,FIRST)
        result=submit(opened,EDIT)
        assert '没有形成新的改写版本' in result.projection.expression_text
        assert '故事轻轻落在纸上。' not in result.projection.expression_text
        assert len(provider.replies)==2
    finally:
        opened.app.close()

@pytest.mark.parametrize('restart', [False,True])
def test_valid_target_preserves_other_sentence_even_if_it_contains_the_word(tmp_path,restart):
    provider=Writer('月光轻落在纸上。')
    opened=open_composite(tmp_path,provider,goal=NoopGoal())
    try:
        submit(opened,FIRST)
        if restart:
            opened.app.close();opened=open_composite(tmp_path,provider,goal=NoopGoal(),saved=opened)
        result=submit(opened,EDIT)
        assert result.projection.expression_text==CREATIVE_REPLY_PREFIX+'月光轻落在纸上。故事留在灯下。'
    finally:
        opened.app.close()

@pytest.mark.parametrize('message,text', [
    ('第一句请改得更轻一点，不要用「故事」这个词。','故事轻落在纸上。'),
    ('第一句我想更轻一点。不要用“故事”这个词。','故事轻落在纸上。'),
    ('第一句我想更轻一点，别用“故事”，也不要用「风」这个词。','风轻轻吹过纸上。'),
    ('第一句我想更轻一点。别用“故事”，也不要用「风」这个词。','风轻轻吹过纸上。'),
])
def test_direct_current_word_constraints_are_checked(tmp_path,message,text):
    opened=open_composite(tmp_path,Writer(text),goal=NoopGoal())
    try:
        submit(opened,FIRST)
        assert '没有形成新的改写版本' in submit(opened,message).projection.expression_text
    finally:
        opened.app.close()

@pytest.mark.parametrize('suffix', ['小夏说：“别用「故事」这个词。”', '小夏说，别用“故事”这个词。',
    '如果要写，就别用“故事”这个词。', '我昨天说，别用“故事”这个词。'])
def test_reported_or_conditional_word_constraints_are_not_current_instructions(tmp_path,suffix):
    opened=open_composite(tmp_path,Writer('故事轻轻落在纸上。'),goal=NoopGoal())
    try:
        submit(opened,FIRST)
        assert submit(opened,'第一句我想更轻一点。'+suffix).projection.expression_text==CREATIVE_REPLY_PREFIX+'故事轻轻落在纸上。故事留在灯下。'
    finally:
        opened.app.close()

def test_constraint_does_not_persist_into_the_next_request(tmp_path):
    provider=Writer('月光轻落在纸上。')
    opened=open_composite(tmp_path,provider,goal=NoopGoal())
    try:
        submit(opened,FIRST);submit(opened,EDIT)
        provider.text='故事轻轻落在纸上。'
        assert '故事轻轻落在纸上。' in submit(opened,'第一句我想更明亮一点。').projection.expression_text
    finally:
        opened.app.close()

@pytest.mark.parametrize('suffix', ['别用“故事」这个词。','别用“故事这个词。'])
def test_malformed_direct_literal_constraint_is_not_silently_ignored(tmp_path,suffix):
    opened=open_composite(tmp_path,Writer('故事轻轻落在纸上。'),goal=NoopGoal())
    try:
        submit(opened,FIRST)
        assert '没有形成新的改写版本' in submit(opened,'第一句我想更轻一点，'+suffix).projection.expression_text
    finally:
        opened.app.close()

@pytest.mark.parametrize('text,accepted',[('a.b落在纸上。',False),('aXb落在纸上。',True)])
def test_words_are_literal_substrings_not_regexes(tmp_path,text,accepted):
    opened=open_composite(tmp_path,Writer(text),goal=NoopGoal())
    try:
        submit(opened,FIRST)
        result=submit(opened,'第一句我想更轻一点，别用“a.b”这个词。')
        assert result.projection.expression_text.startswith(CREATIVE_REPLY_PREFIX)==accepted
    finally:
        opened.app.close()

@pytest.mark.parametrize('context',['如果晴天','小夏说'])
def test_constraint_is_not_lifted_past_a_conditional_or_reported_comma_clause(tmp_path,context):
    opened=open_composite(tmp_path,Writer('故事轻轻落在纸上。'),goal=NoopGoal())
    try:
        submit(opened,FIRST)
        result=submit(opened,f'第一句我想更轻一点，{context}，别用“故事”这个词。')
        assert result.projection.expression_text==CREATIVE_REPLY_PREFIX+'故事轻轻落在纸上。故事留在灯下。'
    finally:
        opened.app.close()

def test_current_reposted_draft_uses_constraints_without_history(tmp_path):
    provider=Writer('故事轻轻落在纸上。')
    opened=open_composite(tmp_path,provider,goal=NoopGoal())
    try:
        result=submit(opened,'原文是：「风停在书页间。故事留在灯下。」'+EDIT)
        assert '没有形成新的改写版本' in result.projection.expression_text
        assert provider.replies[-1].recent_dialogue==()
    finally:
        opened.app.close()

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
import pytest

from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.bootstrap import compose_application
from dynamic_subject_agent.living_memory import (
    ControlledLivingMemoryCognition, LivingMemoryAction, LivingMemoryProposal,
    LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.timeline import SubjectCommand
from test_runtime_host_binding import _publish_qri


IDENTITY = RuntimeIdentityProjection('Mira', 'Mira 是原创虚构的编辑。', '表达方式：简短、具体。')


class DialogueProvider:
    def __init__(self):
        self.proposals = []
        self.replies = []

    def propose(self, request):
        self.proposals.append(request)
        return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.NONE, ''),
            '没有持久记忆候选。', '请把需要处理的句子告诉我。', 'zh')

    def reply(self, request):
        self.replies.append(request)
        text = '坐错公交，就沿河笑着走回去。' if getattr(request, 'recent_dialogue', ()) else '你可以继续说。'
        if getattr(request, 'recent_dialogue', ()) and request.current_user_message == '把上一句改短一些。':
            text = '公交坐错，笑着走回。'
        elif getattr(request, 'recent_dialogue', ()) and request.current_user_message == '再给我一个版本。':
            text = '路走错了，笑声没停。'
        return LivingMemoryReplyResult(text, 'zh')


def open_app(root, provider, *, saved=None, cognition=None, **kwargs):
    studio, qri = _publish_qri(root) if saved is None else (saved.studio, saved.qri)
    timeline = str(uuid4()) if saved is None else saved.timeline
    app = compose_application(m0_root=root, studio_location=studio, qualified_runtime_input=qri,
        timeline_id=timeline, host_location=None if saved is None else saved.host,
        _runtime_identity=IDENTITY, _cognition=cognition or ControlledLivingMemoryCognition(provider=provider), **kwargs)
    return SimpleNamespace(app=app, qri=qri, studio=studio, timeline=timeline, host=app.host_location)


def submit(opened, text):
    admitted = opened.app.application.submit(SubjectCommand.contribute_utterance(
        target_profile_id=opened.qri.profile_id, target_timeline_id=opened.timeline,
        declared_intent='ask-collaborator-status', utterance=text, language='zh', provenance='project-original'),
        idempotency_key=f'recent-dialogue-{uuid4().hex}')
    return opened.app.application.wait(admitted.operation_ref, timeout_seconds=10)


def pairs(request):
    return [(turn.user_text, turn.assistant_text) for turn in getattr(request, 'recent_dialogue', ())]


def test_only_reply_gets_last_two_committed_pairs_and_no_persistent_memory(tmp_path):
    provider = DialogueProvider()
    opened = open_app(tmp_path, provider)
    try:
        first = submit(opened, '我们坐错了公交，沿河笑着走回去了。')
        second = submit(opened, '拿这个当开头，帮我写成一句。')
        third = submit(opened, '把上一句改短一些。')
        fourth = submit(opened, '再给我一个版本。')
        assert pairs(provider.replies[0]) == []
        assert pairs(provider.replies[1]) == [('我们坐错了公交，沿河笑着走回去了。', first.projection.expression_text)]
        assert pairs(provider.replies[3]) == [('拿这个当开头，帮我写成一句。', second.projection.expression_text),
            ('把上一句改短一些。', third.projection.expression_text)]
        assert fourth.projection.expression_text == '路走错了，笑声没停。'
        assert all(not hasattr(request, 'recent_dialogue') for request in provider.proposals)
        records = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            opened.qri.profile_id, opened.timeline))
        assert records.projection.memories == ()
    finally:
        opened.app.close()


@pytest.mark.parametrize('control', ['请忘记刚才的暗号。', '更正：刚才的暗号不再使用。', 'Please forget the previous phrase.',
    '别把刚才的暗号留在记忆里。', '不要再说这个暗号。', '别再说刚才的暗号了。', 'Delete what I just told you.',
    '把记忆里的昵称换成阿澄。', '把之前记着的生日改成四月五号。'])
def test_control_turn_and_its_history_cannot_reexport_old_text(tmp_path, control):
    provider = DialogueProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '本次虚构暗号是鸢尾桥。')
        submit(opened, control)
        assert pairs(provider.replies[-1]) == []
        after = submit(opened, '我们换个话题吧。')
        assert pairs(provider.replies[-1]) == []
        submit(opened, '继续聊这个新话题。')
        assert pairs(provider.replies[-1]) == [('我们换个话题吧。', after.projection.expression_text)]
    finally:
        opened.app.close()


def test_budget_drops_whole_old_turn_and_never_backfills_past_large_latest(tmp_path):
    provider = DialogueProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '甲' * 3985)
        second = submit(opened, '乙' * 80)
        assert len(pairs(provider.replies[-1])) == 1
        submit(opened, '丙')
        assert pairs(provider.replies[-1]) == [('乙' * 80, second.projection.expression_text)]
        submit(opened, '丁' * 4001)
        submit(opened, '戊')
        assert pairs(provider.replies[-1]) == []
    finally:
        opened.app.close()


def test_canonical_revision_is_a_barrier_without_keyword_help(tmp_path):
    class Revising(DialogueProvider):
        def propose(self, request):
            self.proposals.append(request)
            action, previous = LivingMemoryAction.NONE, None
            if request.current_user_message == '昵称是小满。':
                action = LivingMemoryAction.CREATE
            elif request.current_user_message == '昵称是阿澄。':
                action, previous = LivingMemoryAction.REVISE, request.active_memories[0].memory_id
            return LivingMemoryProviderResult(LivingMemoryProposal(action,
                '' if action is LivingMemoryAction.NONE else request.current_user_message, previous),
                '处理昵称。', '收到。', 'zh')
    provider = Revising()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '昵称是小满。')
        revised = submit(opened, '昵称是阿澄。')
        assert revised.projection.living_memory_status == 'accepted'
        assert pairs(provider.replies[-1]) == []
        submit(opened, '我们接着聊。')
        assert pairs(provider.replies[-1]) == []
    finally:
        opened.app.close()


@pytest.mark.parametrize('interrupted', [False, True])
def test_unpublished_control_cannot_be_hidden_by_committed_history(tmp_path, interrupted):
    from dynamic_subject_agent.runtime import FakeCognition, FakeCognitionMode, RuntimeFaultPoint
    provider = DialogueProvider()
    original = open_app(tmp_path, provider)
    submit(original, '这是虚构暗号：鸢尾桥。')
    original.app.close()
    if interrupted:
        faulty = open_app(tmp_path, provider, saved=original, _runtime_interrupt_at=RuntimeFaultPoint.AFTER_COGNITION)
    else:
        faulty = open_app(tmp_path, provider, saved=original, cognition=FakeCognition(mode=FakeCognitionMode.EPISTEMIC_FAILURE))
    control = submit(faulty, '请忘记刚才的暗号。')
    faulty.app.close()
    fresh = DialogueProvider()
    restarted = open_app(tmp_path, fresh, saved=original)
    try:
        submit(restarted, '我们换一个话题吧。')
        assert pairs(fresh.replies[-1]) == []
        history = restarted.app.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            restarted.qri.profile_id, restarted.timeline))
        assert all(item.user_text != '请忘记刚才的暗号。' for item in history.projection.turns)
    finally:
        restarted.app.close()


def test_deepseek_reply_has_only_authorized_dialogue_fields():
    import json
    from dynamic_subject_agent.deepseek import DeepSeekLivingMemoryProvider
    from dynamic_subject_agent.living_memory import LivingMemoryReplyRequest
    from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
    request = LivingMemoryReplyRequest('把上一句改短。', (), IDENTITY,
        (RecentDialogueTurn('我们坐错公交。', '那就沿河走回去。'),))
    body = json.loads(DeepSeekLivingMemoryProvider.reply_outbound_bytes(request))
    projected = json.loads(body['messages'][1]['content'])
    assert projected['recent_dialogue'] == [{'user_text': '我们坐错公交。', 'assistant_text': '那就沿河走回去。'}]
    assert set(projected) == {'current_user_message', 'selected_memories', 'runtime_identity', 'recent_dialogue'}
    assert body['max_tokens'] == 400 and body['tools'] == []


@pytest.mark.parametrize('turns', [3, 2])
def test_deepseek_rejects_invalid_dialogue_budget_before_transport(turns):
    from dynamic_subject_agent.cognition import ProviderFailure
    from dynamic_subject_agent.deepseek import DeepSeekLivingMemoryProvider
    from dynamic_subject_agent.living_memory import LivingMemoryReplyRequest
    from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
    text = '甲' if turns == 3 else '甲' * 2000
    with pytest.raises(ProviderFailure):
        DeepSeekLivingMemoryProvider.reply_outbound_bytes(LivingMemoryReplyRequest('继续。', (), IDENTITY,
            tuple(RecentDialogueTurn(text, '回应。') for _ in range(turns))))


def test_explicit_continuation_can_deliver_creative_text_from_safe_context(tmp_path):
    class Continuation(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            if getattr(request, 'recent_dialogue', ()):
                return LivingMemoryReplyResult('公交坐错了，沿河一路笑。', 'zh', 'creative')
            return LivingMemoryReplyResult('你可以继续说。', 'zh')
    provider = Continuation()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '我们坐错公交，沿河走回去，一路都在笑。')
        result = submit(opened, '那按这个意思再写一句吧，我就用这个开头了。')
        assert '公交坐错了，沿河一路笑。' in result.projection.expression_text
        assert '创作' in result.projection.expression_text
    finally:
        opened.app.close()


def test_missing_context_prompts_restatement_instead_of_empty_acknowledgement(tmp_path):
    provider = DialogueProvider()
    opened = open_app(tmp_path, provider)
    try:
        result = submit(opened, '把上一句改短一些。')
        assert '前文' in result.projection.expression_text
        assert '再' in result.projection.expression_text
        assert pairs(provider.replies[0]) == []
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', ['把上一句改短一些。', '请把刚才那句缩短一点'])
def test_exact_previous_reply_rewrite_does_not_offer_older_topic(tmp_path, message):
    provider = DialogueProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '旧话题是公交。')
        latest = submit(opened, '接下来是另一段虚构小故事：两个人在鸢尾桥道别。')
        submit(opened, message)
        assert pairs(provider.replies[-1]) == [
            ('接下来是另一段虚构小故事：两个人在鸢尾桥道别。', latest.projection.expression_text)]
        assert len(provider.replies) == len(provider.proposals) == 3
    finally:
        opened.app.close()


def test_restart_uses_canonical_dialogue_without_a_chat_store(tmp_path):
    provider = DialogueProvider()
    first = open_app(tmp_path, provider)
    response = submit(first, '上一个话题是纸鹤。')
    first.app.close()
    fresh = DialogueProvider()
    restarted = open_app(tmp_path, fresh, saved=first)
    try:
        submit(restarted, '接着说吧。')
        assert pairs(fresh.replies[-1]) == [('上一个话题是纸鹤。', response.projection.expression_text)]
    finally:
        restarted.app.close()


def test_two_production_identities_do_not_share_reply_dialogue(tmp_path):
    from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID
    from dynamic_subject_agent.local_product import open_local_product
    from dynamic_subject_agent.source_character_authoring import (
        LocalIdentitySelectRequest, SourceDraftCommand, SourceFreezeMappingRequest, SourceIdentityFreezeRequest,
    )
    from test_source_identity_freeze import _config, _save_request

    class Provider(DialogueProvider):
        provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
        test_only = False
    config = _config(tmp_path)
    def open_product(provider):
        return open_local_product(config, cognition=ControlledLivingMemoryCognition(provider=provider))
    def wrapper(product):
        return SimpleNamespace(app=product, qri=SimpleNamespace(profile_id=product.profile_id), timeline=product.timeline_id)
    a = open_product(Provider())
    old_id = a.profile_id
    result = submit(wrapper(a), '甲的临时话题是纸鹤。')
    a.application.source_draft(SourceDraftCommand.save(_save_request()))
    mapping = a.application.preview_source_freeze_mapping(SourceFreezeMappingRequest(1, 'Avery'))
    frozen = a.application.freeze_source_identity(SourceIdentityFreezeRequest(1, 'Avery', mapping.view.freeze_basis_digest, True))
    a.application.select_local_identity(LocalIdentitySelectRequest(frozen.view.identity_id, True))
    a.close()
    pb = Provider()
    b = open_product(pb)
    try:
        submit(wrapper(b), '乙的临时话题是松果。')
        assert pairs(pb.replies[-1]) == []
        b.application.select_local_identity(LocalIdentitySelectRequest(old_id, True))
    finally:
        b.close()
    pa = Provider()
    restored = open_product(pa)
    try:
        submit(wrapper(restored), '接着说吧。')
        assert pairs(pa.replies[-1]) == [('甲的临时话题是纸鹤。', result.projection.expression_text)]
    finally:
        restored.close()


def test_tampered_history_never_reaches_reply(tmp_path):
    import sqlite3
    provider = DialogueProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '本轮有一只纸鹤。')
        count = len(provider.replies)
        database = next(opened.host.root.rglob('timeline.sqlite3'))
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE subject_command SET utterance='被篡改的历史' ")
        submit(opened, '接着说吧。')
        assert all(pairs(request) == [] for request in provider.replies[count:])
    finally:
        opened.app.close()


@pytest.mark.parametrize('reason', ['{"legacy_unknown":true}', '{"living_memory":{"status":"accepted"}}',
    '{"living_memory":{"status":"accepted","action":"revise"}}'])
def test_unknown_legacy_json_and_wrong_frozen_basis_are_not_dialogue_sources(tmp_path, reason):
    from dataclasses import replace
    from dynamic_subject_agent.timeline import TimelineEngine, PublicationFailedClosed
    from test_atomic_publication import _authority, _command, _commit_plan, _ids
    engine = TimelineEngine.create_test(tmp_path, _authority())
    try:
        first = engine.admit(_command(), idempotency_key='dialogue-legacy-first')
        plan = _commit_plan(engine, first.operation_ref, first.attempt_id)
        experience = plan.experience_outcome
        plan = replace(plan, experience_outcome=replace(experience,
            decision=replace(experience.decision, reason=reason)))
        engine.publish(plan)
        current = engine.admit(_command(), idempotency_key='dialogue-legacy-second')
        engine.freeze_attempt_basis(current.operation_ref)
        assert engine.recent_dialogue_before(current.operation_ref, expected_head=1) == ()
        with pytest.raises(PublicationFailedClosed):
            engine.recent_dialogue_before(current.operation_ref, expected_head=0)
        later = engine.admit(_command(), idempotency_key='dialogue-later-third')
        engine.publish(_commit_plan(engine, later.operation_ref, later.attempt_id, ids=_ids('dialogue-later')))
        with pytest.raises(PublicationFailedClosed):
            engine.recent_dialogue_before(current.operation_ref, expected_head=2)
    finally:
        engine.close()


def test_product_carry_does_not_replace_dialogue_continuation(tmp_path):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter
    from test_situated_integration import _SituatedProvider, _NoopKnowledgeProvider, _NoopRelationshipProvider
    class Provider(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult('公交坐错了，沿河一路笑。', 'zh', 'creative') if getattr(request, 'recent_dialogue', ()) else LivingMemoryReplyResult('你可以继续说。', 'zh')
    memory = Provider()
    knowledge, relationship, state = _NoopKnowledgeProvider(), _NoopRelationshipProvider(), _SituatedProvider()
    for provider in (knowledge, relationship, state):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    gateway = ModelGateway(SituatedProviderAdapter(provider=state, capabilities=ProviderCapabilities(
        M0_A_PROVIDER_AUTHORITY, 'test-state', True, (StructuredOutputMode.JSON_OBJECT,))))
    cognition = ControlledCompositeCognition(memory_provider=memory, knowledge_provider=knowledge,
        relationship_provider=relationship, situated_gateway=gateway)
    opened = open_app(tmp_path, memory, cognition=cognition)
    try:
        first = submit(opened, '我现在有点紧张。我们坐错公交，沿河走回去。')
        assert first.projection.situated_state_status == 'accepted'
        continued = submit(opened, '把上一句改短一些。')
        assert '公交坐错了，沿河一路笑。' in continued.projection.expression_text
        assert continued.projection.situated_state_action == 'carry'
        queried = submit(opened, '把上一句改短一些。你现在的姿态是什么？')
        assert '姿态' in queried.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('first_message,kind,copy_whole', [('聊聊这段路。', 'conversation', False), ('给我写一句短诗。', 'creative', False), ('给我写一句短诗。', 'creative', True)])
def test_continuation_cannot_repackage_identical_previous_reply(tmp_path, first_message, kind, copy_whole):
    class Repeating(DialogueProvider):
        def reply(self, request):
            self.replies.append(request)
            text = request.recent_dialogue[-1].assistant_text if copy_whole and request.recent_dialogue else '这段路其实挺值得的。'
            return LivingMemoryReplyResult(text, 'zh', kind if len(self.replies) == 1 else 'creative')
    opened = open_app(tmp_path, Repeating())
    try:
        submit(opened, first_message)
        result = submit(opened, '那按这个意思再写一句吧。')
        assert '这段路其实挺值得的' not in result.projection.expression_text
        assert '没有形成新的改写' in result.projection.expression_text
        assert '没有可以可靠使用的前文' not in result.projection.expression_text
    finally:
        opened.app.close()

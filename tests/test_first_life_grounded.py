"""Synthetic source attribution and reversible v3 integration; no real calls."""
from dataclasses import asdict, replace
import json

import pytest

from dynamic_subject_agent import first_life_grounded as grounded
from dynamic_subject_agent import first_life_relevance as v2
from dynamic_subject_agent.first_life_grounded_provider import DeepSeekFirstLifeGroundedAdapter
from dynamic_subject_agent.first_life_relevance_provider import DeepSeekFirstLifeRelevanceAdapter
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.first_life_authorization import ShareAuthorization, ShareAuthorizationChanged
from dynamic_subject_agent.first_life import FirstLifeSimulationRequest, FirstLifeHeartbeatRequest
from dynamic_subject_agent.first_life_projection import life_model_projection
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from test_first_life_relevance_projection import relevance_fixture
from test_first_life_relevance_compat import RelevanceTransport
from test_first_life_facade import life_fixture, settle, approved, model_fixture, personality_fixture
from test_reviewed_character_chat import send


def choice(**patch):
    return {**dict(action="answer", fact_refs=[], use_life=False, focus="respond-current", dialogue_refs=[]), **patch}


def test_planning_sources_are_complete_exact_pairs_and_expression_copies_only_selected_attribution(relevance_fixture):
    envelope, identity, basis, _, _ = relevance_fixture
    dialogue = CharacterDialogueBasis("available", True, (
        RecentDialogueTurn("我喜欢纸风。", "那张图的眼睛和嘴角有配合。"),
        RecentDialogueTurn("你为什么这么说？", "刚才没有具体图片，不能这样画评。")))
    planning, _ = grounded.life_chat_planning(envelope, identity, "是我说过眼睛吗？", dialogue, True, basis)
    assert planning.dialogue_sources == (
        grounded.DialogueSource("U1", "user", dialogue.recent_dialogue[0].user_text),
        grounded.DialogueSource("A1", "assistant", dialogue.recent_dialogue[0].assistant_text),
        grounded.DialogueSource("U2", "user", dialogue.recent_dialogue[1].user_text),
        grounded.DialogueSource("A2", "assistant", dialogue.recent_dialogue[1].assistant_text))
    expression, _ = grounded.life_chat_expression(planning, choice(dialogue_refs=["A1", "U1"]))
    assert expression.selected_dialogue == (planning.dialogue_sources[1], planning.dialogue_sources[0])
    assert not hasattr(planning, "recent_dialogue") and not hasattr(expression, "recent_dialogue")
    assert not hasattr(expression, "dialogue_sources")
    wire = json.loads(DeepSeekFirstLifeGroundedAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, expression)))
    payload = json.loads(wire["messages"][1]["content"])
    assert payload["selected_dialogue"] == [asdict(row) for row in expression.selected_dialogue]
    assert dialogue.recent_dialogue[1].user_text not in canonical_json(payload)
    assert "二者均不证明世界事实" in wire["messages"][0]["content"]
    assert "不能解释第一次为什么" in wire["messages"][0]["content"]


@pytest.mark.parametrize("refs", [["U9"], ["U1", "U1"], ["U1", "A1", "U2"], [dict(label="U1")]])
def test_unknown_duplicate_unbounded_or_embedded_source_references_rejected(relevance_fixture, refs):
    envelope, identity, basis, dialogue, _ = relevance_fixture
    planning, _ = grounded.life_chat_planning(envelope, identity, "接着说。", dialogue, True, basis)
    with pytest.raises(ValueError): grounded.life_chat_expression(planning, choice(dialogue_refs=refs))


def test_encounter_cannot_select_recent_dialogue_and_no_selection_is_valid(relevance_fixture):
    envelope, identity, basis, dialogue, _ = relevance_fixture
    planning, _ = grounded.life_chat_planning(envelope, identity, "你最初怎么认识我，为何回复？", dialogue, True, basis)
    with pytest.raises(ValueError): grounded.life_chat_expression(planning, choice(focus="explain-encounter", dialogue_refs=["U1"]))
    expression, _ = grounded.life_chat_expression(planning, choice(focus="explain-encounter"))
    assert expression.selected_dialogue == () and expression.focus == "explain-encounter"
    assert "系统推荐" in "".join(expression.conversation.encounter)
    forged = replace(expression, selected_dialogue=(planning.dialogue_sources[0],))
    with pytest.raises(ValueError): DeepSeekFirstLifeGroundedAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, forged))


def test_history_off_has_no_sources_and_no_semantic_amnesia(relevance_fixture):
    envelope, identity, basis, _, _ = relevance_fixture
    planning, _ = grounded.life_chat_planning(envelope, identity, "继续。", CharacterDialogueBasis("available", True), False, basis)
    expression, _ = grounded.life_chat_expression(planning, choice())
    assert planning.dialogue_sources == () and expression.selected_dialogue == ()
    assert not expression.history_enabled and expression.has_prior_committed_exchange
    with pytest.raises(ValueError): grounded.life_chat_expression(planning, choice(dialogue_refs=["A1"]))
    forged = replace(planning, dialogue_sources=(grounded.DialogueSource("U1", "user", "旧话"), grounded.DialogueSource("A1", "assistant", "旧回复")))
    with pytest.raises(ValueError): DeepSeekFirstLifeGroundedAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, forged))


def test_complete_two_turn_source_boundary_4000_without_duplicate_window(relevance_fixture):
    envelope, identity, basis, _, _ = relevance_fixture
    dialogue = CharacterDialogueBasis("available", True, (RecentDialogueTurn("U" * 1000, "A" * 1000),) * 2)
    planning, _ = grounded.life_chat_planning(envelope, identity, "当前话。", dialogue, True, basis)
    assert sum(len(row.text) for row in planning.dialogue_sources) == 4000
    payload = json.loads(json.loads(DeepSeekFirstLifeGroundedAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning)))["messages"][1]["content"])
    assert "recent_dialogue" not in payload and len(payload["dialogue_sources"]) == 4
    bad = replace(dialogue, recent_dialogue=(RecentDialogueTurn("U" * 1001, "A" * 1000),) * 2)
    with pytest.raises(ValueError): grounded.life_chat_planning(envelope, identity, "当前话。", bad, True, basis)
    with pytest.raises(ValueError): grounded._validate_sources((grounded.DialogueSource("A1", "user", "wrong attribution"),), True, selected=True)


def test_text_only_appreciation_has_same_fact_knowledge_and_no_assumed_image(relevance_fixture):
    envelope, identity, basis, dialogue, _ = relevance_fixture
    planning, _ = grounded.life_chat_planning(envelope, identity, "我喜欢纸风的作品。", dialogue, True, basis)
    expression, _ = grounded.life_chat_expression(planning, choice(focus="appreciate-work", fact_refs=["F3"]))
    assert expression.conversation.selected_facts == (planning.conversation.self_knowledge[2],)
    wire = json.loads(DeepSeekFirstLifeGroundedAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, expression)))
    assert "当前输入仅有文字，没有看见图片" in wire["messages"][0]["content"]
    assert "未提供具体图或明确描述" in wire["messages"][0]["content"]
    assert "不按笔名强制害羞、否认" in wire["messages"][0]["content"]


@pytest.mark.parametrize("message", ["我喜欢纸风的作品。", "我喜欢纸风那幅眯眼微笑、右下角有蓝色小花的画。"])
def test_text_description_is_preserved_as_user_report_and_room_source_remains_unknown(relevance_fixture, message):
    envelope, identity, basis, dialogue, _ = relevance_fixture
    planning, _ = grounded.life_chat_planning(envelope, identity, message, dialogue, True, basis)
    expression, _ = grounded.life_chat_expression(planning, choice(focus="appreciate-work"))
    assert expression.conversation.current_message == message
    assert expression.conversation.selected_facts == ()
    wire = json.loads(DeepSeekFirstLifeGroundedAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, expression)))
    policy = wire["messages"][0]["content"]
    assert "明确用文字描述的细节可以作为其描述承接或讨论" in policy
    assert "不补造未描述细节" in policy
    assert "不能据此声称没有参考房间或不是照着房间画" in policy


def test_v3_share_and_decision_wire_delegate_exact_old_bytes_and_v2_rejects_v3_chat(relevance_fixture):
    envelope, identity, basis, dialogue, event = relevance_fixture
    for task in (ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE, v2.share_model_projection(envelope, identity, basis, dialogue, True, event)),
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION, life_model_projection(envelope, identity, basis))):
        assert DeepSeekFirstLifeGroundedAdapter.wire(task) == DeepSeekFirstLifeRelevanceAdapter.wire(task)
    planning, _ = grounded.life_chat_planning(envelope, identity, "说点别的。", dialogue, True, basis)
    with pytest.raises(ValueError): DeepSeekFirstLifeRelevanceAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning))
    v3scope = grounded.first_life_scope(envelope["definition_basis"])
    v2scope = v2.first_life_scope(envelope["definition_basis"])
    assert v3scope["life_policy_sha"] == v2scope["life_policy_sha"] and v3scope["share_policy_sha"] == v2scope["share_policy_sha"]
    assert v3scope["life_chat_policy_sha"] != v2scope["life_chat_policy_sha"]


class GroundedTransport(RelevanceTransport):
    def post_json(self, **kwargs):
        response = super().post_json(**kwargs)
        _, projection = self.calls[-1]
        if "dialogue_sources" not in projection:
            return response
        outer = json.loads(response.body)
        value = json.loads(outer["choices"][0]["message"]["content"])
        value["dialogue_refs"] = ["A1"] if projection["dialogue_sources"] else []
        outer["choices"][0]["message"]["content"] = canonical_json(value)
        return DeepSeekHttpResponse(200, canonical_json(outer).encode())


def open_version(opening, transport, view, version):
    transport.__class__ = GroundedTransport
    digest = grounded.first_life_scope_digest(view.definition_basis) if version == grounded.GROUNDED_VERSION else v2.first_life_scope_digest(view.definition_basis)
    return opening(runtime_policy=version, runtime_policy_digest=digest)


def test_v2_v3_restart_v2_preserves_identity_transcript_scope_and_call_count(life_fixture):
    opening, transport, _, config, view = life_fixture
    v2product = open_version(opening, transport, view, v2.RELEVANCE_VERSION)
    assert send(v2product, "合成开场聊画面。", "grounded-v2-first").status == "terminal"
    original = (v2product.profile_id, v2product.timeline_id, v2product.publication_key)
    before = json.loads(config.state_path.read_text())
    v2product.close()
    v3product = open_version(opening, transport, view, grounded.GROUNDED_VERSION)
    assert (v3product.profile_id, v3product.timeline_id, v3product.publication_key) == original
    assert send(v3product, "你刚才说过什么？", "grounded-v3-second").status == "terminal"
    assert transport.calls[-1][1]["selected_dialogue"][0]["speaker"] == "assistant"
    assert len(transport.calls) == 4
    v3product.close()
    restored = opening()
    assert LocalIdentityAuthority(config).first_life_runtime_policy(original[0]) == grounded.GROUNDED_VERSION
    assert restored.timeline_id == original[1]
    restored.close()
    rollback = open_version(opening, transport, view, v2.RELEVANCE_VERSION)
    assert send(rollback, "回到旧交流策略。", "grounded-v2-rollback").status == "terminal"
    assert len(transport.calls) == 6 and len(transport.calls[-2][1]["recent_dialogue"]) == 2
    after = json.loads(config.state_path.read_text())
    first = next(row for row in before["identities"] if row["identity_id"] == original[0])
    last = next(row for row in after["identities"] if row["identity_id"] == original[0])
    for key in ("publication_key", "life_scope_digest", "life_identity_basis", "freeze_basis_digest", "timeline_id"):
        assert first[key] == last[key]
    assert last["life_runtime_policy"]["revision"] == 3


def test_v3_share_authorization_uses_existing_history_guard_and_v2_share_wire(life_fixture):
    opening, transport, _, config, view = life_fixture
    product = open_version(opening, transport, view, grounded.GROUNDED_VERSION)
    app = product.application
    assert send(product, "合成共同话题。", "grounded-share-initial").status == "terminal"
    authority = LocalIdentityAuthority(config)
    token = authority.first_life_share_authorization(product.profile_id)
    assert type(token) is ShareAuthorization and token.runtime_policy == grounded.GROUNDED_VERSION
    assert app.set_reviewed_character_history(False).status == "active"
    with pytest.raises(ShareAuthorizationChanged):
        with authority.first_life_share_guard(token): pass
    assert settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest("grounded-life-step"))).status == "terminal"
    result = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest("grounded-share-session", "grounded-share-trigger")))
    assert result.status == "terminal"
    assert transport.calls[-1][1]["recent_dialogue"] == [] and not transport.calls[-1][1]["history_enabled"]
    assert "dialogue_sources" not in transport.calls[-1][1]
    assert len(app.query_first_life().shares) == 1

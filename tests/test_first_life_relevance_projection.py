"""Synthetic v2 projection behavior; no real source, credentials or Provider."""
from dataclasses import asdict, replace
import json

import pytest

from dynamic_subject_agent import first_life as legacy
from dynamic_subject_agent import first_life_relevance as relevance
from dynamic_subject_agent.first_life_projection import life_model_projection
from dynamic_subject_agent.first_life_provider import DeepSeekFirstLifeAdapter
from dynamic_subject_agent.first_life_relevance_provider import DeepSeekFirstLifeRelevanceAdapter
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn


@pytest.fixture
def relevance_fixture():
    eligible = [dict(item_id="private-claim", dimension="identity", kind="fact", statement="我是虚构画手小林。",
        event_time="before", knowledge_time="before", derivation="direct"),
        dict(item_id="private-limit", dimension="skill", kind="belief", statement="我相信自己还画不好复杂的车辆，简单外形可以试试。",
        event_time="before", knowledge_time="before", derivation="linked-evidence"),
        dict(item_id="private-work", dimension="identity", kind="fact", statement="我以纸风笔名发表过插画，但尚未在这个渠道公开笔名关联。",
        event_time="before", knowledge_time="before", derivation="direct")]
    envelope = dict(definition_basis="a" * 64, runtime_asset_sha="b" * 64,
        source_declaration=dict(reviewed_digest="c" * 64), runtime_asset=dict(subject=dict(subject_id="private-subject", name="小林"),
        anchor=dict(anchor_id="private-anchor"), initial_stage="起点展览之前", eligible=eligible, chat_organization=None,
        personality=[dict(title="关注作品", interpretation="可以对具体作品交流投入。", when="对方具体谈到作品。",
            choice="可以表达在意而不公开作者关联。", expression="简单回应对方。", limits="不强制害羞，不编造当前情绪。")]))
    first = legacy.CompositionPlan("小兔", "主体靠左，旁边一盏灯", "耳朵轮廓")
    second = replace(first, composition="主体居中，灯旁留白")
    diffs = (legacy.LifeFieldDiff("composition", first.composition, second.composition),)
    versions = (legacy.LifeVersion(1, first, "emphasize-subject", (legacy.LifeFieldDiff("subject", "", first.subject),), 1),
        legacy.LifeVersion(2, second, "balance-space", diffs, 2))
    event = legacy.LifeEvent("private-event", 2, "revise", "系统已保存v2；机械回执", 2, "balance-space")
    record = legacy.LifeRecord("advance", "revised", 2, second, "balance-space", diffs, event.event_id,
        event.summary, 2, False, True, False)
    basis = legacy.FirstLifeBasis(record, (event,), versions, (), True, False, (), 2)
    identity = RuntimeIdentityProjection("小林", "虚构画手", "起点展览之前")
    dialogue = CharacterDialogueBasis("available", True, (RecentDialogueTurn("我喜欢留白清楚的画面。", "留白会让轮廓更清楚。"),))
    return envelope, identity, basis, dialogue, event


def test_focus_is_adjudicated_and_only_selected_full_facts_become_speaking_material(relevance_fixture):
    envelope, identity, basis, dialogue, _ = relevance_fixture
    planning, _ = relevance.life_chat_planning(envelope, identity, "你画复杂车辆也很熟练？", dialogue, True, basis)
    expression, used = relevance.life_chat_expression(planning,
        dict(action="answer", fact_refs=["F2"], use_life=False, focus="explain-limit"))
    assert not used and expression.focus == "explain-limit"
    assert expression.conversation.selected_facts == (planning.conversation.self_knowledge[1],)
    fact = expression.conversation.selected_facts[0]
    assert fact.content == envelope["runtime_asset"]["eligible"][1]["statement"]
    assert (fact.kind, fact.basis, fact.event_scope, fact.knowledge_scope) == ("belief", "linked-evidence", "before", "before")
    assert expression.character_core == planning.character_core and expression.personality == planning.personality
    assert expression.current_activity == {} and expression.current_plan is None and expression.related_event is None
    assert expression.conversation.policy == relevance.LIFE_CHAT_EXPRESSION_POLICY


def test_unrelated_reply_can_select_no_fact_without_losing_background_and_motive_is_not_fact(relevance_fixture):
    envelope, identity, basis, dialogue, _ = relevance_fixture
    planning, _ = relevance.life_chat_planning(envelope, identity, "我今天喜欢蓝色。", dialogue, True, basis)
    expression, _ = relevance.life_chat_expression(planning,
        dict(action="answer", fact_refs=[], use_life=False, focus="respond-current"))
    assert expression.conversation.selected_facts == () and expression.character_core
    encounter = "".join(expression.conversation.encounter)
    assert "系统推荐" in encounter and "用户主动" in encounter
    assert "助手提出" not in encounter and "看看其他人" not in encounter
    wire = json.loads(DeepSeekFirstLifeRelevanceAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, expression)))
    assert relevance.LIFE_CHAT_EXPRESSION_POLICY in wire["messages"][0]["content"]
    assert "完整selected_facts" not in wire["messages"][0]["content"]
    assert "保留limits" in wire["messages"][0]["content"]
    assert "每轮必说的清单" in wire["messages"][0]["content"]


@pytest.mark.parametrize("patch", [dict(focus="free reasoning"), dict(fact_refs=["F1", "F2", "F3"]),
    dict(fact_refs=["F1", "F1"]), dict(fact_refs=["F99"]), dict(use_life="yes"), dict(reason="new hidden chain")])
def test_invalid_planning_cannot_enter_expression(relevance_fixture, patch):
    envelope, identity, basis, dialogue, _ = relevance_fixture
    planning, _ = relevance.life_chat_planning(envelope, identity, "聊聊画面。", dialogue, True, basis)
    with pytest.raises(ValueError):
        relevance.life_chat_expression(planning, {**dict(action="answer", fact_refs=[], use_life=False, focus="respond-current"), **patch})


def test_share_has_one_current_change_and_exact_history_without_technical_receipt(relevance_fixture):
    envelope, identity, basis, dialogue, event = relevance_fixture
    projection = relevance.share_model_projection(envelope, identity, basis, dialogue, True, target_event=event)
    wire = json.loads(DeepSeekFirstLifeRelevanceAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE, projection)))
    payload = json.loads(wire["messages"][1]["content"])
    assert payload["recent_dialogue"] == [asdict(dialogue.recent_dialogue[0])]
    assert set(payload["related_event"]) == {"kind", "differences", "content_kind"}
    assert payload["related_event"]["differences"] == [asdict(basis.versions[1].differences[0])]
    assert "revision" not in payload["current_activity"] and "summary" not in payload["related_event"]
    for private in ("private-event", "private-subject", "private-anchor", "private-claim", "系统已保存v2", "source_declaration"):
        assert private not in canonical_json(payload)
    value = dict(share=True, reply_text="把主体放到中间以后，留白更清楚了，想接着聊聊这个取舍。", language="zh", focus="composition", opening="continuation")
    assert relevance.validate_share_candidate(projection, value) == value["reply_text"]
    assert relevance.validate_share_candidate(projection, dict(share=False, reply_text="", language="zh", focus="none", opening="none")) == ""


def test_history_off_empty_but_self_interest_share_possible_and_no_past_topic_claim(relevance_fixture):
    envelope, identity, basis, _, event = relevance_fixture
    projection = relevance.share_model_projection(envelope, identity, basis, CharacterDialogueBasis("available", True), False, event)
    assert projection.recent_dialogue == () and not projection.history_enabled
    value = dict(share=True, reply_text="我选了更清楚的留白，想给你看看这个取舍。", language="zh", focus="composition", opening="self-interest")
    assert relevance.validate_share_candidate(projection, value)
    with pytest.raises(ValueError): relevance.validate_share_candidate(projection, {**value, "opening": "continuation"})
    task = ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE, replace(projection, recent_dialogue=(RecentDialogueTurn("旧话题", "旧回复"),)))
    with pytest.raises(ValueError): DeepSeekFirstLifeRelevanceAdapter.wire(task)


@pytest.mark.parametrize("dialogue,enabled", [
    (CharacterDialogueBasis("failed-closed"), True), (CharacterDialogueBasis("available", True, (RecentDialogueTurn("a", "b"),) * 3), True),
    (CharacterDialogueBasis("available", True, (RecentDialogueTurn("a" * 2000, "b" * 2001),)), True),
    (CharacterDialogueBasis("available", True, (RecentDialogueTurn("a", ""),)), True),
    (CharacterDialogueBasis("available", True, (RecentDialogueTurn("a", "b"),)), False)])
def test_share_history_failure_never_truncates_or_bypasses_boundary(relevance_fixture, dialogue, enabled):
    envelope, identity, basis, _, event = relevance_fixture
    with pytest.raises(ValueError): relevance.share_model_projection(envelope, identity, basis, dialogue, enabled, event)


def test_exact_two_turn_4000_boundary_and_historical_event_plan_is_its_own(relevance_fixture):
    envelope, identity, basis, _, event = relevance_fixture
    dialogue = CharacterDialogueBasis("available", True, (RecentDialogueTurn("a" * 1000, "b" * 1000),) * 2)
    old_event = replace(event, event_id="old-local-event", revision=1, kind="start")
    projection = relevance.share_model_projection(envelope, identity, replace(basis, events=(old_event, event)), dialogue, True, old_event)
    assert projection.recent_dialogue == dialogue.recent_dialogue
    assert projection.current_plan == asdict(basis.versions[0].plan) != asdict(basis.record.plan)


def test_share_declared_focus_requires_change_or_committed_choice_not_revision(relevance_fixture):
    envelope, identity, basis, dialogue, event = relevance_fixture
    projection = relevance.share_model_projection(envelope, identity, basis, dialogue, True, event)
    value = dict(share=True, reply_text="一个变化。", language="zh", focus="composition", opening="self-interest")
    for patch in (dict(focus="subject"), dict(focus="choice"), dict(focus=["composition", "focus"]), dict(opening="free reason")):
        with pytest.raises(ValueError): relevance.validate_share_candidate(projection, {**value, **patch})
    mechanical = replace(projection, related_event={**projection.related_event, "differences": []})
    with pytest.raises(ValueError): relevance.validate_share_candidate(mechanical, value)
    kept = replace(event, kind="keep")
    choice = relevance.share_model_projection(envelope, identity, replace(basis, events=(kept,)), dialogue, True, kept)
    assert relevance.validate_share_candidate(choice, {**value, "focus": "choice"})
    with pytest.raises(ValueError): relevance.validate_share_candidate(choice, value)


def test_v1_scope_and_life_decision_wire_are_untouched_and_versions_cannot_mix(relevance_fixture):
    envelope, identity, basis, dialogue, event = relevance_fixture
    old_scope = legacy.first_life_scope(envelope["definition_basis"])
    new_scope = relevance.first_life_scope(envelope["definition_basis"])
    assert old_scope["version"] == "first-life-use-1" and new_scope["version"] == "first-life-use-2"
    assert legacy.first_life_scope_digest(envelope["definition_basis"]) != relevance.first_life_scope_digest(envelope["definition_basis"])
    for field in ("life_policy_sha", "life_input", "user_words_in_life", "development_scope", "development_call_limit", "shared_total_budget"):
        assert old_scope[field] == new_scope[field]
    decision = ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION, life_model_projection(envelope, identity, basis))
    assert DeepSeekFirstLifeAdapter.wire(decision) == DeepSeekFirstLifeRelevanceAdapter.wire(decision)
    projection = relevance.share_model_projection(envelope, identity, basis, dialogue, True, event)
    with pytest.raises(ValueError): DeepSeekFirstLifeAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE, projection))
    old_share = life_model_projection(envelope, identity, basis, share=True)
    with pytest.raises(ValueError): DeepSeekFirstLifeRelevanceAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE, old_share))

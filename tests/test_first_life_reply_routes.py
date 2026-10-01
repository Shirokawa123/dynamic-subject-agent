"""Pure synthetic reply-route contracts; no network, credentials or model use."""
from dataclasses import asdict, replace
import json

import pytest

from dynamic_subject_agent import first_life_followup as v4
from dynamic_subject_agent import first_life_reply_routes as routes
from dynamic_subject_agent import first_life_reply_drafts as drafts
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.first_life_followup_provider import DeepSeekFirstLifeFollowupAdapter
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from test_first_life_relevance_projection import relevance_fixture


def planning_for(fixture, *, history=True):
    envelope, identity, basis, dialogue, _ = fixture
    sources = tuple(v4.DialogueSource(label, speaker, text, "dialogue")
        for label, speaker, text in (("U1", "user", dialogue.recent_dialogue[0].user_text),
            ("A1", "assistant", dialogue.recent_dialogue[0].assistant_text)))
    sources += (v4.DialogueSource("S1", "assistant", "我已经把灯拿走了，只留下窗光。", "proactive-share"),)
    followup = v4.FirstLifeFollowupBasis(dialogue, sources) if history else v4.FirstLifeFollowupBasis(
        CharacterDialogueBasis("available", True), ())
    return v4.life_chat_planning(envelope, identity, "那这盏灯呢？", followup, history, basis)[0]


def choice(*, use_life=False):
    return dict(action="answer", fact_refs=["F2"], use_life=use_life,
        focus="clarify-premise", dialogue_refs=["S1"])


def test_b_keeps_judgment_facts_and_attributed_error_without_proposing_disclosure(relevance_fixture):
    planning = planning_for(relevance_fixture)
    old, old_use = v4.life_chat_expression(planning, choice())
    new, use_life = routes.fact_expression_projection(planning, choice())
    assert old_use is False and old.current_activity == {} and old.current_plan is None and old.related_event is None
    assert use_life is False and new.use_life is False
    assert new.current_activity == planning.current_activity
    assert new.current_plan == planning.current_plan
    assert new.related_event == planning.related_event
    assert "灯" in new.current_plan["composition"]
    assert new.selected_dialogue == old.selected_dialogue == (planning.dialogue_sources[-1],)
    assert new.selected_dialogue[0].speaker == "assistant" and new.selected_dialogue[0].kind == "proactive-share"
    assert new.conversation.selected_facts == old.conversation.selected_facts
    assert new.conversation.selected_facts[0].kind == "belief"
    assert new.character_core == planning.character_core and new.personality == planning.personality


def test_a_keeps_same_full_knowledge_facts_and_does_not_infer_disclosure(relevance_fixture):
    planning = planning_for(relevance_fixture)
    whole = routes.whole_reply_projection(planning)
    assert whole.conversation.self_knowledge == planning.conversation.self_knowledge
    assert whole.conversation.disclosure == planning.conversation.disclosure
    assert whole.dialogue_sources == planning.dialogue_sources
    assert (whole.current_activity, whole.current_plan, whole.related_event) == (
        planning.current_activity, planning.current_plan, planning.related_event)
    assert routes.validate_whole_reply(whole, dict(reply_text="先说你刚才的想法。", language="zh", use_life=False)) == (
        "先说你刚才的想法。", False)
    assert routes.validate_whole_reply(whole, dict(reply_text="当前构图里确实还有灯。", language="zh", use_life=True))[1] is True
    expression, used = routes.fact_expression_projection(planning, choice(use_life=True))
    assert used is True and expression.use_life is True
    assert expression.related_event == whole.related_event


@pytest.mark.parametrize("patch", [dict(use_life=1), dict(use_life="false"), dict(use_life=None),
    dict(language="en"), dict(reply_text=" "), dict(reply_text="字" * 1201), dict(reply_text="字\x00"),
    dict(reply_text=None), dict(event_id="private-event"), dict(reason="unbounded reasoning")])
def test_a_bad_output_is_rejected_for_the_caller_to_fail_closed(relevance_fixture, patch):
    whole = routes.whole_reply_projection(planning_for(relevance_fixture))
    value = dict(reply_text="合成候选。", language="zh", use_life=False)
    with pytest.raises(ValueError):
        routes.validate_whole_reply(whole, {**value, **patch})


def test_whole_exact_output_and_no_event_disclosure_are_required(relevance_fixture):
    planning = replace(planning_for(relevance_fixture), related_event=None)
    whole = routes.whole_reply_projection(planning)
    with pytest.raises(ValueError):
        routes.validate_whole_reply(whole, dict(reply_text="旧二字段不足。", language="zh"))
    with pytest.raises(ValueError):
        routes.validate_whole_reply(whole, dict(reply_text="不能披露不存在的事件。", language="zh", use_life=True))
    with pytest.raises(ValueError):
        routes.fact_expression_projection(planning, choice(use_life=True))
    assert routes.validate_whole_reply(whole, dict(reply_text="字" * 1200, language="zh", use_life=False))[1] is False
    expression, used = routes.fact_expression_projection(planning, choice())
    assert not used and expression.current_plan == planning.current_plan and expression.related_event is None


@pytest.mark.parametrize("patch", [dict(fact_refs=["F99"]), dict(fact_refs=["F1", "F2", "F3"]),
    dict(dialogue_refs=["U1", "A1", "S1"]), dict(dialogue_refs=["S1", "S1"]), dict(dialogue_refs=["S2"]),
    dict(focus="explain-encounter"), dict(use_life="false"), dict(action="perform-action")])
def test_b_reuses_bounded_v4_selection_adjudication(relevance_fixture, patch):
    with pytest.raises(ValueError):
        routes.fact_expression_projection(planning_for(relevance_fixture), {**choice(), **patch})


def test_draft_bytes_keep_v4_planning_and_high_expression_configuration(relevance_fixture):
    planning = planning_for(relevance_fixture)
    task = ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning)
    old_wire = DeepSeekFirstLifeFollowupAdapter.wire(task)
    old_expression, _ = v4.life_chat_expression(planning, choice())
    old_expression_task = ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, old_expression)
    old_expression_wire = DeepSeekFirstLifeFollowupAdapter.wire(old_expression_task)
    assert drafts.draft_wire(task) == old_wire
    whole = routes.whole_reply_projection(planning)
    expression, _ = routes.fact_expression_projection(planning, choice())
    for kind, projection in ((ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, whole),
        (ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION, expression)):
        task = ModelTask(kind, projection)
        body = json.loads(drafts.draft_wire(task))
        assert {key: body[key] for key in communication_protocol("thinking-high", "low")["expression"]} == (
            communication_protocol("thinking-high", "low")["expression"])
        assert body["model"] == "deepseek-flash"
        assert json.loads(body["messages"][1]["content"])["current_plan"] == planning.current_plan
        with pytest.raises(ValueError):
            DeepSeekFirstLifeFollowupAdapter.wire(task)
        # Relabelling a new payload as an old task cannot borrow v4's wire eligibility.
        for old_kind in (ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION):
            with pytest.raises(ValueError):
                DeepSeekFirstLifeFollowupAdapter.wire(ModelTask(old_kind, projection))
    assert DeepSeekFirstLifeFollowupAdapter.wire(old_expression_task) == old_expression_wire
    assert DeepSeekFirstLifeFollowupAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning)) == old_wire


def test_new_draft_types_and_policy_are_exact_and_do_not_accept_existing_expression(relevance_fixture):
    planning = planning_for(relevance_fixture)
    whole = routes.whole_reply_projection(planning)
    expression, _ = routes.fact_expression_projection(planning, choice())
    invalid_tasks = (
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, planning),
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, asdict(whole)),
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, replace(whole, policy=v4.LIFE_CHAT_POLICY)),
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, replace(whole, conversation=planning.conversation)),
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION, v4.life_chat_expression(planning, choice())[0]),
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION, replace(expression, use_life=1)),
        ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION, replace(expression, selected_dialogue=planning.dialogue_sources)),
        ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, expression),
    )
    for task in invalid_tasks:
        with pytest.raises(ValueError):
            drafts.draft_wire(task)


def test_history_off_removes_utterances_but_retains_independently_allowed_facts(relevance_fixture):
    planning = planning_for(relevance_fixture, history=False)
    whole = routes.whole_reply_projection(planning)
    expression, used = routes.fact_expression_projection(planning, {**choice(), "dialogue_refs": []})
    assert whole.dialogue_sources == expression.selected_dialogue == ()
    assert not whole.history_enabled and not expression.history_enabled and not used
    assert whole.current_plan == expression.current_plan == planning.current_plan
    assert whole.related_event == expression.related_event == planning.related_event
    with pytest.raises(ValueError):
        routes.whole_reply_projection(replace(planning_for(relevance_fixture), history_enabled=False))


@pytest.mark.parametrize("change", [
    lambda p: replace(p, dialogue_sources=(replace(p.dialogue_sources[0], text="字" * 4001), *p.dialogue_sources[1:])),
    lambda p: replace(p, dialogue_sources=(*p.dialogue_sources[:-1], replace(p.dialogue_sources[-1], text="字" * 401))),
    lambda p: replace(p, conversation=replace(p.conversation, current_message="字" * 1001)),
    lambda p: replace(p, current_plan={**p.current_plan, "database_id": "private"}),
    lambda p: replace(p, current_activity={**p.current_activity, "revision": True}),
    lambda p: replace(p, related_event={**p.related_event, "event_id": "private"}),
    lambda p: replace(p, related_event={**p.related_event, "simulated": 1}),
])
def test_new_projection_rejects_invalid_source_bounds_and_outbound_fields(relevance_fixture, change):
    planning = change(planning_for(relevance_fixture))
    with pytest.raises(ValueError):
        routes.whole_reply_projection(planning)
    with pytest.raises(ValueError):
        routes.fact_expression_projection(planning, choice())


def test_scope_is_local_distinct_and_binds_full_definition_policy_and_baseline(monkeypatch):
    basis = "a" * 64
    a = drafts.reply_scope_digest(basis, routes.WHOLE_LOCAL_POLICY)
    b = drafts.reply_scope_digest(basis, routes.PLANNED_LOCAL_POLICY)
    assert a != b and a != v4.first_life_scope_digest(basis) and b != v4.first_life_scope_digest(basis)
    assert drafts.reply_scope_digest("b" * 64, routes.WHOLE_LOCAL_POLICY) != a
    with pytest.raises(ValueError):
        drafts.reply_scope_digest(basis, v4.FOLLOWUP_VERSION)
    with pytest.raises(ValueError):
        drafts.reply_scope_digest("not-a-definition-digest", routes.WHOLE_LOCAL_POLICY)
    monkeypatch.setattr(routes, "WHOLE_REPLY_POLICY", routes.WHOLE_REPLY_POLICY + "新约束。")
    assert drafts.reply_scope_digest(basis, routes.WHOLE_LOCAL_POLICY) != a
    original = v4.first_life_scope
    monkeypatch.setattr(v4, "first_life_scope", lambda definition: {**original(definition), "test_revision": 1})
    assert drafts.reply_scope_digest(basis, routes.PLANNED_LOCAL_POLICY) != b


def test_deferred_zero_revision_event_is_valid_judgment_material(relevance_fixture):
    planning = planning_for(relevance_fixture)
    planning = replace(planning, current_activity=dict(project_kind="drawing-composition-text", phase="deferred",
        revision=0, allowed_actions=[]), current_plan=None,
        related_event=dict(kind="defer", revision=0, summary="本次暂缓。", differences=[], simulated=True,
            content_kind="creative-composition-text-not-image"))
    whole = routes.whole_reply_projection(planning)
    assert routes.validate_whole_reply(whole, dict(reply_text="这次先放一放。", language="zh", use_life=True))[1]

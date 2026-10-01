"""Offline preparation behavior, not a semantic model evaluation."""
from dataclasses import asdict
import json
import socket

import pytest

from scripts.s109_route_preview import (
    PreparedUseScope, load_scenarios, planning_for, prepare, preview_pair, write_preview,
)


def payload(wire):
    return json.loads(wire["messages"][1]["content"])


def test_same_source_b_uses_real_selection_and_a_preserves_judgment_facts(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline preparation attempted network access")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = prepare()
    assert result["actual_provider_calls"] == result["live_call_budget_approved"] == 0
    assert result["live_execution_available"] is False
    for chain in result["chains"]:
        assert len(chain["turns"]) == 8
        first = chain["turns"][0]["requests"]
        a = payload(first["A"]["wire"])
        b = payload(first["B"]["planning_wire"])
        b.pop("policy")
        b["conversation"].pop("policy")
        assert a == b  # Same facts, dialogue, personality, visibility and state.
        expression = payload(first["B"]["expression_wire"])
        assert expression["current_activity"] == {} and expression["current_plan"] is None
        assert expression["related_event"] is None and expression["selected_dialogue"][0]["kind"] == "proactive-share"
        assert a["current_plan"] is not None
        for field in ("model", "thinking", "reasoning_effort", "max_tokens", "response_format", "stream"):
            assert first["A"]["wire"][field] == first["B"]["expression_wire"][field]
        assert "synthetic-event" not in json.dumps(first, ensure_ascii=False)
        assert "source_declaration" not in json.dumps(first, ensure_ascii=False)


def test_continuous_tape_caps_share_expiry_and_blocked_counterfactuals_are_visible():
    result = prepare()
    for chain in result["chains"]:
        turns = chain["turns"]
        for index, turn in enumerate(turns):
            sources = payload(turn["requests"]["B"]["planning_wire"])["dialogue_sources"]
            assert any(row["label"] == "S1" for row in sources) is (index < 2)
            assert len([row for row in sources if row["kind"] == "dialogue"]) == min(index, 2) * 2
            if index:
                assert sources[-1]["text"] == turns[index - 1]["scripted_reply"]
            assert turn["draft_only_after_block"] is (index >= 4)
        assert turns[4]["blocked_since"] == 5 and turns[-1]["blocked_since"] == 5
        assert turns[-1]["restart_fixture_roundtrip"] is True


def test_explicit_activity_restriction_keeps_later_chat_but_never_reexports_prior_sources():
    for chain in prepare()["chains"]:
        control = chain["turns"][5]["candidate_common_scope"]
        assert control["status"] == "local-control-only" and control["requests"] is None
        for index in (6, 7):
            candidate = chain["turns"][index]["candidate_common_scope"]
            assert candidate["scope"] == dict(activity_allowed=False, dialogue_start=6)
            a = payload(candidate["requests"]["A"]["wire"])
            b = payload(candidate["requests"]["B"]["planning_wire"])
            for p in (a, b):
                assert p["current_activity"] == {} and p["current_plan"] is None and p["related_event"] is None
                assert p["character_core"] and p["personality"]
                assert chain["synthetic_share"] not in json.dumps(p, ensure_ascii=False)
            assert a["dialogue_sources"] == b["dialogue_sources"]
            assert len(a["dialogue_sources"]) == (0 if index == 6 else 2)
            if index == 7:
                assert a["dialogue_sources"][0]["text"] == chain["turns"][6]["user"]
        # Merely turning history off would NOT remove current activity.
        off = payload(chain["turns"][6]["history_off_example"]["A"]["wire"])
        assert off["dialogue_sources"] == [] and off["current_plan"] is not None


def test_scope_restore_and_new_inputs_do_not_depend_on_fixture_object_names():
    scenario = load_scenarios()["scenarios"][0]
    scenario["plans"][1]["subject"] = "合成留出样本：风筝"
    tape = [dict(user="旧话题", assistant="旧回复"), dict(user="聊明暗对比", assistant="先比较明亮部分")]
    scope = PreparedUseScope().restrict_activity(1)
    restored = PreparedUseScope.restore(json.loads(json.dumps(asdict(scope))))
    before = planning_for(scenario, "接着聊明暗", tape, scope=scope)
    after = planning_for(scenario, "接着聊明暗", tape, scope=restored)
    assert before == after and before.current_plan is None
    assert [source.text for source in after.dialogue_sources] == ["聊明暗对比", "先比较明亮部分"]
    with pytest.raises(ValueError):
        PreparedUseScope.restore(dict(activity_allowed="false", dialogue_start=1))
    with pytest.raises(ValueError):
        PreparedUseScope.restore(dict(activity_allowed=False, dialogue_start=-1))
    with pytest.raises(ValueError):
        preview_pair(after, dict(action="answer", fact_refs=[], use_life=True, focus="respond-current", dialogue_refs=[]))


def test_full_turn_limits_and_history_off_apply_before_either_route():
    scenario = load_scenarios()["scenarios"][0]
    tape = [dict(user="甲" * 1000, assistant="乙" * 1000), dict(user="丙" * 1000, assistant="丁" * 1001)]
    # Only a complete latest pair fits; an older half-turn is never retained.
    planning = planning_for(scenario, "继续", tape)
    assert len(planning.dialogue_sources) == 2
    off = planning_for(scenario, "继续", tape, history_enabled=False)
    assert off.dialogue_sources == () and off.history_enabled is False


def test_review_snapshot_is_reproducible_and_never_overwrites_existing_output(tmp_path):
    output = tmp_path / "new-preview"
    result = write_preview(output)
    assert json.loads((output / "requests.json").read_text(encoding="utf-8")) == result
    assert result == prepare()
    marker = (output / "README.md").read_bytes()
    with pytest.raises(FileExistsError):
        write_preview(output)
    assert (output / "README.md").read_bytes() == marker

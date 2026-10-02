"""Expression changes preserve material/authority and reach the public Facade."""
import json
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.first_life_free_input_trial import open_free_input_reply_trial, expression_contract
from dynamic_subject_agent.first_life_conversation_expression import (
    preview_proposal_source, proposal_changes, preview_conversation, conversation_changes)
from dynamic_subject_agent.first_life_current_topic_candidate import preview_current_topic_candidate
from test_first_life_free_input_trial import task_fixture
from test_s117_continuous_comparison import SyntheticTransport
from run_s112_reply_comparison import SCENARIOS_PATH
from owned_dialogue_trial import OwnedDialogueBranch


def test_variant_changes_only_two_paragraphs_and_keeps_old_manifests(tmp_path):
    task = task_fixture()
    before = json.loads(preview_current_topic_candidate(task).wire)
    after = json.loads(preview_proposal_source(task).wire)
    system = before["messages"][0]["content"]
    assert [row.paragraph_number for row in proposal_changes()] == [3, 4]
    assert all(row.after in after["messages"][0]["content"] for row in proposal_changes())
    after["messages"][0]["content"] = system
    assert after == before
    old = open_free_input_reply_trial(tmp_path / str(uuid4()), SCENARIOS_PATH, live=False, confirmed=True)
    kept = (old.root / "approval.json").read_bytes()
    new = open_free_input_reply_trial(tmp_path / str(uuid4()), SCENARIOS_PATH, live=False, confirmed=True, expression_variant="proposal-source")
    assert new.read()["data_use"] == old.read()["data_use"]
    assert new.read()["contract"] == expression_contract("proposal-source")
    with pytest.raises(ValueError):
        open_free_input_reply_trial(old.root, SCENARIOS_PATH, live=False, confirmed=True, expression_variant="proposal-source")
    assert (old.root / "approval.json").read_bytes() == kept


@pytest.mark.parametrize("variant,changes", [("proposal-source", proposal_changes), ("conversation", conversation_changes)])
def test_proposal_variant_uses_exact_wire_and_reopens_with_saved_plan_unchanged(tmp_path, variant, changes):
    transport = SyntheticTransport()
    branch = OwnedDialogueBranch(tmp_path / str(uuid4()), "objects-and-versions", live=False,
        variant=variant, transport=transport, messages=("如果只试一个小变化，你更想试什么？", "刚才那个试法是新的想法吗？"))
    try:
        assert branch.contribute(0) == "terminal"
        branch.reopen()
        assert branch.contribute(1) == "terminal"
        result = branch.finish()
        assert result["status"] == "completed" and len(transport.calls) == 2
        assert all(row.after in transport.calls[-1]["messages"][0]["content"] for row in changes())
        assert result["saved_project_equal"] and result["actions"][0]["additional_model_calls"] == 0
    finally:
        branch.close()


def test_conversation_changes_only_source_and_voice_and_preserves_proposal_root(tmp_path):
    task = task_fixture()
    before = json.loads(preview_proposal_source(task).wire)
    after = json.loads(preview_conversation(task).wire)
    assert [row.paragraph_number for row in conversation_changes()] == [4, 7]
    after["messages"][0]["content"] = before["messages"][0]["content"]
    assert after == before
    old = open_free_input_reply_trial(tmp_path / str(uuid4()), SCENARIOS_PATH, live=False, confirmed=True, expression_variant="proposal-source")
    kept = (old.root / "approval.json").read_bytes()
    new = open_free_input_reply_trial(tmp_path / str(uuid4()), SCENARIOS_PATH, live=False, confirmed=True, expression_variant="conversation")
    assert new.read()["data_use"] == old.read()["data_use"]
    assert new.read()["contract"] == expression_contract("conversation")
    with pytest.raises(ValueError):
        open_free_input_reply_trial(old.root, SCENARIOS_PATH, live=False, confirmed=True, expression_variant="conversation")
    assert (old.root / "approval.json").read_bytes() == kept

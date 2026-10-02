"""A candidate can change expression, never an existing branch or data purpose."""
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

from dynamic_subject_agent.first_life_free_input_trial import open_free_input_reply_trial
from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
from dynamic_subject_agent.first_life_current_topic_candidate import preview_current_topic_candidate
from dynamic_subject_agent.frozen_attempt import canonical_json
from test_s117_continuous_comparison import SyntheticTransport

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from run_s120_continuous_dialogue import run
from run_s112_reply_comparison import SCENARIOS_PATH


def test_original_manifest_byte_exact_and_candidate_cannot_replace_existing_root(tmp_path):
    original=open_free_input_reply_trial(tmp_path/str(uuid4()),SCENARIOS_PATH,live=False,confirmed=True)
    retained=(original.root/"approval.json").read_bytes()
    with pytest.raises(ValueError):open_free_input_reply_trial(original.root,SCENARIOS_PATH,live=False,confirmed=True,expression_variant="current-topic")
    assert original.read()["version"]=="s119-free-input-approval-1" and (original.root/"approval.json").read_bytes()==retained
    candidate=open_free_input_reply_trial(tmp_path/str(uuid4()),SCENARIOS_PATH,live=False,confirmed=True,expression_variant="current-topic")
    assert candidate.read()["data_use"]==original.read()["data_use"]
    assert candidate.read()["version"]=="s120-free-input-approval-1" and candidate.branch("objects-and-versions-A")[1]!=original.branch("objects-and-versions-A")[1]


def test_candidate_full_facade_chain_reopens_without_seed_or_model_replay(tmp_path):
    transport=SyntheticTransport()
    summary=run("current-topic",live=False,root=tmp_path/str(uuid4()),transport=transport)
    assert summary["status"]=="completed",summary
    assert summary["actual_attempts"]==len(transport.calls)==5
    assert len(summary["steps"][-1]["canonical_history"])==6
    for call in transport.calls:
        from dynamic_subject_agent.first_life_current_topic_candidate import TOPIC_REPAIR
        assert TOPIC_REPAIR in call["messages"][0]["content"]
    assert "reopened" in (Path(summary["root"])/"s120-dialogue.jsonl").read_text(encoding="utf-8")

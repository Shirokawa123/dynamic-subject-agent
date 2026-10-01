"""The new purpose permits bounded new text, preserves old authority and history."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport
from dynamic_subject_agent.first_life_development_trial import open_development_reply_trial, DevelopmentReplyAdapter, DevelopmentReplyBudget, OFFLINE_BACKEND, OFFLINE_KEY
from dynamic_subject_agent.first_life_free_input_trial import (open_free_input_reply_trial, FreeInputReplyTrial,
    free_input_trial_from_witness, CALL_PURPOSE)
from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
from dynamic_subject_agent.first_life_followup import DialogueSource
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from test_s117_continuous_comparison import SyntheticTransport


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from serve_s119_whole_chat import FreeInputChatEntry
from run_s112_reply_comparison import SCENARIOS_PATH, send, read_history


def task_fixture():
    package=json.loads((ROOT/"docs/experiments/s115/protocol-comparison.json").read_text(encoding="utf-8"))
    row=package["cases"][0]
    task=recorded_reply_task(row["task_kind"],row["payload"])
    return ModelTask(task.kind,replace(task.payload,conversation=replace(task.payload.conversation,
        current_message="这是新的自由文字问候，不在旧测试句清单内。")))


def test_new_purpose_is_exact_and_old_scope_does_not_accept_new_text(tmp_path):
    old=open_development_reply_trial(tmp_path/str(uuid4()),SCENARIOS_PATH,live=False)
    original=(old.root/"approval.json").read_bytes()
    task=task_fixture()
    with pytest.raises(ValueError):old.validate_task("objects-and-versions-A",task)
    new=open_free_input_reply_trial(tmp_path/str(uuid4()),SCENARIOS_PATH,live=False,confirmed=True)
    new.validate_task("objects-and-versions-A",task)
    assert new.manifest_digest!=old.manifest_digest
    assert free_input_trial_from_witness(new.witness("objects-and-versions-A")).manifest_digest==new.manifest_digest
    assert (old.root/"approval.json").read_bytes()==original and old.read()["version"]=="s117-continuous-development-1"
    with pytest.raises(ValueError):new.branch("objects-and-versions-B")
    with pytest.raises(ValueError):open_free_input_reply_trial(tmp_path/str(uuid4()),SCENARIOS_PATH,live=False,confirmed=False)
    value=json.loads((new.root/"approval.json").read_text(encoding="utf-8"))
    value["data_use"]["current_message_chars"]=1001
    (new.root/"approval.json").write_text(canonical_json(value),encoding="utf-8")
    with pytest.raises(ValueError):new.read()


def test_free_input_rejects_other_material_and_incomplete_or_oversize_sources(tmp_path):
    trial=open_free_input_reply_trial(tmp_path/str(uuid4()),SCENARIOS_PATH,live=False,confirmed=True)
    task=task_fixture()
    changed=[
        replace(task.payload,conversation=replace(task.payload.conversation,current_message="字"*1001)),
        replace(task.payload,current_plan=dict(subject="other",composition="other",focus="other")),
        replace(task.payload,dialogue_sources=(DialogueSource("U1","user","未成对来源","dialogue"),)),
        replace(task.payload,history_enabled=False,dialogue_sources=(DialogueSource("U1","user","问候","dialogue"),DialogueSource("A1","assistant","答复","dialogue"))),
        replace(task.payload,dialogue_sources=(DialogueSource("S1","assistant","其它近况","proactive-share"),)),
    ]
    for payload in changed:
        with pytest.raises(ValueError):trial.validate_task("objects-and-versions-A",ModelTask(task.kind,payload))
    with pytest.raises(ValueError):trial.validate_task("objects-and-versions-A",ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN,task.payload))
    complete=(DialogueSource("U1","user","甲"*1000,"dialogue"),DialogueSource("A1","assistant","乙"*1200,"dialogue"),
        DialogueSource("U2","user","丙"*1000,"dialogue"),DialogueSource("A2","assistant","丁"*800,"dialogue"))
    trial.validate_task("objects-and-versions-A",ModelTask(task.kind,replace(task.payload,dialogue_sources=complete)))
    too_long=complete[:-1]+(replace(complete[-1],text="丁"*801),)
    with pytest.raises(ValueError):trial.validate_task("objects-and-versions-A",ModelTask(task.kind,replace(task.payload,dialogue_sources=too_long)))


def test_canonical_new_text_history_off_reopen_and_private_observations(tmp_path):
    transport=SyntheticTransport()
    entry=FreeInputChatEntry(tmp_path/"entry",live=False,transport=transport)
    case="objects-and-versions"
    try:
        assert not transport.calls and entry.trial.shared_budget().counts()==(None,0,None)
        product=entry.products[case]
        messages=["PRIVATE_NEW_TEXT：这次想先说说颜色。","刚才那句话，我想接着听你的看法。"]
        for index,text in enumerate(messages):
            response=send(product,text,"s119-test-free-text-"+str(index))
            assert response.status=="terminal", response
        wires=[json.loads(call["messages"][1]["content"]) for call in transport.calls]
        assert wires[0]["turn"]["current_message"]==messages[0]
        assert any(row["text"]==messages[0] for row in wires[1]["exchange"]["dialogue_sources"])
        saved=read_history(product)
        product=entry.reopen(case)
        assert read_history(product)==saved and len(transport.calls)==2
        assert product.application.set_reviewed_character_history(False).status=="active"
        assert send(product,"关闭近期交流后的一句新话。","s119-test-history-off-new").status=="terminal"
        latest=json.loads(transport.calls[-1]["messages"][1]["content"])
        assert latest["exchange"]["dialogue_sources"]==[]
        assert latest["exchange"]["history_enabled"] is False
        observed=canonical_json(entry.trial.observations)
        assert "PRIVATE_NEW_TEXT" not in observed and "reply_text" not in observed and "request_body" not in observed
        assert all(set(row)<= {"task_kind","request_digest","wire_sha256","error_code","model","usage","finish_reason","elapsed_seconds"} for row in entry.trial.observations)
        assert entry.trial.shared_budget().counts()==(None,3,None)
        import sqlite3
        with sqlite3.connect(entry.trial.shared_budget().path/"calls.sqlite3") as db:
            assert db.execute("SELECT DISTINCT purpose FROM call_attempt").fetchall()==[(CALL_PURPOSE,)]
    finally:entry.close()
    restored=FreeInputChatEntry(tmp_path/"entry",live=False,transport=transport)
    try:
        assert len(transport.calls)==3 and read_history(restored.products[case])[-1].user_text=="关闭近期交流后的一句新话。"
    finally:restored.close()


def test_separate_new_audit_keeps_an_old_running_reader_valid_and_missing_audit_is_not_reset(tmp_path,monkeypatch):
    from dynamic_subject_agent import development_model_calls as calls
    from dynamic_subject_agent import first_life_free_input_trial as free
    old=calls.DevelopmentCallAudit(tmp_path/"old-audit",initialize=True)
    monkeypatch.setattr(free,"fixed_free_input_audit_path",lambda:tmp_path/"free-input-audit")
    new=free._open_live_audit()
    new.claim("1"*64,"2"*64,purpose=CALL_PURPOSE,run_digest="3"*64)
    new.record("1"*64,status="unknown")
    assert old.counts()==(None,0,None) and new.counts()==(None,1,None)
    # The old process has the old purpose enum loaded, without reloading source.
    monkeypatch.setattr(calls,"PURPOSES",frozenset(("reply-protocol-comparison","continuous-reply-development")))
    assert old.counts()==(None,0,None)
    target=(tmp_path/"free-input-audit").resolve()
    retained=(tmp_path/"retained-audit").resolve()
    assert target.is_relative_to(tmp_path.resolve()) and retained.is_relative_to(tmp_path.resolve())
    target.rename(retained)
    with pytest.raises(ValueError,match="witness"):
        free._open_live_audit()
    assert not target.exists() and retained.is_dir()

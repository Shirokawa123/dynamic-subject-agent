"""Same material/schema and exact paragraph changes through the existing Facade."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.first_life_current_topic_candidate import TOPIC_REPAIR
from dynamic_subject_agent.reply_protocol_trial import open_protocol_run
from test_reply_protocol_facade import LocalProtocolTransport

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/"docs/experiments/s120/expression-scope.json"


def test_self_and_topic_studies_have_exact_equal_material_and_retain_old_manifest(tmp_path):
    old=open_protocol_run(tmp_path/str(uuid4()),ROOT/"docs/experiments/s115/protocol-comparison.json",live=False,study="thinking-mode")
    retained=(old.root/"manifest.json").read_bytes()
    plans={study:open_protocol_run(tmp_path/str(uuid4()),PACKAGE,live=False,study=study) for study in ("self-choice","current-topic")}
    for study,plan in plans.items():
        assert len(plan.sequence)==10
        for row in plan.package["cases"]:
            wires=[json.loads(plan.wire_for(plan.request_for(row["case_id"],variant))) for variant in plan.variants]
            before,after=wires
            before_system=before["messages"][0]["content"].split("\n")
            after_system=after["messages"][0]["content"].split("\n")
            changed=[i+1 for i,(a,b) in enumerate(zip(before_system,after_system,strict=True)) if a!=b]
            assert changed==([3,5] if study=="self-choice" else [5])
            if study=="current-topic":assert after_system[4]==TOPIC_REPAIR
            after["messages"][0]["content"]=before["messages"][0]["content"]
            assert after==before and before["reasoning_effort"]=="high" and before["response_format"]=={"type":"json_object"}
        with pytest.raises(ValueError):open_protocol_run(plan.root,PACKAGE,live=False,study="current-topic" if study=="self-choice" else "self-choice")
    assert old.read()["version"]=="reply-protocol-run-5" and (old.root/"manifest.json").read_bytes()==retained


def test_facade_keeps_each_blank_arm_and_reopening_does_not_repeat(tmp_path):
    spec=importlib.util.spec_from_file_location("s120_runner",ROOT/"scripts/run_s116_protocol_comparison.py")
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    transport=LocalProtocolTransport(blank=True)
    root=tmp_path/str(uuid4())
    result=runner.run_once(root,live=False,transport=transport,study="self-choice",package_path=PACKAGE)
    assert len(transport.calls)==10 and result["character_history_empty"] and result["automatic_retries"]==0
    assert all(r["diagnostic_code"]=="response-content-empty" for r in result["results"])
    with pytest.raises(FileExistsError):runner.run_once(root,live=False,transport=transport,study="self-choice",package_path=PACKAGE)
    assert len(transport.calls)==10

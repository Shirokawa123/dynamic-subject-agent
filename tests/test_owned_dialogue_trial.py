"""The reusable owned runner still uses canonical pairs and original authority."""
import json
from pathlib import Path
import sys
from uuid import uuid4

from test_s117_continuous_comparison import SyntheticTransport

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_s122_experience_choice import PACKAGE, run_branch
from owned_dialogue_trial import digest


def test_complete_owned_reason_chain_reopens_and_exports_only_structural_wire_facts(tmp_path):
    row = json.loads(PACKAGE.read_text(encoding="utf-8"))["cases"][0]
    transport = SyntheticTransport()
    result = run_branch(row, 0, live=False, root=tmp_path / str(uuid4()), transport=transport)
    assert result["status"] == "completed" and result["actual_attempts"] == len(transport.calls) == 4
    assert result["saved_project_equal"] and result["automatic_retries"] == 0
    assert result["actions"] == [dict(kind="reopened", canonical_history_equal=True, additional_model_calls=0)]
    third = result["steps"][2]["envelopes"][0]
    fourth = result["steps"][3]["envelopes"][0]
    assert third["history_enabled"] and third["source_chars"] <= 4400
    assert digest(row["reasons"][0]) in [source["text_digest"] for source in third["sources"]]
    assert digest(row["common"]) not in [source["text_digest"] for source in fourth["sources"]]
    assert third["background_digest"] == fourth["background_digest"]
    assert third["evidence_digest"] == fourth["evidence_digest"]
    assert all("text" not in source for source in third["sources"])

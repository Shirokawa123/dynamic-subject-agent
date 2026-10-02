"""A presentation may select versions, but their canonical context never merges."""
import json
from pathlib import Path
import sys
import pytest

from test_s117_continuous_comparison import SyntheticTransport

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from serve_comparable_chat import ComparableChat
from run_s112_reply_comparison import send, read_history
from dynamic_subject_agent.first_life_conversation_expression import CONVERSATION_EXCHANGE


def test_same_interface_has_independent_roots_wires_history_and_cold_reopen(tmp_path):
    transport = SyntheticTransport()
    entry = ComparableChat(tmp_path / "entry", live=False, transport=transport)
    try:
        assert len(entry.products) == 4 and not transport.calls
        base = "current-topic:objects-and-versions"
        candidate = "conversation:objects-and-versions"
        assert next(iter(entry.products)) == base
        assert entry.entries["current-topic"].trial.root != entry.entries["conversation"].trial.root
        assert send(entry.products[base], "原版独立的合成新话。", "s125-base-owned-message").status == "terminal"
        assert send(entry.products[candidate], "候选独立的合成新话。", "s125-candidate-owned-message").status == "terminal"
        assert CONVERSATION_EXCHANGE not in transport.calls[0]["messages"][0]["content"]
        assert CONVERSATION_EXCHANGE in transport.calls[1]["messages"][0]["content"]
        wire = json.loads(transport.calls[1]["messages"][1]["content"])
        assert all(row["text"] != "原版独立的合成新话。" for row in wire["exchange"]["dialogue_sources"])
        saved = read_history(entry.products[candidate])
        assert read_history(entry.reopen(candidate)) == saved and len(transport.calls) == 2
        assert read_history(entry.products[base])[-1].user_text == "原版独立的合成新话。"
    finally:
        entry.close()


def test_recovery_cannot_relabel_another_valid_variant_pointer(tmp_path):
    root = tmp_path / "entry"
    entry = ComparableChat(root, live=False, transport=SyntheticTransport())
    entry.close()
    source = json.loads((root / "current-topic/current.json").read_text(encoding="utf-8"))
    target = root / "conversation/current.json"
    source["version"] = "s125-comparable-entry-conversation"
    target.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError):
        ComparableChat(root, live=False, transport=SyntheticTransport())

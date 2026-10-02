"""Content negation in a nominal plan question through the real chat Facade."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

import pytest

from dynamic_subject_agent.first_life import FirstLifeContextResetRequest
from dynamic_subject_agent.first_life_dialogue import is_first_life_dialogue_control
from dynamic_subject_agent.recent_dialogue import is_dialogue_control
from test_s117_continuous_comparison import SyntheticTransport


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from serve_s121_readonly_chat import ReadonlyChatEntry
from run_s112_reply_comparison import send, read_history, settle


ORIGINAL_QUESTION = "你开头那条近况说右边没留东西，但保存的方案里书一直在。你想怎么说明？"


@pytest.mark.parametrize("history_enabled", [True, False])
def test_original_question_commits_and_can_be_followed_after_reopen(tmp_path, history_enabled):
    transport = SyntheticTransport()
    entry = ReadonlyChatEntry(tmp_path / "entry", live=False, transport=transport)
    case = "objects-and-versions"
    try:
        product = entry.products[case]
        assert product.application.set_reviewed_character_history(history_enabled).status == "active"
        result = send(product, ORIGINAL_QUESTION, "s121-original-readonly-question")
        assert result.status == "terminal", repr(result)
        assert len(transport.calls) == 1
        saved = [asdict(row) for row in read_history(product)]
        assert saved[-1]["user_text"] == ORIGINAL_QUESTION
        product = entry.reopen(case)
        assert [asdict(row) for row in read_history(product)] == saved
        assert len(transport.calls) == 1
        continued = send(product, "保存的构图里右边不是空白吗？我想接着听你的解释。好吗？", "s121-readonly-followup")
        assert continued.status == "terminal", repr(continued)
        assert len(transport.calls) == 2
        wire = json.loads(transport.calls[-1]["messages"][1]["content"])
        exchange = wire["exchange"]
        assert exchange["history_enabled"] is history_enabled
        if history_enabled:
            sources = exchange["dialogue_sources"]
            assert any(row["speaker"] == "user" and row["text"] == ORIGINAL_QUESTION for row in sources)
            assert any(row["speaker"] == "assistant" and row["text"] == saved[-1]["assistant_text"] for row in sources)
            assert len([row for row in sources if row["kind"] == "dialogue"]) <= 4
        else:
            assert exchange["dialogue_sources"] == []
        assert entry.trial.shared_budget().counts() == (None, 2, None)
        # The legacy v1 contract still conservatively recognizes 保存.
        assert is_dialogue_control(ORIGINAL_QUESTION)
    finally:
        entry.close()


SOURCE_RESTRICTIONS = (
    "我不想再用保存的方案，可以吗？",
    "我没有授权你使用保存的方案，怎么解释？",
    "我不希望你使用保存的方案，可以吗？",
    "我不让你用保存的方案，好吗？",
    "你不可以使用保存的方案，好吗？",
    "我不希望你留着保存的方案，可以吗？",
    "继续使用保存的方案，我不同意，可以吗？",
    "保存的方案再用下去我可不答应，好吗？",
    "继续提保存的方案，我不同意，好吗？",
    "留着保存的方案，我不同意，好吗？",
)


def test_source_restriction_still_blocks_with_history_off_and_after_reopen(tmp_path):
    transport = SyntheticTransport()
    entry = ReadonlyChatEntry(tmp_path / "entry", live=False, transport=transport)
    case = "objects-and-versions"
    try:
        product = entry.products[case]
        assert product.application.set_reviewed_character_history(False).status == "active"
        for index, message in enumerate(SOURCE_RESTRICTIONS):
            assert is_first_life_dialogue_control(message), message
            result = send(product, message, f"s121-actual-source-restriction-{index}")
            assert result.status == "failed-closed", message
            assert result.projection.failure_code == "first-life-history-unverified"
            assert not transport.calls
            product = entry.reopen(case)
            continued = send(product, "接着聊画面吧。", f"s121-source-restriction-followup-{index}")
            assert continued.status == "failed-closed", message
            assert not transport.calls
            if index + 1 < len(SOURCE_RESTRICTIONS):
                reset = settle(product.application, product.application.reset_first_life_context(
                    FirstLifeContextResetRequest(f"s121-test-confirmed-reset-{index}", True)))
                assert reset.status == "terminal" and not transport.calls
    finally:
        entry.close()


def test_old_false_positive_failure_remains_failed_and_is_not_exported(tmp_path, monkeypatch):
    import dynamic_subject_agent.first_life_dialogue as module
    transport = SyntheticTransport()
    entry = ReadonlyChatEntry(tmp_path / "entry", live=False, transport=transport)
    case = "objects-and-versions"
    try:
        product = entry.products[case]
        with monkeypatch.context() as patch:
            patch.setattr(module, "is_first_life_dialogue_control", is_dialogue_control)
            failed = send(product, ORIGINAL_QUESTION, "s121-preserved-old-false-positive")
        assert failed.status == "failed-closed" and not transport.calls
        saved = read_history(product)
        product = entry.reopen(case)
        assert read_history(product) == saved
        assert send(product, "接着聊这幅文字构图吧。", "s121-after-old-false-positive").status == "terminal"
        wire = json.loads(transport.calls[-1]["messages"][1]["content"])
        assert wire["exchange"]["dialogue_sources"] == []
        replay = product.application.wait(failed.operation_ref, timeout_seconds=0)
        assert replay.status == "failed-closed"
        assert all(row.user_text != ORIGINAL_QUESTION for row in read_history(product))
    finally:
        entry.close()

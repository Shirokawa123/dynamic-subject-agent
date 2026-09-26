from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_communication_plan import PLAN_POLICY, EXPRESSION_POLICY
from dynamic_subject_agent.local_product import open_character_communication_plan_lab
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelResult, ModelTaskKind, ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
)
from test_character_evidence_model import model_fixture, CandidateTestAdapter


class LocalCommunicationAdapter(ProviderAdapter):
    def __init__(self, kind, value, *, local=True, failure=False, wrong_kind=False):
        self.kind, self.value, self.failure, self.wrong_kind = kind, value, failure, wrong_kind
        self.calls = []
        self.capabilities = ProviderCapabilities("test", "local-communication", local, (StructuredOutputMode.JSON_OBJECT,))

    def invoke(self, task):
        self.calls.append(task)
        assert task.kind is self.kind
        if self.failure:
            raise RuntimeError("SENSITIVE_INTERNAL_DETAIL")
        return ModelResult(ModelTaskKind.CHARACTER_CONTEXT_REPLY if self.wrong_kind else task.kind,
                           self.value(task.payload) if callable(self.value) else self.value)


@pytest.fixture
def communication_fixture(model_fixture):
    draft, create, path, book = model_fixture
    template = draft["assertions"][0]
    draft["assertions"] = [
        dict(template, id="work", dimension="work", statement="只在一次旧合作中缺过资料；不代表一直缺资料。"),
        dict(template, id="view", kind="belief", dimension="values", statement="我相信细节值得留心，但这不是已证实规律。"),
        dict(template, id="unselected", statement="UNSELECTED_PRIVATE_EXPERIENCE"),
        dict(template, id="future", statement="FUTURE_SECRET", event_time="after", knowledge_time="after"),
    ]
    create()
    parent = path.parent / "communication-products"
    options = dict(draft_path=path, source_root=book.parent, reviewed_digest=sha256(path.read_bytes()).hexdigest())
    opened = []
    def open_lab(plan=None, expression=None, *, plan_options=None, expression_options=None):
        planner = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN,
            {"action": "offer_topic", "fact_refs": ["F2", "F1"]} if plan is None else plan, **(plan_options or {}))
        expresser = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION,
            {"reply_text": "这轮想聊聊细节的取舍。", "language": "zh"} if expression is None else expression, **(expression_options or {}))
        product = open_character_communication_plan_lab(parent, **options,
            plan_gateway=ModelGateway(planner), expression_gateway=ModelGateway(expresser))
        opened.append(product)
        return product, planner, expresser
    yield parent, options, open_lab, draft, book
    for product in opened:
        product.close()


def request(message="随便聊点什么？"):
    return CharacterChatContextRequest("self", "start", message, "flat")


def test_facade_preview_exports_exact_planner_input_and_expression_gets_only_full_selected_facts(communication_fixture):
    parent, _, open_lab, draft, _ = communication_fixture
    product, planner, expresser = open_lab()
    app = product.application
    preview = app.preview_character_reply(request())
    assert preview.status == "previewed" and not planner.calls and not expresser.calls
    payload = asdict(preview.projection)
    assert set(payload) == {"self_knowledge", "stage_description", "encounter", "disclosure", "current_message", "policy"}
    assert payload["policy"] == PLAN_POLICY and [fact["label"] for fact in payload["self_knowledge"]] == ["F1", "F2", "F3"]
    assert "context_digest" not in payload and "request_digest" not in payload
    assert "FUTURE_SECRET" not in json.dumps(payload)
    before = {str(path): path.read_bytes() for path in parent.rglob("*") if path.is_file()}
    result = app.propose_character_reply(request())
    after = {str(path): path.read_bytes() for path in parent.rglob("*") if path.is_file()}
    assert before == after
    assert len(planner.calls) == len(expresser.calls) == 1
    assert planner.calls[0].payload == preview.projection
    expression = asdict(expresser.calls[0].payload)
    assert expression["action"] == "offer_topic" and expression["policy"] == EXPRESSION_POLICY
    assert expression["selected_facts"] == (payload["self_knowledge"][1], payload["self_knowledge"][0])
    assert expression["selected_facts"][1]["content"] == draft["assertions"][0]["statement"]
    assert expression["selected_facts"][0]["kind"] == "belief"
    for key in ("stage_description", "encounter", "disclosure", "current_message"):
        assert expression[key] == payload[key]
    assert "UNSELECTED_PRIVATE_EXPERIENCE" not in json.dumps(expression) and "FUTURE_SECRET" not in json.dumps(expression)
    assert result.status == "candidate" and result.semantic_review == "required" and not result.persisted
    assert result.request_digest == preview.request_digest and not result.review_verdict
    product.close()
    assert app.propose_character_reply(request()).status == "unavailable" and len(planner.calls) == 1


@pytest.mark.parametrize("plan", [
    {}, {"action": "recent_activity", "fact_refs": []}, {"action": "new_life_event", "fact_refs": []},
    {"action": "offer_topic", "fact_refs": ["F999"]}, {"action": "answer", "fact_refs": ["F1", "F1"]},
    {"action": "answer", "fact_refs": ["F1", "F2", "F3", "F4", "F5"]},
    {"action": "conditional_view", "fact_refs": [], "current_view": "最近一直思考。"},
    {"action": "answer", "fact_refs": ["F1"], "fact_text": "我刚旅行回来。"},
    {"action": "answer", "fact_refs": "F1"}, {"action": "answer", "fact_refs": [True]},
    {"action": "answer", "fact_refs": [], "context_digest": "old"},
])
def test_invalid_plans_never_call_expression_or_emit_candidate(communication_fixture, plan):
    _, _, open_lab, _, _ = communication_fixture
    product, planner, expresser = open_lab(plan=plan)
    result = product.application.propose_character_reply(request())
    assert result.status == "failed-closed" and result.code == "communication-plan-unavailable"
    assert not result.reply_text and not result.persisted and len(planner.calls) == 1 and not expresser.calls


@pytest.mark.parametrize("action", ["answer", "offer_topic", "conditional_view", "withhold", "clarify"])
def test_current_actions_allow_empty_fact_selection_without_invented_approved_text(communication_fixture, action):
    _, _, open_lab, _, _ = communication_fixture
    product, _, expresser = open_lab(plan={"action": action, "fact_refs": []})
    result = product.application.propose_character_reply(request())
    assert result.status == "candidate" and result.semantic_review == "required"
    assert expresser.calls[0].payload.selected_facts == () and expresser.calls[0].payload.action == action
    assert "self_knowledge" not in asdict(expresser.calls[0].payload)


@pytest.mark.parametrize("which", ["plan", "expression"])
def test_remote_gateways_with_same_task_support_are_rejected_before_any_task(communication_fixture, which):
    parent, options, _, _, _ = communication_fixture
    planner = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN,
        {"action": "answer", "fact_refs": []}, local=which != "plan")
    expresser = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION,
        {"reply_text": "x", "language": "zh"}, local=which != "expression")
    with pytest.raises(ValueError, match="local-only-communication-gateway-required"):
        open_character_communication_plan_lab(parent, **options,
            plan_gateway=ModelGateway(planner), expression_gateway=ModelGateway(expresser))
    assert not planner.calls and not expresser.calls and not parent.exists()


@pytest.mark.parametrize("stage,option", [("plan", "failure"), ("plan", "wrong_kind"), ("expression", "failure"), ("expression", "wrong_kind")])
def test_gateway_failures_are_sanitized_and_not_retried(communication_fixture, stage, option):
    _, _, open_lab, _, _ = communication_fixture
    product, planner, expresser = open_lab(plan_options={option: True} if stage == "plan" else None,
        expression_options={option: True} if stage == "expression" else None)
    result = product.application.propose_character_reply(request())
    assert result.status == "failed-closed" and result.code == f"communication-{stage}-unavailable"
    assert not result.reply_text and "SENSITIVE" not in str(result)
    assert len(planner.calls) == 1 and len(expresser.calls) == (0 if stage == "plan" else 1)


@pytest.mark.parametrize("value", [{}, {"reply_text": "", "language": "zh"}, {"reply_text": "x" * 1201, "language": "zh"},
    {"reply_text": "x", "language": "en"}, {"reply_text": "x", "language": "zh", "state": "new-event"}])
def test_expression_invalid_structure_fails_closed(communication_fixture, value):
    _, _, open_lab, _, _ = communication_fixture
    product, planner, expresser = open_lab(expression=value)
    result = product.application.propose_character_reply(request())
    assert result.status == "failed-closed" and result.code == "communication-expression-unavailable" and not result.reply_text
    assert len(planner.calls) == len(expresser.calls) == 1


def test_valid_plan_does_not_upgrade_violating_free_expression_into_semantic_fact(communication_fixture):
    _, _, open_lab, _, _ = communication_fixture
    violation = "最近我一直在想这些事，昨天还旅行回来。"
    product, _, _ = open_lab(expression={"reply_text": violation, "language": "zh"})
    result = product.application.propose_character_reply(request())
    assert result.reply_text == violation and result.status == "candidate" and result.semantic_review == "required"
    assert not result.persisted and not result.review_verdict and not result.review_issues


def test_same_local_label_rebuilds_current_fact_not_cached_previous_source(communication_fixture):
    _, options, open_lab, draft, _ = communication_fixture
    old = "旧的完整事实，只发生一次。"
    new = "本轮完整新审核事实，仅在明确的旧合作中成立。"
    draft_path = options["draft_path"]
    data = json.loads(draft_path.read_text(encoding="utf-8"))
    data["assertions"][0]["statement"] = old
    draft_path.write_text(json.dumps(data), encoding="utf-8")
    options["reviewed_digest"] = sha256(draft_path.read_bytes()).hexdigest()
    first, _, expression1 = open_lab(plan={"action": "answer", "fact_refs": ["F1"]})
    first_result = first.application.propose_character_reply(request())
    data["assertions"][0]["statement"] = new
    draft_path.write_text(json.dumps(data), encoding="utf-8")
    options["reviewed_digest"] = sha256(draft_path.read_bytes()).hexdigest()
    second, _, expression2 = open_lab(plan={"action": "answer", "fact_refs": ["F1"]})
    second_result = second.application.propose_character_reply(request())
    assert expression1.calls[0].payload.selected_facts[0].content == old
    assert expression2.calls[0].payload.selected_facts[0].content == new
    assert first_result.request_digest != second_result.request_digest


def test_source_changed_after_preview_stops_before_planning_and_default_direct_path_remains(model_fixture):
    from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
    draft, create, path, book = model_fixture
    generator = CandidateTestAdapter.make({"reply_text": "原直接候选。", "language": "zh"})
    direct = create(CharacterReplyLab(ModelGateway(generator)))
    direct_preview = direct.application.preview_character_reply(request())
    assert direct_preview.projection.policy != PLAN_POLICY
    assert direct.application.propose_character_reply(request()).reply_text == "原直接候选。"
    assert len(generator.calls) == 1 and generator.calls[0].kind is ModelTaskKind.CHARACTER_CONTEXT_REPLY
    planner = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, {"action": "answer", "fact_refs": ["F1"]})
    expresser = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, {"reply_text": "x", "language": "zh"})
    with open_character_communication_plan_lab(path.parent / "new-lab", draft_path=path, source_root=book.parent,
        reviewed_digest=sha256(path.read_bytes()).hexdigest(), plan_gateway=ModelGateway(planner), expression_gateway=ModelGateway(expresser)) as product:
        assert product.application.preview_character_reply(request()).status == "previewed"
        book.write_bytes(book.read_bytes() + b"invalid")
        assert product.application.propose_character_reply(request()).status == "failed-closed"
        assert not planner.calls and not expresser.calls


def test_local_substitute_demo_marks_scope_and_shows_rejection_and_unverified_violation(communication_fixture):
    _, options, _, _, _ = communication_fixture
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_communication_plan_demo.py"
    completed = subprocess.run([sys.executable, str(cli), "--draft", str(options["draft_path"]), "--source-root", str(options["source_root"]),
        "--reviewed-digest", options["reviewed_digest"], "--subject", "self", "--anchor", "start", "--context-mode", "flat"],
        capture_output=True, check=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    assert rows[0]["demonstration"] == "本地替身演示" and "不证明真实模型效果" in rows[0]["limitation"]
    assert rows[1]["result"]["status"] == "candidate" and rows[1]["result"]["semantic_review"] == "required"
    assert rows[2]["result"]["status"] == "failed-closed" and rows[2]["expression_calls"] == 0
    assert rows[3]["result"]["reply_text"].startswith("最近我一直") and rows[3]["result"]["semantic_review"] == "required"

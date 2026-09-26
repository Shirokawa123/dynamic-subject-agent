from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.local_product import open_character_personality_lab
from dynamic_subject_agent.model_gateway import ModelTaskKind, ModelGateway
from test_character_evidence_model import model_fixture, organize_fixture
from test_character_communication_plan import LocalCommunicationAdapter


@pytest.fixture
def personality_fixture(model_fixture):
    draft, create, path, book = model_fixture
    organize_fixture(draft); create()
    sidecar = path.parent / "personality.json"
    data = dict(version="character-personality-draft-1", status="local-interpretation-candidates",
        base_reviewed_digest=sha256(path.read_bytes()).hexdigest(), subject_id="self", anchor_id="start",
        items=[dict(id="candidate-private-id", title="创作候选", interpretation="适合的话题可以投入。", when="本轮谈画画。", choice="可以提具体话题。",
                    expression="不要朗读经历摘要。", limits="过去不等于正在开心。", claim_ids=["a", "work"])])
    opened = []
    def open_lab(*, overrides=None, source_changes=None, plan=None, expression=None, local=True, preview_only=False):
        if source_changes: source_changes(draft); create()
        value = {**data, "base_reviewed_digest": sha256(path.read_bytes()).hexdigest(), **(overrides or {})}
        sidecar.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        planner = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN,
            plan or dict(action="offer_topic", fact_refs=[]), local=local)
        expresser = LocalCommunicationAdapter(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION,
            expression or dict(reply_text="当前可以聊一个取舍。", language="zh"), local=local)
        options = {} if preview_only else dict(plan_gateway=ModelGateway(planner), expression_gateway=ModelGateway(expresser))
        product = open_character_personality_lab(path.parent / "personality-products", draft_path=path, source_root=book.parent,
            reviewed_digest=value["base_reviewed_digest"], sidecar_path=sidecar, personality_digest=sha256(sidecar.read_bytes()).hexdigest(), **options)
        opened.append(product)
        return product, planner, expresser, sidecar
    yield draft, path, book, data, open_lab
    for product in opened: product.close()


def req(message="画画之外也可以聊？", mode="flat"):
    return CharacterChatContextRequest("self", "start", message, mode)


def test_core_and_interpretations_stay_in_both_tasks_even_empty_fact_refs_without_raw_ids(personality_fixture):
    _, path, _, _, open_lab = personality_fixture
    product, planner, expresser, _ = open_lab()
    app = product.application
    preview = app.preview_character_reply(req())
    assert preview.status == "previewed" and not planner.calls and not expresser.calls
    assert preview.projection.character_core[0].dimension == "core"
    assert preview.projection.personality[0].basis == "author-interpretation" and preview.projection.personality[0].support_includes_belief
    before = {str(file): file.read_bytes() for file in (path.parent / "personality-products").rglob("*") if file.is_file()}
    result = app.propose_character_reply(req())
    assert result.status == "candidate" and result.semantic_review == "required" and not result.persisted and not result.review_verdict
    assert planner.calls[0].payload == preview.projection
    output = expresser.calls[0].payload
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekCommunicationTrialAdapter
    with pytest.raises(ValueError): DeepSeekCommunicationTrialAdapter.expression_wire(output)
    assert output.conversation.selected_facts == ()
    assert output.character_core == preview.projection.character_core and output.personality == preview.projection.personality
    rendered = json.dumps(asdict(output), ensure_ascii=False)
    for forbidden in ("claim_ids", "candidate-private-id", "core-self", "FUTURE_PRIVATE_SECRET", "evidence_ids", "reviewed_digest", "sample.epub"):
        assert forbidden not in rendered
    assert before == {str(file): file.read_bytes() for file in (path.parent / "personality-products").rglob("*") if file.is_file()}
    other = app.preview_character_reply(req("无关新主题"))
    assert other.projection.character_core == preview.projection.character_core and other.projection.personality == preview.projection.personality
    product.close()
    assert app.propose_character_reply(req()).status == "unavailable"


def test_personality_preview_only_calls_no_gateway_and_legacy_wire_rejects_envelopes(personality_fixture, monkeypatch):
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekCommunicationTrialAdapter
    _, _, _, _, open_lab = personality_fixture
    product, planner, expresser, _ = open_lab(preview_only=True)
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("preview called gateway"))
    preview = product.application.preview_character_reply(req())
    assert preview.status == "previewed"
    assert product.application.propose_character_reply(req()).code == "personality-preview-only"
    with pytest.raises(ValueError): DeepSeekCommunicationTrialAdapter.planning_wire(preview.projection)
    with pytest.raises(ValueError): DeepSeekCommunicationTrialAdapter.expression_wire(preview.projection)
    assert not planner.calls and not expresser.calls


@pytest.mark.parametrize("changed", ["source", "sidecar"])
def test_changed_source_or_sidecar_fails_closed_before_tasks(personality_fixture, changed):
    _, _, book, _, open_lab = personality_fixture
    product, planner, expresser, sidecar = open_lab()
    assert product.application.preview_character_reply(req()).status == "previewed"
    target = book if changed == "source" else sidecar
    target.write_bytes(target.read_bytes() + b"changed")
    result = product.application.propose_character_reply(req())
    assert result.status == "failed-closed" and not planner.calls and not expresser.calls


def test_missing_sidecar_is_unavailable_without_calling_local_tasks(personality_fixture):
    _, _, _, _, open_lab = personality_fixture
    product, planner, expresser, sidecar = open_lab()
    sidecar.rename(sidecar.with_suffix(".withheld"))
    result = product.application.propose_character_reply(req())
    assert result.status == "unavailable" and result.code == "character-personality-sidecar-missing"
    assert not planner.calls and not expresser.calls


@pytest.mark.parametrize("problem", ["future-ref", "unknown-ref", "duplicate-ref", "subject", "anchor", "excess"])
def test_invalid_sidecar_support_binding_or_limit_cannot_reach_planning(personality_fixture, problem):
    _, _, _, data, open_lab = personality_fixture
    overrides = {}
    if problem in ("subject", "anchor"): overrides[problem + "_id"] = "different"
    else:
        items = json.loads(json.dumps(data["items"]))
        if problem == "future-ref": items[0]["claim_ids"] = ["future"]
        elif problem == "unknown-ref": items[0]["claim_ids"] = ["unknown"]
        elif problem == "duplicate-ref": items[0]["claim_ids"] = ["a", "a"]
        else: items[0]["interpretation"] = "字" * 501
        overrides["items"] = items
    product, planner, expresser, _ = open_lab(overrides=overrides)
    assert product.application.propose_character_reply(req()).status == "failed-closed"
    assert not planner.calls and not expresser.calls


def test_local_lab_refuses_remote_capability(personality_fixture):
    _, _, _, _, open_lab = personality_fixture
    with pytest.raises(ValueError, match="local-only-personality-gateway-required"): open_lab(local=False)


@pytest.mark.parametrize("missing", ["stage", "identity", "oversized-core"])
def test_missing_identity_stage_or_oversized_complete_core_is_not_silently_dropped(personality_fixture, missing):
    _, _, _, _, open_lab = personality_fixture
    def change(draft):
        if missing == "stage": draft.pop("chat_stage_description")
        elif missing == "identity": draft["assertions"][0]["dimension"] = "work"
        else:
            draft["chat_organization"]["core"] = [dict(id=f"private-{i}", title="完整核心", content="字" * 4700, claim_ids=["a"]) for i in range(4)]
    product, planner, expresser, _ = open_lab(source_changes=change)
    assert product.application.propose_character_reply(req(mode="auto")).status in ("failed-closed", "unavailable")
    assert not planner.calls and not expresser.calls


def test_identity_fallback_and_failed_or_violating_expression_remains_unverified(personality_fixture):
    _, _, _, _, open_lab = personality_fixture
    def remove_organization(draft): draft.pop("chat_organization")
    product, _, expresser, _ = open_lab(source_changes=remove_organization, expression=dict(reply_text="最近一直在想新作品。", language="zh"))
    preview = product.application.preview_character_reply(req())
    assert all(item.dimension == "identity" for item in preview.projection.character_core)
    result = product.application.propose_character_reply(req())
    assert result.reply_text.startswith("最近一直") and result.semantic_review == "required" and not result.persisted
    expresser.failure = True
    assert product.application.propose_character_reply(req()).code == "personality-expression-unavailable"

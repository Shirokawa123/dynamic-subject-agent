from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dynamic_subject_agent.character_evidence_model import DIMENSIONS, CharacterModelRequest, CharacterContextRequest, CharacterContextView
from dynamic_subject_agent.local_product import open_character_model_preview


@pytest.fixture
def model_fixture(tmp_path, monkeypatch):
    from dynamic_subject_agent.credentials import WindowsCredentialStore
    monkeypatch.setattr(WindowsCredentialStore, "load", lambda *a: pytest.fail("no credential access"))
    sources = tmp_path / "sources"
    sources.mkdir()
    book = sources / "sample.epub"
    content = b"<html><p>reviewed source</p><div>node evidence</div></html>"
    with ZipFile(book, "w") as z:
        z.writestr("ch.html", content)
    ref = dict(id="r1", file=book.name, file_sha256=sha256(book.read_bytes()).hexdigest(), href="ch.html",
               document_sha256=sha256(content).hexdigest(), paragraph=1, quote="reviewed source",
               quote_sha256=sha256(b"reviewed source").hexdigest(), speaker_id="narrator", source_group="main")
    a = dict(id="a", dimension="identity", kind="fact", statement="A reviewed identity fact.",
             about=["self"], knower_id="self", event_time="before", knowledge_time="before",
             review="reviewed", depends_on=[], evidence_ids=["r1"], relation="identity",
             time_basis="Explicit prior background in synthetic source.")
    draft = dict(version="character-evidence-draft-1", status="local-review-only", subject_id="self",
                 anchor=dict(id="start", status="proposed"),
                 chat_stage_description="The reviewed moment before the public exhibition.",
                 entities=[dict(id=i, name=i, kind="person-reference") for i in ("self", "narrator", "other", "hidden")],
                 evidence=[ref], assertions=[a],
                 coverage_review={d:dict(assessment="partial", gaps=["Still incomplete."]) for d in DIMENSIONS})
    path = tmp_path / "draft.json"
    opened = []
    def create(reply_lab=None):
        path.write_text(json.dumps(draft), encoding="utf-8")
        product = open_character_model_preview(tmp_path / "products", draft_path=path, source_root=sources,
                                               reviewed_digest=sha256(path.read_bytes()).hexdigest(), reply_lab=reply_lab)
        opened.append(product)
        return product
    yield draft, create, path, book
    for product in opened:
        product.close()


def preview(product):
    return product.application.preview_character_model(CharacterModelRequest("self", "start"))


def test_retrospective_evidence_can_support_prior_self_knowledge_without_sealing(model_fixture):
    draft, create, _, _ = model_fixture
    # Publication position is not a temporal decision; the reviewed assessment is.
    draft["evidence"][0]["volume"] = 12
    product = create()
    view = preview(product)
    assert view.status == "previewed" and len(view.known) == 1
    assert not view.sealed_from_draft and view.anchor_status == "proposed"
    assert len(view.coverage) == len(DIMENSIONS)
    assert all(row.assessment == "partial" and row.gaps for row in view.coverage)
    assert [entity.entity_id for entity in view.entities] == ["self"]
    item = view.known[0]
    assert item.knower_id == "self" and item.event_time == item.knowledge_time == "before"
    assert item.time_basis and item.depends_on == ()
    citation = next(ref for ref in view.citations if ref.evidence_id == item.evidence_ids[0])
    assert citation.file == "sample.epub" and citation.href == "ch.html" and citation.ordinal == 1
    assert citation.speaker_id == "narrator"


@pytest.mark.parametrize("change,reason", [
    ({"event_time": "after"}, "event-after-anchor"),
    ({"knowledge_time": "after"}, "learned-after-anchor"),
    ({"event_time": "unknown"}, "event-time-unresolved"),
    ({"knowledge_time": "unknown"}, "knowledge-time-unresolved"),
    ({"knower_id": "other"}, "other-perspective"),
    ({"knower_id": "unknown"}, "awareness-unresolved"),
    ({"review": "candidate"}, "unreviewed-claim"),
    ({"kind": "interpretation"}, "interpretation-not-self-knowledge"),
])
def test_event_time_awareness_perspective_and_review_are_independent(model_fixture, change, reason):
    draft, create, _, _ = model_fixture
    draft["assertions"][0].update(change)
    draft["assertions"][0]["about"] = ["self", "hidden"]
    view = preview(create())
    assert view.status == "previewed" and not view.known
    assert view.excluded[0].reason == reason
    assert "hidden" not in [e.entity_id for e in view.entities]


def test_belief_about_someone_else_is_not_their_private_knowledge(model_fixture):
    draft, create, _, _ = model_fixture
    a = draft["assertions"][0]
    a.update(kind="belief", about=["other"], statement="Subject believes this about another person.")
    view = preview(create())
    assert view.known[0].kind == "belief" and view.known[0].about == ("other",)
    # Knowledge holder, not the statement's subject, determines the viewpoint.
    a["knower_id"] = "other"
    assert not preview(create()).known


def test_if_source_and_unavailable_dependencies_cannot_enter_starting_model(model_fixture):
    draft, create, _, _ = model_fixture
    first = draft["assertions"][0]
    first["knowledge_time"] = "unknown"
    draft["assertions"].append(dict(first, id="b", knowledge_time="before", depends_on=["a"]))
    view = preview(create())
    assert [r.reason for r in view.excluded] == ["knowledge-time-unresolved", "basis-not-eligible"]
    draft["evidence"][0]["source_group"] = "if"
    assert all(row.reason == "non-main-source" for row in preview(create()).excluded)


@pytest.mark.parametrize("broken", ["cycle", "entity", "evidence", "coverage", "false-complete"])
def test_invalid_model_is_not_a_partial_success(model_fixture, broken):
    draft, create, _, _ = model_fixture
    if broken == "cycle": draft["assertions"][0]["depends_on"] = ["a"]
    elif broken == "entity": draft["assertions"][0]["about"] = ["missing"]
    elif broken == "evidence": draft["assertions"][0]["evidence_ids"] = ["missing"]
    elif broken == "coverage": draft["coverage_review"].pop("biography")
    else: draft["coverage_review"]["biography"] = dict(assessment="reviewed-adequate", gaps=[])
    view = preview(create())
    assert view.status == "failed-closed" and not view.known


def test_changed_sources_or_draft_do_not_reuse_previous_success(model_fixture):
    draft, create, path, book = model_fixture
    product = create()
    assert preview(product).status == "previewed"
    original = book.read_bytes()
    book.write_bytes(original + b"changed")
    assert preview(product).status == "failed-closed"
    book.write_bytes(original)
    path.write_bytes(path.read_bytes() + b" ")
    assert preview(product).status == "failed-closed"
    path.rename(path.with_suffix(".held"))
    assert preview(product).status == "unavailable"


def test_typed_text_node_evidence_works_without_fake_paragraph_numbers(model_fixture):
    draft, create, _, _ = model_fixture
    ref = draft["evidence"][0]
    ref.pop("paragraph")
    ref.update(locator_kind="html_text_node", text_node=2, quote="node evidence",
               quote_sha256=sha256(b"node evidence").hexdigest())
    assert preview(create()).status == "previewed"


def test_subject_anchor_lifecycle_and_canonical_no_write(model_fixture):
    draft, create, path, _ = model_fixture
    product = create()
    app = product.application
    root = path.parent / "products"
    def snapshot():
        return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    before = snapshot()
    assert preview(product).status == "previewed"
    assert app.preview_character_model(CharacterModelRequest("other", "start")).status == "rejected"
    assert app.preview_character_model(CharacterModelRequest("self", "later")).status == "rejected"
    assert snapshot() == before
    assert app.character_dialogue_status().status == "unavailable"
    product.close()
    assert preview(product).status == "unavailable"


def test_context_returns_whole_adjacent_paragraphs_and_document_boundaries(model_fixture):
    draft, create, _, book = model_fixture
    content = b"<p>previous context</p><p>reviewed source</p><p>following context</p>"
    with ZipFile(book, "w") as z:
        z.writestr("ch.html", content)
        z.writestr("next.html", b"<p>must not cross documents</p>")
    draft["evidence"][0].update(paragraph=2, file_sha256=sha256(book.read_bytes()).hexdigest(),
                                document_sha256=sha256(content).hexdigest())
    product = create()
    result = product.application.preview_character_model(CharacterContextRequest("self","start","r1",20,20))
    assert result.status == "previewed"
    assert [r.text for r in result.units] == ["previous context","reviewed source","following context"]
    assert [r.is_cited for r in result.units] == [False,True,False]
    assert result.document_start and result.document_end
    assert result.citation.ordinal == 2 and result.citation.href == "ch.html"
    product.close()
    closed = product.application.preview_character_model(CharacterContextRequest("self","start","r1"))
    assert type(closed) is CharacterContextView and closed.status == "unavailable"


def test_context_keeps_typed_text_node_positions(model_fixture):
    draft, create, _, _ = model_fixture
    ref = draft["evidence"][0]
    ref.pop("paragraph")
    ref.update(locator_kind="html_text_node",text_node=2,quote="node evidence",quote_sha256=sha256(b"node evidence").hexdigest())
    result = create().application.preview_character_model(CharacterContextRequest("self","start","r1",1,0))
    assert result.citation.locator_kind == "html_text_node"
    assert [(r.ordinal,r.text) for r in result.units] == [(1,"reviewed source"),(2,"node evidence")]


def test_context_invalid_request_and_changed_source_are_not_empty_success(model_fixture):
    draft, create, _, book = model_fixture
    product = create();app = product.application
    for request in (CharacterContextRequest("self","start","r1",-1,0),
                    CharacterContextRequest("self","start","r1",21,0),
                    CharacterContextRequest("self","start","r1",True,0),
                    CharacterContextRequest("other","start","r1"),
                    CharacterContextRequest("self","start","missing")):
        assert app.preview_character_model(request).status == "rejected"
    book.write_bytes(book.read_bytes()+b"changed")
    result = app.preview_character_model(CharacterContextRequest("self","start","r1"))
    assert result.status == "failed-closed" and not result.units


def test_context_rejects_oversized_window_instead_of_truncating(model_fixture):
    draft, create, _, book = model_fixture
    content=("<p>reviewed source</p><p>"+"x"*6000+"</p>").encode()
    with ZipFile(book,"w") as z:z.writestr("ch.html",content)
    draft["evidence"][0].update(file_sha256=sha256(book.read_bytes()).hexdigest(),document_sha256=sha256(content).hexdigest())
    app=create().application
    result=app.preview_character_model(CharacterContextRequest("self","start","r1",0,1))
    assert result.code == "context-window-too-large" and not result.units
    assert app.preview_character_model(CharacterContextRequest("self","start","r1",0,0)).status == "previewed"


def test_chat_context_keeps_same_self_knowledge_across_topics_and_user_claims(model_fixture, monkeypatch):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    from dynamic_subject_agent.model_gateway import ModelGateway
    monkeypatch.setattr(ModelGateway, "execute", lambda *a, **kw: pytest.fail("offline preview called model"))
    draft, create, _, _ = model_fixture
    draft["assertions"].append(dict(draft["assertions"][0], id="past", dimension="biography",
                                    statement="Previously learned an art skill.", kind="belief"))
    app = create().application
    first = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "你好，你是谁？"))
    second = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "我都知道，你昨晚和我出去了。"))
    assert first.status == second.status == "previewed"
    assert first.self_knowledge == second.self_knowledge and len(first.self_knowledge) == 2
    assert second.self_knowledge[1].kind == "belief"
    assert second.current_message == "我都知道，你昨晚和我出去了。"
    assert second.encounter == first.encounter and second.encounter.status == "proposed-branch"
    assert "用户保持现实身份" in second.encounter.world_context
    assert "不预知用户看过她的故事" in second.encounter.world_context
    assert second.history_status == "not-connected" and not second.can_chat and not second.provider_ready
    assert not any("昨晚" in item.content for item in second.self_knowledge)


def test_chat_context_does_not_copy_future_identity_or_author_metadata(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    draft["assertions"][0]["time_basis"] = "FUTURE_SECRET_MAPPING appears only in author reasoning."
    draft["entities"][0]["name"] = "PRIVATE_ENTITY_LABEL"
    draft["assertions"].append(dict(draft["assertions"][0], id="future", statement="FUTURE_SECRET_MAPPING",
                                    knowledge_time="after"))
    view = create().application.preview_character_chat_context(CharacterChatContextRequest("self", "start", "聊聊工作"))
    wire = json.dumps(asdict(view), ensure_ascii=False)
    assert view.status == "previewed" and len(view.self_knowledge) == 1
    for forbidden in ("FUTURE_SECRET_MAPPING", "PRIVATE_ENTITY_LABEL", "sample.epub", "ch.html",
                      "reviewed source", "evidence_ids", "time_basis", "draft_digest"):
        assert forbidden not in wire
    assert "真名" in view.encounter.public_identity and "未设定公开" in view.encounter.public_identity


def test_chat_context_validates_message_source_anchor_and_lifecycle(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    _, create, path, _ = model_fixture
    product = create(); app = product.application
    for request in ({}, CharacterChatContextRequest("self", "start", " "),
                    CharacterChatContextRequest("self", "start", "x" * 1001),
                    CharacterChatContextRequest("self", "start", None),
                    CharacterChatContextRequest("other", "start", "hi")):
        assert app.preview_character_chat_context(request).status == "rejected"
    path.write_text("corrupted", encoding="utf-8")
    invalid = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "hi"))
    assert invalid.status == "failed-closed" and not invalid.self_knowledge and not invalid.current_message
    product.close()
    assert app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "hi")).status == "unavailable"


def test_chat_context_refuses_empty_or_oversized_basis_instead_of_partial_persona(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    draft["assertions"][0]["knowledge_time"] = "unknown"
    view = create().application.preview_character_chat_context(CharacterChatContextRequest("self", "start", "hi"))
    assert view.status == "unavailable" and view.code == "no-eligible-self-knowledge"
    draft["assertions"][0]["knowledge_time"] = "before"
    template = draft["assertions"][0]
    draft["assertions"] = [dict(template, id=f"a{i}", statement="长" * 1400) for i in range(20)]
    view = create().application.preview_character_chat_context(CharacterChatContextRequest("self", "start", "hi"))
    assert view.status == "rejected" and view.code == "self-knowledge-too-large" and not view.self_knowledge


def test_chat_stage_is_explicit_reviewed_text_not_author_anchor_notes(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    draft["anchor"]["description"] = "AUTHOR_SECRET_FUTURE_MAPPING"
    app = create().application
    view = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "hi"))
    assert view.stage_description == draft["chat_stage_description"]
    assert "AUTHOR_SECRET" not in json.dumps(asdict(view))
    del draft["chat_stage_description"]
    app = create().application
    assert app.preview_character_model(CharacterModelRequest("self", "start")).status == "previewed"
    view = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "hi"))
    assert view.status == "unavailable" and view.code == "chat-stage-not-reviewed"
    assert not view.self_knowledge and view.opening is None


@pytest.mark.parametrize("stage", [None, " ", "x" * 501])
def test_invalid_chat_stage_fails_closed_with_reviewed_digest(model_fixture, stage):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    draft["chat_stage_description"] = stage
    view = create().application.preview_character_chat_context(CharacterChatContextRequest("self", "start", "hi"))
    assert view.status == "failed-closed" and not view.stage_description


def test_public_opening_is_derived_from_encounter_not_private_character_facts(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    draft["assertions"][0]["statement"] = "PRIVATE_FAMILY_NAME_AND_JOB"
    view = create().application.preview_character_chat_context(CharacterChatContextRequest("self", "start", "PRIVATE_USER_MESSAGE"))
    public = json.dumps(asdict(view.opening), ensure_ascii=False)
    assert "PRIVATE" not in public
    assert view.opening.channel == view.encounter.channel
    assert view.opening.visible_interests == view.encounter.public_interests
    assert all(tag in view.opening.recommendation for tag in view.encounter.public_interests)
    assert "助手提出的分支动机" in view.encounter.proposed_motive
    assert "助手提出的时间安放" in view.encounter.proposed_timing
    assert not view.can_chat and not view.provider_ready


class CandidateTestAdapter:
    @staticmethod
    def make(value=None, fail=False, local=True, wrong_kind=False):
        from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelResult, ModelTaskKind
        class Adapter(ProviderAdapter):
            capabilities = ProviderCapabilities("test", "candidate", local, (StructuredOutputMode.JSON_OBJECT,))
            def __init__(self): self.calls = []
            def invoke(self, task):
                self.calls.append(task)
                if fail: raise RuntimeError("sensitive adapter detail")
                return ModelResult(ModelTaskKind.CHARACTER_DIALOGUE_REPLY if wrong_kind else task.kind, value)
        return Adapter()


def test_reply_candidate_uses_exact_projection_through_facade_without_persistence(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelTaskKind
    draft, create, _, _ = model_fixture
    adapter = CandidateTestAdapter.make({"reply_text":"这是离线替身的候选。", "language":"zh"})
    product = create(CharacterReplyLab(ModelGateway(adapter)));app=product.application
    request=CharacterChatContextRequest("self","start","聊聊画画")
    preview=app.preview_character_reply(request)
    assert not adapter.calls and preview.status=="previewed"
    result=app.propose_character_reply(request)
    assert result.status=="candidate" and result.semantic_review=="required" and not result.persisted
    assert len(adapter.calls)==1 and adapter.calls[0].kind is ModelTaskKind.CHARACTER_CONTEXT_REPLY
    assert adapter.calls[0].payload==preview.projection and result.request_digest==preview.request_digest
    payload=asdict(preview.projection)
    assert set(payload)=={"self_knowledge","stage_description","encounter","disclosure","current_message","policy"}
    assert preview.projection.self_knowledge[0].content==draft["assertions"][0]["statement"]
    assert app.preview_character_reply(request)==preview
    product.close()
    assert app.propose_character_reply(request).status=="unavailable" and len(adapter.calls)==1


@pytest.mark.parametrize("value", [None, {}, {"reply_text":"x", "language":"en"},
    {"reply_text":" ", "language":"zh"}, {"reply_text":"x"*1201,"language":"zh"},
    {"reply_text":"x","language":"zh","memory_update":"bad"}])
def test_reply_candidate_rejects_bad_or_state_bearing_output(model_fixture, value):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
    from dynamic_subject_agent.model_gateway import ModelGateway
    _,create,_,_=model_fixture;adapter=CandidateTestAdapter.make(value)
    app=create(CharacterReplyLab(ModelGateway(adapter))).application
    view=app.propose_character_reply(CharacterChatContextRequest("self","start","hi"))
    assert view.status=="failed-closed" and not view.reply_text and len(adapter.calls)==1


def test_candidate_lab_failure_no_retry_and_source_recheck(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
    from dynamic_subject_agent.model_gateway import ModelGateway
    _,create,path,_=model_fixture
    for options in ({"fail":True}, {"wrong_kind":True}):
        adapter=CandidateTestAdapter.make(**options)
        app=create(CharacterReplyLab(ModelGateway(adapter))).application
        request=CharacterChatContextRequest("self","start","hi")
        view=app.propose_character_reply(request)
        assert view.status=="failed-closed" and "sensitive" not in str(view) and len(adapter.calls)==1
        path.write_text("changed",encoding="utf-8")
        assert app.propose_character_reply(request).status=="failed-closed" and len(adapter.calls)==1


def test_candidate_lab_is_unavailable_by_default_and_refuses_remote(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
    from dynamic_subject_agent.model_gateway import ModelGateway
    _,create,_,_=model_fixture
    assert create().application.propose_character_reply(CharacterChatContextRequest("self","start","hi")).status=="unavailable"
    with pytest.raises(ValueError): CharacterReplyLab(ModelGateway(CandidateTestAdapter.make(local=False)))


def organize_fixture(draft):
    template = draft["assertions"][0]
    draft["assertions"].extend([
        dict(template, id="art", dimension="biography", statement="小时候母亲教我画画。"),
        dict(template, id="work", dimension="work", statement="我做过插画，也会担心期限。", kind="belief"),
        dict(template, id="future", statement="FUTURE_PRIVATE_SECRET", knowledge_time="after"),
    ])
    draft["chat_organization"] = dict(
        version="character-chat-organization-1", subject_id="self", anchor_id="start",
        core=[dict(id="core-self", title="自我认识", content="我在意创作，也愿意听取不同看法。", claim_ids=["a"])],
        episodes=[dict(id="child-art", title="学画的经历", content="小时候母亲教我画画。", claim_ids=["art"],
                       cues=["画画", "学画", "小时候", "母亲"])],
        details=[dict(id="work-detail", title="创作的压力", content="我做过插画，也会担心期限。",
                      claim_ids=["work"], cues=["截止", "交稿", "赶稿"])])


def test_organized_core_persists_and_relevant_experiences_change_in_final_reply(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    app = create().application
    art = app.preview_character_reply(CharacterChatContextRequest("self", "start", "你小时候怎么学画的？"))
    work = app.preview_character_reply(CharacterChatContextRequest("self", "start", "我今晚得赶稿，压力很大"))
    unrelated = app.preview_character_reply(CharacterChatContextRequest("self", "start", "今天天气真好"))
    assert art.status == work.status == unrelated.status == "previewed"
    assert art.projection.self_knowledge[0] == work.projection.self_knowledge[0] == unrelated.projection.self_knowledge[0]
    assert [item.dimension for item in art.projection.self_knowledge] == ["core", "episode"]
    assert [item.dimension for item in work.projection.self_knowledge] == ["core", "detail"]
    assert work.projection.self_knowledge[1].kind == "belief"
    assert len(unrelated.projection.self_knowledge) == 1
    assert "不表示本人不知道" in unrelated.projection.policy
    assert len({art.request_digest, work.request_digest, unrelated.request_digest}) == 3
    local = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "今晚得赶稿"))
    selected = next(row for row in local.selection.units if row.unit_id == "work-detail")
    assert selected.claim_ids == ("work",) and selected.matched_terms == ("赶稿",) and selected.decision == "included"


def test_explicit_flat_baseline_matches_legacy_projection_and_missing_organization_is_distinct(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    organized_app = create().application
    message = "想聊聊画画"
    flat = organized_app.preview_character_reply(CharacterChatContextRequest("self", "start", message, "flat"))
    assert len(flat.projection.self_knowledge) == 3
    draft.pop("chat_organization")
    old_app = create().application
    old = old_app.preview_character_reply(CharacterChatContextRequest("self", "start", message))
    assert old == flat  # Includes the exact old policy and request fingerprint.
    missing = old_app.preview_character_chat_context(CharacterChatContextRequest("self", "start", message, "organized"))
    assert missing.status == "unavailable" and missing.code == "chat-organization-not-reviewed"


@pytest.mark.parametrize("basis", ["missing", "future", "other-view", "derived", "core-self"])
def test_invalid_organization_basis_fails_before_selection_even_for_flat(model_fixture, basis):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    template = draft["assertions"][0]
    draft["assertions"].extend([
        dict(template, id="other-view", knower_id="other"),
        dict(template, id="derived", depends_on=["future"]),
    ])
    draft["chat_organization"]["details"][0]["claim_ids"] = [basis]
    app = create().application
    for mode in ("auto", "organized", "flat"):
        result = app.preview_character_reply(CharacterChatContextRequest("self", "start", "无关天气", mode))
        assert result.status == "failed-closed" and result.code == "chat-organization-invalid" and result.projection is None


@pytest.mark.parametrize("invalid", ["null", "anchor", "empty-core", "duplicate-id", "cycle"])
def test_organization_corruption_and_cyclic_claims_are_not_missing_configuration(model_fixture, invalid):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    org = draft["chat_organization"]
    if invalid == "null": draft["chat_organization"] = None
    elif invalid == "anchor": org["anchor_id"] = "later"
    elif invalid == "empty-core": org["core"] = []
    elif invalid == "duplicate-id": org["details"][0]["id"] = "core-self"
    else: draft["assertions"][0]["depends_on"] = ["a"]
    result = create().application.preview_character_reply(CharacterChatContextRequest("self", "start", "画画"))
    assert result.status == "failed-closed" and result.projection is None


def test_actual_json_budget_keeps_whole_core_and_reports_unselected_material(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    draft["chat_organization"]["core"][0]["content"] = '创作"\\\n' * 20
    app = create().application
    core = app.preview_character_reply(CharacterChatContextRequest("self", "start", "天气"))
    actual = len(json.dumps([asdict(row) for row in core.projection.self_knowledge], ensure_ascii=False,
                           sort_keys=True, separators=(",", ":")))
    exact = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "画画", "organized", actual))
    assert exact.status == "previewed" and exact.selection.knowledge_chars == actual
    assert exact.self_knowledge == core.projection.self_knowledge
    assert any(row.decision == "material-budget" for row in exact.selection.units)
    smaller = app.preview_character_reply(CharacterChatContextRequest("self", "start", "画画", "organized", actual - 1))
    assert smaller.status == "rejected" and smaller.code == "organized-core-too-large" and smaller.projection is None


@pytest.mark.parametrize("mode,budget", [("bad", 20000), (None, 20000), ("auto", True), ("auto", 0),
                                       ("auto", -1), ("auto", 20001), ("auto", 10.0)])
def test_facade_rejects_invalid_context_mode_and_budget(model_fixture, mode, budget):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    _, create, _, _ = model_fixture
    result = create().application.preview_character_reply(CharacterChatContextRequest("self", "start", "你好", mode, budget))
    assert result.status == "rejected" and result.projection is None


def test_text_matching_supports_short_chinese_and_related_limit_without_duplicate_core_detail(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    org = draft["chat_organization"]
    org["episodes"][0].pop("cues")
    org["details"] = [dict(id=f"detail-{i}", title="学画小事", content="画画是投入的事情。", claim_ids=["work"])
                      for i in range(8)]
    org["details"].append(dict(id="duplicate-core", title="画画", content=org["core"][0]["content"], claim_ids=["a"]))
    app = create().application
    result = app.preview_character_chat_context(CharacterChatContextRequest("self", "start", "画画"))
    assert len(result.self_knowledge) == 7  # All core + six bounded related units.
    assert sum(row.decision == "included" for row in result.selection.units) == 6
    assert any(row.matched_terms == ("画画",) for row in result.selection.units)
    assert next(row for row in result.selection.units if row.unit_id == "duplicate-core").decision == "content-already-in-core"
    assert any(row.decision == "related-unit-limit" for row in result.selection.units)


def test_compressed_core_does_not_hide_more_specific_detail_with_the_same_claim(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    org = draft["chat_organization"]
    org["core"][0]["claim_ids"] = ["art"]
    org["core"][0]["content"] = "我的绘画兴趣与童年有关。"
    org["details"] = [dict(id="specific", title="童年学画", content="小时候母亲教我画画。", claim_ids=["art"], cues=["母亲"])]
    result = create().application.preview_character_reply(CharacterChatContextRequest("self", "start", "是母亲教你的吗？"))
    assert result.status == "previewed"
    assert any(item.dimension == "detail" and "母亲教我" in item.content for item in result.projection.self_knowledge)


def test_incidental_single_chinese_bigram_does_not_select_an_unrelated_episode(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    draft["chat_organization"]["episodes"][0].update(title="亲人的关系", content="母亲曾经教我画画。", cues=[])
    app = create().application
    weak = app.preview_character_reply(CharacterChatContextRequest("self", "start", "杯子与昨天的关系是什么？"))
    strong = app.preview_character_reply(CharacterChatContextRequest("self", "start", "母亲曾经教你的是什么？"))
    assert len(weak.projection.self_knowledge) == 1
    assert any(row.dimension == "episode" for row in strong.projection.self_knowledge)


def test_short_chinese_topic_punctuation_is_equivalent_without_weakening_long_queries(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    draft, create, _, _ = model_fixture
    organize_fixture(draft)
    org = draft["chat_organization"]
    org["episodes"] = []
    org["details"] = [dict(id="short-topic", title="投入", content="画画让我投入。", claim_ids=["art"])]
    app = create().application
    baseline = app.preview_character_reply(CharacterChatContextRequest("self", "start", "画画"))
    assert len(baseline.projection.self_knowledge) == 2
    for message in ("画画？", "画画。", "画画！", " 画画? ", "“画画”？"):
        result = app.preview_character_reply(CharacterChatContextRequest("self", "start", message))
        assert result.status == "previewed"
        assert result.projection.self_knowledge == baseline.projection.self_knowledge
        assert result.projection.current_message == message
    for message in ("杯子和画画有何联系？", "画？画"):
        result = app.preview_character_reply(CharacterChatContextRequest("self", "start", message))
        assert result.status == "previewed" and len(result.projection.self_knowledge) == 1


def test_organized_projection_is_exact_local_candidate_input_without_audit_or_excluded_leaks(model_fixture):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
    from dynamic_subject_agent.model_gateway import ModelGateway
    draft, create, path, _ = model_fixture
    organize_fixture(draft)
    adapter = CandidateTestAdapter.make({"reply_text": "画画时我也会在意不同的看法。", "language": "zh"})
    app = create(CharacterReplyLab(ModelGateway(adapter))).application
    request = CharacterChatContextRequest("self", "start", "画画")
    previewed = app.preview_character_reply(request)
    result = app.propose_character_reply(request)
    assert result.status == "candidate" and result.request_digest == previewed.request_digest
    assert adapter.calls[0].payload == previewed.projection
    wire = json.dumps(asdict(adapter.calls[0].payload), ensure_ascii=False)
    for forbidden in ("claim_ids", "unit_id", "core-self", "child-art", "work-detail", "selection", "reviewed_digest",
                      "sample.epub", "ch.html", "reviewed source", "FUTURE_PRIVATE_SECRET", "time_basis", "evidence_ids"):
        assert forbidden not in wire
    path.write_bytes(path.read_bytes() + b" ")
    assert app.propose_character_reply(request).status == "failed-closed" and len(adapter.calls) == 1


def test_existing_cli_can_preview_organized_reply_and_explicit_flat_comparison(model_fixture):
    import os
    import subprocess
    import sys
    draft, create, path, book = model_fixture
    organize_fixture(draft)
    create()
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_model_preview.py"
    base = [sys.executable, str(cli), "--draft", str(path), "--source-root", str(book.parent),
            "--reviewed-digest", sha256(path.read_bytes()).hexdigest(), "--subject", "self", "--anchor", "start",
            "--reply-request", "画画"]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    organized = subprocess.run([*base, "--context-mode", "organized"], check=True, capture_output=True, encoding="utf-8", env=env)
    flat = subprocess.run([*base, "--context-mode", "flat"], check=True, capture_output=True, encoding="utf-8", env=env)
    one, two = json.loads(organized.stdout), json.loads(flat.stdout)
    assert one["status"] == two["status"] == "previewed"
    assert one["projection"]["self_knowledge"][0]["dimension"] == "core"
    assert len(one["projection"]["self_knowledge"]) == 2 and len(two["projection"]["self_knowledge"]) == 3

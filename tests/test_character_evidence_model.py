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
    def create():
        path.write_text(json.dumps(draft), encoding="utf-8")
        product = open_character_model_preview(tmp_path / "products", draft_path=path, source_root=sources,
                                               reviewed_digest=sha256(path.read_bytes()).hexdigest())
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

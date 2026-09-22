from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dynamic_subject_agent.character_evidence_model import DIMENSIONS, CharacterModelRequest
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

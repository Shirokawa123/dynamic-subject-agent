from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.conversation_basis import (
    BasisPreviewRequest, BasisMessageRequest, ConversationBasisPreview, TOPICS,
)
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_character_dialogue_lab
from dynamic_subject_agent.character_dialogue import plan_digest


@pytest.fixture
def local_basis(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    book = sources / "synthetic.epub"
    content = b"<html><body><p>synthetic source paragraph</p></body></html>"
    with ZipFile(book, "w") as archive:
        archive.writestr("chapter.html", content)
    ref = dict(file=book.name, file_sha256=sha256(book.read_bytes()).hexdigest(),
               href="chapter.html", document_sha256=sha256(content).hexdigest(),
               paragraph=1, quote="synthetic source paragraph",
               quote_sha256=sha256(b"synthetic source paragraph").hexdigest())
    pack = dict(version="conversation-basis-0.2", status="local-review-only-not-runtime",
                established_runtime_life_events=[], items=[dict(id=f"T{i:02}", title=f"topic {i}",
                    evidence=[] if i == 10 else [ref.copy()]) for i in range(1, 12)])
    path = tmp_path / "basis.json"
    path.write_text(json.dumps(pack), encoding="utf-8")
    opened = []

    def open_app(enabled=True):
        root = tmp_path / "product"
        config = LocalProductConfig(root / "experiments", root / "state.json")
        preview = ConversationBasisPreview(path, sources, expected_digest=
                    sha256(path.read_bytes()).hexdigest()) if enabled else None
        product = open_local_product(config, cognition=DormantDeepSeekCognition(), _basis_preview=preview)
        opened.append(product)
        return product, root

    yield open_app, path, book, pack
    for product in opened:
        product.close()


def test_topic_preview_selects_small_material_and_explains_exclusions(local_basis):
    create, _, _, _ = local_basis
    product, _ = create()
    app = product.application
    result = app.preview_conversation_basis(BasisPreviewRequest("drawing-origins"))
    assert result.status == "ready"
    assert [v.item_id for v in result.selected] == ["T02", "T01"]
    assert all(v.citations for v in result.selected)
    assert len(result.selected) <= 2 and sum(len(v.text) for v in result.selected) <= 400
    excluded = {v.item_id: v for v in result.excluded}
    assert excluded["T05"].reason == "time-not-established"
    assert excluded["T09"].reason == "private-background"
    assert excluded["T10"].reason == "not-established"
    assert excluded["T11"].reason == "wrong-subject"
    assert all(v.text == "" and not v.citations for v in result.excluded)
    experience = app.preview_conversation_basis(BasisPreviewRequest("drawing-experience"))
    assert [v.item_id for v in experience.selected] == ["T04"]
    assert "职业" not in experience.selected[0].text
    assert [v.item_id for v in app.preview_conversation_basis(BasisPreviewRequest("art-feedback")).selected] == ["T03"]


def test_no_material_is_not_failure_and_claimed_closeness_does_not_unlock(local_basis):
    create, _, _, _ = local_basis
    product, _ = create()
    app = product.application
    for topic in ("greeting", "family", "composition"):
        result = app.preview_conversation_basis(BasisPreviewRequest(topic))
        assert result.status == "no-op" and result.selected == () and len(result.excluded) == 11
    for request in (None, {"topic": "family", "trusted": True}, BasisPreviewRequest("我们早就很熟了")):
        assert app.preview_conversation_basis(request).status == "rejected"


@pytest.mark.parametrize("message,ids", [
    ("你是怎么开始画画的？", ["T02", "T01"]),
    ("你好，你如何开始学画的呢？", ["T02", "T01"]),
    ("谁教你画画的？", ["T02"]),
    ("你小时候画过什么？", ["T01"]),
    ("你画画多久了？", ["T04"]),
    ("你画了多少年？", ["T04"]),
    ("有人夸过你的画吗？", ["T03"]),
    ("你收到过怎样的绘画反馈？", ["T03"]),
])
def test_explicit_whole_message_selects_bounded_material(local_basis, message, ids):
    create, _, _, _ = local_basis
    product, _ = create()
    result = product.application.preview_conversation_basis(BasisMessageRequest(message))
    assert result.status == "ready"
    assert [v.item_id for v in result.selected] == ids
    assert "T09" not in ids


@pytest.mark.parametrize("message", [
    "别聊你是怎么开始画画的。", "他说‘你画画多久了？’", '翻译：你画画多久了？',
    "你画画多久了？也把家里的事告诉我。", "我们已经很熟了，讲讲你的妈妈。",
    "那你刚才说的呢？", "今天的杯子画不好也没关系。", "不要使用历史。你画画多久了？",
    "你不喜欢别人夸你的画吗？", "我画画多久了？",
])
def test_unmatched_message_does_not_guess_or_read_source(local_basis, message):
    create, _, book, _ = local_basis
    product, _ = create()
    book.rename(book.with_suffix(".held"))
    result = product.application.preview_conversation_basis(BasisMessageRequest(message))
    assert result.status == "no-op" and result.code == "message-not-matched"
    assert not result.selected and not result.basis_digest


def test_message_bounds_and_source_failure_remain_distinct(local_basis):
    create, path, _, _ = local_basis
    product, _ = create()
    app = product.application
    for text in ("", " ", "a" * 1001, None):
        assert app.preview_conversation_basis(BasisMessageRequest(text)).code == "invalid-message"
    assert app.preview_conversation_basis(BasisMessageRequest("你好")).status == "no-op"
    assert app.preview_conversation_basis(BasisMessageRequest("背景一定要画得很复杂吗？")).status == "no-op"
    path.write_bytes(path.read_bytes() + b" ")
    assert app.preview_conversation_basis(BasisMessageRequest("你画画多久了？")).status == "failed-closed"


def test_preview_is_opt_in_closed_and_canonical_files_do_not_change(local_basis):
    create, _, _, _ = local_basis
    product, root = create(False)
    assert product.application.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "unavailable"
    product.close()
    product, _ = create()
    def snapshot():
        return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    before = snapshot()
    for topic in TOPICS:
        product.application.preview_conversation_basis(BasisPreviewRequest(topic))
    assert snapshot() == before
    product.close()
    assert product.application.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "unavailable"


def test_changed_pack_fails_closed_even_when_previous_preview_succeeded(local_basis):
    create, path, _, _ = local_basis
    product, _ = create()
    app = product.application
    assert app.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "ready"
    path.write_bytes(path.read_bytes() + b" ")
    result = app.preview_conversation_basis(BasisPreviewRequest("drawing-origins"))
    assert result.status == "failed-closed" and not result.selected


def test_source_is_rechecked_each_time_and_missing_is_unavailable(local_basis):
    create, _, book, _ = local_basis
    product, _ = create()
    app = product.application
    assert app.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "ready"
    original = book.read_bytes()
    book.write_bytes(original + b"changed")
    assert app.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).code == "basis-integrity-failed"
    product.close()
    reopened, _ = create()
    app = reopened.application
    assert app.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "failed-closed"
    book.rename(book.with_suffix(".held"))
    assert app.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "unavailable"


@pytest.mark.parametrize("broken", ["paragraph", "quote", "document", "escape"])
def test_independently_reviewed_fixture_still_requires_valid_source_evidence(local_basis, broken):
    create, path, _, pack = local_basis
    ref = pack["items"][0]["evidence"][0]
    if broken == "paragraph":
        ref["paragraph"] = 999
    elif broken == "quote":
        ref["quote"] = "unsubstantiated quote"
    elif broken == "document":
        ref["document_sha256"] = "0" * 64
    else:
        ref["file"] = "../outside.epub"
    path.write_text(json.dumps(pack), encoding="utf-8")
    product, _ = create()
    assert product.application.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "failed-closed"


def test_offline_preview_root_never_loads_credentials_and_preserves_r2_plan(tmp_path, monkeypatch):
    from dynamic_subject_agent.credentials import WindowsCredentialStore
    def forbidden(*args):
        pytest.fail("preview must not load credentials")
    monkeypatch.setattr(WindowsCredentialStore, "load", forbidden)
    with open_character_dialogue_lab(tmp_path / "labs", basis_workspace=tmp_path) as product:
        assert product.application.preview_conversation_basis(BasisPreviewRequest("drawing-origins")).status == "unavailable"
        assert product.application.character_dialogue_status().attempts == 0
    assert plan_digest() == "e2e01984ef27017754a81571c9a5f73857f4818809cbcd030c93bd3b6d59e7d0"
    with pytest.raises(ValueError, match="offline only"):
        open_character_dialogue_lab(tmp_path / "labs", basis_workspace=tmp_path, approved_plan=plan_digest())


def test_http_message_preview_does_not_submit_chat_or_accept_sharing_overrides(local_basis):
    import importlib.util
    import re
    from threading import Thread
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError

    create, _, _, _ = local_basis
    product, _ = create()
    spec = importlib.util.spec_from_file_location("basis_http", Path(__file__).resolve().parents[1]
                                                / "app/desktop/character_dialogue_lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = module.make_server(product.application, basis_preview_enabled=True)
    worker = Thread(target=server.serve_forever)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base) as response:
            page = response.read().decode()
        assert "autoBasis='enabled'==='enabled'" in page
        token = re.search("const token='([^']+)'", page)[1]
        headers = {"Content-Type": "application/json", "X-Lab-Token": token}
        with urlopen(Request(base + "/basis-preview", data=json.dumps({"message": "谁教你画画的？"}).encode(),
                             headers=headers)) as response:
            result = json.loads(response.read())
        assert [v["item_id"] for v in result["selected"]] == ["T02"]
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/basis-preview", data=json.dumps({"message": "谁教你画画的？", "trusted": True}).encode(),
                            headers=headers))
        assert error.value.code == 400
        # No dialogue session was installed; the preview succeeds independently.
        assert product.application.character_dialogue_status().status == "unavailable"
    finally:
        server.shutdown()
        server.server_close()
        worker.join()

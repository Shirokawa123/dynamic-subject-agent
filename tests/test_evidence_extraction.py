from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.evidence_extraction import EvidenceExtractionLab, EvidenceExtractionRequest, EXTRACTION_POLICY, extraction_plan_digest
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_evidence_extraction_lab
from dynamic_subject_agent.model_gateway import ModelGateway, ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelResult
from dynamic_subject_agent.evidence_extraction_provider import DeepSeekEvidenceAdapter
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse, DEEPSEEK_MODEL, DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID


def candidate():
    return dict(statement="A synthetic proposed memory.", dimension="biography", kind="fact", about=["subject"],
                evidence=[dict(label="p1", quote="synthetic source")])


class Adapter(ProviderAdapter):
    capabilities = ProviderCapabilities("offline", "fixture", True, (StructuredOutputMode.JSON_OBJECT,))
    def __init__(self):
        self.calls = []
        self.value = {"candidates": [candidate()], "language": "zh"}
        self.fail = False
    def invoke(self, task):
        self.calls.append(task.payload.payload())
        if self.fail: raise TimeoutError("sensitive transport detail")
        return ModelResult(task.kind, self.value)


@pytest.fixture
def extraction(tmp_path, monkeypatch):
    from dynamic_subject_agent.credentials import WindowsCredentialStore
    monkeypatch.setattr(WindowsCredentialStore, "load", lambda *args: pytest.fail("no real credentials"))
    sources = tmp_path / "sources"
    sources.mkdir()
    book = sources / "sample.epub"
    content = b"<p>synthetic source</p>"
    with ZipFile(book, "w") as z: z.writestr("ch.html", content)
    ref = dict(file=book.name, file_sha256=sha256(book.read_bytes()).hexdigest(), href="ch.html",
               document_sha256=sha256(content).hexdigest(), paragraph=1, quote="synthetic source",
               quote_sha256=sha256(b"synthetic source").hexdigest())
    packet = dict(source_title="synthetic", fragments=[dict(label="p1", text="synthetic source")], evidence=[ref])
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(dict(version="evidence-extraction-sample-1", target_name="subject", anchor="start",
                                    packets=[packet, packet, packet])), encoding="utf-8")
    opened = []
    def create(adapter=None, enabled=True):
        adapter = adapter or Adapter()
        lab = EvidenceExtractionLab(ModelGateway(adapter), path, sources, sample_digest=sha256(path.read_bytes()).hexdigest())
        root = tmp_path / f"product-{len(opened)}"
        product = open_local_product(LocalProductConfig(root / "experiments", root / "state.json"),
            cognition=DormantDeepSeekCognition(), _evidence_extraction=lab if enabled else None)
        opened.append(product)
        return product, adapter, root
    yield create, path, book
    for product in opened: product.close()


def req(index=0, key="k", rights=True, use=True):
    return EvidenceExtractionRequest(index, key, rights, use)


def test_rights_and_use_default_unavailable_and_idempotency(extraction):
    create, _, _ = extraction
    product, adapter, _ = create(enabled=False)
    assert product.application.extract_character_evidence(req()).status == "unavailable"
    product, adapter, _ = create()
    app = product.application
    for r in (req(rights=False), req(use=False), req(rights=1)):
        assert app.extract_character_evidence(r).code == "rights-and-use-required"
    assert not adapter.calls
    result = app.extract_character_evidence(req())
    assert result.status == "candidates" and result.candidates[0].review == "candidate"
    assert result.candidates[0].knower == "unknown"
    assert app.extract_character_evidence(req()) == result
    assert app.extract_character_evidence(req(1)).code == "key-conflict"
    assert app.extract_character_evidence(req(0, "new")).code == "packet-already-attempted"
    assert len(adapter.calls) == 1
    product.close()
    assert app.extract_character_evidence(req()).status == "unavailable"


def test_three_packet_budget_and_no_canonical_changes(extraction):
    create, _, _ = extraction
    product, adapter, root = create()
    def snapshot():
        return {str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    before = snapshot()
    for i in range(3):
        assert product.application.extract_character_evidence(req(i, str(i))).attempts == i + 1
    assert product.application.extract_character_evidence(req(3, "fourth")).status == "rejected"
    assert len(adapter.calls) == 3 and snapshot() == before
    assert set(adapter.calls[0]) == {"target_name", "anchor", "source_title", "fragments"}
    assert "sample.epub" not in json.dumps(adapter.calls)


@pytest.mark.parametrize("bad", ["quote", "label", "review", "time", "padding", "partial", "other-knower", "unknown-time"])
def test_invalid_candidates_do_not_become_partly_accepted(extraction, bad):
    create, _, _ = extraction
    product, adapter, _ = create()
    row = adapter.value["candidates"][0]
    if bad == "quote": row["evidence"][0]["quote"] = "invented quotation"
    elif bad == "label": row["evidence"][0]["label"] = "p999"
    elif bad == "review": row["review"] = "reviewed"
    elif bad == "time": row["knowledge_time"] = "definitely"
    elif bad == "padding": row["statement"] = " " * 301 + "x"
    elif bad == "other-knower": row["knower"] = "narrator"
    elif bad == "unknown-time": row["knowledge_time"] = "before"
    else: adapter.value["candidates"].append(dict(candidate(), reviewed=True))
    result = product.application.extract_character_evidence(req())
    assert result.status == "failed-closed" and not result.candidates
    assert product.application.extract_character_evidence(req()) == result
    assert len(adapter.calls) == 1


def test_failure_counts_and_changed_source_prevents_delivery(extraction):
    create, _, book = extraction
    product, adapter, _ = create()
    adapter.fail = True
    first = product.application.extract_character_evidence(req())
    assert first.status == "failed-closed" and first.attempts == 1
    assert "sensitive" not in repr(first)
    assert product.application.extract_character_evidence(req()) == first
    adapter.fail = False
    book.write_bytes(book.read_bytes() + b"changed")
    result = product.application.extract_character_evidence(req(1, "second"))
    assert result.status == "failed-closed" and result.attempts == 2
    assert len(adapter.calls) == 1


def test_redundant_language_field_is_optional_but_conflicting_value_is_rejected(extraction):
    create, _, _ = extraction
    product, adapter, _ = create()
    adapter.value.pop("language")
    assert product.application.extract_character_evidence(req()).status == "candidates"
    adapter.value["language"] = "en"
    assert product.application.extract_character_evidence(req(1, "next")).status == "failed-closed"


class Transport(DeepSeekTransport):
    def __init__(self, tokens=600, finish="stop"):
        self.calls, self.tokens, self.finish = [], tokens, finish
    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        return DeepSeekHttpResponse(200,json.dumps(dict(model=DEEPSEEK_MODEL,choices=[dict(finish_reason=self.finish,
            message=dict(role="assistant",content=json.dumps({"candidates":[candidate()],"language":"zh"})))],
            usage=dict(prompt_tokens=100,completion_tokens=self.tokens))).encode())


@pytest.mark.parametrize("tokens,finish,status", [(600,"stop","candidates"),(2049,"stop","failed-closed"),(600,"length","failed-closed")])
def test_new_wire_budget_and_complete_json_requirement(extraction,tokens,finish,status):
    create, _, _ = extraction
    transport = Transport(tokens, finish)
    adapter = DeepSeekEvidenceAdapter(transport=transport,credential_ref=CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
    product, _, _ = create(adapter)
    assert product.application.extract_character_evidence(req()).status == status
    wire = json.loads(transport.calls[0]["body"])
    assert wire["max_tokens"] == 2048 and wire["messages"][0]["content"].startswith(EXTRACTION_POLICY)
    assert "sample.epub" not in json.dumps(wire)


def test_extractor_cannot_assign_target_awareness_or_time(extraction):
    create, _, _ = extraction
    product, adapter, _ = create()
    result = product.application.extract_character_evidence(req())
    assert result.status == "candidates"
    row = result.candidates[0]
    assert row.knower == row.event_time == row.knowledge_time == "unknown"
    adapter.value["candidates"][0]["knower"] = "subject"
    assert product.application.extract_character_evidence(req(1,"second")).status == "failed-closed"


def test_audit_does_not_capture_credentials_reasoning_or_tools(extraction):
    create, _, _ = extraction
    class ExtraFieldsTransport(Transport):
        def post_json(self, **kwargs):
            response = super().post_json(**kwargs)
            data = json.loads(response.body)
            data["choices"][0]["message"]["reasoning_content"] = "private-reasoning"
            data["choices"][0]["message"]["tool_calls"] = ["private-tool-argument"]
            return DeepSeekHttpResponse(200,json.dumps(data).encode())
    audits = []
    adapter = DeepSeekEvidenceAdapter(transport=ExtraFieldsTransport(),
        credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID),
        response_audit=audits.append)
    product, _, _ = create(adapter)
    assert product.application.extract_character_evidence(req()).status == "failed-closed"
    serialized = json.dumps(audits)
    assert "private-reasoning" not in serialized and "private-tool-argument" not in serialized
    assert "credential_ref" not in serialized and "Authorization" not in serialized


def test_offline_root_and_incorrect_plan_do_not_load_key(tmp_path,monkeypatch):
    from dynamic_subject_agent.credentials import WindowsCredentialStore
    monkeypatch.setattr(WindowsCredentialStore,"load",lambda *a: pytest.fail("no real key"))
    with pytest.raises(ValueError,match="approval"):
        open_evidence_extraction_lab(tmp_path/'labs',workspace=tmp_path,approved_plan="wrong")
    with open_evidence_extraction_lab(tmp_path/'labs',workspace=tmp_path) as product:
        assert product.application.extract_character_evidence(req()).status == "unavailable"

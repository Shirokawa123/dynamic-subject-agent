"""Preview a reviewed evidence draft as a stage-specific character model.

The preview owns neither a runtime identity nor an event writer. Temporal and
epistemic judgements are reviewed input, not inferred by hashing or ordering.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.source_evidence import load_verified_source_documents

DIMENSIONS = ("identity", "biography", "relationships", "work", "abilities",
              "values", "concerns", "situation", "world-knowledge")


@dataclass(frozen=True)
class CharacterModelRequest:
    subject_id: str
    anchor_id: str


@dataclass(frozen=True)
class CharacterContextRequest:
    subject_id: str
    anchor_id: str
    evidence_id: str
    before: int = 5
    after: int = 5


@dataclass(frozen=True)
class SourceContextUnit:
    ordinal: int
    text: str
    is_cited: bool


@dataclass(frozen=True)
class CharacterContextView:
    status: str
    code: str = ""
    citation: "CharacterEvidenceCitation | None" = None
    units: tuple[SourceContextUnit, ...] = ()
    document_start: bool = False
    document_end: bool = False
    draft_digest: str = ""


@dataclass(frozen=True)
class CharacterEntity:
    entity_id: str
    name: str
    kind: str


@dataclass(frozen=True)
class CharacterModelItem:
    item_id: str
    dimension: str
    kind: str
    statement: str
    about: tuple[str, ...]
    relation: str
    evidence_ids: tuple[str, ...]
    reason: str = ""
    derivation: str = "direct"
    knower_id: str = ""
    event_time: str = ""
    knowledge_time: str = ""
    time_basis: str = ""
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class CharacterEvidenceCitation:
    evidence_id: str
    file: str
    href: str
    locator_kind: str
    ordinal: int
    speaker_id: str
    source_group: str
    file_sha256: str
    document_sha256: str
    quote_sha256: str


@dataclass(frozen=True)
class CharacterCoverage:
    dimension: str
    eligible_count: int
    assessment: str
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class CharacterModelView:
    status: str
    code: str = ""
    subject_id: str = ""
    anchor_id: str = ""
    anchor_status: str = ""
    known: tuple[CharacterModelItem, ...] = ()
    excluded: tuple[CharacterModelItem, ...] = ()
    coverage: tuple[CharacterCoverage, ...] = ()
    entities: tuple[CharacterEntity, ...] = ()
    citations: tuple[CharacterEvidenceCitation, ...] = ()
    draft_digest: str = ""
    sealed_from_draft: bool = False


class CharacterEvidenceModel:
    """One read-only Interface for integrity, dependencies and stage projection."""

    def __init__(self, draft_path: Path, source_root: Path, *, expected_digest: str):
        if (not isinstance(draft_path, Path) or not draft_path.is_absolute()
                or not isinstance(source_root, Path) or not source_root.is_absolute()
                or not isinstance(expected_digest, str) or len(expected_digest) != 64
                or any(c not in "0123456789abcdef" for c in expected_digest)):
            raise ValueError("reviewed local draft required")
        self._draft = draft_path
        self._sources = source_root
        self._digest = expected_digest

    def _load(self):
        with self._draft.open("rb") as stream:
            data = stream.read(4_000_001)
        if len(data) > 4_000_000 or sha256(data).hexdigest() != self._digest:
            raise ValueError("draft changed")
        draft = json.loads(data)
        if draft["version"] != "character-evidence-draft-1" or draft["status"] != "local-review-only":
            raise ValueError("unsupported draft")
        entities = draft["entities"]
        entity_ids = {e["id"] for e in entities}
        if not entities or len(entities) > 500 or len(entity_ids) != len(entities):
            raise ValueError("invalid entities")
        if any(not isinstance(e["name"], str) or not e["name"].strip()
               or not isinstance(e["kind"], str) or not e["kind"].strip() for e in entities):
            raise ValueError("invalid entity labels")
        if draft["subject_id"] not in entity_ids:
            raise ValueError("missing subject")
        if draft["anchor"]["status"] not in ("proposed", "reviewed") or not draft["anchor"]["id"]:
            raise ValueError("invalid anchor")
        refs = draft["evidence"]
        evidence = {e["id"]: e for e in refs}
        if not refs or len(refs) > 2000 or len(evidence) != len(refs):
            raise ValueError("invalid evidence")
        for ref in refs:
            if ref["speaker_id"] not in entity_ids or ref["source_group"] not in ("main", "if", "unknown"):
                raise ValueError("missing perspective")
        assertions = draft["assertions"]
        by_id = {a["id"]: a for a in assertions}
        if not assertions or len(assertions) > 1000 or len(by_id) != len(assertions):
            raise ValueError("invalid assertions")
        for a in assertions:
            if (a["dimension"] not in DIMENSIONS or a["kind"] not in ("fact", "belief", "interpretation")
                    or not isinstance(a["statement"], str) or not 0 < len(a["statement"]) <= 1500
                    or not a["about"] or not set(a["about"]).issubset(entity_ids)
                    or a["knower_id"] not in entity_ids | {"unknown"}
                    or a["review"] not in ("reviewed", "candidate")
                    or a["event_time"] not in ("before", "at", "after", "unknown")
                    or a["knowledge_time"] not in ("before", "at", "after", "unknown")
                    or not a["evidence_ids"] or not set(a["evidence_ids"]).issubset(evidence)
                    or not set(a["depends_on"]).issubset(by_id)
                    or not isinstance(a["relation"], str)
                    or a.get("derivation", "direct") not in ("direct", "linked-evidence")
                    or not isinstance(a["time_basis"], str) or not a["time_basis"].strip()):
                raise ValueError("invalid assertion")
        reviews = draft["coverage_review"]
        if set(reviews) != set(DIMENSIONS):
            raise ValueError("coverage dimensions missing")
        for review in reviews.values():
            if (review["assessment"] not in ("unreviewed", "partial", "reviewed-adequate")
                    or not isinstance(review["gaps"], list)
                    or any(not isinstance(g, str) or not g.strip() for g in review["gaps"])
                    or (review["assessment"] != "reviewed-adequate" and not review["gaps"])):
                raise ValueError("invalid coverage review")
        # Validate dependencies even on currently excluded claims; no cycles can
        # be hidden behind an unknown time or a different perspective.
        visiting, visited = set(), set()
        def visit(key):
            if key in visiting:
                raise ValueError("cyclic basis")
            if key in visited:
                return
            visiting.add(key)
            for parent in by_id[key]["depends_on"]:
                visit(parent)
            visiting.remove(key)
            visited.add(key)
        for key in by_id:
            visit(key)
        documents = load_verified_source_documents(self._sources, refs)
        return draft, evidence, by_id, documents

    @staticmethod
    def _citation(e):
        return CharacterEvidenceCitation(e["id"], e["file"], e["href"], e.get("locator_kind", "paragraph"),
            e["text_node"] if e.get("locator_kind") == "html_text_node" else e["paragraph"],
            e["speaker_id"], e["source_group"], e["file_sha256"], e["document_sha256"], e["quote_sha256"])

    def _context(self, request):
        if (not isinstance(request.subject_id, str) or not isinstance(request.anchor_id, str)
                or not isinstance(request.evidence_id, str)
                or any(type(n) is not int or not 0 <= n <= 20 for n in (request.before, request.after))):
            return CharacterContextView("rejected", "invalid-context-request")
        try:
            draft, evidence, _, documents = self._load()
            if request.subject_id != draft["subject_id"] or request.anchor_id != draft["anchor"]["id"]:
                return CharacterContextView("rejected", "subject-anchor-mismatch")
            if request.evidence_id not in evidence:
                return CharacterContextView("rejected", "unknown-evidence")
            ref = evidence[request.evidence_id]
            citation = self._citation(ref)
            parsed = documents[((self._sources / ref["file"]).resolve(strict=True), ref["href"])]
            positions = dict(enumerate(parsed.rows, 1)) if citation.locator_kind == "paragraph" else parsed.nodes
            last = max(positions)
            start, end = max(1, citation.ordinal - request.before), min(last, citation.ordinal + request.after)
            units = tuple(SourceContextUnit(n, positions[n], n == citation.ordinal)
                          for n in range(start, end + 1) if n in positions)
            if sum(len(unit.text) for unit in units) > 6000:
                return CharacterContextView("rejected", "context-window-too-large")
            return CharacterContextView("previewed", citation=citation, units=units,
                                        document_start=start == 1, document_end=end == last,
                                        draft_digest=self._digest)
        except FileNotFoundError:
            return CharacterContextView("unavailable", "draft-or-source-missing")
        except Exception:
            return CharacterContextView("failed-closed", "evidence-model-invalid")

    def preview(self, request: object) -> CharacterModelView | CharacterContextView:
        if type(request) is CharacterContextRequest:
            return self._context(request)
        if (type(request) is not CharacterModelRequest or not isinstance(request.subject_id, str)
                or not isinstance(request.anchor_id, str)):
            return CharacterModelView("rejected", "typed-subject-anchor-required")
        try:
            draft, evidence, assertions, _ = self._load()
            if request.subject_id != draft["subject_id"] or request.anchor_id != draft["anchor"]["id"]:
                return CharacterModelView("rejected", "subject-anchor-mismatch")
            reasons = {}
            def reason(key):
                if key in reasons:
                    return reasons[key]
                a = assertions[key]
                value = ""
                if a["review"] != "reviewed": value = "unreviewed-claim"
                elif any(evidence[e]["source_group"] != "main" for e in a["evidence_ids"]): value = "non-main-source"
                elif a["kind"] == "interpretation": value = "interpretation-not-self-knowledge"
                elif a["knower_id"] == "unknown": value = "awareness-unresolved"
                elif a["knower_id"] != request.subject_id: value = "other-perspective"
                elif a["event_time"] == "after": value = "event-after-anchor"
                elif a["event_time"] == "unknown": value = "event-time-unresolved"
                elif a["knowledge_time"] == "after": value = "learned-after-anchor"
                elif a["knowledge_time"] == "unknown": value = "knowledge-time-unresolved"
                elif any(reason(parent) for parent in a["depends_on"]): value = "basis-not-eligible"
                reasons[key] = value
                return value
            known, excluded = [], []
            for key, a in assertions.items():
                why = reason(key)
                view = CharacterModelItem(key, a["dimension"], a["kind"], a["statement"], tuple(a["about"]),
                                          a["relation"], tuple(a["evidence_ids"]), why, a.get("derivation", "direct"),
                                          a["knower_id"], a["event_time"], a["knowledge_time"], a["time_basis"],
                                          tuple(a["depends_on"]))
                (excluded if why else known).append(view)
            coverage = []
            for dim in DIMENSIONS:
                count = sum(item.dimension == dim for item in known)
                review = draft["coverage_review"][dim]
                if review["assessment"] == "reviewed-adequate" and (not count or review["gaps"]):
                    raise ValueError("unsupported coverage conclusion")
                coverage.append(CharacterCoverage(dim, count, review["assessment"], tuple(review["gaps"])))
            known_entities = {request.subject_id} | {ref for item in known for ref in item.about}
            return CharacterModelView(
                status="previewed", subject_id=request.subject_id, anchor_id=request.anchor_id,
                anchor_status=draft["anchor"]["status"], known=tuple(known), excluded=tuple(excluded),
                coverage=tuple(coverage), entities=tuple(CharacterEntity(e["id"], e["name"], e["kind"])
                    for e in draft["entities"] if e["id"] in known_entities),
                citations=tuple(self._citation(e) for e in evidence.values()), draft_digest=self._digest)
        except FileNotFoundError:
            return CharacterModelView("unavailable", "draft-or-source-missing")
        except Exception:
            return CharacterModelView("failed-closed", "evidence-model-invalid")

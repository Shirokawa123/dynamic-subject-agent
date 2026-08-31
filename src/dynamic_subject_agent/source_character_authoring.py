"""Authorization-gated, unpublished character candidates from one text source."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ModelGatewayFailure,
    ModelResult,
    ModelTask,
    ModelTaskKind,
    ProviderAdapter,
    ProviderCapabilities,
)


SOURCE_TITLE_MAX_CHARS = 120
SOURCE_TEXT_MAX_CHARS = 16_000
SOURCE_CANDIDATE_LIMIT = 8
SOURCE_ABSOLUTE_CANDIDATE_LIMIT = 32
SOURCE_POLICY_ID = "text-source-character-preview"
SOURCE_POLICY_VERSION = 1
GENESIS_KINDS = frozenset({"identity", "origin", "trait", "voice"})
_ORIGIN_EVIDENCE_MARKERS = (
    "来自",
    "出生",
    "成长",
    "故乡",
    "过去",
    "曾经",
    "起初",
    "成为",
    "形成于",
)


class SourcePreviewStatus(str, Enum):
    AVAILABLE = "available"
    REJECTED = "rejected"
    FAILED_CLOSED = "failed-closed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class TextSourcePreviewRequest:
    source_title: str
    source_text: str
    rights_confirmed: bool
    extraction_use_confirmed: bool


@dataclass(frozen=True)
class SourceCharacterExtractionRequest:
    source_title: str
    source_text: str
    policy_id: str = SOURCE_POLICY_ID
    policy_version: int = SOURCE_POLICY_VERSION


@dataclass(frozen=True)
class ProposedGenesisCandidate:
    kind: str
    content: str
    evidence_quote: str


@dataclass(frozen=True)
class ProposedKnowledgeCandidate:
    title: str
    content: str
    evidence_quote: str


@dataclass(frozen=True)
class SourceCharacterExtractionResult:
    genesis_candidates: tuple[ProposedGenesisCandidate, ...]
    knowledge_candidates: tuple[ProposedKnowledgeCandidate, ...]
    language: str


@dataclass(frozen=True)
class SourceCandidatePreview:
    category: str
    kind: str | None
    title: str | None
    content: str
    evidence_quote: str
    status: str
    reason_code: str


@dataclass(frozen=True)
class TextSourcePreviewResponse:
    status: SourcePreviewStatus
    accepted: tuple[SourceCandidatePreview, ...] = ()
    rejected: tuple[SourceCandidatePreview, ...] = ()
    problem_code: str | None = None

    @classmethod
    def unavailable(cls) -> "TextSourcePreviewResponse":
        return cls(
            status=SourcePreviewStatus.UNAVAILABLE,
            problem_code="source-character-authoring-unavailable",
        )


class SourceCharacterProviderAdapter(ProviderAdapter):
    """Adapt one extraction provider to the provider-neutral ModelGateway seam."""

    def __init__(
        self,
        *,
        provider: object,
        capabilities: ProviderCapabilities,
    ) -> None:
        if not callable(getattr(provider, "extract", None)):
            raise TypeError("source character provider requires extract")
        if not isinstance(capabilities, ProviderCapabilities):
            raise TypeError("capabilities must be typed")
        self._provider = provider
        self.capabilities = capabilities

    def invoke(self, task: ModelTask) -> ModelResult:
        if task.kind is not ModelTaskKind.SOURCE_CHARACTER_EXTRACTION:
            raise ModelGatewayFailure("model-task-unavailable")
        if not isinstance(task.payload, SourceCharacterExtractionRequest):
            raise ModelGatewayFailure("source-character-task-invalid")
        return ModelResult(kind=task.kind, value=self._provider.extract(task.payload))


class TextSourceCharacterAuthoring:
    """Deep Module: authorize, extract and adjudicate one ephemeral preview."""

    def __init__(self, *, gateway: ModelGateway) -> None:
        if not isinstance(gateway, ModelGateway):
            raise TypeError("TextSourceCharacterAuthoring requires ModelGateway")
        self._gateway = gateway

    def preview(self, request: object) -> TextSourcePreviewResponse:
        problem = self._validate_request(request)
        if problem is not None:
            return TextSourcePreviewResponse(
                status=SourcePreviewStatus.REJECTED,
                problem_code=problem,
            )
        assert isinstance(request, TextSourcePreviewRequest)
        extraction_request = SourceCharacterExtractionRequest(
            source_title=request.source_title.strip(),
            source_text=request.source_text,
        )
        try:
            result = self._gateway.execute(
                ModelTask(
                    ModelTaskKind.SOURCE_CHARACTER_EXTRACTION,
                    extraction_request,
                )
            ).value
        except ModelGatewayFailure:
            return TextSourcePreviewResponse(
                status=SourcePreviewStatus.FAILED_CLOSED,
                problem_code="source-character-provider-failed",
            )
        if not self._valid_result_shape(result):
            return TextSourcePreviewResponse(
                status=SourcePreviewStatus.FAILED_CLOSED,
                problem_code="source-character-provider-invalid-output",
            )
        assert isinstance(result, SourceCharacterExtractionResult)
        accepted: list[SourceCandidatePreview] = []
        rejected: list[SourceCandidatePreview] = []
        seen: set[tuple[str, str, str]] = set()
        for index, candidate in enumerate(result.genesis_candidates):
            preview = self._adjudicate_genesis(
                candidate,
                source_text=request.source_text,
                over_limit=index >= SOURCE_CANDIDATE_LIMIT,
                seen=seen,
            )
            (accepted if preview.status == "accepted" else rejected).append(preview)
        for index, candidate in enumerate(result.knowledge_candidates):
            preview = self._adjudicate_knowledge(
                candidate,
                source_text=request.source_text,
                over_limit=index >= SOURCE_CANDIDATE_LIMIT,
                seen=seen,
            )
            (accepted if preview.status == "accepted" else rejected).append(preview)
        return TextSourcePreviewResponse(
            status=SourcePreviewStatus.AVAILABLE,
            accepted=tuple(accepted),
            rejected=tuple(rejected),
        )

    @staticmethod
    def _validate_request(request: object) -> str | None:
        if not isinstance(request, TextSourcePreviewRequest):
            return "source-preview-request-invalid"
        if request.rights_confirmed is not True:
            return "source-rights-confirmation-required"
        if request.extraction_use_confirmed is not True:
            return "source-extraction-use-confirmation-required"
        if (
            not isinstance(request.source_title, str)
            or not request.source_title.strip()
            or len(request.source_title.strip()) > SOURCE_TITLE_MAX_CHARS
            or any(marker in request.source_title for marker in ("\x00", "\r", "\n"))
        ):
            return "source-title-invalid"
        if (
            not isinstance(request.source_text, str)
            or not request.source_text.strip()
            or len(request.source_text) > SOURCE_TEXT_MAX_CHARS
            or "\x00" in request.source_text
        ):
            return "source-text-invalid"
        return None

    @staticmethod
    def _valid_result_shape(result: object) -> bool:
        return (
            isinstance(result, SourceCharacterExtractionResult)
            and result.language == "zh"
            and isinstance(result.genesis_candidates, tuple)
            and isinstance(result.knowledge_candidates, tuple)
            and len(result.genesis_candidates) <= SOURCE_ABSOLUTE_CANDIDATE_LIMIT
            and len(result.knowledge_candidates) <= SOURCE_ABSOLUTE_CANDIDATE_LIMIT
            and all(
                isinstance(candidate, ProposedGenesisCandidate)
                for candidate in result.genesis_candidates
            )
            and all(
                isinstance(candidate, ProposedKnowledgeCandidate)
                for candidate in result.knowledge_candidates
            )
        )

    @staticmethod
    def _adjudicate_genesis(
        candidate: ProposedGenesisCandidate,
        *,
        source_text: str,
        over_limit: bool,
        seen: set[tuple[str, str, str]],
    ) -> SourceCandidatePreview:
        reason = "accepted"
        if over_limit:
            reason = "candidate-limit-exceeded"
        elif not isinstance(candidate.kind, str) or candidate.kind not in GENESIS_KINDS:
            reason = "genesis-kind-invalid"
        elif not _bounded(candidate.content, maximum=500):
            reason = "candidate-content-invalid"
        elif not _verbatim(candidate.evidence_quote, source_text=source_text):
            reason = "candidate-evidence-not-verbatim"
        elif candidate.kind == "origin" and not any(
            marker in candidate.evidence_quote
            for marker in _ORIGIN_EVIDENCE_MARKERS
        ):
            reason = "genesis-origin-evidence-insufficient"
        key = (
            "genesis",
            _visible(candidate.kind),
            _visible(candidate.content).strip(),
        )
        if reason == "accepted" and key in seen:
            reason = "duplicate-candidate"
        if reason == "accepted":
            seen.add(key)
        return SourceCandidatePreview(
            category="genesis",
            kind=candidate.kind,
            title=None,
            content=_visible(candidate.content),
            evidence_quote=_visible(candidate.evidence_quote),
            status="accepted" if reason == "accepted" else "rejected",
            reason_code=reason,
        )

    @staticmethod
    def _adjudicate_knowledge(
        candidate: ProposedKnowledgeCandidate,
        *,
        source_text: str,
        over_limit: bool,
        seen: set[tuple[str, str, str]],
    ) -> SourceCandidatePreview:
        reason = "accepted"
        if over_limit:
            reason = "candidate-limit-exceeded"
        elif not _bounded(candidate.title, maximum=100):
            reason = "knowledge-title-invalid"
        elif not _bounded(candidate.content, maximum=1_000):
            reason = "candidate-content-invalid"
        elif not _verbatim(candidate.evidence_quote, source_text=source_text):
            reason = "candidate-evidence-not-verbatim"
        key = (
            "knowledge",
            _visible(candidate.title).strip(),
            _visible(candidate.content).strip(),
        )
        if reason == "accepted" and key in seen:
            reason = "duplicate-candidate"
        if reason == "accepted":
            seen.add(key)
        return SourceCandidatePreview(
            category="knowledge",
            kind=None,
            title=_visible(candidate.title),
            content=_visible(candidate.content),
            evidence_quote=_visible(candidate.evidence_quote),
            status="accepted" if reason == "accepted" else "rejected",
            reason_code=reason,
        )


def _bounded(value: object, *, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and "\x00" not in value
    )


def _verbatim(value: object, *, source_text: str) -> bool:
    return _bounded(value, maximum=500) and value in source_text


def _visible(value: object) -> str:
    return value[:1_000] if isinstance(value, str) else ""


__all__ = [
    "GENESIS_KINDS",
    "ProposedGenesisCandidate",
    "ProposedKnowledgeCandidate",
    "SOURCE_CANDIDATE_LIMIT",
    "SOURCE_POLICY_ID",
    "SOURCE_POLICY_VERSION",
    "SOURCE_TEXT_MAX_CHARS",
    "SOURCE_TITLE_MAX_CHARS",
    "SourceCandidatePreview",
    "SourceCharacterExtractionRequest",
    "SourceCharacterExtractionResult",
    "SourceCharacterProviderAdapter",
    "SourcePreviewStatus",
    "TextSourceCharacterAuthoring",
    "TextSourcePreviewRequest",
    "TextSourcePreviewResponse",
]

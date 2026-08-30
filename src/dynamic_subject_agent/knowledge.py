"""Controlled knowledge citation cognition using provider proposals and Python adjudication."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    ExperienceAdjudicationRequest,
    ExperienceChangeCandidate,
    ExperienceReadView,
)
from dynamic_subject_agent.knowledge_entries import (
    KNOWLEDGE_CANDIDATE_LIMIT,
    KnowledgeEntry,
    select_knowledge_candidates,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionFailedClosed,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
    M0_A_PROVIDER_AUTHORITY,
)
from dynamic_subject_agent.timeline import SubjectCommand


@dataclass(frozen=True)
class KnowledgeProviderRequest:
    current_user_message: str
    candidate_entries: tuple[KnowledgeEntry, ...]


@dataclass(frozen=True)
class KnowledgeProposal:
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeProviderResult:
    proposal: KnowledgeProposal
    experience_summary: str
    reply_text: str
    language: str


class ControlledKnowledgeCognition(CognitionEngine):
    """No-write cognition seam; only ExperienceDomain may accept a citation."""

    adapter_version = "knowledge-citation-cognition-1.0"
    provider_authority = M0_A_PROVIDER_AUTHORITY
    experimental = True
    test_only = True

    def __init__(self, *, provider: object) -> None:
        if not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose analyze(request)")
        provider_authority = getattr(
            provider,
            "provider_authority",
            M0_A_PROVIDER_AUTHORITY,
        )
        if not isinstance(provider_authority, str) or not provider_authority:
            raise TypeError("provider_authority must be a non-empty string")
        self.provider_authority = provider_authority
        self.test_only = bool(getattr(provider, "test_only", True))
        self._provider = provider

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        candidates = select_knowledge_candidates(command.utterance)
        request = KnowledgeProviderRequest(
            current_user_message=command.utterance,
            candidate_entries=candidates,
        )
        try:
            result = self._provider.analyze(request)
        except Exception as error:
            provider_code = getattr(getattr(error, "code", None), "name", None)
            detail = "Knowledge provider failed without a usable proposal"
            if provider_code:
                detail = f"{detail} (provider code: {provider_code})"
            raise CognitionFailedClosed(
                "provider",
                "knowledge-provider-failed",
                detail,
            ) from error
        candidate_ids = {entry.entry_id for entry in candidates}
        if (
            not isinstance(result, KnowledgeProviderResult)
            or not isinstance(result.proposal, KnowledgeProposal)
            or not isinstance(result.proposal.citation_ids, tuple)
            or any(entry_id not in candidate_ids for entry_id in result.proposal.citation_ids)
            or len(set(result.proposal.citation_ids)) != len(result.proposal.citation_ids)
            or not result.reply_text.strip()
            or result.language != command.language
        ):
            raise CognitionFailedClosed(
                "provider",
                "knowledge-provider-invalid-output",
                "Knowledge provider returned an invalid bounded result",
            )
        citation_candidate: ExperienceChangeCandidate | None = None
        if result.proposal.citation_ids:
            citation_candidate = ExperienceChangeCandidate(
                candidate_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        "knowledge:"
                        f"{basis.operation_id}:"
                        f"{':'.join(sorted(result.proposal.citation_ids))}",
                    )
                ),
                target_experience_id=basis.experience_id,
                evidence_refs=(basis.operation_id,),
                knowledge_citation_ids=result.proposal.citation_ids,
            )
        summary = result.experience_summary.strip() or (
            f"引用 {len(result.proposal.citation_ids)} 条封存知识条目。"
            if result.proposal.citation_ids
            else "本轮无适用的封存知识条目。"
        )
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=summary,
            expression_candidate=ExpressionCandidate(
                text=result.reply_text,
                language=result.language,
            ),
        )
        experience_request = ExperienceAdjudicationRequest(
            basis=basis,
            current_state=ExperienceReadView(
                verified_prefix_digest=basis.verified_prefix_digest,
                memory_trace_refs=(),
            ),
            candidates=(citation_candidate,) if citation_candidate else (),
            knowledge_candidates=candidates,
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                experience=experience_request,
            ),
        )

    @classmethod
    def for_profile(
        cls,
        profile: str,
        *,
        deepseek_transport: object | None = None,
        credential_ref: object | None = None,
    ) -> "ControlledKnowledgeCognition":
        if profile != "default":
            raise ValueError("Knowledge profile adapter is unavailable")
        from dynamic_subject_agent.deepseek import DeepSeekKnowledgeProvider

        return cls(
            provider=DeepSeekKnowledgeProvider(
                transport=deepseek_transport,
                credential_ref=credential_ref,
            )
        )


__all__ = [
    "ControlledKnowledgeCognition",
    "KnowledgeProposal",
    "KnowledgeProviderRequest",
    "KnowledgeProviderResult",
]

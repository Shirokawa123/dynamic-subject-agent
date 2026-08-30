"""Controlled relationship stance cognition using provider proposals and Python adjudication."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    RelationshipAdjudicationRequest,
    RelationshipChangeCandidate,
    RelationshipReadView,
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


RELATIONSHIP_POLICY_VERSION = "relationship-stance-v1"

from dynamic_subject_agent.relationship_events import (
    ALL_RELATIONSHIP_EVENTS,
    NO_UPDATE_EVENTS,
    UPDATE_EVENTS,
)


@dataclass(frozen=True)
class RelationshipProviderRequest:
    current_user_message: str
    stance_summary: str


@dataclass(frozen=True)
class RelationshipProposal:
    event: str
    evidence_quote: str


@dataclass(frozen=True)
class RelationshipProviderResult:
    proposal: RelationshipProposal
    experience_summary: str
    reply_text: str
    language: str


class ControlledRelationshipCognition(CognitionEngine):
    """No-write cognition seam; only RelationshipDomain may accept an event."""

    adapter_version = "relationship-stance-cognition-1.0"
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
        if not context.relationship_enabled:
            return self._bounded_noop_proposal(
                context=context,
                basis=basis,
                experience_summary="关系参与未启用。",
                expression_candidate=ExpressionCandidate(
                    text="（关系参与未启用）",
                    language=command.language,
                ),
            )
        stance_summary = (
            context.relationship_stance_summary.strip()
            or "尚无立场互动记录。"
        )
        request = RelationshipProviderRequest(
            current_user_message=command.utterance,
            stance_summary=stance_summary,
        )
        try:
            result = self._provider.analyze(request)
        except Exception as error:
            provider_code = getattr(getattr(error, "code", None), "name", None)
            detail = "Relationship provider failed without a usable proposal"
            if provider_code:
                detail = f"{detail} (provider code: {provider_code})"
            raise CognitionFailedClosed(
                "provider",
                "relationship-provider-failed",
                detail,
            ) from error
        summary = result.experience_summary.strip() or (
            f"关系事件分类：{result.proposal.event}。"
        )
        if (
            not isinstance(result, RelationshipProviderResult)
            or not isinstance(result.proposal, RelationshipProposal)
            or result.proposal.event not in ALL_RELATIONSHIP_EVENTS
            or not isinstance(result.proposal.evidence_quote, str)
            or result.proposal.evidence_quote not in command.utterance
            or not result.reply_text.strip()
            or result.language != command.language
            or not summary.strip()
        ):
            raise CognitionFailedClosed(
                "provider",
                "relationship-provider-invalid-output",
                "Relationship provider returned an invalid bounded result",
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
        event_candidate = RelationshipChangeCandidate(
            candidate_id=str(
                uuid5(
                    NAMESPACE_URL,
                    "relationship:"
                    f"{basis.operation_id}:{result.proposal.event}",
                )
            ),
            relationship_target_id=context.profile_id,
            evidence_refs=(basis.operation_id,),
            event=result.proposal.event,
            evidence_quote=result.proposal.evidence_quote,
            source_user_message_id=basis.operation_id,
            policy_version=RELATIONSHIP_POLICY_VERSION,
        )
        relationship_request = RelationshipAdjudicationRequest(
            basis=basis,
            relationship_enabled=True,
            relationship_target_id=context.profile_id,
            current_state=base.impact_envelope.relationship.current_state,
            candidates=(event_candidate,),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                relationship=relationship_request,
            ),
        )

    @classmethod
    def for_profile(
        cls,
        profile: str,
        *,
        deepseek_transport: object | None = None,
        credential_ref: object | None = None,
    ) -> "ControlledRelationshipCognition":
        if profile != "default":
            raise ValueError("Relationship profile adapter is unavailable")
        from dynamic_subject_agent.deepseek import DeepSeekRelationshipProvider

        return cls(
            provider=DeepSeekRelationshipProvider(
                transport=deepseek_transport,
                credential_ref=credential_ref,
            )
        )


__all__ = [
    "ALL_RELATIONSHIP_EVENTS",
    "ControlledRelationshipCognition",
    "NO_UPDATE_EVENTS",
    "RELATIONSHIP_POLICY_VERSION",
    "RelationshipProviderRequest",
    "RelationshipProviderResult",
    "RelationshipProposal",
    "UPDATE_EVENTS",
]

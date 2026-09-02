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
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
    M0_A_PROVIDER_AUTHORITY,
)
from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ModelGatewayFailure,
    ModelResult,
    ModelTask,
    ModelTaskKind,
    ProviderAdapter,
    ProviderCapabilities,
    StructuredOutputMode,
)
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection


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
class RelationshipReplyRequest:
    current_user_message: str
    stance_summary: str
    runtime_identity: RuntimeIdentityProjection


@dataclass(frozen=True)
class RelationshipReplyResult:
    reply_text: str
    language: str


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


class RelationshipProviderAdapter(ProviderAdapter):
    def __init__(self, *, provider: object) -> None:
        self._split = callable(getattr(provider, "propose", None)) and callable(
            getattr(provider, "reply", None)
        )
        if not self._split and not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose propose/reply or analyze")
        provider_id = getattr(provider, "provider_authority", M0_A_PROVIDER_AUTHORITY)
        if not isinstance(provider_id, str) or not provider_id:
            raise TypeError("provider_authority must be a non-empty string")
        self._provider = provider
        self.capabilities = ProviderCapabilities(
            provider_id=provider_id,
            model_id=str(getattr(provider, "model_id", type(provider).__name__)),
            local=bool(getattr(provider, "local", False)),
            structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
        )

    def invoke(self, task: ModelTask) -> ModelResult:
        if task.kind is ModelTaskKind.RELATIONSHIP_ANALYSIS and isinstance(
            task.payload,
            RelationshipProviderRequest,
        ):
            result = (
                self._provider.propose(task.payload)
                if self._split
                else self._provider.analyze(task.payload)
            )
            return ModelResult(task.kind, result)
        if (
            task.kind is ModelTaskKind.RELATIONSHIP_REPLY
            and isinstance(task.payload, RelationshipReplyRequest)
            and self._split
        ):
            return ModelResult(task.kind, self._provider.reply(task.payload))
        raise ModelGatewayFailure("relationship-task-invalid")


class ControlledRelationshipCognition(CognitionEngine):
    """No-write cognition seam; only RelationshipDomain may accept an event."""

    adapter_version = "relationship-stance-cognition-1.0"
    provider_authority = M0_A_PROVIDER_AUTHORITY
    experimental = True
    test_only = True

    def __init__(
        self,
        *,
        provider: object,
        runtime_identity: RuntimeIdentityProjection | None = None,
    ) -> None:
        split = callable(getattr(provider, "propose", None)) and callable(
            getattr(provider, "reply", None)
        )
        if not split and not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose propose/reply or analyze")
        if split and not isinstance(runtime_identity, RuntimeIdentityProjection):
            raise TypeError("split provider requires RuntimeIdentityProjection")
        provider_authority = getattr(
            provider,
            "provider_authority",
            M0_A_PROVIDER_AUTHORITY,
        )
        if not isinstance(provider_authority, str) or not provider_authority:
            raise TypeError("provider_authority must be a non-empty string")
        self.provider_authority = provider_authority
        self.test_only = bool(getattr(provider, "test_only", True))
        self._gateway = ModelGateway(RelationshipProviderAdapter(provider=provider))
        self._split = split
        self._runtime_identity = runtime_identity

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
            result = self._gateway.execute(
                ModelTask(ModelTaskKind.RELATIONSHIP_ANALYSIS, request)
            ).value
        except Exception as error:
            return self._failure(
                context,
                command,
                basis,
                "relationship-provider-failed",
            )
        if (
            not isinstance(result, RelationshipProviderResult)
            or not isinstance(result.proposal, RelationshipProposal)
            or result.proposal.event not in ALL_RELATIONSHIP_EVENTS
            or not isinstance(result.proposal.evidence_quote, str)
            or result.proposal.evidence_quote not in command.utterance
            or not result.reply_text.strip()
            or result.language != command.language
        ):
            return self._failure(
                context,
                command,
                basis,
                "relationship-provider-invalid-output",
            )
        summary = result.experience_summary.strip() or (
            f"关系事件分类：{result.proposal.event}。"
        )
        reply_text = result.reply_text
        if self._split:
            try:
                reply_result = self._gateway.execute(
                    ModelTask(
                        ModelTaskKind.RELATIONSHIP_REPLY,
                        RelationshipReplyRequest(
                            command.utterance,
                            stance_summary,
                            self._runtime_identity,
                        ),
                    )
                ).value
            except Exception:
                return self._failure(
                    context,
                    command,
                    basis,
                    "relationship-provider-failed",
                )
            if (
                not isinstance(reply_result, RelationshipReplyResult)
                or not reply_result.reply_text.strip()
                or reply_result.language != command.language
            ):
                return self._failure(
                    context,
                    command,
                    basis,
                    "relationship-provider-invalid-output",
                )
            guarded_reply = self._runtime_identity.guard_reply(
                reply_result.reply_text
            )
            if guarded_reply is None:
                return self._failure(
                    context,
                    command,
                    basis,
                    "relationship-provider-invalid-output",
                )
            reply_text = guarded_reply
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=summary,
            expression_candidate=ExpressionCandidate(
                text=reply_text,
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

    def _failure(
        self,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
        code: str,
    ) -> CognitiveProposal:
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary="Relationship 本轮失败关闭。",
            expression_candidate=ExpressionCandidate(
                text="（无关系状态相关内容）",
                language=command.language,
            ),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                relationship=RelationshipAdjudicationRequest(
                    basis=basis,
                    relationship_enabled=True,
                    relationship_target_id=context.profile_id,
                    current_state=base.impact_envelope.relationship.current_state,
                    candidates=(),
                    failure_code=code,
                ),
            ),
        )

    @classmethod
    def for_profile(
        cls,
        profile: str,
        *,
        deepseek_transport: object | None = None,
        credential_ref: object | None = None,
        runtime_identity: RuntimeIdentityProjection | None = None,
    ) -> "ControlledRelationshipCognition":
        if profile != "default":
            raise ValueError("Relationship profile adapter is unavailable")
        from dynamic_subject_agent.deepseek import DeepSeekRelationshipProvider

        return cls(
            provider=DeepSeekRelationshipProvider(
                transport=deepseek_transport,
                credential_ref=credential_ref,
            ),
            runtime_identity=runtime_identity,
        )


__all__ = [
    "ALL_RELATIONSHIP_EVENTS",
    "ControlledRelationshipCognition",
    "RelationshipProviderAdapter",
    "NO_UPDATE_EVENTS",
    "RELATIONSHIP_POLICY_VERSION",
    "RelationshipProviderRequest",
    "RelationshipProviderResult",
    "RelationshipProposal",
    "RelationshipReplyRequest",
    "RelationshipReplyResult",
    "UPDATE_EVENTS",
]

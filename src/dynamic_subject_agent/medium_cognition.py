"""Provider-neutral cognition for evidence-gated Medium State."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    MediumStateChangeCandidate,
    SubjectStateAdjudicationRequest,
    SubjectStateReadView,
)
from dynamic_subject_agent.medium_state import (
    POLICY_HASH,
    POLICY_ID,
    POLICY_VERSION,
    SIGNALS,
    MediumStateCandidate,
    MediumStateEngine,
    MediumStateRecord,
    virtual_or_current,
)
from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ModelGatewayFailure,
    ModelResult,
    ModelTask,
    ModelTaskKind,
    ProviderAdapter,
    ProviderCapabilities,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
)
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.runtime_identity_reply import guard_runtime_identity_reply
from dynamic_subject_agent.timeline import SubjectCommand


_NO_MEDIUM_EXPRESSION = "（无中期状态相关内容）"
_BASELINE_LABELS = {
    "settled": "平稳",
    "concerned": "关切",
    "encouraged": "受到鼓舞",
}


@dataclass(frozen=True)
class MediumClassificationRequest:
    current_user_message: str
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


@dataclass(frozen=True)
class MediumClassificationResult:
    candidate: MediumStateCandidate | None
    experience_summary: str
    language: str


@dataclass(frozen=True)
class MediumReplyRequest:
    current_user_message: str
    baseline: str
    runtime_identity: RuntimeIdentityProjection | None


@dataclass(frozen=True)
class MediumReplyResult:
    reply_text: str
    language: str


class MediumOutputRejected(ValueError):
    pass


def canonicalize_medium_output(
    raw: object,
    *,
    request: MediumClassificationRequest,
) -> MediumClassificationResult:
    if not isinstance(raw, dict):
        raise MediumOutputRejected("Medium output must be an object")
    expected = {"action", "signal", "evidence_quote", "experience_summary", "language"}
    if set(raw) != expected:
        raise MediumOutputRejected("Medium fields differ from contract")
    normalized = dict(raw)
    action = normalized.get("action")
    if action == "noop":
        if normalized.get("evidence_quote") is None:
            normalized["evidence_quote"] = ""
        if normalized.get("experience_summary") is None:
            normalized["experience_summary"] = ""
    if action not in {"noop", "signal"} or normalized.get("language") != "zh":
        raise MediumOutputRejected("Medium action or language is invalid")
    signal = normalized.get("signal")
    evidence = normalized.get("evidence_quote")
    summary = normalized.get("experience_summary")
    if not isinstance(summary, str) or len(summary) > 1_000:
        raise MediumOutputRejected("Medium summary is invalid")
    if action == "noop":
        if signal is not None or evidence != "":
            raise MediumOutputRejected("Medium noop shape is invalid")
        candidate = None
    else:
        if (
            signal not in SIGNALS
            or not isinstance(evidence, str)
            or not evidence.strip()
            or len(evidence) > 1_000
            or evidence not in request.current_user_message
        ):
            raise MediumOutputRejected("Medium signal shape is invalid")
        candidate = MediumStateCandidate("signal", signal, evidence)
    return MediumClassificationResult(candidate, summary, "zh")


class MediumProviderAdapter(ProviderAdapter):
    def __init__(self, *, provider: object, capabilities: ProviderCapabilities) -> None:
        if not callable(getattr(provider, "classify", None)) or not callable(
            getattr(provider, "reply", None)
        ):
            raise TypeError("Medium provider requires classify and reply")
        self._provider = provider
        self.capabilities = capabilities

    def invoke(self, task: ModelTask) -> ModelResult:
        if task.kind is ModelTaskKind.MEDIUM_STATE_CLASSIFICATION:
            if not isinstance(task.payload, MediumClassificationRequest):
                raise ModelGatewayFailure("medium-classification-task-invalid")
            value = self._provider.classify(task.payload)
        elif task.kind is ModelTaskKind.MEDIUM_STATE_REPLY:
            if not isinstance(task.payload, MediumReplyRequest):
                raise ModelGatewayFailure("medium-reply-task-invalid")
            value = self._provider.reply(task.payload)
        else:
            raise ModelGatewayFailure("model-task-unavailable")
        return ModelResult(task.kind, value)


class ControlledMediumCognition(CognitionEngine):
    adapter_version = "medium-cognition-1.0"
    experimental = True
    test_only = True

    def __init__(self, *, gateway: ModelGateway) -> None:
        self._gateway = gateway
        self.provider_authority = gateway.capabilities.provider_id
        self.test_only = gateway.capabilities.provider_id.startswith("test-")

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        current = virtual_or_current(context.medium_state)
        direct_query = any(
            marker in command.utterance
            for marker in ("你现在的中期状态是什么", "当前 Medium State 是什么", "当前基线是什么")
        )
        if direct_query:
            result = MediumClassificationResult(None, "Python 直接查询 Medium State。", command.language)
            deterministic_reply = (
                f"我当前的中期基线是“{_BASELINE_LABELS[current.baseline]}”，"
                f"版本 {current.version}。"
            )
        else:
            request = MediumClassificationRequest(command.utterance)
            try:
                result = self._gateway.execute(
                    ModelTask(ModelTaskKind.MEDIUM_STATE_CLASSIFICATION, request)
                ).value
            except Exception:
                return self._failure(
                    context,
                    command,
                    basis,
                    plan.expected_basis.head_sequence,
                    "medium-classification-failed",
                )
            deterministic_reply = None
        if (
            not isinstance(result, MediumClassificationResult)
            or result.candidate is not None
            and not isinstance(result.candidate, MediumStateCandidate)
            or not isinstance(result.experience_summary, str)
            or result.language != command.language
        ):
            return self._failure(
                context,
                command,
                basis,
                plan.expected_basis.head_sequence,
                "medium-classification-invalid",
            )
        prepared = MediumStateEngine().evaluate(
            current_head_sequence=plan.expected_basis.head_sequence,
            source_user_message_id=plan.operation_ref.operation_id,
            message_text=command.utterance,
            current_state=current,
            recent_completed_signals=context.medium_signals,
            candidate=result.candidate,
        )
        relevant = direct_query or (
            result.candidate is not None
            and prepared.reason_code != "direct_subject_state_command"
        )
        if deterministic_reply is not None:
            expression = deterministic_reply
        elif relevant:
            try:
                reply = self._gateway.execute(
                    ModelTask(
                        ModelTaskKind.MEDIUM_STATE_REPLY,
                        MediumReplyRequest(
                            command.utterance,
                            prepared.after_baseline,
                            context.runtime_identity,
                        ),
                    )
                ).value
            except Exception:
                return self._failure(
                    context,
                    command,
                    basis,
                    plan.expected_basis.head_sequence,
                    "medium-reply-failed",
                )
            if (
                not isinstance(reply, MediumReplyResult)
                or reply.language != command.language
                or not reply.reply_text.strip()
            ):
                return self._failure(
                    context,
                    command,
                    basis,
                    plan.expected_basis.head_sequence,
                    "medium-reply-invalid",
                )
            expression = (
                reply.reply_text
                if not isinstance(
                    context.runtime_identity,
                    RuntimeIdentityProjection,
                )
                else guard_runtime_identity_reply(reply.reply_text)
            )
            if expression is None:
                return self._failure(
                    context,
                    command,
                    basis,
                    plan.expected_basis.head_sequence,
                    "medium-reply-invalid",
                )
        else:
            expression = _NO_MEDIUM_EXPRESSION
        candidates: tuple[MediumStateChangeCandidate, ...] = ()
        if result.candidate is not None and result.candidate.action == "signal":
            candidates = (
                MediumStateChangeCandidate(
                    candidate_id=str(
                        uuid5(
                            NAMESPACE_URL,
                            f"medium:{basis.operation_id}:{result.candidate.signal}:{result.candidate.evidence_quote}",
                        )
                    ),
                    target_profile_id=context.profile_id,
                    evidence_refs=(basis.operation_id,),
                    candidate=result.candidate,
                ),
            )
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=result.experience_summary or "Medium State 完成有界裁决。",
            expression_candidate=ExpressionCandidate(expression, command.language),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                subject_state=SubjectStateAdjudicationRequest(
                    basis=basis,
                    current_state=SubjectStateReadView(
                        (),
                        (),
                        situated_state=context.situated_state,
                        medium_state=current,
                        medium_signals=context.medium_signals,
                    ),
                    situated_effect_candidates=(),
                    development_candidates=(),
                    current_user_message=command.utterance,
                    source_user_message_id=plan.operation_ref.operation_id,
                    observed_at_us=context.observed_at_us,
                    medium_candidates=candidates,
                    medium_expression_active=relevant,
                    medium_expression_priority=direct_query,
                    current_head_sequence=plan.expected_basis.head_sequence,
                ),
            ),
        )

    def _failure(
        self,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
        current_head_sequence: int,
        code: str,
    ) -> CognitiveProposal:
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary="Medium State 本轮失败关闭。",
            expression_candidate=ExpressionCandidate(_NO_MEDIUM_EXPRESSION, command.language),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                subject_state=SubjectStateAdjudicationRequest(
                    basis=basis,
                    current_state=SubjectStateReadView(
                        (),
                        (),
                        situated_state=context.situated_state,
                        medium_state=virtual_or_current(context.medium_state),
                        medium_signals=context.medium_signals,
                    ),
                    situated_effect_candidates=(),
                    development_candidates=(),
                    current_user_message=command.utterance,
                    source_user_message_id=basis.operation_id,
                    observed_at_us=context.observed_at_us,
                    medium_failure_code=code,
                    current_head_sequence=current_head_sequence,
                ),
            ),
        )


__all__ = [
    "ControlledMediumCognition",
    "MediumClassificationRequest",
    "MediumClassificationResult",
    "MediumOutputRejected",
    "MediumProviderAdapter",
    "MediumReplyRequest",
    "MediumReplyResult",
    "canonicalize_medium_output",
]

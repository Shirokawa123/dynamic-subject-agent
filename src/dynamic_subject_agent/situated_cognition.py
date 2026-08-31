"""Provider-neutral cognition for short-lived Situated State."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    SituatedEffectCandidate,
    SubjectStateAdjudicationRequest,
    SubjectStateReadView,
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
from dynamic_subject_agent.situated_state import (
    POLICY_HASH,
    POLICY_ID,
    POLICY_VERSION,
    POSTURES,
    SituatedStateCandidate,
    SituatedStateEngine,
    SituatedStateTarget,
    direct_command_posture,
    provider_projection,
)
from dynamic_subject_agent.timeline import SubjectCommand


_NO_SITUATED_EXPRESSION = "（无情境状态相关内容）"


@dataclass(frozen=True)
class SituatedClassificationRequest:
    current_user_message: str
    active_state: tuple[SituatedStateTarget, ...]
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


@dataclass(frozen=True)
class SituatedClassificationResult:
    candidate: SituatedStateCandidate | None
    experience_summary: str
    language: str


@dataclass(frozen=True)
class SituatedReplyRequest:
    current_user_message: str
    posture: str


@dataclass(frozen=True)
class SituatedReplyResult:
    reply_text: str
    language: str


class SituatedOutputRejected(ValueError):
    pass


def canonicalize_situated_output(
    raw: object,
    *,
    request: SituatedClassificationRequest,
) -> SituatedClassificationResult:
    if not isinstance(raw, dict):
        raise SituatedOutputRejected("Situated output must be an object")
    expected = {"action", "posture", "evidence_quote", "experience_summary", "language"}
    if set(raw) != expected:
        raise SituatedOutputRejected("Situated fields differ from contract")
    normalized = dict(raw)
    action = normalized.get("action")
    if action == "noop":
        if normalized.get("evidence_quote") is None:
            normalized["evidence_quote"] = ""
        if normalized.get("experience_summary") is None:
            normalized["experience_summary"] = ""
    if action not in {"noop", "set"}:
        raise SituatedOutputRejected("Situated action is invalid")
    posture = normalized.get("posture")
    evidence = normalized.get("evidence_quote")
    summary = normalized.get("experience_summary")
    if normalized.get("language") != "zh":
        raise SituatedOutputRejected("Situated language is invalid")
    if not isinstance(summary, str) or len(summary) > 1_000:
        raise SituatedOutputRejected("Situated summary is invalid")
    if action == "noop":
        if posture is not None or evidence != "":
            raise SituatedOutputRejected("Situated noop shape is invalid")
        candidate = None
    else:
        if (
            posture not in POSTURES
            or not isinstance(evidence, str)
            or not evidence.strip()
            or len(evidence) > 1_000
            or evidence not in request.current_user_message
        ):
            raise SituatedOutputRejected("Situated set shape is invalid")
        candidate = SituatedStateCandidate("set", posture, evidence)
    return SituatedClassificationResult(
        candidate=candidate,
        experience_summary=summary,
        language="zh",
    )


class SituatedProviderAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        provider: object,
        capabilities: ProviderCapabilities,
    ) -> None:
        if not callable(getattr(provider, "classify", None)) or not callable(
            getattr(provider, "reply", None)
        ):
            raise TypeError("Situated provider requires classify and reply")
        self._provider = provider
        self.capabilities = capabilities

    def invoke(self, task: ModelTask) -> ModelResult:
        if task.kind is ModelTaskKind.SITUATED_STATE_CLASSIFICATION:
            if not isinstance(task.payload, SituatedClassificationRequest):
                raise ModelGatewayFailure("situated-classification-task-invalid")
            value = self._provider.classify(task.payload)
        elif task.kind is ModelTaskKind.SITUATED_STATE_REPLY:
            if not isinstance(task.payload, SituatedReplyRequest):
                raise ModelGatewayFailure("situated-reply-task-invalid")
            value = self._provider.reply(task.payload)
        else:
            raise ModelGatewayFailure("model-task-unavailable")
        return ModelResult(kind=task.kind, value=value)


class ControlledSituatedCognition(CognitionEngine):
    adapter_version = "situated-cognition-1.0"
    experimental = True
    test_only = True

    def __init__(self, *, gateway: ModelGateway) -> None:
        if not isinstance(gateway, ModelGateway):
            raise TypeError("gateway must be ModelGateway")
        self.provider_authority = gateway.capabilities.provider_id
        self.test_only = gateway.capabilities.provider_id.startswith("test-")
        self._gateway = gateway

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        now_us = context.observed_at_us
        active_projection = provider_projection(context.situated_state, now_us=now_us)
        direct_query = any(
            marker in command.utterance
            for marker in ("你现在是什么状态", "当前情境状态是什么", "你现在的姿态是什么")
        )
        commanded_posture = direct_command_posture(command.utterance)
        if direct_query:
            result = SituatedClassificationResult(None, "Python 直接查询 Situated State。", command.language)
            deterministic_reply = (
                f"我当前的短时姿态是 {context.situated_state.posture}。"
                if context.situated_state is not None
                else "我当前没有持续中的短时情境姿态。"
            )
        elif commanded_posture is not None:
            result = SituatedClassificationResult(
                SituatedStateCandidate(
                    "set",
                    commanded_posture,
                    command.utterance.strip(),
                ),
                "Python 识别到直接状态命令，交由 Domain 拒绝。",
                command.language,
            )
            deterministic_reply = (
                "短时姿态不会因为直接命令而改变；它只会根据有依据的当前经历形成。"
            )
        else:
            request = SituatedClassificationRequest(
                current_user_message=command.utterance,
                active_state=active_projection,
            )
            try:
                result = self._gateway.execute(
                    ModelTask(ModelTaskKind.SITUATED_STATE_CLASSIFICATION, request)
                ).value
            except Exception:
                return self._failure_proposal(context, command, basis, "situated-classification-failed")
            deterministic_reply = None
        if (
            not isinstance(result, SituatedClassificationResult)
            or result.candidate is not None
            and not isinstance(result.candidate, SituatedStateCandidate)
            or not isinstance(result.experience_summary, str)
            or len(result.experience_summary) > 1_000
            or result.language != command.language
        ):
            return self._failure_proposal(context, command, basis, "situated-classification-invalid")
        prepared = SituatedStateEngine().evaluate(
            source_user_message_id=plan.operation_ref.operation_id,
            message_text=command.utterance,
            current_state=context.situated_state,
            candidate=result.candidate,
            analysis_status="succeeded",
            now_us=now_us,
        )
        reply_posture = prepared.posture if prepared.action in {"set", "carry"} else None
        if deterministic_reply is not None:
            expression = deterministic_reply
        elif reply_posture is not None:
            try:
                reply = self._gateway.execute(
                    ModelTask(
                        ModelTaskKind.SITUATED_STATE_REPLY,
                        SituatedReplyRequest(command.utterance, reply_posture),
                    )
                ).value
            except Exception:
                return self._failure_proposal(context, command, basis, "situated-reply-failed")
            if (
                not isinstance(reply, SituatedReplyResult)
                or reply.language != command.language
                or not reply.reply_text.strip()
                or len(reply.reply_text) > 8_000
            ):
                return self._failure_proposal(context, command, basis, "situated-reply-invalid")
            expression = reply.reply_text
        else:
            expression = _NO_SITUATED_EXPRESSION
        candidates: tuple[SituatedEffectCandidate, ...] = ()
        if result.candidate is not None and result.candidate.action == "set":
            candidates = (
                SituatedEffectCandidate(
                    candidate_id=str(
                        uuid5(
                            NAMESPACE_URL,
                            f"situated:{basis.operation_id}:{result.candidate.posture}:{result.candidate.evidence_quote}",
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
            experience_summary=result.experience_summary or "Situated State 完成有界裁决。",
            expression_candidate=ExpressionCandidate(expression, command.language),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                subject_state=SubjectStateAdjudicationRequest(
                    basis=basis,
                    current_state=SubjectStateReadView((), (), context.situated_state),
                    situated_effect_candidates=candidates,
                    development_candidates=(),
                    current_user_message=command.utterance,
                    source_user_message_id=plan.operation_ref.operation_id,
                    observed_at_us=now_us,
                    situated_expression_active=(
                        deterministic_reply is not None or reply_posture is not None
                    ),
                ),
            ),
        )

    def _failure_proposal(
        self,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
        code: str,
    ) -> CognitiveProposal:
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary="Situated State 本轮失败关闭。",
            expression_candidate=ExpressionCandidate(_NO_SITUATED_EXPRESSION, command.language),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                subject_state=SubjectStateAdjudicationRequest(
                    basis=basis,
                    current_state=SubjectStateReadView((), (), context.situated_state),
                    situated_effect_candidates=(),
                    development_candidates=(),
                    current_user_message=command.utterance,
                    source_user_message_id=basis.operation_id,
                    observed_at_us=context.observed_at_us,
                    situated_failure_code=code,
                ),
            ),
        )


__all__ = [
    "ControlledSituatedCognition",
    "SituatedClassificationRequest",
    "SituatedClassificationResult",
    "SituatedOutputRejected",
    "SituatedProviderAdapter",
    "SituatedReplyRequest",
    "SituatedReplyResult",
    "canonicalize_situated_output",
]

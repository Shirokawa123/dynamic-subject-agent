"""Two-stage cognition for participant goals and commitments."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    ExperienceAdjudicationRequest,
    ExperienceChangeCandidate,
    ExperienceReadView,
)
from dynamic_subject_agent.participant_goals import (
    ACTIVE_RECORD_LIMIT,
    MAX_EVIDENCE_QUOTE_CHARS,
    MAX_TERMS_CHARS,
    POLICY_HASH,
    POLICY_ID,
    POLICY_VERSION,
    REPLY_RECORD_LIMIT,
    ParticipantGoalCommitmentCandidate,
    ParticipantGoalCommitmentEngine,
    ParticipantGoalCommitmentRecord,
    ParticipantGoalCommitmentTarget,
    active_targets,
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
from dynamic_subject_agent.timeline import SubjectCommand


_NO_GOAL_EXPRESSION = "（无目标或承诺相关内容）"


class ParticipantGoalOutputRejected(ValueError):
    """A provider-neutral structured result cannot be canonicalized safely."""


def canonicalize_participant_goal_output(
    raw: object,
    *,
    request: ParticipantGoalClassificationRequest,
) -> ParticipantGoalClassificationResult:
    """Normalize harmless noop variants, then validate the exact task contract."""

    if not isinstance(raw, dict):
        raise ParticipantGoalOutputRejected("classification output must be an object")
    expected = {
        "action",
        "kind",
        "terms",
        "target_ref",
        "next_status",
        "evidence_quote",
        "selected_turn_refs",
        "experience_summary",
        "language",
    }
    if set(raw) != expected:
        raise ParticipantGoalOutputRejected("classification fields differ from contract")
    normalized = dict(raw)
    action = normalized.get("action")
    if action == "noop":
        if normalized.get("evidence_quote") is None:
            normalized["evidence_quote"] = ""
        if normalized.get("experience_summary") is None:
            normalized["experience_summary"] = ""
        if normalized.get("selected_turn_refs") is None:
            normalized["selected_turn_refs"] = []
    if action not in {"create", "revise", "transition", "noop"}:
        raise ParticipantGoalOutputRejected("action is outside the closed set")
    if normalized.get("kind") not in {None, "goal", "commitment"}:
        raise ParticipantGoalOutputRejected("kind is outside the closed set")
    terms = normalized.get("terms")
    if terms is not None and (
        not isinstance(terms, str) or len(terms) > MAX_TERMS_CHARS
    ):
        raise ParticipantGoalOutputRejected("terms are invalid")
    target_ref = normalized.get("target_ref")
    projected_refs = {record.turn_ref for record in request.active_records}
    if target_ref is not None and (
        not isinstance(target_ref, str) or target_ref not in projected_refs
    ):
        raise ParticipantGoalOutputRejected("target_ref is not projected")
    next_status = normalized.get("next_status")
    if next_status not in {
        None,
        "active",
        "achieved",
        "abandoned",
        "fulfilled",
        "released",
    }:
        raise ParticipantGoalOutputRejected("next_status is outside the closed set")
    evidence_quote = normalized.get("evidence_quote")
    if (
        not isinstance(evidence_quote, str)
        or len(evidence_quote) > MAX_EVIDENCE_QUOTE_CHARS
        or evidence_quote
        and evidence_quote not in request.current_user_message
    ):
        raise ParticipantGoalOutputRejected("evidence is not verbatim")
    selected = normalized.get("selected_turn_refs")
    if (
        not isinstance(selected, list)
        or len(selected) > REPLY_RECORD_LIMIT
        or any(not isinstance(turn_ref, str) for turn_ref in selected)
        or len(set(selected)) != len(selected)
        or any(turn_ref not in projected_refs for turn_ref in selected)
    ):
        raise ParticipantGoalOutputRejected("reply selection is invalid")
    summary = normalized.get("experience_summary")
    if not isinstance(summary, str) or len(summary) > 1_000:
        raise ParticipantGoalOutputRejected("summary is invalid")
    if normalized.get("language") != "zh":
        raise ParticipantGoalOutputRejected("language is invalid")
    shape_valid = (
        action == "noop"
        and normalized["kind"] is None
        and terms is None
        and target_ref is None
        and next_status is None
        and evidence_quote == ""
    ) or (
        action == "create"
        and normalized["kind"] in {"goal", "commitment"}
        and isinstance(terms, str)
        and bool(terms.strip())
        and target_ref is None
        and next_status == "active"
        and bool(evidence_quote)
    ) or (
        action == "revise"
        and normalized["kind"] in {"goal", "commitment"}
        and isinstance(terms, str)
        and bool(terms.strip())
        and isinstance(target_ref, str)
        and next_status == "active"
        and bool(evidence_quote)
    ) or (
        action == "transition"
        and normalized["kind"] is None
        and terms is None
        and isinstance(target_ref, str)
        and next_status in {"achieved", "abandoned", "fulfilled", "released"}
        and bool(evidence_quote)
    )
    if not shape_valid:
        raise ParticipantGoalOutputRejected("action-specific shape is invalid")
    candidate = None
    if action != "noop":
        candidate = ParticipantGoalCommitmentCandidate(
            action=action,
            kind=normalized["kind"],
            terms=terms,
            target_ref=target_ref,
            next_status=next_status,
            evidence_quote=evidence_quote,
        )
    return ParticipantGoalClassificationResult(
        candidate=candidate,
        selected_turn_refs=tuple(selected),
        experience_summary=summary,
        language="zh",
    )


@dataclass(frozen=True)
class ParticipantGoalProviderRecord:
    turn_ref: str
    kind: str
    terms: str
    status: str


@dataclass(frozen=True)
class ParticipantGoalClassificationRequest:
    current_user_message: str
    active_records: tuple[ParticipantGoalProviderRecord, ...]
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


@dataclass(frozen=True)
class ParticipantGoalClassificationResult:
    candidate: ParticipantGoalCommitmentCandidate | None
    selected_turn_refs: tuple[str, ...]
    experience_summary: str
    language: str


@dataclass(frozen=True)
class ParticipantGoalReplyRecord:
    kind: str
    terms: str
    status: str


@dataclass(frozen=True)
class ParticipantGoalReplyRequest:
    current_user_message: str
    selected_records: tuple[ParticipantGoalReplyRecord, ...]
    runtime_identity: RuntimeIdentityProjection | None


@dataclass(frozen=True)
class ParticipantGoalReplyResult:
    reply_text: str
    language: str


@dataclass(frozen=True)
class DeterministicParticipantGoalRoute:
    candidate: ParticipantGoalCommitmentCandidate | None
    selected_turn_refs: tuple[str, ...]
    reply_text: str
    experience_summary: str


def route_participant_goal_deterministically(
    message: str,
    *,
    targets: tuple[ParticipantGoalCommitmentTarget, ...],
) -> DeterministicParticipantGoalRoute | None:
    """Handle explicit product grammar and direct queries without any model."""

    text = message.strip()
    bare = text.rstrip("。！？!? ")
    goals = tuple(target for target in targets if target.record.kind == "goal")
    commitments = tuple(
        target for target in targets if target.record.kind == "commitment"
    )
    if any(
        marker in bare
        for marker in (
            "我的目标是什么",
            "我现在的目标是什么",
            "我目前的目标是什么",
            "我有哪些目标",
            "我的目标有哪些",
        )
    ):
        selected = goals[:REPLY_RECORD_LIMIT]
        reply = (
            "你当前的目标是："
            + "；".join(target.record.terms for target in selected)
            + "。"
            if selected
            else "你目前还没有明确记录的目标。"
        )
        return DeterministicParticipantGoalRoute(
            candidate=None,
            selected_turn_refs=tuple(target.turn_ref for target in selected),
            reply_text=reply,
            experience_summary="Python 直接查询参与者目标。",
        )
    if any(
        marker in bare
        for marker in (
            "我的承诺是什么",
            "我现在的承诺是什么",
            "我目前的承诺是什么",
            "我有哪些承诺",
            "我的承诺有哪些",
        )
    ):
        selected = commitments[:REPLY_RECORD_LIMIT]
        reply = (
            "你当前的承诺是："
            + "；".join(target.record.terms for target in selected)
            + "。"
            if selected
            else "你目前还没有明确记录的承诺。"
        )
        return DeterministicParticipantGoalRoute(
            candidate=None,
            selected_turn_refs=tuple(target.turn_ref for target in selected),
            reply_text=reply,
            experience_summary="Python 直接查询参与者承诺。",
        )
    patterns = (
        (r"^我的目标改为([^。；;！？!?]+)(?:[。；;！？!?]|$)", "revise", "goal", goals, "active"),
        (r"^我的承诺改为([^。；;！？!?]+)(?:[。；;！？!?]|$)", "revise", "commitment", commitments, "active"),
        (r"^我的目标是([^。；;！？!?]+)(?:[。；;！？!?]|$)", "create", "goal", (), "active"),
        (r"^我承诺([^。；;！？!?]+)(?:[。；;！？!?]|$)", "create", "commitment", (), "active"),
    )
    for pattern, action, kind, candidates, next_status in patterns:
        match = re.match(pattern, text)
        if match is None:
            continue
        terms = match.group(1).strip()
        if not terms:
            return None
        target_ref = candidates[0].turn_ref if candidates else None
        return DeterministicParticipantGoalRoute(
            candidate=ParticipantGoalCommitmentCandidate(
                action=action,
                kind=kind,
                terms=terms,
                target_ref=target_ref,
                next_status=next_status,
                evidence_quote=match.group(0).rstrip("。；;！？!? "),
            ),
            selected_turn_refs=(),
            reply_text="我会按你明确说出的内容记录这项目标或承诺变化。",
            experience_summary="Python 识别明确的参与者目标或承诺变化。",
        )
    transitions = (
        (("我的目标已达成", "目标已达成"), goals, "achieved"),
        (("我放弃这个目标", "我放弃目标"), goals, "abandoned"),
        (("我已履行承诺", "我的承诺已履行"), commitments, "fulfilled"),
        (("我取消承诺", "我解除承诺"), commitments, "released"),
    )
    for phrases, candidates, next_status in transitions:
        if bare not in phrases or not candidates:
            continue
        return DeterministicParticipantGoalRoute(
            candidate=ParticipantGoalCommitmentCandidate(
                action="transition",
                kind=None,
                terms=None,
                target_ref=candidates[0].turn_ref,
                next_status=next_status,
                evidence_quote=bare,
            ),
            selected_turn_refs=(),
            reply_text="我会按你的明确报告更新这项目标或承诺状态。",
            experience_summary="Python 识别明确的参与者终态报告。",
        )
    relevance_markers = (
        "目标",
        "承诺",
        "达成",
        "放弃",
        "履行",
        "解除",
        "取消",
    )
    if not targets and not any(marker in bare for marker in relevance_markers):
        return DeterministicParticipantGoalRoute(
            candidate=None,
            selected_turn_refs=(),
            reply_text=_NO_GOAL_EXPRESSION,
            experience_summary="Python 判定本轮与参与者目标或承诺无关。",
        )
    return None


class ParticipantGoalProviderAdapter(ProviderAdapter):
    """Adapt one provider's goal methods to the provider-neutral task Port."""

    def __init__(
        self,
        *,
        provider: object,
        capabilities: ProviderCapabilities,
    ) -> None:
        if not callable(getattr(provider, "classify", None)) or not callable(
            getattr(provider, "reply", None)
        ):
            raise TypeError("participant goal provider requires classify and reply")
        if not isinstance(capabilities, ProviderCapabilities):
            raise TypeError("capabilities must be ProviderCapabilities")
        self._provider = provider
        self.capabilities = capabilities

    def invoke(self, task: ModelTask) -> ModelResult:
        if task.kind is ModelTaskKind.PARTICIPANT_GOAL_CLASSIFICATION:
            if not isinstance(task.payload, ParticipantGoalClassificationRequest):
                raise ModelGatewayFailure("participant-goal-classification-task-invalid")
            value = self._provider.classify(task.payload)
        elif task.kind is ModelTaskKind.PARTICIPANT_GOAL_REPLY:
            if not isinstance(task.payload, ParticipantGoalReplyRequest):
                raise ModelGatewayFailure("participant-goal-reply-task-invalid")
            value = self._provider.reply(task.payload)
        else:
            raise ModelGatewayFailure("model-task-unavailable")
        return ModelResult(kind=task.kind, value=value)


class ControlledParticipantGoalCognition(CognitionEngine):
    """No-write cognition; Experience performs the authoritative adjudication."""

    adapter_version = "participant-goal-cognition-1.0"
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
        records = tuple(context.participant_goal_commitments[:ACTIVE_RECORD_LIMIT])
        targets = active_targets(records)
        request = ParticipantGoalClassificationRequest(
            current_user_message=command.utterance,
            active_records=tuple(
                ParticipantGoalProviderRecord(
                    turn_ref=target.turn_ref,
                    kind=target.record.kind,
                    terms=target.record.terms,
                    status=target.record.status,
                )
                for target in targets
            ),
        )
        deterministic = route_participant_goal_deterministically(
            command.utterance,
            targets=targets,
        )
        if deterministic is not None:
            result = ParticipantGoalClassificationResult(
                candidate=deterministic.candidate,
                selected_turn_refs=deterministic.selected_turn_refs,
                experience_summary=deterministic.experience_summary,
                language=command.language,
            )
        else:
            try:
                gateway_result = self._gateway.execute(
                    ModelTask(
                        kind=ModelTaskKind.PARTICIPANT_GOAL_CLASSIFICATION,
                        payload=request,
                    )
                )
                result = gateway_result.value
            except Exception as error:
                del error
                return self._failure_proposal(
                    context=context,
                    basis=basis,
                    command=command,
                    code="participant-goal-classification-failed",
                )
        if (
            not isinstance(result, ParticipantGoalClassificationResult)
            or result.candidate is not None
            and not isinstance(result.candidate, ParticipantGoalCommitmentCandidate)
            or result.candidate is not None
            and result.candidate.action not in {"create", "revise", "transition"}
            or result.candidate is not None
            and not isinstance(result.candidate.evidence_quote, str)
            or result.candidate is not None
            and result.candidate.kind not in {None, "goal", "commitment"}
            or result.candidate is not None
            and result.candidate.terms is not None
            and not isinstance(result.candidate.terms, str)
            or result.candidate is not None
            and result.candidate.target_ref is not None
            and not isinstance(result.candidate.target_ref, str)
            or result.candidate is not None
            and result.candidate.next_status
            not in {None, "active", "achieved", "abandoned", "fulfilled", "released"}
            or not isinstance(result.selected_turn_refs, tuple)
            or len(result.selected_turn_refs) > REPLY_RECORD_LIMIT
            or any(
                not isinstance(turn_ref, str)
                for turn_ref in result.selected_turn_refs
            )
            or len(set(result.selected_turn_refs)) != len(result.selected_turn_refs)
            or not isinstance(result.experience_summary, str)
            or len(result.experience_summary) > 1_000
            or result.language != command.language
        ):
            return self._failure_proposal(
                context=context,
                basis=basis,
                command=command,
                code="participant-goal-classification-invalid",
            )
        by_ref = {target.turn_ref: target.record for target in targets}
        if any(turn_ref not in by_ref for turn_ref in result.selected_turn_refs):
            return self._failure_proposal(
                context=context,
                basis=basis,
                command=command,
                code="participant-goal-selection-invalid",
            )
        selected = tuple(by_ref[turn_ref] for turn_ref in result.selected_turn_refs)
        prechecked = ParticipantGoalCommitmentEngine().evaluate(
            source_user_message_id=plan.operation_ref.operation_id,
            message_text=command.utterance,
            current_records=targets,
            candidate=result.candidate,
        )
        relevant = bool(selected) or prechecked.decision != "no_update"
        if deterministic is not None:
            expression = deterministic.reply_text
        elif relevant:
            try:
                reply_result = self._gateway.execute(
                    ModelTask(
                        kind=ModelTaskKind.PARTICIPANT_GOAL_REPLY,
                        payload=ParticipantGoalReplyRequest(
                            current_user_message=command.utterance,
                            selected_records=tuple(
                                ParticipantGoalReplyRecord(
                                    kind=record.kind,
                                    terms=record.terms,
                                    status=record.status,
                                )
                                for record in selected
                            ),
                            runtime_identity=context.runtime_identity,
                        ),
                    )
                )
                reply = reply_result.value
            except Exception as error:
                del error
                return self._failure_proposal(
                    context=context,
                    basis=basis,
                    command=command,
                    code="participant-goal-reply-failed",
                )
            if (
                not isinstance(reply, ParticipantGoalReplyResult)
                or reply.language != command.language
                or not isinstance(reply.reply_text, str)
                or not reply.reply_text.strip()
                or len(reply.reply_text) > 8_000
            ):
                return self._failure_proposal(
                    context=context,
                    basis=basis,
                    command=command,
                    code="participant-goal-reply-invalid",
                )
            expression = (
                reply.reply_text
                if not isinstance(
                    context.runtime_identity,
                    RuntimeIdentityProjection,
                )
                else context.runtime_identity.guard_reply(reply.reply_text)
            )
            if expression is None:
                return self._failure_proposal(
                    context=context,
                    basis=basis,
                    command=command,
                    code="participant-goal-reply-invalid",
                )
        else:
            expression = _NO_GOAL_EXPRESSION
        candidates: tuple[ExperienceChangeCandidate, ...] = ()
        if result.candidate is not None and result.candidate.action != "noop":
            candidates = (
                ExperienceChangeCandidate(
                    candidate_id=str(
                        uuid5(
                            NAMESPACE_URL,
                            "participant-goal:"
                            f"{basis.operation_id}:{result.candidate.action}:"
                            f"{result.candidate.evidence_quote}",
                        )
                    ),
                    target_experience_id=basis.experience_id,
                    evidence_refs=(basis.operation_id,),
                    participant_goal_candidate=result.candidate,
                ),
            )
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=(
                result.experience_summary.strip()
                or "本轮完成参与者目标与承诺的有界分类。"
            ),
            expression_candidate=ExpressionCandidate(
                text=expression,
                language=result.language,
            ),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                experience=ExperienceAdjudicationRequest(
                    basis=basis,
                    current_state=ExperienceReadView(
                        verified_prefix_digest=basis.verified_prefix_digest,
                        memory_trace_refs=tuple(
                            memory.memory_id for memory in context.active_memories
                        ),
                        active_memories=context.active_memories,
                        participant_goal_commitments=records,
                    ),
                    candidates=candidates,
                    current_user_message=command.utterance,
                    source_user_message_id=plan.operation_ref.operation_id,
                    selected_participant_goal_record_ids=tuple(
                        record.record_id for record in selected
                    ),
                    participant_goal_expression_priority=(
                        deterministic is not None
                    ),
                ),
            ),
        )

    def _failure_proposal(
        self,
        *,
        context: CognitionRuntimeView,
        basis: ExperienceBasis,
        command: SubjectCommand,
        code: str,
    ) -> CognitiveProposal:
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary="参与者目标能力本轮失败关闭，未产生状态候选。",
            expression_candidate=ExpressionCandidate(
                text=_NO_GOAL_EXPRESSION,
                language=command.language,
            ),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                experience=ExperienceAdjudicationRequest(
                    basis=basis,
                    current_state=ExperienceReadView(
                        verified_prefix_digest=basis.verified_prefix_digest,
                        memory_trace_refs=tuple(
                            memory.memory_id for memory in context.active_memories
                        ),
                        active_memories=context.active_memories,
                        participant_goal_commitments=(
                            context.participant_goal_commitments
                        ),
                    ),
                    candidates=(),
                    current_user_message=command.utterance,
                    participant_goal_failure_code=code,
                ),
            ),
        )


__all__ = [
    "ControlledParticipantGoalCognition",
    "DeterministicParticipantGoalRoute",
    "ParticipantGoalOutputRejected",
    "ParticipantGoalClassificationRequest",
    "ParticipantGoalClassificationResult",
    "ParticipantGoalProviderAdapter",
    "ParticipantGoalProviderRecord",
    "ParticipantGoalReplyRecord",
    "ParticipantGoalReplyRequest",
    "ParticipantGoalReplyResult",
    "canonicalize_participant_goal_output",
    "route_participant_goal_deterministically",
]

"""Two-stage cognition for participant goals and commitments."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    ExperienceAdjudicationRequest,
    ExperienceChangeCandidate,
    ExperienceReadView,
)
from dynamic_subject_agent.participant_goals import (
    ACTIVE_RECORD_LIMIT,
    POLICY_HASH,
    POLICY_ID,
    POLICY_VERSION,
    REPLY_RECORD_LIMIT,
    ParticipantGoalCommitmentCandidate,
    ParticipantGoalCommitmentEngine,
    ParticipantGoalCommitmentRecord,
    active_targets,
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


_NO_GOAL_EXPRESSION = "（无目标或承诺相关内容）"


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


@dataclass(frozen=True)
class ParticipantGoalReplyResult:
    reply_text: str
    language: str


class ControlledParticipantGoalCognition(CognitionEngine):
    """No-write cognition; Experience performs the authoritative adjudication."""

    adapter_version = "participant-goal-cognition-1.0"
    experimental = True
    test_only = True

    def __init__(self, *, provider: object) -> None:
        if not callable(getattr(provider, "classify", None)) or not callable(
            getattr(provider, "reply", None)
        ):
            raise TypeError("participant goal provider requires classify and reply")
        authority = getattr(provider, "provider_authority", M0_A_PROVIDER_AUTHORITY)
        if not isinstance(authority, str) or not authority:
            raise TypeError("provider_authority must be a non-empty string")
        self.provider_authority = authority
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
        try:
            result = self._provider.classify(request)
        except Exception as error:
            raise CognitionFailedClosed(
                "provider",
                "participant-goal-classification-failed",
                "participant goal classification failed without a usable result",
            ) from error
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
            raise CognitionFailedClosed(
                "provider",
                "participant-goal-classification-invalid",
                "participant goal classification returned an invalid bounded result",
            )
        by_ref = {target.turn_ref: target.record for target in targets}
        if any(turn_ref not in by_ref for turn_ref in result.selected_turn_refs):
            raise CognitionFailedClosed(
                "provider",
                "participant-goal-selection-invalid",
                "participant goal selection named an unprojected turn reference",
            )
        selected = tuple(by_ref[turn_ref] for turn_ref in result.selected_turn_refs)
        prechecked = ParticipantGoalCommitmentEngine().evaluate(
            source_user_message_id=plan.operation_ref.operation_id,
            message_text=command.utterance,
            current_records=targets,
            candidate=result.candidate,
        )
        relevant = bool(selected) or prechecked.decision != "no_update"
        if relevant:
            try:
                reply = self._provider.reply(
                    ParticipantGoalReplyRequest(
                        current_user_message=command.utterance,
                        selected_records=tuple(
                            ParticipantGoalReplyRecord(
                                kind=record.kind,
                                terms=record.terms,
                                status=record.status,
                            )
                            for record in selected
                        ),
                    )
                )
            except Exception as error:
                raise CognitionFailedClosed(
                    "provider",
                    "participant-goal-reply-failed",
                    "participant goal reply failed without usable text",
                ) from error
            if (
                not isinstance(reply, ParticipantGoalReplyResult)
                or reply.language != command.language
                or not isinstance(reply.reply_text, str)
                or not reply.reply_text.strip()
                or len(reply.reply_text) > 8_000
            ):
                raise CognitionFailedClosed(
                    "provider",
                    "participant-goal-reply-invalid",
                    "participant goal reply returned invalid bounded text",
                )
            expression = reply.reply_text
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
                ),
            ),
        )


__all__ = [
    "ControlledParticipantGoalCognition",
    "ParticipantGoalClassificationRequest",
    "ParticipantGoalClassificationResult",
    "ParticipantGoalProviderRecord",
    "ParticipantGoalReplyRecord",
    "ParticipantGoalReplyRequest",
    "ParticipantGoalReplyResult",
]

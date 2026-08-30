"""SubjectState Domain: short-lived Situated State and deferred Development."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from dynamic_subject_agent.timeline import (
    CandidateDecisionRecord,
    DecisionStatus,
    DevelopmentOutcome,
    SubjectCoreOutcome,
    SubjectStateDomainOutcome,
)
from dynamic_subject_agent.domains._shared import (
    DomainAdjudicationFailedClosed,
    DomainCapabilityState,
    ExperienceBasis,
    noop_decision,
    require_tuple,
    stable_id,
    validate_basis,
)
from dynamic_subject_agent.situated_state import (
    POLICY_HASH,
    POLICY_ID,
    POLICY_VERSION,
    POSTURES,
    SituatedStateCandidate,
    SituatedStateEngine,
    SituatedStateRecord,
)


@dataclass(frozen=True)
class SituatedEffectCandidate:
    candidate_id: str
    target_profile_id: str
    evidence_refs: tuple[str, ...]
    candidate: SituatedStateCandidate


@dataclass(frozen=True)
class DevelopmentChangeCandidate:
    candidate_id: str
    target_profile_id: str
    consolidation_eligibility_ref: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SubjectStateReadView:
    subject_core_revision_refs: tuple[str, ...]
    development_revision_refs: tuple[str, ...]
    situated_state: SituatedStateRecord | None = None


@dataclass(frozen=True)
class SubjectStateAdjudicationRequest:
    basis: ExperienceBasis
    current_state: SubjectStateReadView
    situated_effect_candidates: tuple[SituatedEffectCandidate, ...]
    development_candidates: tuple[DevelopmentChangeCandidate, ...]
    current_user_message: str = ""
    source_user_message_id: str = ""
    observed_at_us: int = 0
    situated_failure_code: str | None = None
    situated_expression_active: bool = False


class SubjectStateDomain:
    """Adjudicate Situated State without promoting it into Development."""

    material_change_capability = DomainCapabilityState.AVAILABLE

    def adjudicate(
        self,
        request: SubjectStateAdjudicationRequest,
    ) -> SubjectStateDomainOutcome:
        if not isinstance(request, SubjectStateAdjudicationRequest):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "wrong-domain-request",
                "SubjectStateDomain requires SubjectStateAdjudicationRequest",
            )
        basis = validate_basis(request.basis, domain="subject-state")
        if not isinstance(request.current_state, SubjectStateReadView):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "invalid-read-view",
                "SubjectState current state must be a typed read-only view",
            )
        situated = require_tuple(
            request.situated_effect_candidates,
            domain="subject-state",
            field="situated_effect_candidates",
        )
        development = require_tuple(
            request.development_candidates,
            domain="subject-state",
            field="development_candidates",
        )
        if development:
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "development-capability-unavailable",
                "Situated State cannot create Development changes",
            )
        if len(situated) > 1:
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "multiple-situated-candidates",
                "one turn may propose at most one Situated State candidate",
            )
        for change in situated:
            if not isinstance(change, SituatedEffectCandidate):
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "wrong-domain-candidate",
                    "only SituatedEffectCandidate may enter SubjectCore",
                )
            if change.target_profile_id != basis.profile_id:
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "candidate-target-mismatch",
                    "SituatedEffectCandidate names a different Profile",
                )
            if not isinstance(change.candidate, SituatedStateCandidate):
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "situated-candidate-invalid",
                    "Situated candidate must be typed",
                )
            try:
                UUID(change.candidate_id)
            except (TypeError, ValueError):
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "situated-candidate-identity-invalid",
                    "Situated candidate id must be canonical",
                ) from None
        current = request.current_state.situated_state
        if current is not None:
            self._validate_current(current)
        failure = request.situated_failure_code
        if not isinstance(request.situated_expression_active, bool):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "situated-expression-active-invalid",
                "Situated expression flag must be bool",
            )
        if failure is not None and (
            failure
            not in {
                "situated-classification-failed",
                "situated-classification-invalid",
                "situated-reply-failed",
                "situated-reply-invalid",
            }
            or situated
        ):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "situated-failure-invalid",
                "Situated failure must be typed and carry no candidate",
            )
        active = current is not None
        if not situated and not active and failure is None:
            return self._outcome(basis, None)
        if (
            request.observed_at_us <= 0
            or not request.current_user_message
            or not request.source_user_message_id
        ):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "situated-request-incomplete",
                "Situated adjudication requires message identity and observed time",
            )
        try:
            source_id = str(UUID(request.source_user_message_id))
        except (TypeError, ValueError):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "situated-source-identity-invalid",
                "Situated source identity must be canonical",
            ) from None
        if source_id != basis.operation_id:
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "situated-source-mismatch",
                "Situated source must be the current operation",
            )
        candidate = situated[0].candidate if situated else None
        plan = SituatedStateEngine().evaluate(
            source_user_message_id=request.source_user_message_id,
            message_text=request.current_user_message,
            current_state=current,
            candidate=candidate,
            analysis_status="failed" if failure is not None else "succeeded",
            now_us=request.observed_at_us,
        )
        state_id = (
            situated[0].candidate_id
            if situated and plan.action == "set"
            else plan.target_state_id
        )
        payload = {
            "status": (
                "failed-closed"
                if failure is not None
                else plan.decision.replace("_", "-")
            ),
            "action": plan.action,
            "reason_code": failure or plan.reason_code,
            "state_id": state_id,
            "posture": plan.posture,
            "source_user_message_id": plan.source_user_message_id,
            "evidence_quote": plan.evidence_quote,
            "target_state_id": plan.target_state_id,
            "remaining_turns": plan.remaining_turns,
            "expires_at_us": plan.expires_at_us,
            "used_for_reply": plan.action in {"set", "carry"},
            "policy_id": plan.policy_id,
            "policy_version": plan.policy_version,
            "policy_hash": plan.policy_hash,
        }
        return self._outcome(basis, payload)

    @staticmethod
    def _validate_current(record: SituatedStateRecord) -> None:
        try:
            UUID(record.state_id)
            UUID(record.source_user_message_id)
        except (TypeError, ValueError):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "situated-read-identity-invalid",
                "Situated read state requires canonical identities",
            ) from None
        if (
            record.status != "active"
            or record.posture not in POSTURES
            or record.remaining_turns not in {0, 1}
            or record.expires_at_us <= 0
            or record.policy_id != POLICY_ID
            or record.policy_version != POLICY_VERSION
            or record.policy_hash != POLICY_HASH
        ):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "situated-read-record-invalid",
                "Situated read state violates current policy",
            )

    @staticmethod
    def _outcome(
        basis: ExperienceBasis,
        situated_payload: dict[str, object] | None,
    ) -> SubjectStateDomainOutcome:
        top = noop_decision(
            basis,
            scope="subject-state",
            reason_code=(
                "subject-state.situated-adjudicated"
                if situated_payload is not None
                else "subject-state.no-material-change"
            ),
        )
        if situated_payload is None:
            subject_core = noop_decision(
                basis,
                scope="subject-core",
                reason_code="subject-state.subject-core.no-applicable-candidate",
            )
        else:
            subject_core = CandidateDecisionRecord(
                decision_id=stable_id(basis, "subject-core-decision"),
                scope="subject-core",
                status=DecisionStatus.NO_OP,
                reason=json.dumps(
                    {
                        "code": "subject-state.situated",
                        "provenance": basis.source_provenance,
                        "situated_state": situated_payload,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                rule_version="situated-state-1.0",
                actual_revision_ids=(),
            )
        return SubjectStateDomainOutcome(
            outcome_id=stable_id(basis, "subject-state-outcome"),
            decision=top,
            subject_core=SubjectCoreOutcome(
                outcome_id=stable_id(basis, "subject-core-outcome"),
                decision=subject_core,
            ),
            development=DevelopmentOutcome(
                outcome_id=stable_id(basis, "development-outcome"),
                decision=noop_decision(
                    basis,
                    scope="development",
                    reason_code="subject-state.development.no-applicable-candidate",
                ),
            ),
        )


__all__ = [
    "DevelopmentChangeCandidate",
    "SituatedEffectCandidate",
    "SubjectStateAdjudicationRequest",
    "SubjectStateDomain",
    "SubjectStateReadView",
]

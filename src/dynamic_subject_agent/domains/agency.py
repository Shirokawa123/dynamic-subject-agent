"""Agency Domain: intentions, projects, commitments, and action authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from dynamic_subject_agent.subject_tasks import SubjectTaskCommand, SubjectTaskProposal, SubjectTaskRecord, decide
from dynamic_subject_agent.text_artifacts import TextSaveApproval, TextArtifactPreview, approve

from dynamic_subject_agent.timeline import AgencyDomainOutcome
from dynamic_subject_agent.domains._shared import (
    DomainAdjudicationFailedClosed,
    DomainCapabilityState,
    ExperienceBasis,
    noop_decision,
    require_tuple,
    stable_id,
    validate_basis,
)


@dataclass(frozen=True)
class AgencyChangeCandidate:
    candidate_id: str
    target_profile_id: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AgencyReadView:
    intention_refs: tuple[str, ...]
    project_refs: tuple[str, ...]
    commitment_refs: tuple[str, ...]
    action_refs: tuple[str, ...]
    tasks: tuple[SubjectTaskRecord, ...] = ()


@dataclass(frozen=True)
class AgencyAdjudicationRequest:
    basis: ExperienceBasis
    current_state: AgencyReadView
    candidates: tuple[AgencyChangeCandidate, ...]
    task_command: SubjectTaskCommand | None = None
    task_proposal: SubjectTaskProposal | None = None
    admitted_command: str = ''
    artifact_approval: TextSaveApproval | None = None
    artifact_preview: TextArtifactPreview | None = None


class AgencyDomain:
    """Adjudicate Agency inputs without creating or dispatching effects."""

    material_change_capability = DomainCapabilityState.UNAVAILABLE
    subject_task_capability = DomainCapabilityState.AVAILABLE

    def adjudicate(self, request: AgencyAdjudicationRequest) -> AgencyDomainOutcome:
        if not isinstance(request, AgencyAdjudicationRequest):
            raise DomainAdjudicationFailedClosed(
                "agency",
                "wrong-domain-request",
                "AgencyDomain requires AgencyAdjudicationRequest",
            )
        basis = validate_basis(request.basis, domain="agency")
        if not isinstance(request.current_state, AgencyReadView):
            raise DomainAdjudicationFailedClosed(
                "agency",
                "invalid-read-view",
                "Agency current state must be a typed read-only view",
            )
        candidates = require_tuple(
            request.candidates,
            domain="agency",
            field="candidates",
        )
        for candidate in candidates:
            if not isinstance(candidate, AgencyChangeCandidate):
                raise DomainAdjudicationFailedClosed(
                    "agency",
                    "wrong-domain-candidate",
                    "only AgencyChangeCandidate may enter AgencyDomain",
                )
            if candidate.target_profile_id != basis.profile_id:
                raise DomainAdjudicationFailedClosed(
                    "agency",
                    "candidate-target-mismatch",
                    "Agency candidate names a different Profile",
                )
        if candidates:
            raise DomainAdjudicationFailedClosed(
                "agency",
                "material-change-capability-unavailable",
                "M0-A cannot safely adjudicate an Agency material-change candidate",
            )
        if request.artifact_approval is not None:
            try:
                if request.task_command is not None or TextSaveApproval.from_json(request.admitted_command)!=request.artifact_approval:
                    raise ValueError('approval differs from admission')
                record,effect,reply=approve(request.artifact_approval,request.current_state.tasks,request.artifact_preview)
                if effect and (effect.profile_id!=basis.profile_id or effect.timeline_id!=basis.timeline_id):
                    raise ValueError('effect identity differs from admission')
            except (TypeError,ValueError,AttributeError):
                raise DomainAdjudicationFailedClosed('agency','invalid-artifact-approval','exact approval could not be verified') from None
            decision=replace(noop_decision(basis,scope='agency',reason_code='text-effect.result'),rule_version='agency-text-effect-1.0',
                reason=json.dumps({'code':'text-effect.result','provenance':basis.source_provenance,
                    'subject_task':asdict(record) if record else None,'reply':reply,'approval':asdict(request.artifact_approval),
                    'effect':asdict(effect) if effect else None},ensure_ascii=False,sort_keys=True,separators=(',',':')))
            return AgencyDomainOutcome(stable_id(basis,'agency-outcome'),decision,bool(effect))
        if request.task_command is not None:
            try:
                if SubjectTaskCommand.from_json(request.admitted_command) != request.task_command:
                    raise ValueError('task command differs from admission')
                for item in require_tuple(request.current_state.tasks, domain='agency', field='tasks'):
                    SubjectTaskRecord.from_dict(asdict(item))
                record, reply = decide(request.task_command, request.task_proposal, request.current_state.tasks, new_id=basis.operation_id)
            except (TypeError, ValueError, AttributeError):
                raise DomainAdjudicationFailedClosed('agency', 'invalid-task-input', 'task input could not be verified') from None
            decision = replace(noop_decision(basis,scope='agency',reason_code='subject-task.result'),
                rule_version='agency-task-1.0', reason=json.dumps({'code':'subject-task.result',
                    'provenance':basis.source_provenance,
                    'subject_task':asdict(record) if record else None, 'reply':reply,
                    'proposal':asdict(request.task_proposal) if isinstance(request.task_proposal,SubjectTaskProposal) else None},
                    ensure_ascii=False,sort_keys=True,separators=(',',':')))
            return AgencyDomainOutcome(stable_id(basis,'agency-outcome'),decision,False)
        return AgencyDomainOutcome(
            outcome_id=stable_id(basis, "agency-outcome"),
            decision=noop_decision(
                basis,
                scope="agency",
                reason_code="agency.no-applicable-candidate",
            ),
            committed_effect_eligible=False,
        )

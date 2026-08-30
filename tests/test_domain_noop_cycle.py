from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from dynamic_subject_agent.domains import (
    AgencyAdjudicationRequest,
    AgencyChangeCandidate,
    AgencyDomain,
    AgencyReadView,
    CompleteDomainOutcomeSet,
    DomainAdjudicationFailedClosed,
    DomainCapabilityState,
    DomainOutcomeSetRejected,
    ExperienceAdjudicationRequest,
    ExperienceBasis,
    ExperienceDomain,
    ExperienceImpactEnvelope,
    ExperienceImpactEnvelopeRejected,
    ExperienceReadView,
    RelationshipAdjudicationRequest,
    RelationshipChangeCandidate,
    RelationshipDomain,
    RelationshipReadView,
    SubjectStateAdjudicationRequest,
    SubjectStateDomain,
    SubjectStateReadView,
)
from dynamic_subject_agent.timeline import (
    AttemptState,
    CommitPlanRejected,
    CommittedEffectSet,
    CycleCommitPlan,
    DecisionStatus,
    EffectDispatchState,
    EpistemicOutcome,
    ExperienceRecord,
    Expression,
    FixtureAuthority,
    OperationState,
    PublicationInterrupted,
    RevisionSet,
    SubjectCommand,
    TimelineEngine,
)


PROFILE_ID = "c627e693-68f0-43f7-b3db-e55490b47b32"
TIMELINE_ID = "471f4fd1-69fd-49df-aa14-3af405d301cf"
AUTHORITY_SCOPE_ID = "91f6a5fc-22dc-482b-b482-5ca9089d1e69"
IDEMPOTENCY_KEY = "lantern-zine-domain-noop-0001"


def _id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"m0-08-domain-test:{name}"))


def _authority() -> FixtureAuthority:
    return FixtureAuthority(
        authority_scope_id=AUTHORITY_SCOPE_ID,
        profile_id=PROFILE_ID,
        timeline_id=TIMELINE_ID,
        allowed_intents=("ask-collaborator-status",),
        allowed_provenance=("project-original",),
    )


def _command() -> SubjectCommand:
    return SubjectCommand.contribute_utterance(
        target_profile_id=PROFILE_ID,
        target_timeline_id=TIMELINE_ID,
        declared_intent="ask-collaborator-status",
        utterance=(
            "Could you check whether the lantern issue can still make "
            "Friday's print slot?"
        ),
        language="en",
        provenance="project-original",
    )


def _envelope(admitted, pending) -> ExperienceImpactEnvelope:
    basis = ExperienceBasis(
        operation_id=admitted.operation_ref.operation_id,
        attempt_id=admitted.attempt_id,
        subject_event_id=pending.subject_event_id,
        experience_id=_id("experience"),
        profile_id=PROFILE_ID,
        timeline_id=TIMELINE_ID,
        epistemic_outcome_id=_id("epistemic"),
        verified_prefix_digest=pending.timeline_basis.verified_prefix_digest,
        source_provenance="project-original",
        integrity_verified=True,
    )
    return ExperienceImpactEnvelope(
        experience=ExperienceAdjudicationRequest(
            basis=basis,
            current_state=ExperienceReadView(
                verified_prefix_digest=basis.verified_prefix_digest,
                memory_trace_refs=(),
            ),
            candidates=(),
        ),
        subject_state=SubjectStateAdjudicationRequest(
            basis=basis,
            current_state=SubjectStateReadView(
                subject_core_revision_refs=(),
                development_revision_refs=(),
            ),
            situated_effect_candidates=(),
            development_candidates=(),
        ),
        agency=AgencyAdjudicationRequest(
            basis=basis,
            current_state=AgencyReadView(
                intention_refs=(),
                project_refs=(),
                commitment_refs=(),
                action_refs=(),
            ),
            candidates=(),
        ),
        relationship=RelationshipAdjudicationRequest(
            basis=basis,
            relationship_enabled=False,
            relationship_target_id=PROFILE_ID,
            current_state=RelationshipReadView(
                relationship_target_id=PROFILE_ID,
                subject_stance_revision_refs=(),
                interaction_norm_revision_refs=(),
                mutual_commitment_revision_refs=(),
                narrative_revision_refs=(),
                authored_origin_refs=(),
                earned_evidence_refs=(),
            ),
            candidates=(),
        ),
    )


def _test_only_commit_plan(
    admitted,
    pending,
    envelope: ExperienceImpactEnvelope,
    outcomes: CompleteDomainOutcomeSet,
) -> CycleCommitPlan:
    """Compose the M0-08 test fixture; production composition remains M0-09."""

    subject_state = outcomes.subject_state
    return CycleCommitPlan(
        plan_id=_id("plan"),
        cycle_plan_id=_id("cycle-plan"),
        operation_ref=admitted.operation_ref,
        attempt_id=admitted.attempt_id,
        subject_event_id=pending.subject_event_id,
        profile_id=PROFILE_ID,
        timeline_id=TIMELINE_ID,
        expected_basis=pending.timeline_basis,
        experience=ExperienceRecord(
            experience_id=envelope.basis.experience_id,
            summary="The admitted original fixture entered four Domain adjudications.",
            experienced_at_us=1_800_000_000_000_000,
        ),
        epistemic_outcome=EpistemicOutcome(
            epistemic_outcome_id=envelope.basis.epistemic_outcome_id,
            status=DecisionStatus.NO_OP,
            reason="the verified epistemic prefix is unchanged",
            route_version="m0-epistemic-route-1",
            verified_prefix_digest=envelope.basis.verified_prefix_digest,
            completed_stages=(),
        ),
        experience_outcome=outcomes.experience,
        subject_state_outcome=subject_state,
        agency_outcome=outcomes.agency,
        relationship_outcome=outcomes.relationship,
        revision_set=RevisionSet(
            revision_set_id=_id("revision-set"),
            revision_ids=(),
        ),
        expression=Expression(
            expression_id=_id("expression"),
            text="I can check the print-slot status within this fixture.",
            language="en",
            grounding_decision_ids=(
                outcomes.experience.decision.decision_id,
                subject_state.decision.decision_id,
                subject_state.subject_core.decision.decision_id,
                subject_state.development.decision.decision_id,
                outcomes.agency.decision.decision_id,
                outcomes.relationship.decision.decision_id,
            ),
        ),
        committed_effect_set=CommittedEffectSet(
            effect_set_id=_id("effect-set"),
            reference_ids=(),
            dispatch_state=EffectDispatchState.UNAVAILABLE,
            reason="real committed-effect dispatch is unavailable in M0",
        ),
    )


def _reason(decision) -> dict[str, str]:
    return json.loads(decision.reason)


def test_four_domains_publish_distinct_reasoned_noops(tmp_path: Path) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    pending = engine.query(admitted.operation_ref)
    envelope = _envelope(admitted, pending)

    outcomes = CompleteDomainOutcomeSet.collect(
        (
            RelationshipDomain().adjudicate(envelope.relationship),
            AgencyDomain().adjudicate(envelope.agency),
            ExperienceDomain().adjudicate(envelope.experience),
            SubjectStateDomain().adjudicate(envelope.subject_state),
        )
    )
    published = engine.publish(
        _test_only_commit_plan(admitted, pending, envelope, outcomes)
    )
    queried = engine.query_outcome(admitted.operation_ref)
    operation = engine.query(admitted.operation_ref)
    engine.close()

    assert published.outcome_id == queried.outcome_id
    assert operation.operation_state is OperationState.COMPLETED
    assert operation.attempt_state is AttemptState.PUBLISHED
    assert operation.timeline_head_sequence == 1
    assert queried.experience_outcome.decision.status is DecisionStatus.NO_OP
    assert queried.subject_state_outcome.decision.status is DecisionStatus.NO_OP
    assert queried.agency_outcome.decision.status is DecisionStatus.NO_OP
    assert queried.relationship_outcome.decision.status is DecisionStatus.NO_OP
    assert _reason(queried.experience_outcome.decision) == {
        "code": "experience.no-applicable-candidate",
        "provenance": "project-original",
    }
    assert _reason(queried.subject_state_outcome.subject_core.decision) == {
        "code": "subject-state.subject-core.no-applicable-candidate",
        "provenance": "project-original",
    }
    assert _reason(queried.subject_state_outcome.development.decision) == {
        "code": "subject-state.development.no-applicable-candidate",
        "provenance": "project-original",
    }
    assert _reason(queried.agency_outcome.decision) == {
        "code": "agency.no-applicable-candidate",
        "provenance": "project-original",
    }
    assert _reason(queried.relationship_outcome.decision) == {
        "code": "relationship.disabled-by-configuration",
        "provenance": "project-original",
    }
    assert queried.relationship_outcome.relationship_target_id == PROFILE_ID
    assert queried.revision_set.revision_ids == ()
    assert queried.committed_effect_set.reference_ids == ()


def test_complete_set_constructor_cannot_bypass_wrong_domain_validation(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    pending = engine.query(admitted.operation_ref)
    envelope = _envelope(admitted, pending)
    experience = ExperienceDomain().adjudicate(envelope.experience)
    subject_state = SubjectStateDomain().adjudicate(envelope.subject_state)
    agency = AgencyDomain().adjudicate(envelope.agency)
    engine.close()

    with pytest.raises(DomainOutcomeSetRejected) as rejected:
        CompleteDomainOutcomeSet(
            experience=experience,
            subject_state=subject_state,
            agency=agency,
            relationship=agency,  # type: ignore[arg-type]
        )

    assert rejected.value.code == "wrong-domain-outcome-type"


def _adjudicated(envelope: ExperienceImpactEnvelope) -> tuple[object, ...]:
    return (
        ExperienceDomain().adjudicate(envelope.experience),
        SubjectStateDomain().adjudicate(envelope.subject_state),
        AgencyDomain().adjudicate(envelope.agency),
        RelationshipDomain().adjudicate(envelope.relationship),
    )


def test_outcome_collection_is_order_independent_and_deterministic(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    envelope = _envelope(admitted, engine.query(admitted.operation_ref))
    produced = _adjudicated(envelope)
    engine.close()

    forward = CompleteDomainOutcomeSet.collect(produced)
    reverse = CompleteDomainOutcomeSet.collect(reversed(produced))

    assert forward == reverse
    assert _reason(forward.subject_state.decision)["code"] == (
        "subject-state.no-material-change"
    )
    assert forward.subject_state.subject_core != forward.subject_state.development
    assert ExperienceDomain.material_change_capability is (
        DomainCapabilityState.AVAILABLE
    )
    assert SubjectStateDomain.material_change_capability is (
        DomainCapabilityState.UNAVAILABLE
    )
    assert AgencyDomain.material_change_capability is DomainCapabilityState.UNAVAILABLE
    assert RelationshipDomain.material_change_capability is (
        DomainCapabilityState.UNAVAILABLE
    )


def test_wrong_domain_candidate_and_unavailable_candidate_fail_closed(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    envelope = _envelope(admitted, engine.query(admitted.operation_ref))
    wrong_domain = RelationshipChangeCandidate(
        candidate_id=_id("wrong-domain-candidate"),
        relationship_target_id=PROFILE_ID,
        evidence_refs=(),
    )
    wrong_request = replace(
        envelope.agency,
        candidates=(wrong_domain,),  # type: ignore[arg-type]
    )

    with pytest.raises(DomainAdjudicationFailedClosed) as wrong:
        AgencyDomain().adjudicate(wrong_request)

    assert wrong.value.status is DecisionStatus.FAILED_CLOSED
    assert wrong.value.code == "wrong-domain-candidate"

    unavailable_request = replace(
        envelope.agency,
        candidates=(
            AgencyChangeCandidate(
                candidate_id=_id("agency-candidate"),
                target_profile_id=PROFILE_ID,
                evidence_refs=(),
            ),
        ),
    )
    with pytest.raises(DomainAdjudicationFailedClosed) as unavailable:
        AgencyDomain().adjudicate(unavailable_request)
    engine.close()

    assert unavailable.value.status is DecisionStatus.FAILED_CLOSED
    assert unavailable.value.code == "material-change-capability-unavailable"


def test_envelope_rejects_mixed_experience_bases(tmp_path: Path) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    envelope = _envelope(admitted, engine.query(admitted.operation_ref))
    mismatched_agency = replace(
        envelope.agency,
        basis=replace(envelope.basis, attempt_id=_id("other-attempt")),
    )

    with pytest.raises(ExperienceImpactEnvelopeRejected) as rejected:
        replace(envelope, agency=mismatched_agency)
    engine.close()

    assert rejected.value.code == "mixed-experience-basis"


def test_collection_rejects_missing_duplicate_and_wrong_outcomes(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    envelope = _envelope(admitted, engine.query(admitted.operation_ref))
    experience, subject_state, agency, relationship = _adjudicated(envelope)
    engine.close()

    with pytest.raises(DomainOutcomeSetRejected) as missing:
        CompleteDomainOutcomeSet.collect((experience, subject_state, agency))
    assert missing.value.code == "missing-domain-outcome"

    with pytest.raises(DomainOutcomeSetRejected) as duplicate:
        CompleteDomainOutcomeSet.collect(
            (experience, subject_state, agency, relationship, experience)
        )
    assert duplicate.value.code == "duplicate-domain-outcome"

    with pytest.raises(DomainOutcomeSetRejected) as wrong:
        CompleteDomainOutcomeSet.collect(
            (experience, subject_state, agency, subject_state.subject_core)
        )
    assert wrong.value.code == "wrong-domain-outcome-type"


@pytest.mark.parametrize("bad_kind", ("missing", "wrong-type"))
def test_timeline_rejects_bad_domain_field_without_partial_publication(
    tmp_path: Path,
    bad_kind: str,
) -> None:
    engine = TimelineEngine.create_test(tmp_path / bad_kind, _authority())
    admitted = engine.admit(
        _command(),
        idempotency_key=f"{IDEMPOTENCY_KEY}-{bad_kind}",
    )
    pending = engine.query(admitted.operation_ref)
    envelope = _envelope(admitted, pending)
    outcomes = CompleteDomainOutcomeSet.collect(_adjudicated(envelope))
    plan = _test_only_commit_plan(admitted, pending, envelope, outcomes)
    invalid_relationship = None if bad_kind == "missing" else outcomes.agency
    invalid = replace(
        plan,
        relationship_outcome=invalid_relationship,  # type: ignore[arg-type]
    )

    with pytest.raises(CommitPlanRejected) as rejected:
        engine.publish(invalid)

    snapshot = engine.query(admitted.operation_ref)
    with pytest.raises(PublicationInterrupted) as unavailable:
        engine.query_outcome(admitted.operation_ref)
    engine.close()

    assert rejected.value.code == "commit-plan-incomplete"
    assert unavailable.value.code == "timeline-outcome-unavailable"
    assert snapshot.operation_state is OperationState.ADMITTED_PENDING
    assert snapshot.attempt_state is AttemptState.PENDING
    assert snapshot.timeline_head_sequence == 0
    assert snapshot.timeline_outcome_id is None


def test_technical_failure_is_not_fabricated_as_noop_or_publication(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    envelope = _envelope(admitted, engine.query(admitted.operation_ref))
    broken_agency = replace(
        envelope.agency,
        basis=replace(envelope.basis, integrity_verified=False),
    )

    with pytest.raises(DomainAdjudicationFailedClosed) as failed:
        AgencyDomain().adjudicate(broken_agency)

    only_completed = (
        ExperienceDomain().adjudicate(envelope.experience),
        SubjectStateDomain().adjudicate(envelope.subject_state),
        RelationshipDomain().adjudicate(envelope.relationship),
    )
    with pytest.raises(DomainOutcomeSetRejected) as incomplete:
        CompleteDomainOutcomeSet.collect(only_completed)

    snapshot = engine.query(admitted.operation_ref)
    with pytest.raises(PublicationInterrupted):
        engine.query_outcome(admitted.operation_ref)
    engine.close()

    assert failed.value.status is DecisionStatus.FAILED_CLOSED
    assert failed.value.code == "experience-basis-unverified"
    assert incomplete.value.code == "missing-domain-outcome"
    assert snapshot.operation_state is OperationState.ADMITTED_PENDING
    assert snapshot.attempt_state is AttemptState.PENDING
    assert snapshot.timeline_head_sequence == 0


def test_domain_modules_have_no_persistence_cross_domain_or_legacy_edge() -> None:
    domain_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "dynamic_subject_agent"
        / "domains"
    )
    files = {
        "experience": domain_root / "experience.py",
        "subject_state": domain_root / "subject_state.py",
        "agency": domain_root / "agency.py",
        "relationship": domain_root / "relationship.py",
    }
    forbidden_names = {
        "ApplicationFacade",
        "CycleCommitPlan",
        "SubjectRuntime",
        "TimelineEngine",
        "sqlite3",
    }

    for name, path in files.items():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        referenced_names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        sibling_imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("dynamic_subject_agent.domains.")
            and node.module != "dynamic_subject_agent.domains._shared"
        }

        assert not sibling_imports, f"{name} imports another Domain module"
        assert not (referenced_names & forbidden_names)
        assert "legacy" not in source.lower()

    relationship_fields = set(RelationshipReadView.__dataclass_fields__)
    assert "trust" not in relationship_fields
    assert "boundary_tension" not in relationship_fields

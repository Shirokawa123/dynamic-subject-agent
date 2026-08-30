from __future__ import annotations

import json
import os
import subprocess
import sys

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from uuid import NAMESPACE_URL, uuid5

import pytest
from dynamic_subject_agent.timeline import (
    AgencyDomainOutcome,
    AttemptState,
    CandidateDecisionRecord,
    CommittedEffectSet,
    CommitPlanConflict,
    CommitPlanRejected,
    CycleCommitPlan,
    DecisionStatus,
    DevelopmentOutcome,
    EffectDispatchState,
    EpistemicOutcome,
    ExperienceDomainOutcome,
    ExperienceRecord,
    Expression,
    FaultPoint,
    FixtureAuthority,
    OperationState,
    PublicationInterrupted,
    PublicationProblem,
    RelationshipDomainOutcome,
    RevisionSet,
    SubjectCommand,
    SubjectCoreOutcome,
    SubjectStateDomainOutcome,
    StaleTimelineBasis,
    TimelineEngine,
)

PROFILE_ID = "c627e693-68f0-43f7-b3db-e55490b47b32"
TIMELINE_ID = "471f4fd1-69fd-49df-aa14-3af405d301cf"
AUTHORITY_SCOPE_ID = "91f6a5fc-22dc-482b-b482-5ca9089d1e69"
IDEMPOTENCY_KEY = "lantern-zine-publication-0001"

IDS = {
    "plan": "5330c541-b0df-4338-92c2-f41b1d7358c4",
    "cycle_plan": "79dbd960-dfb6-4b14-a48b-9a6e7084e501",
    "experience": "09c5bfda-0134-4ed1-9f4c-0cb5104c3a68",
    "epistemic": "6fe0cb23-22af-435d-91db-e05776557559",
    "experience_decision": "918e9d36-5fb9-405d-af30-28a93961b767",
    "experience_outcome": "121514fb-1f92-48bc-b6ca-0d87ed7e5aa7",
    "subject_state_decision": "05d910b4-2df5-4daf-89a0-f038b99ac32f",
    "subject_state_outcome": "7bec1ecf-97dc-479a-9c80-bdc74d1fcbe0",
    "subject_core_decision": "a1fbe3dc-290c-4941-8269-ae45ac023f12",
    "subject_core_outcome": "c946df4f-da94-4c85-b23c-93de340ad1fb",
    "development_decision": "f7a2ae70-4eca-4a38-8428-a00a3d00b278",
    "development_outcome": "ce1604c9-f6e9-450a-bda7-45e4be2cf3eb",
    "agency_decision": "18c971a5-81df-4d20-85c6-6257e3eee894",
    "agency_outcome": "ab5cc214-d5ed-4fcd-85b1-c5ef3e13015c",
    "relationship_decision": "e8111492-dd7b-40eb-b063-da22602ae1ca",
    "relationship_outcome": "a60c47be-61a0-4b80-8148-29f9932c4395",
    "revision_set": "de6d9c2b-1fc5-4881-8550-925133687f09",
    "expression": "115923fd-7d8c-4b3a-a4e5-3f0d48df41bb",
    "effect_set": "5ba28869-daf4-4503-be1e-bd4d65c51ccc",
}


PUBLICATION_ROLLBACK_POINTS = (
    FaultPoint.BEFORE_PLAN_CLAIM,
    FaultPoint.AFTER_PLAN_CLAIM,
    FaultPoint.BEFORE_PUBLICATION_TRANSACTION,
    FaultPoint.AFTER_COMMIT_PLAN_RECEIPT,
    FaultPoint.AFTER_EXPERIENCE,
    FaultPoint.AFTER_EPISTEMIC,
    FaultPoint.AFTER_CANDIDATE_DECISIONS,
    FaultPoint.AFTER_DOMAIN_OUTCOMES,
    FaultPoint.AFTER_REVISION_SET,
    FaultPoint.AFTER_EXPRESSION,
    FaultPoint.AFTER_EFFECT_SET,
    FaultPoint.AFTER_TIMELINE_OUTCOME,
    FaultPoint.AFTER_HEAD_ADVANCE,
    FaultPoint.AFTER_ATTEMPT_TERMINAL,
    FaultPoint.BEFORE_PUBLICATION_COMMIT,
)


PUBLICATION_HARD_CRASH_POINTS = PUBLICATION_ROLLBACK_POINTS + (
    FaultPoint.AFTER_PUBLICATION_COMMIT,
)


class InjectedPublicationFault(RuntimeError):
    pass


class OneShotFault:
    def __init__(self, point: FaultPoint) -> None:
        self.point = point
        self.hit = False

    def __call__(self, observed: FaultPoint) -> None:
        if observed is self.point and not self.hit:
            self.hit = True
            raise InjectedPublicationFault(self.point.value)


def _ids(label: str) -> dict[str, str]:
    return {key: str(uuid5(NAMESPACE_URL, f"m0-07:{label}:{key}")) for key in IDS}


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


def _noop(decision_id: str, scope: str, reason: str) -> CandidateDecisionRecord:
    return CandidateDecisionRecord(
        decision_id=decision_id,
        scope=scope,
        status=DecisionStatus.NO_OP,
        reason=reason,
        rule_version="m0-noop-rules-1",
        actual_revision_ids=(),
    )


def _commit_plan(
    engine: TimelineEngine,
    operation_ref,
    attempt_id: str,
    *,
    ids: dict[str, str] = IDS,
) -> CycleCommitPlan:
    pending = engine.query(operation_ref)
    experience_decision = _noop(
        ids["experience_decision"],
        "experience",
        "no epistemic candidate applies to the fixture contribution",
    )
    subject_core_decision = _noop(
        ids["subject_core_decision"],
        "subject-core",
        "no situated state candidate was proposed",
    )
    development_decision = _noop(
        ids["development_decision"],
        "development",
        "long-term consolidation is unavailable in M0",
    )
    subject_state_decision = _noop(
        ids["subject_state_decision"],
        "subject-state",
        "both subject-state authorities completed without change",
    )
    agency_decision = _noop(
        ids["agency_decision"],
        "agency",
        "no intention or action candidate was proposed",
    )
    relationship_decision = _noop(
        ids["relationship_decision"],
        "relationship",
        "no relationship candidate was proposed",
    )
    return CycleCommitPlan(
        plan_id=ids["plan"],
        cycle_plan_id=ids["cycle_plan"],
        operation_ref=operation_ref,
        attempt_id=attempt_id,
        subject_event_id=pending.subject_event_id,
        profile_id=PROFILE_ID,
        timeline_id=TIMELINE_ID,
        expected_basis=pending.timeline_basis,
        experience=ExperienceRecord(
            experience_id=ids["experience"],
            summary="The admitted contribution entered the bounded M0 experience cycle.",
            experienced_at_us=1_800_000_000_000_000,
        ),
        epistemic_outcome=EpistemicOutcome(
            epistemic_outcome_id=ids["epistemic"],
            status=DecisionStatus.NO_OP,
            reason="the verified epistemic prefix is unchanged",
            route_version="m0-epistemic-route-1",
            verified_prefix_digest=pending.timeline_basis.verified_prefix_digest,
            completed_stages=(),
        ),
        experience_outcome=ExperienceDomainOutcome(
            outcome_id=ids["experience_outcome"],
            decision=experience_decision,
            epistemic_outcome_id=ids["epistemic"],
        ),
        subject_state_outcome=SubjectStateDomainOutcome(
            outcome_id=ids["subject_state_outcome"],
            decision=subject_state_decision,
            subject_core=SubjectCoreOutcome(
                outcome_id=ids["subject_core_outcome"],
                decision=subject_core_decision,
            ),
            development=DevelopmentOutcome(
                outcome_id=ids["development_outcome"],
                decision=development_decision,
            ),
        ),
        agency_outcome=AgencyDomainOutcome(
            outcome_id=ids["agency_outcome"],
            decision=agency_decision,
            committed_effect_eligible=False,
        ),
        relationship_outcome=RelationshipDomainOutcome(
            outcome_id=ids["relationship_outcome"],
            decision=relationship_decision,
            relationship_target_id=PROFILE_ID,
        ),
        revision_set=RevisionSet(
            revision_set_id=ids["revision_set"],
            revision_ids=(),
        ),
        expression=Expression(
            expression_id=ids["expression"],
            text="I can check the print-slot status within this fixture.",
            language="en",
            grounding_decision_ids=(
                ids["experience_decision"],
                ids["subject_state_decision"],
                ids["subject_core_decision"],
                ids["development_decision"],
                ids["agency_decision"],
                ids["relationship_decision"],
            ),
        ),
        committed_effect_set=CommittedEffectSet(
            effect_set_id=ids["effect_set"],
            reference_ids=(),
            dispatch_state=EffectDispatchState.UNAVAILABLE,
            reason="real committed-effect dispatch is unavailable in M0",
        ),
    )


def test_complete_plan_publishes_one_authoritative_outcome(tmp_path: Path) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    plan = _commit_plan(engine, admitted.operation_ref, admitted.attempt_id)

    published = engine.publish(plan)
    location = engine.location
    engine.close()

    restarted = TimelineEngine.open(location)
    operation = restarted.query(admitted.operation_ref)
    outcome = restarted.query_outcome(admitted.operation_ref)
    restarted.close()

    assert published.replayed is False
    assert operation.operation_state is OperationState.COMPLETED
    assert operation.attempt_state is AttemptState.PUBLISHED
    assert operation.timeline_head_sequence == 1
    assert operation.timeline_outcome_id == outcome.outcome_id
    assert outcome.head_sequence == 1
    assert outcome.plan_id == IDS["plan"]
    assert outcome.experience.experience_id == IDS["experience"]
    assert outcome.epistemic_outcome.status is DecisionStatus.NO_OP
    assert outcome.experience_outcome.outcome_id == IDS["experience_outcome"]
    assert (
        outcome.subject_state_outcome.subject_core.outcome_id
        == IDS["subject_core_outcome"]
    )
    assert (
        outcome.subject_state_outcome.development.outcome_id
        == IDS["development_outcome"]
    )
    assert outcome.agency_outcome.outcome_id == IDS["agency_outcome"]
    assert outcome.relationship_outcome.outcome_id == IDS["relationship_outcome"]
    assert outcome.revision_set.revision_ids == ()
    assert outcome.expression.text == (
        "I can check the print-slot status within this fixture."
    )
    assert outcome.committed_effect_set.reference_ids == ()
    assert (
        outcome.committed_effect_set.dispatch_state is EffectDispatchState.UNAVAILABLE
    )


def test_exact_retry_reuses_outcome_and_changed_plan_conflicts(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    plan = _commit_plan(engine, admitted.operation_ref, admitted.attempt_id)

    first = engine.publish(plan)
    location = engine.location
    engine.close()

    restarted = TimelineEngine.open(location)
    replay = restarted.publish(plan)
    changed = replace(
        plan,
        expression=replace(
            plan.expression,
            text="A different expression cannot reuse the same plan identity.",
        ),
    )
    with pytest.raises(CommitPlanConflict) as conflict:
        restarted.publish(changed)
    outcome = restarted.query_outcome(admitted.operation_ref)
    restarted.close()

    assert replay.replayed is True
    assert replay.outcome_id == first.outcome_id == outcome.outcome_id
    assert conflict.value.code == "commit-plan-identity-conflict"
    assert outcome.head_sequence == 1


def test_incomplete_grounding_rejects_without_publication(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(_command(), idempotency_key=IDEMPOTENCY_KEY)
    plan = _commit_plan(engine, admitted.operation_ref, admitted.attempt_id)
    incomplete = replace(
        plan,
        expression=replace(
            plan.expression,
            grounding_decision_ids=plan.expression.grounding_decision_ids[:-1],
        ),
    )

    with pytest.raises(CommitPlanRejected) as rejected:
        engine.publish(incomplete)
    pending = engine.query(admitted.operation_ref)
    published = engine.publish(plan)
    engine.close()

    assert rejected.value.code == "commit-plan-expression-grounding-invalid"
    assert pending.operation_state is OperationState.ADMITTED_PENDING
    assert pending.attempt_state is AttemptState.PENDING
    assert pending.timeline_head_sequence == 0
    assert published.head_sequence == 1


def test_two_plans_for_one_expected_head_publish_at_most_one(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    first_admitted = engine.admit(
        _command(),
        idempotency_key="lantern-zine-publication-race-a",
    )
    second_admitted = engine.admit(
        _command(),
        idempotency_key="lantern-zine-publication-race-b",
    )
    first_plan = _commit_plan(
        engine,
        first_admitted.operation_ref,
        first_admitted.attempt_id,
        ids=_ids("race-a"),
    )
    second_plan = _commit_plan(
        engine,
        second_admitted.operation_ref,
        second_admitted.attempt_id,
        ids=_ids("race-b"),
    )
    location = engine.location
    engine.close()

    barrier = Barrier(2)

    def compete(plan: CycleCommitPlan) -> tuple[str, str | None]:
        contender = TimelineEngine.open(location)
        try:
            barrier.wait(timeout=5)
            try:
                published = contender.publish(plan)
            except StaleTimelineBasis:
                return ("stale", None)
            return ("published", published.outcome_id)
        finally:
            contender.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(compete, (first_plan, second_plan)))

    assert sorted(result[0] for result in results) == ["published", "stale"]
    winner_index = next(
        index for index, result in enumerate(results) if result[0] == "published"
    )
    admitted = (first_admitted, second_admitted)
    plans = (first_plan, second_plan)

    restarted = TimelineEngine.open(location)
    winner = restarted.query(admitted[winner_index].operation_ref)
    loser = restarted.query(admitted[1 - winner_index].operation_ref)
    replay = restarted.publish(plans[winner_index])
    outcome = restarted.query_outcome(admitted[winner_index].operation_ref)
    restarted.close()

    assert winner.operation_state is OperationState.COMPLETED
    assert winner.attempt_state is AttemptState.PUBLISHED
    assert loser.operation_state is OperationState.INTERRUPTED
    assert loser.attempt_state is AttemptState.INTERRUPTED
    assert winner.timeline_head_sequence == loser.timeline_head_sequence == 1
    assert replay.replayed is True
    assert replay.outcome_id == outcome.outcome_id == results[winner_index][1]


@pytest.mark.parametrize(
    "point", PUBLICATION_ROLLBACK_POINTS, ids=lambda item: item.value
)
def test_publication_fault_rolls_back_and_exact_plan_recovers(
    tmp_path: Path,
    point: FaultPoint,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(
        _command(),
        idempotency_key=f"lantern-zine-fault-{point.value}",
    )
    plan = _commit_plan(
        engine,
        admitted.operation_ref,
        admitted.attempt_id,
        ids=_ids(f"fault-{point.value}"),
    )
    location = engine.location
    engine.close()

    faulted = TimelineEngine.open(
        location,
        _fault_hook=OneShotFault(point),
    )
    with pytest.raises(PublicationProblem):
        faulted.publish(plan)
    faulted.close()

    restarted = TimelineEngine.open(location)
    pending = restarted.query(admitted.operation_ref)
    with pytest.raises(PublicationInterrupted):
        restarted.query_outcome(admitted.operation_ref)
    published = restarted.publish(plan)
    outcome = restarted.query_outcome(admitted.operation_ref)
    replay = restarted.publish(plan)
    restarted.close()

    assert pending.operation_state is OperationState.ADMITTED_PENDING
    assert pending.attempt_state is AttemptState.PENDING
    assert pending.timeline_head_sequence == 0
    assert published.replayed is False
    assert published.outcome_id == outcome.outcome_id == replay.outcome_id
    assert replay.replayed is True
    assert outcome.head_sequence == 1
    assert outcome.revision_set.revision_ids == ()
    assert outcome.committed_effect_set.reference_ids == ()


def test_after_commit_interruption_recovers_existing_outcome(
    tmp_path: Path,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(
        _command(),
        idempotency_key="lantern-zine-publication-after-commit",
    )
    plan = _commit_plan(
        engine,
        admitted.operation_ref,
        admitted.attempt_id,
        ids=_ids("after-commit"),
    )
    location = engine.location
    engine.close()

    faulted = TimelineEngine.open(
        location,
        _fault_hook=OneShotFault(FaultPoint.AFTER_PUBLICATION_COMMIT),
    )
    recovered = faulted.publish(plan)
    replay = faulted.publish(plan)
    snapshot = faulted.query(admitted.operation_ref)
    outcome = faulted.query_outcome(admitted.operation_ref)
    faulted.close()

    assert recovered.recovered_after_commit is True
    assert recovered.replayed is True
    assert replay.replayed is True
    assert recovered.outcome_id == replay.outcome_id == outcome.outcome_id
    assert snapshot.operation_state is OperationState.COMPLETED
    assert snapshot.attempt_state is AttemptState.PUBLISHED
    assert snapshot.timeline_head_sequence == 1


@pytest.mark.parametrize(
    "point",
    PUBLICATION_HARD_CRASH_POINTS,
    ids=lambda item: f"hard-{item.value}",
)
def test_hard_crash_is_atomic_and_same_plan_is_recoverable(
    tmp_path: Path,
    point: FaultPoint,
) -> None:
    engine = TimelineEngine.create_test(tmp_path, _authority())
    admitted = engine.admit(
        _command(),
        idempotency_key=f"lantern-zine-hard-{point.value}",
    )
    plan = _commit_plan(
        engine,
        admitted.operation_ref,
        admitted.attempt_id,
        ids=_ids(f"hard-{point.value}"),
    )
    location = engine.location
    engine.close()

    location_file = tmp_path / "location.json"
    plan_file = tmp_path / "plan.json"
    location_file.write_text(
        json.dumps(location.to_dict(), sort_keys=True),
        encoding="utf-8",
    )
    plan_file.write_text(
        json.dumps(plan.to_dict(), sort_keys=True),
        encoding="utf-8",
    )
    mature_root = Path(__file__).resolve().parents[1]
    worker = mature_root / "tests" / "support" / "publication_crash_worker.py"
    environment = os.environ.copy()
    prior_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(mature_root / "src") + (
        "" if not prior_pythonpath else os.pathsep + prior_pythonpath
    )
    crashed = subprocess.run(
        (
            sys.executable,
            str(worker),
            str(location_file),
            str(plan_file),
            point.value,
        ),
        cwd=mature_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert crashed.returncode == 86, (crashed.stdout, crashed.stderr)

    restarted = TimelineEngine.open(location)
    after_crash = restarted.query(admitted.operation_ref)
    recovered = restarted.publish(plan)
    outcome = restarted.query_outcome(admitted.operation_ref)
    replay = restarted.publish(plan)
    restarted.close()

    committed_before_crash = point is FaultPoint.AFTER_PUBLICATION_COMMIT
    assert after_crash.timeline_head_sequence == int(committed_before_crash)
    assert after_crash.operation_state is (
        OperationState.COMPLETED
        if committed_before_crash
        else OperationState.ADMITTED_PENDING
    )
    assert after_crash.attempt_state is (
        AttemptState.PUBLISHED if committed_before_crash else AttemptState.PENDING
    )
    assert recovered.replayed is committed_before_crash
    assert recovered.outcome_id == outcome.outcome_id == replay.outcome_id
    assert replay.replayed is True
    assert outcome.head_sequence == 1
    assert outcome.revision_set.revision_ids == ()
    assert outcome.committed_effect_set.reference_ids == ()

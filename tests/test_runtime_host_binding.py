from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from dynamic_subject_agent.host import (
    BindingState,
    RuntimeHost,
    RuntimeHostConflict,
    RuntimeHostFailedClosed,
    RuntimeHostFaultPoint,
    RuntimeHostInterrupted,
    RuntimeHostRejected,
)
from dynamic_subject_agent.runtime import FakeCognition, M0AFixture
from dynamic_subject_agent.studio import (
    CapabilityManifest,
    FreezeDecision,
    GenesisPremise,
    ParticipantProfile,
    PolicyKernel,
    QualifiedRuntimeInput,
    SourceDeclaration,
    StudioRootRef,
    SubjectStudio,
)
from dynamic_subject_agent.timeline import OperationState, SubjectCommand


def _publish_qri(test_root: Path) -> tuple[StudioRootRef, QualifiedRuntimeInput]:
    fixture = M0AFixture.lantern_zine()
    studio = SubjectStudio.create_test(test_root, policy_kernel=PolicyKernel())
    profile = ParticipantProfile(
        profile_id=fixture.authority.profile_id,
        display_name="Avery Chen",
        identity_core="Avery is the sole participant identity in this branch.",
        source=SourceDeclaration.project_original(rights_confirmed=True),
    )
    draft = studio.create_draft(
        profile=profile,
        premise=GenesisPremise.original_lantern_zine(),
    )
    preview = studio.preview(draft.draft_id)
    decision = studio.decide_policy(draft.draft_id, CapabilityManifest.m0())
    snapshot = studio.seal(
        draft.draft_id,
        FreezeDecision.for_preview(
            preview,
            decided_by="m0-12-runtime-host-test",
            rationale="Seal the original input for the RuntimeHost slice.",
        ),
        policy_decision_id=decision.decision_id,
    )
    qri = studio.publish(
        snapshot.snapshot_id,
        policy_decision_id=decision.decision_id,
        publication_key="m0-12-runtime-host-qri-0001",
    )
    location = studio.location
    studio.close()
    return location, qri


def _publish_successor_qri(
    studio_location: StudioRootRef,
    predecessor: QualifiedRuntimeInput,
) -> QualifiedRuntimeInput:
    studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
    successor = studio.publish(
        predecessor.genesis_snapshot_id,
        policy_decision_id=predecessor.policy_decision_ids[0],
        publication_key="m0-12-runtime-host-qri-0002",
        predecessor_qualification_id=predecessor.qualification_id,
    )
    studio.close()
    return successor


def test_published_qri_builds_one_binding_lane_and_restarts_query(
    tmp_path: Path,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )

    route = host.open_runtime(qri, timeline_id=timeline_id)
    repeated = host.open_runtime(qri, timeline_id=timeline_id)
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Could you check whether the lantern issue can still make Friday?",
        language="en",
        provenance="project-original",
    )
    with host.lease(profile_id=qri.profile_id, timeline_id=timeline_id) as lease:
        first = lease.execute(command, idempotency_key="m0-12-host-cycle-0001")
    location = host.location
    host.close()

    restarted = RuntimeHost.open(
        location,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    recovered = restarted.query_binding(
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
    )
    with restarted.lease(
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
    ) as lease:
        replayed = lease.execute(command, idempotency_key="m0-12-host-cycle-0001")
        followed = lease.follow(first.operation_ref)
    restarted.close()

    assert route == repeated
    assert route.binding.state is BindingState.ACTIVE
    assert recovered.binding_id == route.binding.binding_id
    assert recovered.timeline_root == route.binding.timeline_root
    assert first.snapshot.operation_state is OperationState.COMPLETED
    assert replayed.operation_ref == followed.operation_ref == first.operation_ref
    assert replayed.outcome == followed.outcome == first.outcome
    assert replayed.admission_replayed is True
    assert replayed.publication_replayed is True


def test_build_failure_preserves_active_binding_then_successor_swaps_before_event(
    tmp_path: Path,
) -> None:
    studio_location, first_qri = _publish_qri(tmp_path)
    second_qri = _publish_successor_qri(studio_location, first_qri)
    timeline_id = str(uuid4())
    fail_health = False

    def fault(point: RuntimeHostFaultPoint) -> None:
        if fail_health and point is RuntimeHostFaultPoint.AFTER_ASSEMBLY_HEALTH:
            raise OSError("injected assembly health failure")

    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
        _fault_hook=fault,
    )
    first = host.open_runtime(first_qri, timeline_id=timeline_id).binding
    fail_health = True

    with pytest.raises(RuntimeHostFailedClosed):
        host.open_runtime(second_qri, timeline_id=timeline_id)

    unchanged = host.query_binding(
        profile_id=first_qri.profile_id,
        timeline_id=timeline_id,
    )
    fail_health = False
    successor = host.open_runtime(second_qri, timeline_id=timeline_id).binding
    host.close()

    assert unchanged == first
    assert successor.binding_id != first.binding_id
    assert successor.binding_revision == first.binding_revision + 1
    assert successor.binding_epoch == first.binding_epoch + 1
    assert successor.predecessor_binding_id == first.binding_id
    assert successor.timeline_root != first.timeline_root
    assert successor.qualification_id == second_qri.qualification_id


def test_drain_reopens_same_binding_and_retire_survives_cold_start(
    tmp_path: Path,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Record one event before the RuntimeHost lifecycle test.",
        language="en",
        provenance="project-original",
    )
    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    initial = host.open_runtime(qri, timeline_id=timeline_id)
    with host.lease(profile_id=qri.profile_id, timeline_id=timeline_id) as lease:
        lease.execute(command, idempotency_key="m0-12-lifecycle-cycle-0001")

    drained = host.drain(profile_id=qri.profile_id, timeline_id=timeline_id)
    with pytest.raises(RuntimeHostRejected, match="runtime-lane-unavailable"):
        host.lease(profile_id=qri.profile_id, timeline_id=timeline_id)
    reopened = host.open_runtime(qri, timeline_id=timeline_id)
    retired = host.retire(profile_id=qri.profile_id, timeline_id=timeline_id)
    location = host.location
    host.close()

    restarted = RuntimeHost.open(
        location,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    recovered = restarted.query_binding(
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
    )
    with pytest.raises(RuntimeHostRejected, match="binding-not-active"):
        restarted.lease(profile_id=qri.profile_id, timeline_id=timeline_id)
    restarted.close()

    assert drained.serving is False
    assert reopened.binding.binding_id == initial.binding.binding_id
    assert reopened.lane_id == initial.lane_id
    assert retired.state is BindingState.RETIRED
    assert retired.first_subject_event_sealed is True
    assert recovered == retired


def test_post_activation_exception_is_typed_unknown_and_same_binding_recovers(
    tmp_path: Path,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    interrupt_once = True

    def fault(point: RuntimeHostFaultPoint) -> None:
        nonlocal interrupt_once
        if interrupt_once and point is RuntimeHostFaultPoint.AFTER_CONTROL_ACTIVATION:
            interrupt_once = False
            raise OSError("injected response loss after ControlStore activation")

    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
        _fault_hook=fault,
    )

    with pytest.raises(RuntimeHostInterrupted) as interrupted:
        host.open_runtime(qri, timeline_id=timeline_id)

    recovered = host.open_runtime(qri, timeline_id=timeline_id)
    queried = host.query_binding(profile_id=qri.profile_id, timeline_id=timeline_id)
    host.close()

    assert (
        interrupted.value.fault_point is RuntimeHostFaultPoint.AFTER_CONTROL_ACTIVATION
    )
    assert recovered.binding == queried
    assert recovered.binding.binding_revision == 1
    assert recovered.health.serving is True


def test_concurrent_cycle_uses_one_lane_and_second_lease_fails_closed(
    tmp_path: Path,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    host.open_runtime(qri, timeline_id=timeline_id)
    acquired = Event()
    release = Event()
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Serialize this cycle through the one authority lane.",
        language="en",
        provenance="project-original",
    )

    def owner() -> OperationState:
        with host.lease(profile_id=qri.profile_id, timeline_id=timeline_id) as lease:
            acquired.set()
            assert release.wait(timeout=5)
            return lease.execute(
                command,
                idempotency_key="m0-12-concurrent-cycle-0001",
            ).snapshot.operation_state

    def contender() -> str:
        assert acquired.wait(timeout=5)
        try:
            host.lease(profile_id=qri.profile_id, timeline_id=timeline_id)
        except RuntimeHostConflict as error:
            return error.code
        return "unexpected-lease"

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner_future = pool.submit(owner)
        contender_future = pool.submit(contender)
        contention = contender_future.result(timeout=5)
        release.set()
        state = owner_future.result(timeout=5)
    host.close()

    assert contention == "runtime-lease-contended"
    assert state is OperationState.COMPLETED


def test_first_subject_event_seals_whole_timeline_against_successor_rebinding(
    tmp_path: Path,
) -> None:
    studio_location, first_qri = _publish_qri(tmp_path)
    second_qri = _publish_successor_qri(studio_location, first_qri)
    timeline_id = str(uuid4())
    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    initial = host.open_runtime(first_qri, timeline_id=timeline_id)
    command = SubjectCommand.contribute_utterance(
        target_profile_id=first_qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Seal this Timeline to its current authority history.",
        language="en",
        provenance="project-original",
    )
    with host.lease(
        profile_id=first_qri.profile_id,
        timeline_id=timeline_id,
    ) as lease:
        lease.execute(command, idempotency_key="m0-12-seal-cycle-0001")

    with pytest.raises(RuntimeHostConflict, match="timeline-binding-sealed"):
        host.open_runtime(second_qri, timeline_id=timeline_id)

    unchanged = host.query_binding(
        profile_id=first_qri.profile_id,
        timeline_id=timeline_id,
    )
    host.close()

    assert unchanged.binding_id == initial.binding.binding_id
    assert unchanged.first_subject_event_sealed is True


def test_mixed_or_fabricated_authority_and_second_host_fail_closed(
    tmp_path: Path,
) -> None:
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    host = RuntimeHost.create(
        tmp_path,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    route = host.open_runtime(qri, timeline_id=timeline_id)

    with pytest.raises(RuntimeHostConflict, match="second-runtime-host"):
        RuntimeHost.open(
            host.location,
            studio_location=studio_location,
            cognition=FakeCognition(),
        )
    with pytest.raises(RuntimeHostRejected, match="published-qri-required"):
        host.open_runtime(M0AFixture.lantern_zine(), timeline_id=timeline_id)  # type: ignore[arg-type]

    object.__setattr__(qri, "provider_authority", "legacy-provider:forbidden")
    with pytest.raises(RuntimeHostRejected, match="qri-identity-mismatch"):
        host.open_runtime(qri, timeline_id=timeline_id)
    unchanged = host.query_binding(
        profile_id=route.binding.profile_id,
        timeline_id=timeline_id,
    )
    host.close()

    assert unchanged == route.binding

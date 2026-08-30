from __future__ import annotations

import ast
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from dynamic_subject_agent.runtime import FakeCognition, FakeCognitionMode
from dynamic_subject_agent.timeline import SubjectCommand
from test_runtime_host_binding import _publish_qri


class _BlockingFakeCognition(FakeCognition):
    def __init__(self, entered: Event, release: Event) -> None:
        super().__init__()
        self._entered = entered
        self._release = release
        self.proposal_count = 0

    def propose(self, **kwargs: object):
        self.proposal_count += 1
        self._entered.set()
        if not self._release.wait(timeout=5):
            raise RuntimeError("test did not release the bounded Fake Cognition")
        return super().propose(**kwargs)


def test_composed_facade_submit_and_wait_share_one_canonical_operation(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Can the original lantern issue still make Friday's print slot?",
        language="en",
        provenance="project-original",
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="m0-13-application-cycle-0001",
        )
        observed = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert submitted.status in {
        ApplicationOperationStatus.PENDING,
        ApplicationOperationStatus.TERMINAL,
    }
    assert observed.status is ApplicationOperationStatus.TERMINAL
    assert observed.operation_ref == submitted.operation_ref
    assert observed.projection is not None
    assert observed.projection.timeline_outcome_id is not None


def test_host_operation_kind_is_typed_unavailable_without_subject_routing(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.timeline import OperationKind

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Keep Host and Subject operations explicitly distinct.",
        language="en",
        provenance="project-original",
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="m0-13-operation-kind-0001",
        )
        assert submitted.operation_ref is not None
        host_ref = replace(
            submitted.operation_ref,
            operation_kind=OperationKind.HOST,
        )
        response = composition.application.follow(host_ref)
    finally:
        composition.close()

    assert response.status is ApplicationOperationStatus.UNAVAILABLE
    assert response.operation_ref is None
    assert response.problem is not None
    assert response.problem.code == "host-operation-unavailable"


def test_wait_timeout_and_caller_departure_do_not_cancel_or_copy_experience(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application

    entered = Event()
    release = Event()
    cognition = _BlockingFakeCognition(entered, release)
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=cognition,
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Keep processing after this bounded caller wait ends.",
        language="en",
        provenance="project-original",
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="m0-13-timeout-disconnect-0001",
        )
        assert entered.wait(timeout=5)
        timed_out = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=0.01,
        )
        followed_while_running = composition.application.follow(submitted.operation_ref)
        assert timed_out.status is ApplicationOperationStatus.PENDING
        assert timed_out.operation_ref == submitted.operation_ref
        del timed_out
        release.set()
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        repeated = composition.application.submit(
            command,
            idempotency_key="m0-13-timeout-disconnect-0001",
        )
    finally:
        release.set()
        composition.close()

    assert followed_while_running.status is ApplicationOperationStatus.PENDING
    assert followed_while_running.operation_ref == submitted.operation_ref
    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert repeated.status is ApplicationOperationStatus.TERMINAL
    assert terminal.operation_ref == repeated.operation_ref == submitted.operation_ref
    assert terminal.projection == repeated.projection
    assert cognition.proposal_count == 1


def test_sync_async_repeat_and_concurrent_submit_converge_or_conflict_typed(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application

    entered = Event()
    release = Event()
    cognition = _BlockingFakeCognition(entered, release)
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=cognition,
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Converge every caller on one original contribution.",
        language="en",
        provenance="project-original",
    )
    conflicting = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="This different contribution must not reuse the identity.",
        language="en",
        provenance="project-original",
    )

    def submit() -> object:
        return composition.application.submit(
            command,
            idempotency_key="m0-13-concurrent-submit-0001",
        )

    try:
        with ThreadPoolExecutor(max_workers=4) as callers:
            submitted = [
                future.result(timeout=5)
                for future in [callers.submit(submit) for _ in range(4)]
            ]
        assert entered.wait(timeout=5)
        conflict = composition.application.submit(
            conflicting,
            idempotency_key="m0-13-concurrent-submit-0001",
        )
        release.set()
        terminal = composition.application.wait(
            submitted[0].operation_ref,
            timeout_seconds=5,
        )
        synchronous_repeat = composition.application.submit(
            command,
            idempotency_key="m0-13-concurrent-submit-0001",
        )
    finally:
        release.set()
        composition.close()

    operation_refs = {response.operation_ref for response in submitted}
    assert len(operation_refs) == 1
    assert conflict.status is ApplicationOperationStatus.CONFLICT
    assert conflict.operation_ref == submitted[0].operation_ref
    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert synchronous_repeat.status is ApplicationOperationStatus.TERMINAL
    assert synchronous_repeat.operation_ref == terminal.operation_ref
    assert terminal.projection == synchronous_repeat.projection
    assert terminal.projection is not None
    assert terminal.projection.timeline_head_sequence == 1
    assert cognition.proposal_count == 1


def test_restart_submit_follow_and_authorized_queries_preserve_identity(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
        CurrentApplicationProjection,
        RuntimeApplicationProjection,
        TimelineApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Keep the canonical operation stable across a Host restart.",
        language="en",
        provenance="project-original",
    )
    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    submitted = first.application.submit(
        command,
        idempotency_key="m0-13-restart-query-0001",
    )
    terminal = first.application.wait(submitted.operation_ref, timeout_seconds=5)
    host_location = first.host_location
    first.close()

    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
    )
    try:
        replayed = restarted.application.submit(
            command,
            idempotency_key="m0-13-restart-query-0001",
        )
        followed = restarted.application.follow(submitted.operation_ref)
        current = restarted.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.CURRENT,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
        runtime = restarted.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.RUNTIME,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
        timeline = restarted.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.TIMELINE,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        restarted.close()

    assert replayed.operation_ref == followed.operation_ref == terminal.operation_ref
    assert replayed.projection == followed.projection == terminal.projection
    assert current.status is ApplicationQueryStatus.AVAILABLE
    assert runtime.status is ApplicationQueryStatus.AVAILABLE
    assert timeline.status is ApplicationQueryStatus.AVAILABLE
    assert isinstance(current.projection, CurrentApplicationProjection)
    assert isinstance(runtime.projection, RuntimeApplicationProjection)
    assert isinstance(timeline.projection, TimelineApplicationProjection)
    assert current.projection.binding_id == runtime.projection.binding_id
    assert current.projection.binding_revision == 1
    assert current.projection.binding_epoch == 1
    assert timeline.projection.head_sequence == 1


def test_missing_and_unauthorized_follow_or_query_are_indistinguishable(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationOperationStatus,
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
    )
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Do not disclose whether an unauthorized operation exists.",
        language="en",
        provenance="project-original",
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="m0-13-nondisclosure-0001",
        )
        assert submitted.operation_ref is not None
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        missing = composition.application.follow(
            replace(submitted.operation_ref, operation_id=str(uuid4()))
        )
        unauthorized = composition.application.follow(
            replace(submitted.operation_ref, authority_scope_id=str(uuid4()))
        )
        tampered_refs = (
            replace(submitted.operation_ref, root_id=str(uuid4())),
            replace(submitted.operation_ref, timeline_store_id=str(uuid4())),
            replace(submitted.operation_ref, contract_version="M0-CONTRACT-tampered"),
            replace(
                submitted.operation_ref,
                admitted_payload_fingerprint="0" * 64,
            ),
        )
        tampered = [composition.application.follow(item) for item in tampered_refs]
        unknown_query = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.CURRENT,
                target_profile_id=str(uuid4()),
                target_timeline_id=timeline_id,
            )
        )
        unauthorized_query = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.CURRENT,
                target_profile_id=qri.profile_id,
                target_timeline_id=str(uuid4()),
            )
        )
    finally:
        composition.close()

    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert missing == unauthorized
    assert missing.status is ApplicationOperationStatus.NOT_FOUND_OR_NOT_AUTHORIZED
    assert all(response == missing for response in tampered)
    assert unknown_query == unauthorized_query
    assert unknown_query.status is ApplicationQueryStatus.NOT_FOUND_OR_NOT_AUTHORIZED


def test_binding_identity_tamper_fails_closed_without_a_second_operation(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationOperationStatus,
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.host import RuntimeHostFailedClosed

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Fail closed when the frozen binding identity changes.",
        language="en",
        provenance="project-original",
    )
    close_error: RuntimeHostFailedClosed | None = None
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="m0-13-binding-tamper-0001",
        )
        assert submitted.operation_ref is not None
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        with sqlite3.connect(composition.host_location.control_database) as writer:
            writer.execute(
                "UPDATE runtime_authority_binding SET binding_epoch = binding_epoch + 1 "
                "WHERE state = 'active'"
            )
        followed = composition.application.follow(submitted.operation_ref)
        queried = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.RUNTIME,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        try:
            composition.close()
        except RuntimeHostFailedClosed as error:
            close_error = error

    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert followed.status is ApplicationOperationStatus.FAILED_CLOSED
    assert followed.operation_ref is None
    assert queried.status is ApplicationQueryStatus.FAILED_CLOSED
    assert close_error is not None
    assert close_error.code == "binding-identity-mismatch"


def test_second_facade_and_second_composition_lane_fail_closed(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationFacade
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.host import RuntimeHostConflict

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )
    try:
        with pytest.raises(TypeError, match="created only by compose_application"):
            ApplicationFacade(object(), _token=object())
        with pytest.raises(ValueError, match="absolute M0 root"):
            compose_application(
                m0_root=Path("relative-m0-root"),
                studio_location=studio_location,
                qualified_runtime_input=qri,
                timeline_id=timeline_id,
            )
        with pytest.raises(RuntimeError, match="explicit-host-location-required"):
            compose_application(
                m0_root=tmp_path,
                studio_location=studio_location,
                qualified_runtime_input=qri,
                timeline_id=timeline_id,
            )
        with pytest.raises(RuntimeHostConflict, match="second-runtime-host"):
            compose_application(
                m0_root=tmp_path,
                studio_location=studio_location,
                qualified_runtime_input=qri,
                timeline_id=timeline_id,
                host_location=first.host_location,
            )
    finally:
        first.close()


def test_failed_closed_unavailable_and_projection_are_typed_and_minimal(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationOperationStatus,
        ApplicationQueryStatus,
    )
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=FakeCognition(mode=FakeCognitionMode.EPISTEMIC_FAILURE),
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Expose only an authorized canonical failure projection.",
        language="en",
        provenance="project-original",
    )
    try:
        invalid = composition.application.submit(
            object(),
            idempotency_key="m0-13-invalid-0001",
        )
        invalid_query = composition.application.query(object())
        submitted = composition.application.submit(
            command,
            idempotency_key="m0-13-failed-closed-0001",
        )
        failed = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert invalid.status is ApplicationOperationStatus.UNAVAILABLE
    assert invalid_query.status is ApplicationQueryStatus.UNAVAILABLE
    assert failed.status is ApplicationOperationStatus.FAILED_CLOSED
    assert failed.projection is not None
    serialized = json.dumps(asdict(failed), default=str, sort_keys=True).casefold()
    for forbidden in (
        "cognitiveproposal",
        "experience_summary",
        "impact_envelope",
        "chain-of-thought",
        "credential",
        "api_key",
    ):
        assert forbidden not in serialized


def test_interrupted_response_resumes_same_operation_after_host_restart(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.runtime import RuntimeFaultPoint

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Resume this interrupted attempt as the same operation.",
        language="en",
        provenance="project-original",
    )
    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _runtime_interrupt_at=RuntimeFaultPoint.AFTER_COGNITION,
    )
    submitted = first.application.submit(
        command,
        idempotency_key="m0-13-interrupted-0001",
    )
    interrupted = first.application.wait(
        submitted.operation_ref,
        timeout_seconds=5,
    )
    host_location = first.host_location
    first.close()

    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
    )
    try:
        pending = restarted.application.follow(submitted.operation_ref)
        terminal = restarted.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        restarted.close()

    assert interrupted.status is ApplicationOperationStatus.INTERRUPTED
    assert interrupted.operation_ref == submitted.operation_ref
    assert pending.status in {
        ApplicationOperationStatus.PENDING,
        ApplicationOperationStatus.TERMINAL,
    }
    assert pending.operation_ref == submitted.operation_ref
    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert terminal.operation_ref == submitted.operation_ref


def test_facade_source_routes_only_through_host_and_has_no_second_state_store() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "dynamic_subject_agent"
    application_path = package_root / "application.py"
    bootstrap_path = package_root / "bootstrap.py"
    application_source = application_path.read_text(encoding="utf-8")
    bootstrap_source = bootstrap_path.read_text(encoding="utf-8")
    application_tree = ast.parse(application_source)
    bootstrap_tree = ast.parse(bootstrap_source)

    application_imports = {
        node.module
        for node in ast.walk(application_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        module.startswith("dynamic_subject_agent.domains")
        for module in application_imports
    )
    assert "sqlite3" not in application_imports
    assert "TimelineEngine" not in application_source
    assert "CognitiveProposal" not in application_source
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"execute", "publish", "adjudicate"}
        for node in ast.walk(application_tree)
    )
    forbidden_bootstrap_calls = {"getcwd", "cwd", "getenv", "environ", "chdir"}
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in forbidden_bootstrap_calls
        for node in ast.walk(bootstrap_tree)
    )
    combined = (application_source + bootstrap_source).casefold()
    for forbidden in (
        "conversationservice",
        "runtimemanager",
        "legacyruntimegateway",
        "fallback_to_legacy",
        "data/private",
    ):
        assert forbidden.casefold() not in combined


def test_hard_exit_after_admission_recovers_same_operation_and_outcome(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.host import RuntimeHostRootRef
    from dynamic_subject_agent.timeline import OperationKind, OperationRef

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    idempotency_key = "m0-13-hard-exit-recovery-0001"
    command_fields = {
        "target_profile_id": qri.profile_id,
        "target_timeline_id": timeline_id,
        "declared_intent": "ask-collaborator-status",
        "utterance": "Recover this exact operation after a hard process exit.",
        "language": "en",
        "provenance": "project-original",
    }
    command = SubjectCommand.contribute_utterance(**command_fields)
    config_path = tmp_path / "application-hard-crash-config.json"
    descriptor_path = tmp_path / "application-hard-crash-descriptor.json"
    release_path = tmp_path / "application-hard-crash-release"
    config_path.write_text(
        json.dumps(
            {
                "command": command_fields,
                "idempotency_key": idempotency_key,
                "m0_root": str(tmp_path),
                "qri_publication_key": qri.publication_key,
                "studio_location": studio_location.to_dict(),
                "timeline_id": timeline_id,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    worker_path = Path(__file__).with_name("application_hard_crash_worker.py")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    process = subprocess.run(
        (
            sys.executable,
            str(worker_path),
            "--config",
            str(config_path),
            "--descriptor",
            str(descriptor_path),
            "--release",
            str(release_path),
        ),
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )
    assert process.returncode == 91, (process.stdout, process.stderr)
    assert descriptor_path.is_file()

    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    host_location = RuntimeHostRootRef.from_dict(descriptor["host_location"])
    ref_payload = descriptor["operation_ref"]
    operation_ref = OperationRef(
        contract_version=ref_payload["contract_version"],
        root_id=ref_payload["root_id"],
        timeline_store_id=ref_payload["timeline_store_id"],
        authority_scope_id=ref_payload["authority_scope_id"],
        operation_id=ref_payload["operation_id"],
        operation_kind=OperationKind(ref_payload["operation_kind"]),
        admitted_payload_fingerprint=ref_payload["admitted_payload_fingerprint"],
    )
    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
    )
    try:
        replayed = restarted.application.submit(
            command,
            idempotency_key=idempotency_key,
        )
        terminal = restarted.application.wait(
            operation_ref,
            timeout_seconds=5,
        )
        followed = restarted.application.follow(operation_ref)
    finally:
        restarted.close()

    assert replayed.operation_ref == operation_ref
    assert terminal.operation_ref == followed.operation_ref == operation_ref
    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert followed.status is ApplicationOperationStatus.TERMINAL
    assert terminal.projection == followed.projection

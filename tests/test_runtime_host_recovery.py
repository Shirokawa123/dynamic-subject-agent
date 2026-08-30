from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dynamic_subject_agent.host import (
    BindingState,
    RuntimeHost,
    RuntimeHostFaultPoint,
    RuntimeHostRejected,
    RuntimeHostRootRef,
)
from dynamic_subject_agent.runtime import FakeCognition
from dynamic_subject_agent.studio import PolicyKernel, StudioRootRef, SubjectStudio
from dynamic_subject_agent.timeline import OperationState, SubjectCommand


@pytest.mark.parametrize("fault_point", tuple(RuntimeHostFaultPoint))
def test_every_runtime_host_hard_exit_recovers_one_authority_lane(
    tmp_path: Path,
    fault_point: RuntimeHostFaultPoint,
) -> None:
    mature_root = Path(__file__).resolve().parents[1]
    root = tmp_path / fault_point.value
    control = tmp_path / f"{fault_point.value}.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(mature_root / "src")
    worker = mature_root / "tests" / "support" / "runtime_host_crash_worker.py"
    result = subprocess.run(
        (
            sys.executable,
            str(worker),
            "--root",
            str(root),
            "--control",
            str(control),
            "--fault-point",
            fault_point.value,
        ),
        cwd=mature_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 97, (result.stdout, result.stderr)
    payload = json.loads(control.read_text(encoding="utf-8"))
    studio_location = StudioRootRef.from_dict(payload["studio_location"])
    host_location = RuntimeHostRootRef.from_dict(payload["host_location"])
    studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
    qri = studio.query_qri(publication_key=payload["target_publication_key"])
    studio.close()

    restarted = RuntimeHost.open(
        host_location,
        studio_location=studio_location,
        cognition=FakeCognition(),
    )
    if fault_point is RuntimeHostFaultPoint.AFTER_RETIRE_GATE_CLOSED:
        retired = restarted.query_binding(
            profile_id=qri.profile_id,
            timeline_id=payload["timeline_id"],
        )
        with pytest.raises(RuntimeHostRejected, match="binding-not-active"):
            restarted.lease(
                profile_id=qri.profile_id,
                timeline_id=payload["timeline_id"],
            )
        restarted.close()
        assert retired.state is BindingState.RETIRED
        assert retired.first_subject_event_sealed is True
        return
    route = restarted.open_runtime(qri, timeline_id=payload["timeline_id"])
    repeated = restarted.open_runtime(qri, timeline_id=payload["timeline_id"])
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=payload["timeline_id"],
        declared_intent="ask-collaborator-status",
        utterance="Recover the same RuntimeHost lane after a hard exit.",
        language="en",
        provenance="project-original",
    )
    with restarted.lease(
        profile_id=qri.profile_id,
        timeline_id=payload["timeline_id"],
    ) as lease:
        outcome = lease.execute(
            command,
            idempotency_key=f"m0-12-hard-exit-{fault_point.value}",
        )
    restarted.close()

    assert repeated == route
    assert outcome.snapshot.operation_state is OperationState.COMPLETED
    assert outcome.snapshot.timeline_head_sequence == 1

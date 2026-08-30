from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dynamic_subject_agent.host import RuntimeHost, RuntimeHostFaultPoint
from dynamic_subject_agent.runtime import FakeCognition, M0AFixture
from dynamic_subject_agent.studio import (
    CapabilityManifest,
    FreezeDecision,
    GenesisPremise,
    ParticipantProfile,
    PolicyKernel,
    SourceDeclaration,
    SubjectStudio,
)
from dynamic_subject_agent.timeline import SubjectCommand


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument(
        "--fault-point",
        type=RuntimeHostFaultPoint,
        choices=tuple(RuntimeHostFaultPoint),
        required=True,
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    fixture = M0AFixture.lantern_zine()
    studio = SubjectStudio.create_test(args.root, policy_kernel=PolicyKernel())
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
            decided_by="m0-12-runtime-host-crash-worker",
            rationale="Seal the original input for Host crash recovery.",
        ),
        policy_decision_id=decision.decision_id,
    )
    first_qri = studio.publish(
        snapshot.snapshot_id,
        policy_decision_id=decision.decision_id,
        publication_key="m0-12-host-crash-qri-0001",
    )
    successor_qri = studio.publish(
        snapshot.snapshot_id,
        policy_decision_id=decision.decision_id,
        publication_key="m0-12-host-crash-qri-0002",
        predecessor_qualification_id=first_qri.qualification_id,
    )
    studio_location = studio.location
    studio.close()

    def crash(point: RuntimeHostFaultPoint) -> None:
        if point is args.fault_point:
            os._exit(97)

    host = RuntimeHost.create(
        args.root,
        studio_location=studio_location,
        cognition=FakeCognition(),
        _fault_hook=crash,
    )
    timeline_id = fixture.authority.timeline_id
    target = (
        successor_qri
        if args.fault_point is RuntimeHostFaultPoint.AFTER_OLD_GATE_CLOSED
        else first_qri
    )
    args.control.write_text(
        json.dumps(
            {
                "host_location": host.location.to_dict(),
                "studio_location": studio_location.to_dict(),
                "target_publication_key": target.publication_key,
                "timeline_id": timeline_id,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if args.fault_point is RuntimeHostFaultPoint.AFTER_OLD_GATE_CLOSED:
        host.open_runtime(first_qri, timeline_id=timeline_id)
        host.open_runtime(successor_qri, timeline_id=timeline_id)
    elif args.fault_point is RuntimeHostFaultPoint.AFTER_RETIRE_GATE_CLOSED:
        host.open_runtime(first_qri, timeline_id=timeline_id)
        command = SubjectCommand.contribute_utterance(
            target_profile_id=first_qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance="Seal and retire this binding before the injected hard exit.",
            language="en",
            provenance="project-original",
        )
        with host.lease(
            profile_id=first_qri.profile_id,
            timeline_id=timeline_id,
        ) as lease:
            lease.execute(
                command,
                idempotency_key="m0-12-retire-hard-exit-0001",
            )
        host.retire(profile_id=first_qri.profile_id, timeline_id=timeline_id)
    else:
        host.open_runtime(first_qri, timeline_id=timeline_id)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

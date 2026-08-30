"""Test-only worker that hard-exits after M0 13 canonical Admission."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import sleep

from dynamic_subject_agent.bootstrap import compose_application
from dynamic_subject_agent.runtime import FakeCognition
from dynamic_subject_agent.studio import PolicyKernel, StudioRootRef, SubjectStudio
from dynamic_subject_agent.timeline import SubjectCommand


class _HardExitCognition(FakeCognition):
    def __init__(self, release_path: Path) -> None:
        super().__init__()
        self._release_path = release_path

    def propose(self, **kwargs: object):
        while not self._release_path.exists():
            sleep(0.01)
        os._exit(91)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    studio_location = StudioRootRef.from_dict(config["studio_location"])
    studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
    try:
        qri = studio.query_qri(publication_key=config["qri_publication_key"])
    finally:
        studio.close()
    command = SubjectCommand.contribute_utterance(**config["command"])
    composition = compose_application(
        m0_root=Path(config["m0_root"]),
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=config["timeline_id"],
        _cognition=_HardExitCognition(args.release),
    )
    submitted = composition.application.submit(
        command,
        idempotency_key=config["idempotency_key"],
    )
    operation_ref = submitted.operation_ref
    if operation_ref is None:
        raise RuntimeError("hard-crash worker did not receive an OperationRef")
    args.descriptor.write_text(
        json.dumps(
            {
                "host_location": composition.host_location.to_dict(),
                "operation_ref": {
                    "contract_version": operation_ref.contract_version,
                    "root_id": operation_ref.root_id,
                    "timeline_store_id": operation_ref.timeline_store_id,
                    "authority_scope_id": operation_ref.authority_scope_id,
                    "operation_id": operation_ref.operation_id,
                    "operation_kind": operation_ref.operation_kind.value,
                    "admitted_payload_fingerprint": (
                        operation_ref.admitted_payload_fingerprint
                    ),
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    args.release.write_text("hard-exit-after-canonical-admission\n", encoding="utf-8")
    while True:
        sleep(0.05)


if __name__ == "__main__":
    main()

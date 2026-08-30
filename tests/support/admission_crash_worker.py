from __future__ import annotations

import json
import os
import sys

from dynamic_subject_agent.timeline import (
    CanonicalRootRef,
    FaultPoint,
    FixtureAuthority,
    SubjectCommand,
    TimelineEngine,
)


def main() -> int:
    location = CanonicalRootRef.from_dict(json.loads(sys.argv[1]))
    authority = FixtureAuthority.from_dict(json.loads(sys.argv[2]))
    command = SubjectCommand.from_dict(json.loads(sys.argv[3]))
    idempotency_key = sys.argv[4]
    selected = FaultPoint(sys.argv[5])

    def terminate(point: FaultPoint) -> None:
        if point is selected:
            os._exit(86)

    engine = TimelineEngine.open(
        location,
        expected_authority=authority,
        _fault_hook=terminate,
    )
    engine.admit(command, idempotency_key=idempotency_key)
    engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

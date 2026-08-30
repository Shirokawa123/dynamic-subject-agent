"""Hard-crash worker for the M0 07 Publication transaction."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dynamic_subject_agent.timeline import (
    CanonicalRootRef,
    CycleCommitPlan,
    FaultPoint,
    TimelineEngine,
)


CRASH_EXIT_CODE = 86


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    location = CanonicalRootRef.from_dict(
        json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    )
    plan = CycleCommitPlan.from_dict(
        json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    )
    target = FaultPoint(sys.argv[3])

    def crash(observed: FaultPoint) -> None:
        if observed is target:
            os._exit(CRASH_EXIT_CODE)

    engine = TimelineEngine.open(location, _fault_hook=crash)
    try:
        engine.publish(plan)
    finally:
        engine.close()
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dynamic_subject_agent.studio import (
    CapabilityManifest,
    FreezeDecision,
    GenesisPremise,
    ParticipantProfile,
    PolicyDisposition,
    PolicyKernel,
    SourceDeclaration,
    StudioRejected,
    SubjectStudio,
)


class _ManualClock:
    def __init__(self) -> None:
        self.now_us = 1_000_000

    def __call__(self) -> int:
        return self.now_us


class PolicyFailureProtectionTests(unittest.TestCase):
    def _new_studio(self, prefix: str) -> tuple[SubjectStudio, _ManualClock]:
        temporary = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(temporary.cleanup)
        clock = _ManualClock()
        studio = SubjectStudio.create_test(
            Path(temporary.name),
            policy_kernel=PolicyKernel(clock=clock),
        )
        self.addCleanup(studio.close)
        return studio, clock

    def _draft(
        self,
        studio: SubjectStudio,
        *,
        rights_confirmed: bool,
    ) -> str:
        profile = ParticipantProfile.original(
            display_name="Avery Chen",
            identity_core="Avery remains the sole participant identity.",
            source=SourceDeclaration.project_original(
                rights_confirmed=rights_confirmed
            ),
        )
        return studio.create_draft(
            profile=profile,
            premise=GenesisPremise.original_lantern_zine(),
        ).draft_id

    def test_denied_unavailable_and_expired_decisions_leave_no_sealed_artifact(
        self,
    ) -> None:
        denied_studio, _ = self._new_studio("m0-10-policy-denied-")
        denied_draft = self._draft(denied_studio, rights_confirmed=False)
        denied_preview = denied_studio.preview(denied_draft)
        denied = denied_studio.decide_policy(
            denied_draft,
            CapabilityManifest.m0(),
        )
        self.assertIs(denied.disposition, PolicyDisposition.DENIED)
        with self.assertRaisesRegex(StudioRejected, "rights-declaration-missing"):
            denied_studio.seal(
                denied_draft,
                FreezeDecision.for_preview(
                    denied_preview,
                    decided_by="project-authoring-test",
                    rationale="This must remain denied.",
                ),
                policy_decision_id=denied.decision_id,
            )
        self.assertIsNone(denied_studio.query_draft(denied_draft).sealed_snapshot_id)

        unavailable_studio, _ = self._new_studio("m0-10-policy-unavailable-")
        unavailable_draft = self._draft(unavailable_studio, rights_confirmed=True)
        unavailable_preview = unavailable_studio.preview(unavailable_draft)
        unavailable_manifest = CapabilityManifest(
            manifest_version="m0-missing-fake-cognition-1.0",
            included=("four-domain-typed-noop", "host-authoring"),
            certified=("four-domain-typed-noop", "host-authoring"),
            unavailable=(
                "fake-cognition",
                "real-cognition",
                "real-provider",
                "network-access",
            ),
        )
        unavailable = unavailable_studio.decide_policy(
            unavailable_draft,
            unavailable_manifest,
        )
        self.assertIs(unavailable.disposition, PolicyDisposition.UNAVAILABLE)
        with self.assertRaisesRegex(StudioRejected, "required-capability-unavailable"):
            unavailable_studio.seal(
                unavailable_draft,
                FreezeDecision.for_preview(
                    unavailable_preview,
                    decided_by="project-authoring-test",
                    rationale="Missing Fake Cognition must remain unavailable.",
                ),
                policy_decision_id=unavailable.decision_id,
            )
        self.assertIsNone(
            unavailable_studio.query_draft(unavailable_draft).sealed_snapshot_id
        )

        expired_studio, clock = self._new_studio("m0-10-policy-expired-")
        expired_draft = self._draft(expired_studio, rights_confirmed=True)
        expired_preview = expired_studio.preview(expired_draft)
        expiring = expired_studio.decide_policy(
            expired_draft,
            CapabilityManifest.m0(),
            validity_us=10,
        )
        self.assertIs(expiring.disposition, PolicyDisposition.QUALIFIED)
        clock.now_us += 11
        with self.assertRaisesRegex(StudioRejected, "policy-expired"):
            expired_studio.seal(
                expired_draft,
                FreezeDecision.for_preview(
                    expired_preview,
                    decided_by="project-authoring-test",
                    rationale="An expired decision must not seal.",
                ),
                policy_decision_id=expiring.decision_id,
            )
        self.assertIsNone(expired_studio.query_draft(expired_draft).sealed_snapshot_id)


if __name__ == "__main__":
    unittest.main()

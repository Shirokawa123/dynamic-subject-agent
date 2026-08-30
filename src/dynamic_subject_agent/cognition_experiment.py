"""Confirmed phase-two preparation for one isolated Cognition experiment.

This Module consumes exact digest-bound HITL evidence and publishes one complete
but unsealed Studio draft by build-then-move.  It exposes no seal, QRI, binding,
Timeline, submit, export or clear operation.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from dynamic_subject_agent.studio import (
    GenesisPremise,
    ParticipantProfile,
    PolicyKernel,
    SourceDeclaration,
    StudioProblem,
    StudioRootRef,
    SubjectStudio,
    _CONFIRMED_EXPERIMENT_PREPARATION_TOKEN,
    _validate_experimental_base,
)


DEEPSEEK_EXPERIMENT_ID = "2d46499e-8777-4784-a3ab-ced4a6a748ac"
DEEPSEEK_ROOT_ID = "8fbcfda5-0923-4fe4-826c-9139886e8a54"
DEEPSEEK_PROFILE_STORE_ID = "1f0c9058-4f77-45a8-b0b3-4e735399b85f"
DEEPSEEK_PROFILE_ID = "1a909364-f988-4557-a652-dba414c2e59c"
DEEPSEEK_PROFILE_SOURCE_ID = "d3f76993-dbf6-4d67-90bb-b5b9ad4ec523"
DEEPSEEK_GENESIS_BRANCH_ID = "7257d111-ab7b-46d0-ae3c-7140d8c70c6f"
DEEPSEEK_GENESIS_DRAFT_ID = "41b4c879-a22f-40ad-b0ab-45e1f87c2c0d"
DEEPSEEK_GENESIS_SOURCE_ID = "cae5ad40-1bfd-46dc-a828-ff9219345998"
DEEPSEEK_CONTEXT_BRIEF_ID = "e90417d5-f737-431d-b004-ee20d5cb9aac"
_PREVIEW_SHA256 = (
    "c76074f9c37c0ca4c4a5fbdc50fcd4fa934c439569c0ffa01048c0a6388dea25"
)
_CONFIRMATION_SHA256 = (
    "87feee0df98b8bded41855f72994cdaef5b4b2167c9f636d8813406c4f635380"
)
_PROFILE_DISPLAY_NAME = "Lantern Zine collaborator / current authorized participant"
_PROFILE_IDENTITY_CORE = (
    "The current user is the sole present-day participant in this isolated original "
    "branch; no legacy/private identity, role, approval, history, trust, or "
    "relationship state is inherited."
)
_SUBJECT_IDENTITY = (
    "Avery is an adult fictional creator and editor of the original community "
    "publication Lantern Zine."
)
_CANON_START = (
    "Avery and the participant are preparing the original Lantern Zine and checking "
    "whether its next issue can still reach Friday's print slot; no later progress "
    "is asserted."
)
_RELATIONSHIP_PREMISE = (
    "Avery and the participant are newly acquainted collaborators; no trust, promise, "
    "shared memory, completed work, or earned relationship state is preloaded."
)
_AUTHORITY_STATE = MappingProxyType(
    {
        "profile": 1,
        "draft": 1,
        "sealed_genesis": 0,
        "policy_decision": 0,
        "qualified_runtime_input": 0,
        "runtime_binding": 0,
        "runtime_timeline": 0,
        "operation": 0,
        "experience": 0,
        "timeline_outcome": 0,
        "physical_clear": 0,
    }
)


class DeepSeekExperimentPreparationRejected(Exception):
    """The exact phase-two evidence or isolated draft could not be trusted."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PreparedDeepSeekDraft:
    experiment_base: Path
    location: StudioRootRef
    profile_id: str
    branch_id: str
    draft_id: str
    revision: int
    sealed_snapshot_id: None
    preview_sha256: str
    confirmation_sha256: str
    authority_state: Mapping[str, int]


@dataclass(frozen=True)
class _PreparationPlan:
    experiment_base: Path
    preview_sha256: str
    confirmation_sha256: str


def _canonical_uuid(value: Any, field: str) -> str:
    try:
        canonical = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-identity-invalid",
            f"{field} must be a canonical UUID",
        ) from error
    if canonical != value:
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-identity-invalid",
            f"{field} must be canonical",
        )
    return canonical


def _read_evidence(path: Path, *, expected_sha256: str) -> tuple[dict[str, Any], str]:
    if not isinstance(path, Path) or not path.is_absolute():
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-evidence-path-invalid",
            "evidence paths must be explicit absolute Paths",
        )
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
            raise OSError("evidence is absent or linked")
        raw = path.read_bytes()
    except OSError as error:
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-evidence-unreadable",
            "phase-two evidence is absent, linked or unreadable",
        ) from error
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-evidence-digest-mismatch",
            "phase-two evidence does not match the confirmed immutable record",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-evidence-unreadable",
            "phase-two evidence is not valid UTF-8 JSON",
        ) from error
    if not isinstance(payload, dict):
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-evidence-semantics-invalid",
            "phase-two evidence must be a JSON object",
        )
    return payload, digest


def _plan_from_evidence(
    *,
    preview_record: Path,
    confirmation_record: Path,
) -> _PreparationPlan:
    preview, preview_sha256 = _read_evidence(
        preview_record,
        expected_sha256=_PREVIEW_SHA256,
    )
    confirmation, confirmation_sha256 = _read_evidence(
        confirmation_record,
        expected_sha256=_CONFIRMATION_SHA256,
    )
    authority = preview.get("provider_neutral_experimental_authority_preview")
    identities = authority.get("identities") if isinstance(authority, dict) else None
    profile = authority.get("participant_profile") if isinstance(authority, dict) else None
    genesis = authority.get("genesis_draft") if isinstance(authority, dict) else None
    decision = confirmation.get("user_decision")
    reference = confirmation.get("preview")
    expected_identities = {
        "experiment_id": DEEPSEEK_EXPERIMENT_ID,
        "root_id": DEEPSEEK_ROOT_ID,
        "profile_store_id": DEEPSEEK_PROFILE_STORE_ID,
        "profile_id": DEEPSEEK_PROFILE_ID,
        "profile_source_id": DEEPSEEK_PROFILE_SOURCE_ID,
        "genesis_branch_id": DEEPSEEK_GENESIS_BRANCH_ID,
        "genesis_draft_id": DEEPSEEK_GENESIS_DRAFT_ID,
        "genesis_source_id": DEEPSEEK_GENESIS_SOURCE_ID,
        "context_brief_id": DEEPSEEK_CONTEXT_BRIEF_ID,
        "deepseek_terms_disclosure_id": "d0ee253f-0789-4af2-93c2-89d9bd1a0b01",
        "proposed_deepseek_provider_authority_id": (
            "02081deb-96be-4f1c-8a17-9cc39f8daaac"
        ),
    }
    if (
        preview.get("evidence_contract")
        != "POST-M0-01-HITL-PHASE-2-DEEPSEEK-PREVIEW-1.0"
        or preview.get("status") != "awaiting-explicit-user-confirmation"
        or preview.get("preview_plan_id")
        != "157e2601-3203-43e0-975e-fb402415fc9d"
        or confirmation.get("evidence_contract")
        != "POST-M0-01-HITL-PHASE-2-DEEPSEEK-CONFIRMATION-1.0"
        or confirmation.get("status")
        != "confirmed-for-adapter-and-unsealed-draft-preparation"
        or not isinstance(reference, dict)
        or reference.get("sha256") != preview_sha256
        or reference.get("preview_plan_id") != preview.get("preview_plan_id")
        or decision
        != {
            "provider": "DeepSeek Open Platform API",
            "model": "deepseek-v4-flash",
            "accepted_unknown_and_automatic_disk_cache_terms": True,
            "accepted_single_attempt_hard_budget_usd": 0.003,
            "accepted_exact_outbound_from_preview": True,
            "accepted_credential_ref_boundary": "deepseek-api-key-v1",
            "accepted_process_environment_name": "DEEPSEEK" + "_API_KEY",
        }
        or identities != expected_identities
        or profile
        != {
            "display_name": _PROFILE_DISPLAY_NAME,
            "identity_core": _PROFILE_IDENTITY_CORE,
            "authored_origin": "project-original",
            "source_asset_count": 0,
            "inherits_legacy_or_private_history": False,
        }
        or genesis
        != {
            "subject_identity": _SUBJECT_IDENTITY,
            "canon_start": _CANON_START,
            "initial_relationship_premise": _RELATIONSHIP_PREMISE,
            "authored_origin": "project-original",
            "source_asset_count": 0,
            "inherits_legacy_or_private_history": False,
            "state": "uncreated-and-unsealed",
        }
    ):
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-evidence-semantics-invalid",
            "phase-two evidence does not bind the exact confirmed selection",
        )
    experiment_base = Path(str(authority.get("experiment_base", "")))
    canonical_root = Path(str(authority.get("canonical_studio_root", "")))
    if (
        not experiment_base.is_absolute()
        or experiment_base.name != DEEPSEEK_EXPERIMENT_ID
        or canonical_root
        != experiment_base / "mature-runtime-m0" / "roots" / DEEPSEEK_ROOT_ID
    ):
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-path-invalid",
            "the confirmed experiment path or root identity is inconsistent",
        )
    return _PreparationPlan(
        experiment_base=experiment_base,
        preview_sha256=preview_sha256,
        confirmation_sha256=confirmation_sha256,
    )


def _exact_profile() -> ParticipantProfile:
    return ParticipantProfile(
        profile_id=DEEPSEEK_PROFILE_ID,
        display_name=_PROFILE_DISPLAY_NAME,
        identity_core=_PROFILE_IDENTITY_CORE,
        source=SourceDeclaration(
            source_id=DEEPSEEK_PROFILE_SOURCE_ID,
            origin_kind="project-original",
            rights_confirmed=True,
            source_asset_refs=(),
            uses_disallowed_inheritance=False,
        ),
    )


def _exact_premise() -> GenesisPremise:
    return GenesisPremise(
        subject_identity=_SUBJECT_IDENTITY,
        canon_start=_CANON_START,
        initial_relationship_premise=_RELATIONSHIP_PREMISE,
        source=SourceDeclaration(
            source_id=DEEPSEEK_GENESIS_SOURCE_ID,
            origin_kind="project-original",
            rights_confirmed=True,
            source_asset_refs=(),
            uses_disallowed_inheritance=False,
        ),
    )


def _publish_unsealed(plan: _PreparationPlan) -> PreparedDeepSeekDraft:
    final_base = plan.experiment_base
    studio: SubjectStudio | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="post-m0-cognition-build-") as build:
            staging_base = Path(build) / DEEPSEEK_EXPERIMENT_ID
            studio = SubjectStudio._create_reserved_experimental(
                staging_base,
                root_id=DEEPSEEK_ROOT_ID,
                profile_store_id=DEEPSEEK_PROFILE_STORE_ID,
                policy_kernel=PolicyKernel(),
                _authority=_CONFIRMED_EXPERIMENT_PREPARATION_TOKEN,
            )
            draft = studio._create_reserved_draft(
                profile=_exact_profile(),
                premise=_exact_premise(),
                draft_id=DEEPSEEK_GENESIS_DRAFT_ID,
                branch_id=DEEPSEEK_GENESIS_BRANCH_ID,
                _authority=_CONFIRMED_EXPERIMENT_PREPARATION_TOKEN,
            )
            preview = studio.preview(draft.draft_id)
            if (
                preview.profile_id != DEEPSEEK_PROFILE_ID
                or preview.branch_id != DEEPSEEK_GENESIS_BRANCH_ID
                or preview.revision != 1
                or draft.sealed_snapshot_id is not None
                or preview.authoritative is not False
            ):
                raise DeepSeekExperimentPreparationRejected(
                    "phase-two-draft-invalid",
                    "the staged draft does not match the unsealed contract",
                )
            studio.close()
            studio = None
            reserved = _validate_experimental_base(final_base)
            reserved.rmdir()
            staging_base.replace(reserved)
    except DeepSeekExperimentPreparationRejected:
        raise
    except StudioProblem as error:
        raise DeepSeekExperimentPreparationRejected(error.code, error.detail) from error
    except OSError as error:
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-atomic-publication-failed",
            "the complete unsealed draft could not be moved to its exact target",
        ) from error
    except Exception as error:
        raise DeepSeekExperimentPreparationRejected(
            "phase-two-preparation-failed-closed",
            "the confirmed experimental draft could not be prepared",
        ) from error
    finally:
        if studio is not None:
            studio.close()
    location = StudioRootRef(
        root_path=str(
            final_base / "mature-runtime-m0" / "roots" / DEEPSEEK_ROOT_ID
        ),
        root_id=DEEPSEEK_ROOT_ID,
        profile_store_id=DEEPSEEK_PROFILE_STORE_ID,
        root_kind="experimental",
    )
    return PreparedDeepSeekDraft(
        experiment_base=final_base,
        location=location,
        profile_id=DEEPSEEK_PROFILE_ID,
        branch_id=DEEPSEEK_GENESIS_BRANCH_ID,
        draft_id=DEEPSEEK_GENESIS_DRAFT_ID,
        revision=1,
        sealed_snapshot_id=None,
        preview_sha256=plan.preview_sha256,
        confirmation_sha256=plan.confirmation_sha256,
        authority_state=_AUTHORITY_STATE,
    )


class DeepSeekExperimentDraftPreparer:
    """One-shot phase-two Interface; it cannot continue into runtime activation."""

    def __new__(cls, *args: object, **kwargs: object) -> DeepSeekExperimentDraftPreparer:
        raise TypeError("DeepSeekExperimentDraftPreparer is not instantiable")

    @staticmethod
    def prepare(
        *,
        preview_record: Path,
        confirmation_record: Path,
    ) -> PreparedDeepSeekDraft:
        return _publish_unsealed(
            _plan_from_evidence(
                preview_record=preview_record,
                confirmation_record=confirmation_record,
            )
        )

    @staticmethod
    def _prepare_test(test_parent: Path) -> PreparedDeepSeekDraft:
        if not isinstance(test_parent, Path) or not test_parent.is_absolute():
            raise TypeError("test_parent must be an explicit absolute Path")
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        prospective_parent = test_parent.resolve(strict=False)
        if not prospective_parent.is_relative_to(temporary_root):
            raise DeepSeekExperimentPreparationRejected(
                "test-parent-not-temporary",
                "the preparation seam is restricted to system temporary data",
            )
        return _publish_unsealed(
            _PreparationPlan(
                experiment_base=prospective_parent / DEEPSEEK_EXPERIMENT_ID,
                preview_sha256="test-only",
                confirmation_sha256="test-only",
            )
        )


__all__ = [
    "DEEPSEEK_EXPERIMENT_ID",
    "DEEPSEEK_GENESIS_BRANCH_ID",
    "DEEPSEEK_GENESIS_DRAFT_ID",
    "DEEPSEEK_PROFILE_ID",
    "DEEPSEEK_PROFILE_STORE_ID",
    "DEEPSEEK_ROOT_ID",
    "DeepSeekExperimentDraftPreparer",
    "DeepSeekExperimentPreparationRejected",
    "PreparedDeepSeekDraft",
]

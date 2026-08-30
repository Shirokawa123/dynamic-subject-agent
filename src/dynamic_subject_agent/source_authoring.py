"""Offline, unpublished SubjectStudio candidates from confirmed source subsets."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.source_requalification import ConfirmedQualifiedSourceSubset


_RESERVED_PATH_SEGMENTS = frozenset(
    {"archive", "archives", "backup", "backups", "legacy", "private", "retired", "sagiri"}
)
_AUTHORIZATION_RECEIPT_NAME = "POST-M0-02-PHASE-4-AUTHORIZATION-RECEIPT-01.json"
_AUTHORIZATION_RECEIPT_SHA256 = (
    "b9a23f51c173145642fb736a52f674b53b52d880a9150f27ee7a4999d220e816"
)


class OfflineAuthoringRejected(Exception):
    """The exact confirmed source subset cannot be used for offline authoring."""


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise OfflineAuthoringRejected("authoring path cannot be inspected") from error
    return stat.S_ISLNK(status.st_mode) or bool(
        getattr(status, "st_file_attributes", 0) & 0x400
    )


def _has_link_or_reparse_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            if _is_link_or_reparse(current):
                return True
    return False


def _artifact_id(subset: ConfirmedQualifiedSourceSubset) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "offline-subjectstudio-artifact:" + subset.subset_digest,
        )
    )


def _artifact_root(
    qualification_ledger: Path,
    subset: ConfirmedQualifiedSourceSubset,
    *,
    authorization_receipt: Path | None,
    expected_authorization_sha256: str,
    test_authorization: bool,
) -> Path:
    database = qualification_ledger / "qualification.sqlite3"
    try:
        with closing(
            sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        ) as connection:
            connection.execute("PRAGMA query_only = ON")
            row = connection.execute(
                "SELECT manifest_digest, manifest_json, subset_json "
                "FROM source_manifest WHERE manifest_id = ?",
                (subset.manifest_id,),
            ).fetchone()
        if row is None or row[2] is None:
            raise OfflineAuthoringRejected(
                "qualification ledger has no confirmed subset"
            )
        manifest = json.loads(row[1])
        stored_subset = json.loads(row[2])
        calculated_manifest_digest = _digest(
            {
                "version": manifest["version"],
                "manifest_id": manifest["manifest_id"],
                "selection_root": manifest["selection_root"],
                "items": manifest["items"],
            }
        )
        if (
            manifest["manifest_id"] != subset.manifest_id
            or manifest["manifest_digest"] != row[0]
            or calculated_manifest_digest != row[0]
            or stored_subset
            != {
                "manifest_id": subset.manifest_id,
                "report_digest": subset.report_digest,
                "source_ids": list(subset.source_ids),
                "confirmation_id": subset.confirmation_id,
                "subset_digest": subset.subset_digest,
            }
        ):
            raise OfflineAuthoringRejected("qualification ledger is tampered")
        selection_root = Path(manifest["selection_root"])
    except OfflineAuthoringRejected:
        raise
    except (json.JSONDecodeError, KeyError, OSError, sqlite3.Error, TypeError) as error:
        raise OfflineAuthoringRejected("qualification ledger is unavailable") from error
    root = (
        selection_root.parent
        / "subjectstudio-artifacts"
        / f"artifact-{_artifact_id(subset)}"
    )
    receipt = authorization_receipt or (
        selection_root.parent / _AUTHORIZATION_RECEIPT_NAME
    )
    if test_authorization:
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        try:
            selection_root.resolve(strict=True).relative_to(temporary_root)
            receipt.resolve(strict=True).relative_to(temporary_root)
        except (OSError, ValueError) as error:
            raise OfflineAuthoringRejected(
                "test authorization is restricted to the process temporary root"
            ) from error
    try:
        if (
            not receipt.is_absolute()
            or _has_link_or_reparse_component(receipt)
            or not receipt.is_file()
        ):
            raise OfflineAuthoringRejected("authoring authorization is unavailable")
        receipt_bytes = receipt.read_bytes()
        if hashlib.sha256(receipt_bytes).hexdigest() != expected_authorization_sha256:
            raise OfflineAuthoringRejected("authoring authorization digest is invalid")
        authorization = json.loads(receipt_bytes.decode("utf-8"))
        expected_contract = (
            "POST-M0-02-PHASE-4-AUTHORIZATION-RECEIPT-TEST-1.0"
            if test_authorization
            else "POST-M0-02-PHASE-4-AUTHORIZATION-RECEIPT-01"
        )
        expected_manifest = {
            "manifest_id": subset.manifest_id,
            "manifest_digest": row[0],
            "selection_root": str(selection_root),
            "source_ids": [item["source_id"] for item in manifest["items"]],
            "source_hashes": [
                item["expected_sha256"] for item in manifest["items"]
            ],
        }
        expected_subset = {
            "manifest_id": subset.manifest_id,
            "report_digest": subset.report_digest,
            "source_ids": list(subset.source_ids),
            "confirmation_id": subset.confirmation_id,
            "subset_digest": subset.subset_digest,
        }
        if (
            authorization.get("contract") != expected_contract
            or authorization.get("status")
            != "confirmed-exact-subset-offline-authoring-only"
            or authorization.get("manifest") != expected_manifest
            or authorization.get("qualification_ledger_root")
            != str(qualification_ledger)
            or authorization.get("confirmed_subset") != expected_subset
            or authorization.get("exact_artifact_root") != str(root)
        ):
            raise OfflineAuthoringRejected(
                "authoring authorization does not bind the exact ledger and subset"
            )
    except OfflineAuthoringRejected:
        raise
    except (json.JSONDecodeError, OSError, UnicodeError) as error:
        raise OfflineAuthoringRejected("authoring authorization is unavailable") from error
    return root


@dataclass(frozen=True)
class ArtifactProvenance:
    manifest_id: str
    manifest_digest: str
    report_digest: str
    subset_digest: str
    source_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    rights_basis: str
    declared_use: str
    artifact_root: str


@dataclass(frozen=True)
class UnsealedGenesisArtifact:
    candidate_id: str
    authored_origin_document: str
    content_digest: str


@dataclass(frozen=True)
class UnsealedKnowledgeArtifact:
    candidate_id: str
    source_documents: tuple[str, ...]
    content_digest: str


@dataclass(frozen=True)
class UnpublishedSubjectStudioArtifact:
    artifact_id: str
    genesis: UnsealedGenesisArtifact
    knowledge: UnsealedKnowledgeArtifact
    provenance: ArtifactProvenance
    published: bool
    unsealed: bool
    authority_counts: dict[str, int]


class OfflineSubjectStudioAuthoring:
    def __init__(
        self,
        root: Path,
        qualification_ledger: Path,
        confirmed_subset: ConfirmedQualifiedSourceSubset,
        authoring_hook: Callable[[str], None] | None,
    ) -> None:
        self._database = root / "offline-authoring.sqlite3"
        self._qualification_ledger = qualification_ledger
        self._confirmed_subset = confirmed_subset
        self._authoring_hook = authoring_hook

    @classmethod
    def open(
        cls,
        *,
        qualification_ledger: Path,
        confirmed_subset: ConfirmedQualifiedSourceSubset,
        authoring_hook: Callable[[str], None] | None = None,
    ) -> "OfflineSubjectStudioAuthoring":
        return cls._open(
            qualification_ledger=qualification_ledger,
            confirmed_subset=confirmed_subset,
            authorization_receipt=None,
            expected_authorization_sha256=_AUTHORIZATION_RECEIPT_SHA256,
            test_authorization=False,
            authoring_hook=authoring_hook,
        )

    @classmethod
    def open_test(
        cls,
        *,
        qualification_ledger: Path,
        confirmed_subset: ConfirmedQualifiedSourceSubset,
        authorization_receipt: Path,
        expected_authorization_sha256: str,
        authoring_hook: Callable[[str], None] | None = None,
    ) -> "OfflineSubjectStudioAuthoring":
        return cls._open(
            qualification_ledger=qualification_ledger,
            confirmed_subset=confirmed_subset,
            authorization_receipt=authorization_receipt,
            expected_authorization_sha256=expected_authorization_sha256,
            test_authorization=True,
            authoring_hook=authoring_hook,
        )

    @classmethod
    def _open(
        cls,
        *,
        qualification_ledger: Path,
        confirmed_subset: ConfirmedQualifiedSourceSubset,
        authorization_receipt: Path | None,
        expected_authorization_sha256: str,
        test_authorization: bool,
        authoring_hook: Callable[[str], None] | None,
    ) -> "OfflineSubjectStudioAuthoring":
        if not isinstance(confirmed_subset, ConfirmedQualifiedSourceSubset):
            raise OfflineAuthoringRejected("confirmed qualified subset is required")
        if not isinstance(qualification_ledger, Path):
            raise OfflineAuthoringRejected("read-only qualification ledger is required")
        if (
            not qualification_ledger.is_absolute()
            or any(part in {".", ".."} for part in qualification_ledger.parts)
            or any(
                character in str(qualification_ledger)
                for character in ("*", "?", "[", "]")
            )
            or any(
                part.lower() in _RESERVED_PATH_SEGMENTS
                for part in qualification_ledger.parts
            )
        ):
            raise OfflineAuthoringRejected("qualification ledger path is unsafe")
        database = qualification_ledger / "qualification.sqlite3"
        if (
            _has_link_or_reparse_component(qualification_ledger)
            or _has_link_or_reparse_component(database)
            or not database.is_file()
        ):
            raise OfflineAuthoringRejected("qualification ledger is unavailable")
        root = _artifact_root(
            qualification_ledger,
            confirmed_subset,
            authorization_receipt=authorization_receipt,
            expected_authorization_sha256=expected_authorization_sha256,
            test_authorization=test_authorization,
        )
        if (
            not root.is_absolute()
            or any(part in {".", ".."} for part in root.parts)
            or any(character in str(root) for character in ("*", "?", "[", "]"))
            or any(part.lower() in _RESERVED_PATH_SEGMENTS for part in root.parts)
        ):
            raise OfflineAuthoringRejected("authoring root is unsafe")
        if _has_link_or_reparse_component(root):
            raise OfflineAuthoringRejected(
                "authoring root must not traverse a link or junction"
            )
        try:
            root.parent.mkdir(parents=False, exist_ok=True)
        except OSError as error:
            raise OfflineAuthoringRejected("authoring root is unavailable") from error
        if root.exists():
            existing = {path.name for path in root.iterdir()} if root.is_dir() else set()
            if not root.is_dir() or not existing or not existing.issubset(
                {"offline-authoring.sqlite3", "offline-authoring.sqlite3-journal"}
            ):
                raise OfflineAuthoringRejected(
                    "authoring root must be new or an exact existing artifact root"
                )
        else:
            root.mkdir(parents=True, exist_ok=False)
        instance = cls(
            root,
            qualification_ledger,
            confirmed_subset,
            authoring_hook,
        )
        try:
            with sqlite3.connect(instance._database) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS artifact "
                    "(subset_digest TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
                columns = tuple(
                    row[1] for row in connection.execute("PRAGMA table_info(artifact)")
                )
                if columns != ("subset_digest", "payload"):
                    raise OfflineAuthoringRejected("authoring store schema is invalid")
        except sqlite3.Error as error:
            raise OfflineAuthoringRejected("authoring store is unavailable") from error
        return instance

    @property
    def artifact_root(self) -> Path:
        return self._database.parent

    def author(self) -> UnpublishedSubjectStudioArtifact:
        subset = self._confirmed_subset
        artifact = self._expected_artifact()
        if self._authoring_hook is not None:
            self._authoring_hook("after-source-read-before-authoring-transaction")
        payload = self._serialize_artifact(artifact)
        with sqlite3.connect(self._database, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM artifact WHERE subset_digest = ?",
                (subset.subset_digest,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO artifact(subset_digest,payload) VALUES (?,?)",
                    (subset.subset_digest, payload),
                )
                if self._authoring_hook is not None:
                    self._authoring_hook("after-artifact-insert-before-commit")
            elif row[0] != payload:
                raise OfflineAuthoringRejected("stored artifact provenance is invalid")
        if self._authoring_hook is not None:
            self._authoring_hook("after-authoring-commit")
        return artifact

    def query(self) -> UnpublishedSubjectStudioArtifact:
        subset = self._confirmed_subset
        expected = self._expected_artifact()
        try:
            with closing(
                sqlite3.connect(
                    f"file:{self._database.as_posix()}?mode=ro",
                    uri=True,
                )
            ) as connection:
                connection.execute("PRAGMA query_only = ON")
                row = connection.execute(
                    "SELECT payload FROM artifact WHERE subset_digest = ?",
                    (subset.subset_digest,),
                ).fetchone()
        except sqlite3.Error as error:
            raise OfflineAuthoringRejected("authoring store cannot be read") from error
        if row is None:
            raise OfflineAuthoringRejected("unpublished artifact is unavailable")
        if row[0] != self._serialize_artifact(expected):
            raise OfflineAuthoringRejected("stored artifact provenance is invalid")
        return expected

    def _expected_artifact(self) -> UnpublishedSubjectStudioArtifact:
        subset = self._confirmed_subset
        provenance, source_document = self._load_confirmed_source(subset)
        source_digest = provenance.source_hashes[0]
        return UnpublishedSubjectStudioArtifact(
            artifact_id=_artifact_id(subset),
            genesis=UnsealedGenesisArtifact(
                candidate_id=str(
                    uuid5(NAMESPACE_URL, "offline-genesis:" + subset.subset_digest)
                ),
                authored_origin_document=source_document,
                content_digest=source_digest,
            ),
            knowledge=UnsealedKnowledgeArtifact(
                candidate_id=str(
                    uuid5(NAMESPACE_URL, "offline-knowledge:" + subset.subset_digest)
                ),
                source_documents=(source_document,),
                content_digest=source_digest,
            ),
            provenance=provenance,
            published=False,
            unsealed=True,
            authority_counts={
                "qualified_runtime_input": 0,
                "runtime_binding": 0,
                "runtime_timeline": 0,
                "operation": 0,
                "timeline_outcome": 0,
                "effect": 0,
                "physical_clear": 0,
            },
        )

    @staticmethod
    def _serialize_artifact(artifact: UnpublishedSubjectStudioArtifact) -> str:
        return json.dumps(
            artifact,
            default=lambda value: value.__dict__,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _load_confirmed_source(
        self,
        subset: ConfirmedQualifiedSourceSubset,
    ) -> tuple[ArtifactProvenance, str]:
        database = self._qualification_ledger / "qualification.sqlite3"
        if (
            _has_link_or_reparse_component(self._qualification_ledger)
            or _has_link_or_reparse_component(database)
            or not database.is_file()
        ):
            raise OfflineAuthoringRejected("qualification ledger is unavailable")
        try:
            with closing(
                sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
            ) as connection:
                connection.execute("PRAGMA query_only = ON")
                row = connection.execute(
                    "SELECT manifest_digest, manifest_json, report_json, subset_json "
                    "FROM source_manifest WHERE manifest_id = ?",
                    (subset.manifest_id,),
                ).fetchone()
            if row is None or row[2] is None or row[3] is None:
                raise OfflineAuthoringRejected(
                    "qualification ledger has no confirmed audit subset"
                )
            manifest = json.loads(row[1])
            report = json.loads(row[2])
            stored_subset = json.loads(row[3])
            calculated_manifest_digest = _digest(
                {
                    "version": manifest["version"],
                    "manifest_id": manifest["manifest_id"],
                    "selection_root": manifest["selection_root"],
                    "items": manifest["items"],
                }
            )
            calculated_report_digest = _digest(
                {
                    "manifest_id": report["manifest_id"],
                    "manifest_digest": report["manifest_digest"],
                    "confirmation_id": report["confirmation_id"],
                    "results": report["results"],
                }
            )
            if (
                manifest["manifest_id"] != subset.manifest_id
                or manifest["manifest_digest"] != row[0]
                or calculated_manifest_digest != row[0]
                or report["manifest_id"] != subset.manifest_id
                or report["manifest_digest"] != row[0]
                or report["report_digest"] != subset.report_digest
                or calculated_report_digest != subset.report_digest
            ):
                raise OfflineAuthoringRejected("qualification ledger is tampered")
            if stored_subset != {
                "manifest_id": subset.manifest_id,
                "report_digest": subset.report_digest,
                "source_ids": list(subset.source_ids),
                "confirmation_id": subset.confirmation_id,
                "subset_digest": subset.subset_digest,
            }:
                raise OfflineAuthoringRejected(
                    "qualification ledger does not match confirmed subset"
                )
            items = manifest["items"]
            if len(items) != 1 or items[0]["source_id"] != subset.source_ids[0]:
                raise OfflineAuthoringRejected(
                    "qualification ledger does not match confirmed subset"
                )
            item = items[0]
            content_type = str(item["declared_content_type"]).lower().replace(" ", "")
            if content_type not in {
                "text/plain",
                "text/plain;charset=utf-8",
                "text/markdown",
                "text/markdown;charset=utf-8",
            }:
                raise OfflineAuthoringRejected(
                    "qualified source content type is unavailable for authoring"
                )
            selection_root = Path(manifest["selection_root"])
            source_path = selection_root / item["relative_path"]
            if (
                _has_link_or_reparse_component(selection_root)
                or _has_link_or_reparse_component(source_path)
                or not source_path.is_file()
            ):
                raise OfflineAuthoringRejected("qualified source is unavailable")
            source_bytes = source_path.read_bytes()
            if (
                len(source_bytes) != item["declared_size_bytes"]
                or hashlib.sha256(source_bytes).hexdigest() != item["expected_sha256"]
            ):
                raise OfflineAuthoringRejected("qualified source identity changed")
            source_document = source_bytes.decode("utf-8")
            if not source_document.strip():
                raise OfflineAuthoringRejected("qualified source document is blank")
            provenance = ArtifactProvenance(
                manifest_id=subset.manifest_id,
                manifest_digest=row[0],
                report_digest=report["report_digest"],
                subset_digest=subset.subset_digest,
                source_ids=subset.source_ids,
                source_hashes=(item["expected_sha256"],),
                rights_basis=item["rights_basis"],
                declared_use=item["declared_use"],
                artifact_root=str(self.artifact_root),
            )
            return provenance, source_document
        except OfflineAuthoringRejected:
            raise
        except (OSError, UnicodeError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
            raise OfflineAuthoringRejected("qualified source cannot be authored") from error

__all__ = [
    "ArtifactProvenance",
    "OfflineAuthoringRejected",
    "OfflineSubjectStudioAuthoring",
    "UnsealedGenesisArtifact",
    "UnsealedKnowledgeArtifact",
    "UnpublishedSubjectStudioArtifact",
]

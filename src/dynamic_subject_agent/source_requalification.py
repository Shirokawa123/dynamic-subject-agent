"""Offline, exact-item source requalification before any Studio authoring.

This Module is deliberately not a runtime input, discovery tool, importer, or
publisher.  Its small Interface persists an exact source-text-free manifest,
binds a first confirmation, audits only the listed files, and returns a typed
per-item report.  A later vertical slice may consume a second confirmation to
produce an unpublished artifact preview.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, UUID, uuid5


_MANIFEST_VERSION = "post-m0-source-requalification-v1"
_SHA256_LENGTH = 64
_WILDCARD_CHARACTERS = frozenset("*?[]{}")
_RESERVED_PATH_SEGMENTS = frozenset(
    {
        "archive",
        "archives",
        "backup",
        "backups",
        "legacy",
        "private",
        "retired",
        "sagiri",
    }
)
_ALLOWED_USE = "local-private-subjectstudio-authoring"


class SourceRequalificationProblem(Exception):
    """A manifest, confirmation, or audit cannot be trusted."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class SourceRequalificationRejected(SourceRequalificationProblem):
    """The request violates an exact-source qualification invariant."""


class SourceRequalificationConflict(SourceRequalificationProblem):
    """An immutable identity was reused for different qualification content."""


class SourceRequalificationFailedClosed(SourceRequalificationProblem):
    """A technical fault prevented a trustworthy audit result."""


def _canonical_uuid(value: str, field: str) -> str:
    try:
        canonical = str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as error:
        raise SourceRequalificationRejected(
            "source-identity-invalid", f"{field} must be a canonical UUID"
        ) from error
    if canonical != value:
        raise SourceRequalificationRejected(
            "source-identity-invalid", f"{field} must be canonical"
        )
    return canonical


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return _sha256(_canonical_json(value).encode("utf-8"))


def _valid_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _reject_unsafe_path(path: Path, field: str) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise SourceRequalificationRejected(
            "source-path-invalid", f"{field} must be an explicit absolute Path"
        )
    rendered = str(path)
    if any(character in rendered for character in _WILDCARD_CHARACTERS):
        raise SourceRequalificationRejected(
            "source-path-invalid", f"{field} must not contain wildcard syntax"
        )
    normalized_parts = tuple(part.lower() for part in path.parts)
    if any(part in {".", ".."} for part in normalized_parts):
        raise SourceRequalificationRejected(
            "source-path-invalid", f"{field} must not contain traversal segments"
        )
    if any(part in _RESERVED_PATH_SEGMENTS for part in normalized_parts):
        raise SourceRequalificationRejected(
            "source-path-reserved", f"{field} has a reserved path segment"
        )


def _is_link_or_reparse(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError as error:
        raise SourceRequalificationFailedClosed(
            "source-path-unreadable", "the exact listed source cannot be inspected"
        ) from error
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


@dataclass(frozen=True)
class SourceManifestItem:
    """One exact, user-selected source item; it never carries source text."""

    source_id: str
    source_path: Path
    expected_sha256: str
    declared_content_type: str
    declared_size_bytes: int
    rights_basis: str
    declared_use: str
    rights_confirmed: bool

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        source_path: Path,
        expected_sha256: str,
        declared_content_type: str,
        declared_size_bytes: int,
        rights_basis: str,
        declared_use: str,
        rights_confirmed: bool,
    ) -> SourceManifestItem:
        source_id = _canonical_uuid(source_id, "source_id")
        _reject_unsafe_path(source_path, "source_path")
        if _has_link_or_reparse_component(source_path):
            raise SourceRequalificationRejected(
                "source-path-linked", "source_path must not traverse a link or junction"
            )
        if source_path.exists():
            if not source_path.is_file():
                raise SourceRequalificationRejected(
                    "source-path-not-file", "source_path must name one exact file"
                )
        if not _valid_sha256(expected_sha256):
            raise SourceRequalificationRejected(
                "source-hash-invalid", "expected_sha256 must be lowercase SHA-256"
            )
        if (
            not isinstance(declared_content_type, str)
            or not declared_content_type
            or len(declared_content_type) > 128
        ):
            raise SourceRequalificationRejected(
                "source-type-invalid", "declared_content_type must be explicit"
            )
        if not isinstance(declared_size_bytes, int) or declared_size_bytes < 0:
            raise SourceRequalificationRejected(
                "source-size-invalid", "declared_size_bytes must be non-negative"
            )
        if not isinstance(rights_basis, str) or not rights_basis.strip():
            raise SourceRequalificationRejected(
                "rights-basis-invalid", "rights_basis must be explicit"
            )
        if declared_use != _ALLOWED_USE:
            raise SourceRequalificationRejected(
                "source-use-unavailable", "the declared use is not available"
            )
        if not isinstance(rights_confirmed, bool):
            raise SourceRequalificationRejected(
                "rights-confirmation-invalid", "rights_confirmed must be explicit"
            )
        return cls(
            source_id=source_id,
            source_path=source_path,
            expected_sha256=expected_sha256,
            declared_content_type=declared_content_type,
            declared_size_bytes=declared_size_bytes,
            rights_basis=rights_basis.strip(),
            declared_use=declared_use,
            rights_confirmed=rights_confirmed,
        )

    def _stored_dict(self, selection_root: Path) -> dict[str, Any]:
        try:
            relative_path = self.source_path.relative_to(selection_root)
        except ValueError as error:
            raise SourceRequalificationRejected(
                "source-path-outside-root", "each listed item must be inside selection_root"
            ) from error
        if not relative_path.parts or any(part in {".", ".."} for part in relative_path.parts):
            raise SourceRequalificationRejected(
                "source-path-invalid", "each listed item must be an exact child file"
            )
        return {
            "source_id": self.source_id,
            "relative_path": relative_path.as_posix(),
            "expected_sha256": self.expected_sha256,
            "declared_content_type": self.declared_content_type,
            "declared_size_bytes": self.declared_size_bytes,
            "rights_basis": self.rights_basis,
            "declared_use": self.declared_use,
            "rights_confirmed": self.rights_confirmed,
        }


@dataclass(frozen=True)
class SourceRequalificationManifest:
    """Immutable, exact-item manifest created before any source bytes are read."""

    manifest_id: str
    selection_root: Path
    items: tuple[SourceManifestItem, ...]
    manifest_digest: str

    @classmethod
    def create(
        cls,
        *,
        selection_root: Path,
        manifest_id: str,
        items: tuple[SourceManifestItem, ...],
    ) -> SourceRequalificationManifest:
        _reject_unsafe_path(selection_root, "selection_root")
        if _has_link_or_reparse_component(selection_root):
            raise SourceRequalificationRejected(
                "selection-root-linked",
                "selection_root must not traverse a link or junction",
            )
        if selection_root.exists():
            if not selection_root.is_dir():
                raise SourceRequalificationRejected(
                    "selection-root-invalid", "selection_root must be a directory"
                )
        manifest_id = _canonical_uuid(manifest_id, "manifest_id")
        items = tuple(items)
        if not items or len(items) > 256:
            raise SourceRequalificationRejected(
                "manifest-item-count-invalid", "manifest must contain 1 to 256 exact items"
            )
        if len({item.source_id for item in items}) != len(items):
            raise SourceRequalificationRejected(
                "manifest-source-identity-duplicate", "source identities must be unique"
            )
        stored_items = tuple(item._stored_dict(selection_root) for item in items)
        if len({item["relative_path"] for item in stored_items}) != len(stored_items):
            raise SourceRequalificationRejected(
                "manifest-source-path-duplicate", "each source path may appear once"
            )
        digest = _digest(
            {
                "version": _MANIFEST_VERSION,
                "manifest_id": manifest_id,
                "selection_root": str(selection_root),
                "items": stored_items,
            }
        )
        return cls(
            manifest_id=manifest_id,
            selection_root=selection_root,
            items=items,
            manifest_digest=digest,
        )

    def _stored_dict(self) -> dict[str, Any]:
        return {
            "version": _MANIFEST_VERSION,
            "manifest_id": self.manifest_id,
            "selection_root": str(self.selection_root),
            "items": [item._stored_dict(self.selection_root) for item in self.items],
            "manifest_digest": self.manifest_digest,
        }


@dataclass(frozen=True)
class SourceManifestPreview:
    """Redacted, source-text-free first-confirmation disclosure."""

    manifest_id: str
    manifest_digest: str
    item_count: int
    source_text_free_items: tuple[dict[str, Any], ...]

    def to_source_text_free_dict(self) -> dict[str, Any]:
        return {
            "contract": _MANIFEST_VERSION,
            "status": "awaiting-manifest-confirmation",
            "manifest_id": self.manifest_id,
            "manifest_digest": self.manifest_digest,
            "item_count": self.item_count,
            "items": list(self.source_text_free_items),
            "read_boundary": "no source bytes are read until exact manifest confirmation",
            "runtime_authority": False,
        }


@dataclass(frozen=True)
class ManifestConfirmation:
    manifest_id: str
    manifest_digest: str
    confirmation_id: str


@dataclass(frozen=True)
class SourceAuditResult:
    source_id: str
    status: str
    code: str


@dataclass(frozen=True)
class SourceAuditReport:
    manifest_id: str
    manifest_digest: str
    confirmation_id: str
    results: tuple[SourceAuditResult, ...]
    report_digest: str
    unpublished: bool
    runtime_authority_count: int

    @property
    def passed_source_ids(self) -> tuple[str, ...]:
        return tuple(result.source_id for result in self.results if result.status == "passed")

    @property
    def failed_source_ids(self) -> tuple[str, ...]:
        return tuple(result.source_id for result in self.results if result.status == "failed")


@dataclass(frozen=True)
class ConfirmedQualifiedSourceSubset:
    """Second-confirmed immutable input; it is not a Studio or runtime artifact."""

    manifest_id: str
    report_digest: str
    source_ids: tuple[str, ...]
    confirmation_id: str
    subset_digest: str


@dataclass(frozen=True)
class UnpublishedArtifactPreview:
    """A stable provenance candidate that has no publication authority."""

    artifact_id: str
    source_provenance_digest: str
    published: bool
    authority_state: dict[str, int]


class SourceRequalificationSession:
    """The offline qualification Interface; it has no runtime or publication method."""

    def __init__(
        self,
        ledger_root: Path,
        *,
        audit_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._ledger_root = ledger_root
        self._database = ledger_root / "qualification.sqlite3"
        self._audit_hook = audit_hook

    @classmethod
    def open(
        cls,
        ledger_root: Path,
        *,
        _audit_hook: Callable[[str], None] | None = None,
    ) -> SourceRequalificationSession:
        _reject_unsafe_path(ledger_root, "ledger_root")
        if _has_link_or_reparse_component(ledger_root):
            raise SourceRequalificationRejected(
                "ledger-root-linked", "ledger_root must not traverse a link or junction"
            )
        try:
            ledger_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise SourceRequalificationFailedClosed(
                "ledger-root-unavailable", "the qualification ledger root cannot be created"
            ) from error
        session = cls(ledger_root, audit_hook=_audit_hook)
        session._initialize()
        return session

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database, timeout=30)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS source_manifest (
                        manifest_id TEXT PRIMARY KEY,
                        manifest_digest TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        confirmation_id TEXT,
                        report_json TEXT,
                        subset_json TEXT,
                        artifact_json TEXT
                    )
                    """
                )
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(source_manifest)")
                }
                for column in ("subset_json", "artifact_json"):
                    if column not in columns:
                        connection.execute(
                            f"ALTER TABLE source_manifest ADD COLUMN {column} TEXT"
                        )
        except sqlite3.Error as error:
            raise SourceRequalificationFailedClosed(
                "ledger-initialization-failed", "the qualification ledger cannot be initialized"
            ) from error

    def preview_manifest(self, manifest: SourceRequalificationManifest) -> SourceManifestPreview:
        if not isinstance(manifest, SourceRequalificationManifest):
            raise SourceRequalificationRejected(
                "manifest-invalid", "manifest must be a SourceRequalificationManifest"
            )
        stored = manifest._stored_dict()
        serialized = _canonical_json(stored)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT manifest_digest FROM source_manifest WHERE manifest_id = ?",
                    (manifest.manifest_id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO source_manifest(manifest_id, manifest_digest, manifest_json) VALUES (?, ?, ?)",
                        (manifest.manifest_id, manifest.manifest_digest, serialized),
                    )
                elif existing[0] != manifest.manifest_digest:
                    raise SourceRequalificationConflict(
                        "manifest-identity-conflict", "manifest identity already names different content"
                    )
        except SourceRequalificationProblem:
            raise
        except sqlite3.Error as error:
            raise SourceRequalificationFailedClosed(
                "manifest-record-failed", "the manifest could not be recorded"
            ) from error
        items = tuple(
            {
                "source_id": item.source_id,
                "expected_sha256": item.expected_sha256,
                "declared_content_type": item.declared_content_type,
                "declared_size_bytes": item.declared_size_bytes,
                "rights_basis": item.rights_basis,
                "declared_use": item.declared_use,
                "rights_confirmed": item.rights_confirmed,
            }
            for item in manifest.items
        )
        return SourceManifestPreview(
            manifest_id=manifest.manifest_id,
            manifest_digest=manifest.manifest_digest,
            item_count=len(items),
            source_text_free_items=items,
        )

    def confirm_manifest(
        self, *, manifest_id: str, manifest_digest: str
    ) -> ManifestConfirmation:
        manifest_id = _canonical_uuid(manifest_id, "manifest_id")
        if not _valid_sha256(manifest_digest):
            raise SourceRequalificationRejected(
                "manifest-digest-invalid", "manifest_digest must be lowercase SHA-256"
            )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT manifest_digest, confirmation_id FROM source_manifest WHERE manifest_id = ?",
                    (manifest_id,),
                ).fetchone()
                if row is None or row[0] != manifest_digest:
                    raise SourceRequalificationRejected(
                        "manifest-confirmation-invalid", "the exact preview is not available for confirmation"
                    )
                confirmation_id = row[1] or _digest(
                    {"manifest_id": manifest_id, "manifest_digest": manifest_digest, "decision": "confirmed"}
                )
                connection.execute(
                    "UPDATE source_manifest SET confirmation_id = ? WHERE manifest_id = ?",
                    (confirmation_id, manifest_id),
                )
        except SourceRequalificationProblem:
            raise
        except sqlite3.Error as error:
            raise SourceRequalificationFailedClosed(
                "manifest-confirmation-record-failed", "the manifest confirmation could not be recorded"
            ) from error
        return ManifestConfirmation(
            manifest_id=manifest_id,
            manifest_digest=manifest_digest,
            confirmation_id=confirmation_id,
        )

    def audit(self, confirmation: ManifestConfirmation) -> SourceAuditReport:
        if not isinstance(confirmation, ManifestConfirmation):
            raise SourceRequalificationRejected(
                "manifest-confirmation-invalid", "audit requires an exact confirmation"
            )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT manifest_digest, manifest_json, confirmation_id, report_json FROM source_manifest WHERE manifest_id = ?",
                    (confirmation.manifest_id,),
                ).fetchone()
                if (
                    row is None
                    or row[0] != confirmation.manifest_digest
                    or row[2] != confirmation.confirmation_id
                ):
                    raise SourceRequalificationRejected(
                        "audit-confirmation-invalid", "audit confirmation does not bind the exact manifest"
                    )
                if row[3] is not None:
                    return self._report_from_dict(json.loads(row[3]))
                manifest = json.loads(row[1])
                self._validate_stored_manifest(
                    manifest,
                    expected_manifest_id=confirmation.manifest_id,
                    expected_manifest_digest=confirmation.manifest_digest,
                )
                results = tuple(self._audit_item(manifest, item) for item in manifest["items"])
                report = self._report_from_results(
                    manifest_id=confirmation.manifest_id,
                    manifest_digest=confirmation.manifest_digest,
                    confirmation_id=confirmation.confirmation_id,
                    results=results,
                )
                if self._audit_hook is not None:
                    self._audit_hook("after-results-before-report-record")
                connection.execute(
                    "UPDATE source_manifest SET report_json = ? WHERE manifest_id = ?",
                    (_canonical_json(self._report_to_dict(report)), confirmation.manifest_id),
                )
                return report
        except SourceRequalificationProblem:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, sqlite3.Error) as error:
            raise SourceRequalificationFailedClosed(
                "source-audit-failed-closed", "the exact listed items could not be audited"
            ) from error

    def confirm_subset(
        self,
        *,
        manifest_id: str,
        report_digest: str,
        selected_source_ids: tuple[str, ...],
    ) -> ConfirmedQualifiedSourceSubset:
        manifest_id = _canonical_uuid(manifest_id, "manifest_id")
        if not _valid_sha256(report_digest):
            raise SourceRequalificationRejected(
                "audit-report-digest-invalid", "report_digest must be lowercase SHA-256"
            )
        selected_source_ids = tuple(_canonical_uuid(value, "selected_source_id") for value in selected_source_ids)
        if not selected_source_ids or len(set(selected_source_ids)) != len(selected_source_ids):
            raise SourceRequalificationRejected(
                "subset-selection-invalid", "subset must contain unique passed source identities"
            )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT report_json, subset_json FROM source_manifest WHERE manifest_id = ?",
                    (manifest_id,),
                ).fetchone()
                if row is None or row[0] is None:
                    raise SourceRequalificationRejected(
                        "subset-report-unavailable", "an exact audit report is required"
                    )
                report = self._report_from_dict(json.loads(row[0]))
                if report.report_digest != report_digest:
                    raise SourceRequalificationRejected(
                        "subset-report-mismatch", "subset confirmation must bind the exact audit report"
                    )
                if not set(selected_source_ids).issubset(set(report.passed_source_ids)):
                    raise SourceRequalificationRejected(
                        "subset-selection-invalid", "failed or unreviewed items cannot enter the subset"
                    )
                expected = self._subset_from_values(
                    manifest_id=manifest_id,
                    report_digest=report_digest,
                    source_ids=tuple(sorted(selected_source_ids)),
                )
                if row[1] is None:
                    connection.execute(
                        "UPDATE source_manifest SET subset_json = ? WHERE manifest_id = ?",
                        (_canonical_json(self._subset_to_dict(expected)), manifest_id),
                    )
                    return expected
                stored = self._subset_from_dict(json.loads(row[1]))
                if stored != expected:
                    raise SourceRequalificationConflict(
                        "subset-confirmation-conflict", "second confirmation is immutable"
                    )
                return stored
        except SourceRequalificationProblem:
            raise
        except (sqlite3.Error, UnicodeError, json.JSONDecodeError) as error:
            raise SourceRequalificationFailedClosed(
                "subset-confirmation-failed", "the second confirmation could not be recorded"
            ) from error

    def preview_unpublished_artifact(
        self, subset: ConfirmedQualifiedSourceSubset
    ) -> UnpublishedArtifactPreview:
        if not isinstance(subset, ConfirmedQualifiedSourceSubset):
            raise SourceRequalificationRejected(
                "artifact-subset-invalid", "artifact preview requires an exact confirmed subset"
            )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT subset_json, artifact_json FROM source_manifest WHERE manifest_id = ?",
                    (subset.manifest_id,),
                ).fetchone()
                if row is None or row[0] is None:
                    raise SourceRequalificationRejected(
                        "artifact-subset-unavailable", "the confirmed subset is not available"
                    )
                stored_subset = self._subset_from_dict(json.loads(row[0]))
                if stored_subset != subset:
                    raise SourceRequalificationRejected(
                        "artifact-subset-mismatch", "artifact preview must bind the exact second confirmation"
                    )
                expected = UnpublishedArtifactPreview(
                    artifact_id=str(uuid5(NAMESPACE_URL, "post-m0-unpublished-artifact:" + subset.subset_digest)),
                    source_provenance_digest=subset.subset_digest,
                    published=False,
                    authority_state={
                        "qualified_runtime_input": 0,
                        "runtime_binding": 0,
                        "runtime_timeline": 0,
                        "operation": 0,
                        "timeline_outcome": 0,
                        "physical_clear": 0,
                    },
                )
                if row[1] is None:
                    connection.execute(
                        "UPDATE source_manifest SET artifact_json = ? WHERE manifest_id = ?",
                        (_canonical_json(expected.__dict__), subset.manifest_id),
                    )
                    return expected
                stored = self._artifact_from_dict(json.loads(row[1]))
                if stored != expected:
                    raise SourceRequalificationFailedClosed(
                        "artifact-record-tampered",
                        "stored artifact does not match confirmed provenance",
                    )
                return stored
        except SourceRequalificationProblem:
            raise
        except (sqlite3.Error, UnicodeError, json.JSONDecodeError) as error:
            raise SourceRequalificationFailedClosed(
                "artifact-preview-failed-closed", "the unpublished artifact preview could not be recorded"
            ) from error

    @staticmethod
    def _validate_stored_manifest(
        payload: dict[str, Any],
        *,
        expected_manifest_id: str,
        expected_manifest_digest: str,
    ) -> None:
        try:
            calculated_digest = _digest(
                {
                    "version": payload["version"],
                    "manifest_id": payload["manifest_id"],
                    "selection_root": payload["selection_root"],
                    "items": payload["items"],
                }
            )
            matches = (
                payload["version"] == _MANIFEST_VERSION
                and payload["manifest_id"] == expected_manifest_id
                and payload["manifest_digest"] == expected_manifest_digest
                and calculated_digest == expected_manifest_digest
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SourceRequalificationFailedClosed(
                "manifest-record-tampered", "stored manifest has an invalid exact identity"
            ) from error
        if not matches:
            raise SourceRequalificationFailedClosed(
                "manifest-record-tampered", "stored manifest does not match confirmed content"
            )

    @staticmethod
    def _audit_item(manifest: dict[str, Any], item: dict[str, Any]) -> SourceAuditResult:
        source_id = str(item["source_id"])
        if not item["rights_confirmed"]:
            return SourceAuditResult(source_id, "failed", "rights-unconfirmed")
        root = Path(manifest["selection_root"])
        relative = Path(item["relative_path"])
        if not relative.parts or any(part in {".", ".."} for part in relative.parts):
            return SourceAuditResult(source_id, "failed", "source-path-invalid")
        candidate = root / relative
        try:
            _reject_unsafe_path(candidate, "listed_source")
            if _has_link_or_reparse_component(root):
                return SourceAuditResult(source_id, "failed", "source-path-linked")
            if not candidate.exists():
                return SourceAuditResult(source_id, "failed", "source-missing")
            if _has_link_or_reparse_component(candidate):
                return SourceAuditResult(source_id, "failed", "source-path-linked")
            if not candidate.is_file():
                return SourceAuditResult(source_id, "failed", "source-path-not-file")
            payload = candidate.read_bytes()
        except SourceRequalificationProblem:
            return SourceAuditResult(source_id, "failed", "source-path-unreadable")
        except OSError:
            return SourceAuditResult(source_id, "failed", "source-unreadable")
        if len(payload) != item["declared_size_bytes"]:
            return SourceAuditResult(source_id, "failed", "source-size-changed")
        if _sha256(payload) != item["expected_sha256"]:
            return SourceAuditResult(source_id, "failed", "source-hash-changed")
        return SourceAuditResult(source_id, "passed", "source-qualified")

    @staticmethod
    def _report_from_results(
        *,
        manifest_id: str,
        manifest_digest: str,
        confirmation_id: str,
        results: tuple[SourceAuditResult, ...],
    ) -> SourceAuditReport:
        digest = _digest(
            {
                "manifest_id": manifest_id,
                "manifest_digest": manifest_digest,
                "confirmation_id": confirmation_id,
                "results": [result.__dict__ for result in results],
            }
        )
        return SourceAuditReport(
            manifest_id=manifest_id,
            manifest_digest=manifest_digest,
            confirmation_id=confirmation_id,
            results=results,
            report_digest=digest,
            unpublished=True,
            runtime_authority_count=0,
        )

    @staticmethod
    def _report_to_dict(report: SourceAuditReport) -> dict[str, Any]:
        return {
            "manifest_id": report.manifest_id,
            "manifest_digest": report.manifest_digest,
            "confirmation_id": report.confirmation_id,
            "results": [result.__dict__ for result in report.results],
            "report_digest": report.report_digest,
        }

    @staticmethod
    def _report_from_dict(payload: dict[str, Any]) -> SourceAuditReport:
        results = tuple(
            SourceAuditResult(
                source_id=str(item["source_id"]),
                status=str(item["status"]),
                code=str(item["code"]),
            )
            for item in payload["results"]
        )
        report = SourceRequalificationSession._report_from_results(
            manifest_id=str(payload["manifest_id"]),
            manifest_digest=str(payload["manifest_digest"]),
            confirmation_id=str(payload["confirmation_id"]),
            results=results,
        )
        if report.report_digest != payload["report_digest"]:
            raise SourceRequalificationFailedClosed(
                "audit-report-tampered", "stored audit report digest does not match"
            )
        return report

    @staticmethod
    def _subset_from_values(
        *, manifest_id: str,
        report_digest: str,
        source_ids: tuple[str, ...],
    ) -> ConfirmedQualifiedSourceSubset:
        confirmation_id = _digest(
            {
                "manifest_id": manifest_id,
                "report_digest": report_digest,
                "source_ids": list(source_ids),
                "decision": "confirmed",
            }
        )
        subset_digest = _digest(
            {
                "manifest_id": manifest_id,
                "report_digest": report_digest,
                "source_ids": list(source_ids),
                "confirmation_id": confirmation_id,
            }
        )
        return ConfirmedQualifiedSourceSubset(
            manifest_id=manifest_id,
            report_digest=report_digest,
            source_ids=source_ids,
            confirmation_id=confirmation_id,
            subset_digest=subset_digest,
        )

    @staticmethod
    def _subset_to_dict(subset: ConfirmedQualifiedSourceSubset) -> dict[str, Any]:
        return {
            "manifest_id": subset.manifest_id,
            "report_digest": subset.report_digest,
            "source_ids": list(subset.source_ids),
            "confirmation_id": subset.confirmation_id,
            "subset_digest": subset.subset_digest,
        }

    @staticmethod
    def _subset_from_dict(payload: dict[str, Any]) -> ConfirmedQualifiedSourceSubset:
        subset = SourceRequalificationSession._subset_from_values(
            manifest_id=str(payload["manifest_id"]),
            report_digest=str(payload["report_digest"]),
            source_ids=tuple(str(value) for value in payload["source_ids"]),
        )
        if (
            subset.confirmation_id != payload["confirmation_id"]
            or subset.subset_digest != payload["subset_digest"]
        ):
            raise SourceRequalificationFailedClosed(
                "subset-record-tampered", "stored subset confirmation does not match"
            )
        return subset

    @staticmethod
    def _artifact_from_dict(payload: dict[str, Any]) -> UnpublishedArtifactPreview:
        return UnpublishedArtifactPreview(
            artifact_id=str(payload["artifact_id"]),
            source_provenance_digest=str(payload["source_provenance_digest"]),
            published=bool(payload["published"]),
            authority_state={str(key): int(value) for key, value in payload["authority_state"].items()},
        )


__all__ = [
    "ManifestConfirmation",
    "ConfirmedQualifiedSourceSubset",
    "SourceAuditReport",
    "SourceAuditResult",
    "SourceManifestItem",
    "SourceManifestPreview",
    "SourceRequalificationConflict",
    "SourceRequalificationFailedClosed",
    "SourceRequalificationManifest",
    "SourceRequalificationProblem",
    "SourceRequalificationRejected",
    "SourceRequalificationSession",
    "UnpublishedArtifactPreview",
]

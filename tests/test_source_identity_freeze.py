from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.credentials import (
    DEEPSEEK_CREDENTIAL_SLOT,
    DeepSeekCredentialVerifier,
    InMemoryCredentialStore,
)
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
from dynamic_subject_agent.host import RuntimeHostProblem
from dynamic_subject_agent.source_character_authoring import (
    LocalIdentitySelectRequest,
    LocalIdentityStatus,
    SourceDraftCandidate,
    SourceDraftCommand,
    SourceDraftSaveRequest,
    SourceDraftStatus,
    SourceFreezeMappingRequest,
    SourceIdentityFreezeRequest,
    SourceIdentityFreezeStatus,
)
from dynamic_subject_agent.studio import PolicyKernel, StudioRootRef, SubjectStudio


def _config(tmp_path: Path) -> LocalProductConfig:
    root = tmp_path / "DynamicSubjectAgent"
    return LocalProductConfig(
        product_parent=root / "m0" / "experiments",
        state_path=root / "state.json",
        relationship_mode="dynamic",
    )


def _save_request() -> SourceDraftSaveRequest:
    source_text = (
        "Avery 是临河社区刊物《灯笼》的编辑。"
        "她在编辑工作中习惯先核对来源再回答。"
        "Avery 说话简洁，不确定时会直接说‘资料里没有写，我不知道’。"
        "《灯笼》每周五 17:00 截单；"
        "正式付印前必须由编辑和印刷厂共同确认一张配色样张。"
    )
    return SourceDraftSaveRequest(
        source_title="Avery 原创人物简报",
        source_text=source_text,
        candidates=(
            SourceDraftCandidate(
                "genesis",
                "identity",
                None,
                "Avery 是临河社区刊物《灯笼》的编辑。",
                "Avery 是临河社区刊物《灯笼》的编辑。",
                True,
            ),
            SourceDraftCandidate(
                "genesis",
                "trait",
                None,
                "Avery 在编辑工作中习惯先核对来源再回答。",
                "她在编辑工作中习惯先核对来源再回答。",
                True,
            ),
            SourceDraftCandidate(
                "genesis",
                "voice",
                None,
                "Avery 说话简洁，不确定时会直接说‘资料里没有写，我不知道’。",
                "Avery 说话简洁，不确定时会直接说‘资料里没有写，我不知道’。",
                True,
            ),
            SourceDraftCandidate(
                "knowledge",
                None,
                "《灯笼》截单时间",
                "《灯笼》每周五 17:00 截单。",
                "《灯笼》每周五 17:00 截单；",
                True,
            ),
            SourceDraftCandidate(
                "knowledge",
                None,
                "付印前确认流程",
                "正式付印前必须由编辑和印刷厂共同确认一张配色样张。",
                "正式付印前必须由编辑和印刷厂共同确认一张配色样张。",
                True,
            ),
        ),
        local_save_confirmed=True,
        base_revision=0,
    )


def _revised_save_request() -> SourceDraftSaveRequest:
    original = _save_request()
    return SourceDraftSaveRequest(
        source_title=original.source_title,
        source_text=original.source_text,
        candidates=tuple(
            replace(candidate, selected=False)
            if candidate.category == "knowledge" and candidate.title == "付印前确认流程"
            else candidate
            for candidate in original.candidates
        ),
        local_save_confirmed=True,
        base_revision=1,
    )


def test_exact_source_basis_freezes_once_without_replacing_legacy_identity(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    legacy_profile_id = product.profile_id
    legacy_timeline_id = product.timeline_id
    try:
        saved = product.application.source_draft(
            SourceDraftCommand.save(_save_request())
        )
        assert saved.status is SourceDraftStatus.AVAILABLE
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        request = SourceIdentityFreezeRequest(
            expected_revision=1,
            display_name="Avery",
            freeze_basis_digest=mapping.view.freeze_basis_digest,
            confirmed=True,
        )
        created = product.application.freeze_source_identity(request)
        replayed = product.application.freeze_source_identity(request)
        tampered = product.application.freeze_source_identity(
            SourceIdentityFreezeRequest(1, "Avery", "0" * 64, True)
        )
        identities = product.application.local_identities()
        selected = product.application.select_local_identity(
            LocalIdentitySelectRequest(created.view.identity_id, True)
        )
    finally:
        product.close()

    assert created.status is SourceIdentityFreezeStatus.CREATED
    assert created.view is not None
    assert created.view.knowledge_member_count == 2
    assert created.view.active is False
    assert replayed.status is SourceIdentityFreezeStatus.REPLAYED
    assert replayed.view == created.view
    assert tampered.status is SourceIdentityFreezeStatus.CONFLICT
    assert identities.status is LocalIdentityStatus.AVAILABLE
    assert len(identities.identities) == 2
    assert selected.status is LocalIdentityStatus.SELECTED

    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert state["active_identity_id"] == created.view.identity_id
    assert len(state["identities"]) == 2
    assert state["identities"][0]["timeline_id"] == legacy_timeline_id
    sealed = state["identities"][1]
    assert sealed["identity_id"] == created.view.identity_id
    assert sealed["host_location"] is not None
    assert sealed["timeline_id"] is not None
    studio = SubjectStudio.open(
        StudioRootRef.from_dict(sealed["studio_location"]),
        policy_kernel=PolicyKernel(),
    )
    try:
        qri = studio.query_qri(publication_key=sealed["publication_key"])
        snapshot = studio.query_snapshot(qri.genesis_snapshot_id)
        entries = studio.knowledge_entries(qri.knowledge_snapshot_id)
    finally:
        studio.close()
    assert snapshot.source_freeze_basis_digest == mapping.view.freeze_basis_digest
    assert [entry.title for entry in entries] == [
        "《灯笼》截单时间",
        "付印前确认流程",
    ]
    assert all(entry.source_ref.startswith("source-freeze:") for entry in entries)

    reopened = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        assert reopened.profile_id == created.view.identity_id
        assert reopened.timeline_id != legacy_timeline_id
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            KnowledgeApplicationProjection,
        )

        knowledge = reopened.application.query(
            ApplicationQuery(
                ApplicationQueryKind.KNOWLEDGE,
                reopened.profile_id,
                reopened.timeline_id,
            )
        )
        assert isinstance(knowledge.projection, KnowledgeApplicationProjection)
        assert [entry.title for entry in knowledge.projection.entries] == [
            "《灯笼》截单时间",
            "付印前确认流程",
        ]
        after_start_replay = reopened.application.freeze_source_identity(request)
        assert after_start_replay.status is SourceIdentityFreezeStatus.REPLAYED
        draft = reopened.application.source_draft(SourceDraftCommand.query())
        assert draft.status is SourceDraftStatus.AVAILABLE
        assert draft.view is not None and draft.view.revision == 1
        restored = reopened.application.select_local_identity(
            LocalIdentitySelectRequest(legacy_profile_id, True)
        )
        assert restored.status is LocalIdentityStatus.SELECTED
    finally:
        reopened.close()

    legacy = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        assert legacy.profile_id == legacy_profile_id
        assert legacy.timeline_id == legacy_timeline_id
    finally:
        legacy.close()


def test_registry_interruption_recovers_same_sealed_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.local_identity_authority as local_identity_authority

    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        product.application.source_draft(SourceDraftCommand.save(_save_request()))
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        request = SourceIdentityFreezeRequest(
            1,
            "Avery",
            mapping.view.freeze_basis_digest,
            True,
        )
        real_write = local_identity_authority._write_state

        def interrupted_write(path, payload):
            del path, payload
            raise OSError("fault after QRI publication")

        monkeypatch.setattr(
            local_identity_authority,
            "_write_state",
            interrupted_write,
        )
        interrupted = product.application.freeze_source_identity(request)
        monkeypatch.setattr(local_identity_authority, "_write_state", real_write)
        recovered = product.application.freeze_source_identity(request)
    finally:
        product.close()

    assert interrupted.status is SourceIdentityFreezeStatus.FAILED_CLOSED
    assert recovered.status is SourceIdentityFreezeStatus.REPLAYED
    assert recovered.view is not None
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert len(state["identities"]) == 2


def test_knowledge_member_tamper_fails_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        product.application.source_draft(SourceDraftCommand.save(_save_request()))
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        frozen = product.application.freeze_source_identity(
            SourceIdentityFreezeRequest(
                1,
                "Avery",
                mapping.view.freeze_basis_digest,
                True,
            )
        )
        assert frozen.view is not None
    finally:
        product.close()
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    sealed = state["identities"][1]
    location = StudioRootRef.from_dict(sealed["studio_location"])
    connection = sqlite3.connect(location.profile_database, autocommit=True)
    try:
        connection.execute(
            "UPDATE knowledge_snapshot_member SET content = 'tampered' WHERE ordinal = 0"
        )
    finally:
        connection.close()
    studio = SubjectStudio.open(location, policy_kernel=PolicyKernel())
    try:
        qri = studio.query_qri(publication_key=sealed["publication_key"])
        try:
            studio.knowledge_entries(qri.knowledge_snapshot_id)
        except Exception as error:
            assert getattr(error, "code", None) == "knowledge-snapshot-integrity-failed"
        else:
            raise AssertionError("tampered Knowledge member must fail closed")
    finally:
        studio.close()


def test_source_identity_with_no_selected_knowledge_does_not_inherit_legacy_fixture(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    save = _save_request()
    genesis_only = SourceDraftSaveRequest(
        source_title=save.source_title,
        source_text=save.source_text,
        candidates=tuple(
            candidate
            for candidate in save.candidates
            if candidate.category == "genesis"
        ),
        local_save_confirmed=True,
        base_revision=0,
    )
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        product.application.source_draft(SourceDraftCommand.save(genesis_only))
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        frozen = product.application.freeze_source_identity(
            SourceIdentityFreezeRequest(
                1,
                "Avery",
                mapping.view.freeze_basis_digest,
                True,
            )
        )
        assert frozen.view is not None
        product.application.select_local_identity(
            LocalIdentitySelectRequest(frozen.view.identity_id, True)
        )
    finally:
        product.close()
    reopened = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        assert reopened.profile_id == frozen.view.identity_id
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            KnowledgeApplicationProjection,
        )

        knowledge = reopened.application.query(
            ApplicationQuery(
                ApplicationQueryKind.KNOWLEDGE,
                reopened.profile_id,
                reopened.timeline_id,
            )
        )
        assert isinstance(knowledge.projection, KnowledgeApplicationProjection)
        assert knowledge.projection.entries == ()
    finally:
        reopened.close()


def test_frozen_basis_replays_after_source_draft_revision_and_delete(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        product.application.source_draft(SourceDraftCommand.save(_save_request()))
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        request = SourceIdentityFreezeRequest(
            1,
            "Avery",
            mapping.view.freeze_basis_digest,
            True,
        )
        created = product.application.freeze_source_identity(request)
        assert created.status is SourceIdentityFreezeStatus.CREATED
        revised = product.application.source_draft(
            SourceDraftCommand.save(_revised_save_request())
        )
        after_revision = product.application.freeze_source_identity(request)
        deleted = product.application.source_draft(
            SourceDraftCommand.delete(confirmed=True)
        )
        after_delete = product.application.freeze_source_identity(request)
    finally:
        product.close()
    assert revised.view is not None and revised.view.revision == 2
    assert after_revision.status is SourceIdentityFreezeStatus.REPLAYED
    assert deleted.status is SourceDraftStatus.DELETED
    assert after_delete.status is SourceIdentityFreezeStatus.REPLAYED
    assert after_delete.view == created.view


def test_source_revision_cannot_commit_during_locked_freeze_publisher(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        product.application.source_draft(SourceDraftCommand.save(_save_request()))
    finally:
        product.close()
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    location = StudioRootRef.from_dict(state["studio_location"])
    entered = Event()
    release = Event()

    def hold_mapping():
        studio = SubjectStudio.open(location, policy_kernel=PolicyKernel())
        try:
            return studio.execute_locked_source_freeze(
                SourceFreezeMappingRequest(1, "Avery"),
                lambda _mapping: (entered.set(), release.wait(5), "published")[2],
            )
        finally:
            studio.close()

    def revise():
        studio = SubjectStudio.open(location, policy_kernel=PolicyKernel())
        try:
            return studio.source_draft(
                SourceDraftCommand.save(_revised_save_request())
            )
        finally:
            studio.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        freeze_future = executor.submit(hold_mapping)
        assert entered.wait(2)
        revise_future = executor.submit(revise)
        assert not revise_future.done()
        release.set()
        assert freeze_future.result(timeout=5) == "published"
        revised = revise_future.result(timeout=5)
    assert revised.status is SourceDraftStatus.AVAILABLE
    assert revised.view is not None and revised.view.revision == 2


def test_registry_identity_label_tamper_fails_closed_on_open(tmp_path: Path) -> None:
    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        product.application.source_draft(SourceDraftCommand.save(_save_request()))
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        frozen = product.application.freeze_source_identity(
            SourceIdentityFreezeRequest(
                1,
                "Avery",
                mapping.view.freeze_basis_digest,
                True,
            )
        )
        assert frozen.view is not None
        product.application.select_local_identity(
            LocalIdentitySelectRequest(frozen.view.identity_id, True)
        )
    finally:
        product.close()
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    state["identities"][1]["display_name"] = "tampered label"
    config.state_path.write_text(json.dumps(state), encoding="utf-8")
    try:
        open_local_product(config, cognition=DormantDeepSeekCognition())
    except RuntimeError as error:
        assert str(error) == "local-identity-authority-mismatch"
    else:
        raise AssertionError("tampered active identity must fail closed")


@pytest.mark.parametrize("tamper", ["host", "timeline"])
def test_registry_host_or_timeline_tamper_fails_closed_before_open(
    tmp_path: Path,
    tamper: str,
) -> None:
    config = _config(tmp_path)
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        product.application.source_draft(SourceDraftCommand.save(_save_request()))
        mapping = product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(1, "Avery")
        )
        assert mapping.view is not None
        frozen = product.application.freeze_source_identity(
            SourceIdentityFreezeRequest(
                1,
                "Avery",
                mapping.view.freeze_basis_digest,
                True,
            )
        )
        assert frozen.view is not None
        product.application.select_local_identity(
            LocalIdentitySelectRequest(frozen.view.identity_id, True)
        )
    finally:
        product.close()
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    source = state["identities"][1]
    if tamper == "host":
        source["host_location"] = state["identities"][0]["host_location"]
    else:
        source["timeline_id"] = str(uuid4())
    config.state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises((RuntimeError, RuntimeHostProblem)):
        open_local_product(config, cognition=DormantDeepSeekCognition())


def test_deepseek_open_loads_one_identity_authority_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.local_product as local_product
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority

    config = _config(tmp_path)
    original = LocalIdentityAuthority.load_active
    calls = 0

    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(LocalIdentityAuthority, "load_active", counted)
    product = local_product.open_deepseek_local_product(config, api_key="test-key")
    try:
        assert calls == 1
    finally:
        product.close()


def test_desktop_lifecycle_failure_rolls_back_active_identity(tmp_path: Path) -> None:
    from app.desktop.server import DesktopState

    config = _config(tmp_path)
    store = InMemoryCredentialStore()
    store.save(DEEPSEEK_CREDENTIAL_SLOT, "configured-key")
    calls = 0

    def factory(_key: str):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("injected composition failure")
        return open_local_product(config, cognition=DormantDeepSeekCognition())

    desktop = DesktopState(
        credential_store=store,
        credential_slot=DEEPSEEK_CREDENTIAL_SLOT,
        verifier=DeepSeekCredentialVerifier(),
        product_factory=factory,
    )
    try:
        initial = desktop.local_identities()
        current_id = next(
            item["identity_id"]
            for item in initial["identities"]
            if item["active"]
        )
        same = desktop.select_local_identity(
            {"identity_id": current_id, "confirmed": True}
        )
        assert same["ok"] and calls == 1
        save = _save_request()
        saved = desktop.source_draft(
            "save",
            {
                "source_title": save.source_title,
                "source_text": save.source_text,
                "candidates": [
                    {
                        "category": item.category,
                        "kind": item.kind,
                        "title": item.title,
                        "content": item.content,
                        "evidence_quote": item.evidence_quote,
                        "selected": item.selected,
                    }
                    for item in save.candidates
                ],
                "local_save_confirmed": True,
                "base_revision": 0,
            },
        )
        assert saved["ok"]
        mapping = desktop.preview_source_freeze_mapping(
            {"expected_revision": 1, "display_name": "Avery"}
        )
        frozen = desktop.freeze_source_identity(
            {
                "expected_revision": 1,
                "display_name": "Avery",
                "freeze_basis_digest": mapping["view"]["freeze_basis_digest"],
                "confirmed": True,
            }
        )
        before = desktop.local_identities()
        legacy_id = next(
            item["identity_id"] for item in before["identities"] if item["active"]
        )
        failed = desktop.select_local_identity(
            {"identity_id": frozen["view"]["identity_id"], "confirmed": True}
        )
        after = desktop.local_identities()
    finally:
        desktop.close()
    assert failed == {
        "ok": False,
        "status": "failed-closed",
        "problem": "local-identity-open-failed",
    }
    assert after["ok"], after
    assert next(
        item["identity_id"] for item in after["identities"] if item["active"]
    ) == legacy_id

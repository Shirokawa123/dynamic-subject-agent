"""Loopback HTTP Adapter over the local product ApplicationFacade."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from collections.abc import Callable
from time import time_ns
from uuid import uuid4

from dynamic_subject_agent.credentials import (
    CredentialStore,
    CredentialSlot,
    CredentialStoreUnavailable,
    CredentialVerificationStatus,
    DeepSeekCredentialVerifier,
    DEEPSEEK_CREDENTIAL_SLOT,
    WindowsCredentialStore,
)
from dynamic_subject_agent.local_product import (
    LocalProductConfig,
    OpenedLocalProduct,
    open_deepseek_local_product,
)
from dynamic_subject_agent.source_character_authoring import (
    LocalIdentitySelectRequest,
    LocalIdentityStatus,
    SourceDraftCandidate,
    SourceDraftCommand,
    SourceDraftSaveRequest,
    SourceDraftStatus,
    SourceFreezeMappingRequest,
    SourceFreezeMappingStatus,
    SourceIdentityFreezeRequest,
    SourceIdentityFreezeStatus,
    SourcePreviewStatus,
    TextSourcePreviewRequest,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEFAULT_CONFIG = LocalProductConfig.default()
STATE_PATH = _DEFAULT_CONFIG.state_path
PERSISTENT_PARENT = _DEFAULT_CONFIG.product_parent

_POSTURE_LABELS = {
    "focused": "专注",
    "gentle": "温和",
    "cautious": "谨慎",
}
_BASELINE_LABELS = {
    "settled": "平稳",
    "concerned": "关切",
    "encouraged": "受到鼓舞",
}
_SIGNAL_LABELS = {
    "concern": "担忧",
    "encouragement": "鼓舞",
    "settling": "趋于平稳",
}


def _explanation(capability: str, kind: str, message: str) -> dict[str, str]:
    return {"capability": capability, "kind": kind, "message": message}


def _turn_explanations(projection: object, *, new_memory_content: str | None) -> list[dict[str, str]]:
    explanations: list[dict[str, str]] = []
    memory_status = getattr(projection, "living_memory_status", None)
    recalled = tuple(getattr(projection, "living_memory_recalled_ids", ()))
    if memory_status == "accepted":
        detail = (
            f"已形成新记录：「{new_memory_content}」"
            if new_memory_content
            else "已形成一条新记录。"
        )
        explanations.append(_explanation("记忆", "changed", detail))
    elif recalled:
        explanations.append(
            _explanation("记忆", "used", f"本轮召回了 {len(recalled)} 条既有记忆。")
        )
    elif memory_status == "rejected":
        explanations.append(
            _explanation("记忆", "kept", "候选内容没有通过证据规则，现有记忆保持不变。")
        )
    elif memory_status == "failed-closed":
        explanations.append(
            _explanation("记忆", "failed", "本轮记忆处理未能完成；其他能力仍可正常提交。")
        )

    if getattr(projection, "knowledge_status", None) == "failed-closed":
        explanations.append(
            _explanation("知识", "failed", "本轮知识处理未能完成；没有把不确定内容当作来源。")
        )

    relationship_status = getattr(projection, "relationship_status", None)
    relationship_candidate = getattr(projection, "relationship_candidate_event", None)
    if relationship_status == "accepted":
        explanations.append(
            _explanation("关系", "changed", "这次互动形成了一条有证据的关系经历。")
        )
    elif relationship_status == "no-update" and relationship_candidate == "relationship_claim":
        explanations.append(
            _explanation("关系", "kept", "单方面的关系声称不会直接改变关系。")
        )
    elif relationship_status == "rejected":
        explanations.append(
            _explanation("关系", "kept", "关系候选没有通过证据规则，关系保持不变。")
        )
    elif relationship_status == "failed-closed":
        explanations.append(
            _explanation("关系", "failed", "本轮关系处理未能完成；没有写入关系变化。")
        )

    goal_status = getattr(projection, "participant_goal_commitment_status", None)
    goal_action = getattr(projection, "participant_goal_commitment_action", None)
    selected_count = getattr(
        projection,
        "participant_goal_commitment_selected_count",
        0,
    )
    if goal_status == "accepted":
        action_labels = {
            "create": "已记录一项目标或承诺。",
            "revise": "已按明确表述修订一项目标或承诺。",
            "transition": "已按明确报告更新一项目标或承诺的状态。",
        }
        explanations.append(
            _explanation(
                "目标与承诺",
                "changed",
                action_labels.get(goal_action, "目标或承诺记录已更新。"),
            )
        )
    elif goal_status == "no-update" and selected_count:
        explanations.append(
            _explanation(
                "目标与承诺",
                "used",
                f"回答参考了 {selected_count} 条已记录的目标或承诺。",
            )
        )
    elif goal_status == "rejected":
        explanations.append(
            _explanation(
                "目标与承诺",
                "kept",
                "表述没有通过明确证据规则，现有记录保持不变。",
            )
        )
    elif goal_status == "failed-closed":
        explanations.append(
            _explanation(
                "目标与承诺",
                "failed",
                "本轮目标与承诺处理未能完成；其他能力的结果仍然有效。",
            )
        )

    situated_status = getattr(projection, "situated_state_status", None)
    situated_action = getattr(projection, "situated_state_action", None)
    situated_reason = getattr(projection, "situated_state_reason_code", None)
    posture = getattr(projection, "situated_state_posture", None)
    posture_label = _POSTURE_LABELS.get(posture, posture or "中性")
    if situated_status == "accepted" and situated_action == "set":
        explanations.append(
            _explanation(
                "当前姿态",
                "changed",
                f"本轮进入“{posture_label}”姿态；30 分钟内还会延续一轮。",
            )
        )
    elif situated_status == "accepted" and situated_action == "carry":
        explanations.append(
            _explanation(
                "当前姿态",
                "used",
                f"本轮沿用了“{posture_label}”姿态；本轮结束后回到中性。",
            )
        )
    elif situated_action == "consume":
        explanations.append(
            _explanation("当前姿态", "changed", "上一轮短时姿态已经用完，现已回到中性。")
        )
    elif situated_status == "rejected":
        explanations.append(
            _explanation(
                "当前姿态",
                "kept",
                (
                    "直接命令不能作为状态证据，当前姿态保持不变。"
                    if situated_reason == "direct_command_not_evidence"
                    else "表述不足以改变短时姿态，当前姿态保持不变。"
                ),
            )
        )
    elif situated_status == "failed-closed":
        explanations.append(
            _explanation("当前姿态", "failed", "本轮短时姿态处理未能完成；没有写入新姿态。")
        )

    medium_status = getattr(projection, "medium_state_status", None)
    medium_reason = getattr(projection, "medium_state_reason_code", None)
    medium_signal = getattr(projection, "medium_state_signal", None)
    before = getattr(projection, "medium_state_before_baseline", None)
    after = getattr(projection, "medium_state_baseline", None)
    after_label = _BASELINE_LABELS.get(after, after or "平稳")
    if medium_status == "accepted":
        before_label = _BASELINE_LABELS.get(before, before or "平稳")
        explanations.append(
            _explanation(
                "中期基线",
                "changed",
                f"独立证据达到门槛，基线从“{before_label}”变为“{after_label}”。",
            )
        )
    elif medium_status == "rejected" and medium_reason == "insufficient_independent_evidence":
        signal_label = _SIGNAL_LABELS.get(medium_signal, "状态")
        explanations.append(
            _explanation(
                "中期基线",
                "kept",
                f"记录到一条“{signal_label}”证据；独立证据尚不足，基线保持“{after_label}”。",
            )
        )
    elif medium_status == "rejected":
        explanations.append(
            _explanation(
                "中期基线",
                "kept",
                (
                    f"直接命令不能作为中期状态证据，基线保持“{after_label}”。"
                    if medium_reason == "direct_subject_state_command"
                    else f"状态候选未通过规则，基线保持“{after_label}”。"
                ),
            )
        )
    elif medium_status == "failed-closed":
        explanations.append(
            _explanation("中期基线", "failed", "本轮中期状态处理未能完成；既有基线保持不变。")
        )
    return explanations


def build_product(
    api_key: str,
    relationship_mode: str = "dynamic",
) -> OpenedLocalProduct:
    config = LocalProductConfig(
        product_parent=PERSISTENT_PARENT,
        state_path=STATE_PATH,
        relationship_mode=relationship_mode,
    )
    return open_deepseek_local_product(config, api_key=api_key)


class AppState:
    """Translate HTTP turns into the public application Interface."""

    def __init__(self, product: OpenedLocalProduct) -> None:
        self.product = product

    def _memories(self) -> list[dict]:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            LivingMemoryApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is ApplicationQueryStatus.AVAILABLE
            and isinstance(response.projection, LivingMemoryApplicationProjection)
        ):
            return [
                {
                    "content": memory.content,
                    "status": memory.status,
                    "memory_kind": memory.memory_kind,
                }
                for memory in response.projection.memories
            ]
        return []

    def snapshot(self) -> dict:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            RelationshipApplicationProjection,
        )

        relationship = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.RELATIONSHIP,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        accepted = (
            tuple(
                interaction
                for interaction in relationship.projection.interactions
                if interaction.status == "accepted"
            )
            if (
                relationship.status is ApplicationQueryStatus.AVAILABLE
                and isinstance(
                    relationship.projection,
                    RelationshipApplicationProjection,
                )
            )
            else ()
        )
        identities = self.local_identities()
        active_identity = next(
            (
                item
                for item in identities.get("identities", [])
                if item.get("active")
            ),
            None,
        )
        knowledge_entries = self._knowledge_entries()
        return {
            "profile_id": self.product.profile_id,
            "display_name": (
                active_identity["display_name"] if active_identity else "Avery"
            ),
            "identities": identities.get("identities", []),
            "memories": self._memories(),
            "knowledge_count": len(knowledge_entries),
            "relationship_accepted_count": len(accepted),
            "relationship_latest_event": accepted[0].event if accepted else None,
            "participant_goals": self._participant_goals(),
            "situated_state": self._situated_state(),
            "medium_state": self._medium_state(),
        }

    def _participant_goals(self) -> list[dict]:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            ParticipantGoalCommitmentApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.PARTICIPANT_GOALS,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is ApplicationQueryStatus.AVAILABLE
            and isinstance(
                response.projection,
                ParticipantGoalCommitmentApplicationProjection,
            )
        ):
            return [
                {
                    "kind": record.kind,
                    "terms": record.terms,
                    "status": record.status,
                    "evidence_quote": record.evidence_quote,
                }
                for record in response.projection.records
            ]
        return []

    def _situated_state(self) -> dict | None:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            SituatedStateApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.SITUATED_STATE,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is not ApplicationQueryStatus.AVAILABLE
            or not isinstance(response.projection, SituatedStateApplicationProjection)
            or response.projection.state is None
        ):
            return None
        state = response.projection.state
        expires_in = max(0, (state.expires_at_us - time_ns() // 1_000) // 1_000_000)
        return {
            "posture": state.posture,
            "remaining_turns": state.remaining_turns,
            "expires_in_seconds": int(expires_in),
        }

    def _medium_state(self) -> dict:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            MediumStateApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.MEDIUM_STATE,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is ApplicationQueryStatus.AVAILABLE
            and isinstance(response.projection, MediumStateApplicationProjection)
        ):
            state = response.projection.state
            return {"baseline": state.baseline, "version": state.version}
        return {"baseline": "settled", "version": 0}

    def submit_turn(self, text: str) -> dict:
        from dynamic_subject_agent.timeline import SubjectCommand

        command = SubjectCommand.contribute_utterance(
            target_profile_id=self.product.profile_id,
            target_timeline_id=self.product.timeline_id,
            declared_intent="ask-collaborator-status",
            utterance=text,
            language="zh",
            provenance="project-original",
        )
        submitted = self.product.application.submit(
            command,
            idempotency_key=f"local-product-{uuid4().hex}",
        )
        terminal = self.product.application.wait(
            submitted.operation_ref,
            timeout_seconds=30,
        )
        projection = terminal.projection
        if terminal.status.value != "terminal" or projection is None:
            stage = projection.failure_stage if projection else None
            code = (
                projection.failure_code
                if projection
                else (terminal.problem.code if terminal.problem else "unknown")
            )
            return {"ok": False, "stage": stage, "code": code}
        knowledge_by_id = {
            entry.entry_id: entry for entry in self._knowledge_entries()
        }
        citations = []
        for entry_id in projection.knowledge_citation_ids:
            entry = knowledge_by_id.get(entry_id)
            citations.append(
                {
                    "entry_id": entry_id,
                    "title": entry.title if entry else entry_id,
                    "source": "封存来源" if entry else "",
                }
            )
        new_kind = None
        new_content = None
        if projection.living_memory_status == "accepted":
            memories = self._memories()
            if memories:
                new_kind = memories[0]["memory_kind"]
                new_content = memories[0]["content"]
        return {
            "ok": True,
            "new_memory_kind": new_kind,
            "new_memory_content": new_content,
            "expression": projection.expression_text,
            "living_memory_status": projection.living_memory_status,
            "recalled_ids": list(projection.living_memory_recalled_ids),
            "knowledge_status": projection.knowledge_status,
            "relationship_status": projection.relationship_status,
            "relationship_event": projection.relationship_event,
            "participant_goal_status": (
                projection.participant_goal_commitment_status
            ),
            "participant_goal_action": (
                projection.participant_goal_commitment_action
            ),
            "situated_state_status": projection.situated_state_status,
            "situated_state_action": projection.situated_state_action,
            "situated_state_posture": projection.situated_state_posture,
            "medium_state_status": projection.medium_state_status,
            "medium_state_baseline": projection.medium_state_baseline,
            "citations": citations,
            "explanations": _turn_explanations(
                projection,
                new_memory_content=new_content,
            ),
        }

    def _knowledge_entries(self) -> tuple:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            KnowledgeApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.KNOWLEDGE,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is ApplicationQueryStatus.AVAILABLE
            and isinstance(response.projection, KnowledgeApplicationProjection)
        ):
            return response.projection.entries
        return ()

    def preview_character_source(
        self,
        *,
        source_title: object,
        source_text: object,
        rights_confirmed: object,
        extraction_use_confirmed: object,
    ) -> dict:
        response = self.product.application.preview_character_source(
            TextSourcePreviewRequest(
                source_title=source_title,  # type: ignore[arg-type]
                source_text=source_text,  # type: ignore[arg-type]
                rights_confirmed=rights_confirmed,  # type: ignore[arg-type]
                extraction_use_confirmed=extraction_use_confirmed,  # type: ignore[arg-type]
            )
        )

        def candidate(item) -> dict:
            return {
                "category": item.category,
                "kind": item.kind,
                "title": item.title,
                "content": item.content,
                "evidence_quote": item.evidence_quote,
                "status": item.status,
                "reason_code": item.reason_code,
            }

        return {
            "ok": response.status is SourcePreviewStatus.AVAILABLE,
            "status": response.status.value,
            "problem": response.problem_code,
            "accepted": [candidate(item) for item in response.accepted],
            "rejected": [candidate(item) for item in response.rejected],
        }

    def source_draft(self, action: str, payload: dict | None = None) -> dict:
        if action == "query":
            command = SourceDraftCommand.query()
        elif action == "delete":
            command = SourceDraftCommand.delete(confirmed=True)
        elif action == "save" and isinstance(payload, dict):
            raw_candidates = payload.get("candidates")
            try:
                candidates = tuple(
                    SourceDraftCandidate(**item) for item in raw_candidates
                )
            except (TypeError, ValueError):
                return {
                    "ok": False,
                    "status": "rejected",
                    "problem": "source-draft-candidates-invalid",
                    "view": None,
                    "replayed": False,
                }
            command = SourceDraftCommand.save(
                SourceDraftSaveRequest(
                    source_title=payload.get("source_title"),
                    source_text=payload.get("source_text"),
                    candidates=candidates,
                    local_save_confirmed=payload.get("local_save_confirmed"),
                    base_revision=payload.get("base_revision"),
                )
            )
        else:
            return {
                "ok": False,
                "status": "rejected",
                "problem": "source-draft-command-invalid",
                "view": None,
                "replayed": False,
            }
        response = self.product.application.source_draft(command)
        view = None
        if response.view is not None:
            view = {
                "source_title": response.view.source_title,
                "source_digest": response.view.source_digest,
                "revision": response.view.revision,
                "candidates": [
                    {
                        "category": item.category,
                        "kind": item.kind,
                        "title": item.title,
                        "content": item.content,
                        "evidence_quote": item.evidence_quote,
                        "selected": item.selected,
                    }
                    for item in response.view.candidates
                ],
            }
        return {
            "ok": response.status
            in {
                SourceDraftStatus.AVAILABLE,
                SourceDraftStatus.ABSENT,
                SourceDraftStatus.DELETED,
            },
            "status": response.status.value,
            "problem": response.problem_code,
            "view": view,
            "replayed": response.replayed,
        }

    def preview_source_freeze_mapping(
        self,
        *,
        expected_revision: object,
        display_name: object,
    ) -> dict:
        response = self.product.application.preview_source_freeze_mapping(
            SourceFreezeMappingRequest(
                expected_revision=expected_revision,  # type: ignore[arg-type]
                display_name=display_name,  # type: ignore[arg-type]
            )
        )
        view = None
        if response.view is not None:
            view = {
                "source_title": response.view.source_title,
                "source_digest": response.view.source_digest,
                "draft_revision": response.view.draft_revision,
                "mapping_policy_version": response.view.mapping_policy_version,
                "freeze_basis_digest": response.view.freeze_basis_digest,
                "profile": {
                    "display_name": response.view.profile.display_name,
                    "identity_core": response.view.profile.identity_core,
                },
                "genesis": {
                    "subject_identity": response.view.genesis.subject_identity,
                    "canon_start": response.view.genesis.canon_start,
                    "initial_relationship_premise": (
                        response.view.genesis.initial_relationship_premise
                    ),
                },
                "knowledge_members": [
                    {
                        "title": item.title,
                        "content": item.content,
                        "evidence_quote": item.evidence_quote,
                        "source_digest": item.source_digest,
                    }
                    for item in response.view.knowledge_members
                ],
                "selected_candidates": [
                    {
                        "category": item.category,
                        "kind": item.kind,
                        "title": item.title,
                        "content": item.content,
                        "evidence_quote": item.evidence_quote,
                    }
                    for item in response.view.selected_candidates
                ],
            }
        return {
            "ok": response.status is SourceFreezeMappingStatus.AVAILABLE,
            "status": response.status.value,
            "problem": response.problem_code,
            "view": view,
        }

    def freeze_source_identity(
        self,
        *,
        expected_revision: object,
        display_name: object,
        freeze_basis_digest: object,
        confirmed: object,
    ) -> dict:
        response = self.product.application.freeze_source_identity(
            SourceIdentityFreezeRequest(
                expected_revision=expected_revision,  # type: ignore[arg-type]
                display_name=display_name,  # type: ignore[arg-type]
                freeze_basis_digest=freeze_basis_digest,  # type: ignore[arg-type]
                confirmed=confirmed,  # type: ignore[arg-type]
            )
        )
        return {
            "ok": response.status
            in {SourceIdentityFreezeStatus.CREATED, SourceIdentityFreezeStatus.REPLAYED},
            "status": response.status.value,
            "problem": response.problem_code,
            "view": (
                None
                if response.view is None
                else {
                    "identity_id": response.view.identity_id,
                    "display_name": response.view.display_name,
                    "freeze_basis_digest": response.view.freeze_basis_digest,
                    "knowledge_member_count": response.view.knowledge_member_count,
                    "active": response.view.active,
                }
            ),
        }

    def local_identities(self) -> dict:
        response = self.product.application.local_identities()
        return {
            "ok": response.status is LocalIdentityStatus.AVAILABLE,
            "status": response.status.value,
            "problem": response.problem_code,
            "identities": [
                {
                    "identity_id": item.identity_id,
                    "display_name": item.display_name,
                    "freeze_basis_digest": item.freeze_basis_digest,
                    "active": item.active,
                }
                for item in response.identities
            ],
        }

    def select_local_identity(self, identity_id: object, confirmed: object) -> dict:
        response = self.product.application.select_local_identity(
            LocalIdentitySelectRequest(
                identity_id=identity_id,  # type: ignore[arg-type]
                confirmed=confirmed,  # type: ignore[arg-type]
            )
        )
        return {
            "ok": response.status is LocalIdentityStatus.SELECTED,
            "status": response.status.value,
            "problem": response.problem_code,
        }


class DesktopState:
    """Own credential setup and the optional opened product lifecycle."""

    def __init__(
        self,
        *,
        credential_store: CredentialStore,
        credential_slot: CredentialSlot,
        verifier: DeepSeekCredentialVerifier,
        product_factory: Callable[[str], OpenedLocalProduct] = build_product,
    ) -> None:
        if not isinstance(credential_store, CredentialStore):
            raise TypeError("credential_store must satisfy CredentialStore")
        if not isinstance(verifier, DeepSeekCredentialVerifier):
            raise TypeError("verifier must be DeepSeekCredentialVerifier")
        if not isinstance(credential_slot, CredentialSlot):
            raise TypeError("credential_slot must be CredentialSlot")
        self._credential_store = credential_store
        self._credential_slot = credential_slot
        self._verifier = verifier
        self._product_factory = product_factory
        self._product: OpenedLocalProduct | None = None
        self._app: AppState | None = None
        self._problem: str | None = None
        self._verification = "not-run"
        self._lock = RLock()
        self._open_existing()

    def _open_existing(self) -> None:
        key = ""
        try:
            key = self._credential_store.load(self._credential_slot) or ""
            if key:
                self._replace_product(self._product_factory(key))
        except CredentialStoreUnavailable as error:
            self._problem = error.code
        except Exception:
            self._problem = "product-open-failed"
        finally:
            key = ""

    def _replace_product(self, product: OpenedLocalProduct | None) -> None:
        previous = self._product
        self._product = product
        self._app = None if product is None else AppState(product)
        if previous is not None and previous is not product:
            previous.close()

    def setup_snapshot(self) -> dict:
        with self._lock:
            try:
                configured = self._credential_store.configured(self._credential_slot)
            except CredentialStoreUnavailable as error:
                configured = False
                self._problem = error.code
            return {
                "configured": configured,
                "provider_id": self._credential_slot.provider_id,
                "product_ready": self._app is not None,
                "verification": self._verification,
                "problem": self._problem,
            }

    def save_and_verify(self, api_key: object) -> dict:
        with self._lock:
            try:
                verification = self._verifier.verify(api_key)  # type: ignore[arg-type]
            except CredentialStoreUnavailable as error:
                self._problem = error.code
                return {"ok": False, **self.setup_snapshot()}
            self._verification = verification.value
            if verification is not CredentialVerificationStatus.VALID:
                self._problem = (
                    "credential-invalid"
                    if verification is CredentialVerificationStatus.INVALID
                    else "credential-verification-unavailable"
                )
                return {"ok": False, **self.setup_snapshot()}
            key = str(api_key)
            try:
                self._credential_store.save(self._credential_slot, key)
                self._replace_product(None)
                product = self._product_factory(key)
                self._replace_product(product)
                self._problem = None
            except CredentialStoreUnavailable as error:
                self._problem = error.code
                return {"ok": False, **self.setup_snapshot()}
            except Exception:
                self._problem = "product-open-failed"
                return {"ok": False, **self.setup_snapshot()}
            finally:
                key = ""
            return {"ok": True, **self.setup_snapshot()}

    def delete_credential(self) -> dict:
        with self._lock:
            self._replace_product(None)
            try:
                deleted = self._credential_store.delete(self._credential_slot)
                self._problem = None
                self._verification = "not-run"
            except CredentialStoreUnavailable as error:
                deleted = False
                self._problem = error.code
            return {"ok": self._problem is None, "deleted": deleted, **self.setup_snapshot()}

    def snapshot(self) -> dict:
        with self._lock:
            if self._app is None:
                return {"ok": False, "error": "credential-setup-required"}
            return {"ok": True, **self._app.snapshot()}

    def submit_turn(self, text: str) -> dict:
        with self._lock:
            if self._app is None:
                return {"ok": False, "stage": "credential", "code": "setup-required"}
            return self._app.submit_turn(text)

    def preview_character_source(self, payload: dict) -> dict:
        with self._lock:
            if self._app is None:
                return {
                    "ok": False,
                    "status": "unavailable",
                    "problem": "credential-setup-required",
                    "accepted": [],
                    "rejected": [],
                }
            return self._app.preview_character_source(**payload)

    def source_draft(self, action: str, payload: dict | None = None) -> dict:
        with self._lock:
            if self._app is None:
                return {
                    "ok": False,
                    "status": "unavailable",
                    "problem": "credential-setup-required",
                    "view": None,
                    "replayed": False,
                }
            return self._app.source_draft(action, payload)

    def preview_source_freeze_mapping(self, payload: dict) -> dict:
        with self._lock:
            if self._app is None:
                return {
                    "ok": False,
                    "status": "unavailable",
                    "problem": "credential-setup-required",
                    "view": None,
                }
            return self._app.preview_source_freeze_mapping(**payload)

    def freeze_source_identity(self, payload: dict) -> dict:
        with self._lock:
            if self._app is None:
                return {
                    "ok": False,
                    "status": "unavailable",
                    "problem": "credential-setup-required",
                    "view": None,
                }
            return self._app.freeze_source_identity(**payload)

    def local_identities(self) -> dict:
        with self._lock:
            if self._app is None:
                return {
                    "ok": False,
                    "status": "unavailable",
                    "problem": "credential-setup-required",
                    "identities": [],
                }
            return self._app.local_identities()

    def select_local_identity(self, payload: dict) -> dict:
        with self._lock:
            if self._app is None:
                return {
                    "ok": False,
                    "status": "unavailable",
                    "problem": "credential-setup-required",
                }
            before = self._app.local_identities()
            previous = next(
                (
                    item["identity_id"]
                    for item in before.get("identities", [])
                    if item.get("active")
                ),
                None,
            )
            result = self._app.select_local_identity(
                payload.get("identity_id"),
                payload.get("confirmed"),
            )
            if not result["ok"]:
                return result
            key = ""
            try:
                key = self._credential_store.load(self._credential_slot) or ""
                if not key:
                    raise RuntimeError("credential-unavailable")
                replacement = self._product_factory(key)
                self._replace_product(replacement)
            except Exception:
                rollback_ok = False
                if previous is not None and self._app is not None:
                    rollback = self._app.select_local_identity(previous, True)
                    rollback_ok = bool(rollback.get("ok"))
                if not rollback_ok:
                    self._replace_product(None)
                return {
                    "ok": False,
                    "status": "failed-closed",
                    "problem": "local-identity-open-failed",
                }
            finally:
                key = ""
            return {"ok": True, "status": "selected", **self._app.snapshot()}

    def close(self) -> None:
        with self._lock:
            self._replace_product(None)


def build_handler(state: DesktopState):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: object) -> None:
            self._send(
                status,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _read_json(self, *, maximum: int = 8_192) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > maximum:
                raise ValueError("request-size-invalid")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request-body-invalid")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(
                    200,
                    (STATIC_DIR / "index.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
            elif path == "/api/state":
                payload = state.snapshot()
                self._json(200 if payload.get("ok") else 409, payload)
            elif path == "/api/setup":
                self._json(200, state.setup_snapshot())
            elif path == "/api/authoring/draft":
                payload = state.source_draft("query")
                self._json(200 if payload["ok"] else 422, payload)
            elif path == "/api/identities":
                payload = state.local_identities()
                self._json(200 if payload["ok"] else 422, payload)
            else:
                self._json(404, {"error": "not-found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/credential":
                try:
                    payload = self._read_json(maximum=8_192)
                    api_key = payload.pop("api_key", None)
                    if payload:
                        raise ValueError("unexpected-fields")
                    try:
                        result = state.save_and_verify(api_key)
                    finally:
                        api_key = None
                except (UnicodeError, ValueError, json.JSONDecodeError):
                    self._json(400, {"ok": False, "problem": "invalid-request"})
                    return
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path == "/api/authoring/preview":
                try:
                    payload = self._read_json(maximum=65_536)
                    expected = {
                        "source_title",
                        "source_text",
                        "rights_confirmed",
                        "extraction_use_confirmed",
                    }
                    if set(payload) != expected:
                        raise ValueError("unexpected-fields")
                except (UnicodeError, ValueError, json.JSONDecodeError):
                    self._json(400, {"ok": False, "problem": "invalid-request"})
                    return
                result = state.preview_character_source(payload)
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path == "/api/authoring/draft":
                try:
                    payload = self._read_json(maximum=65_536)
                    expected = {
                        "source_title",
                        "source_text",
                        "candidates",
                        "local_save_confirmed",
                        "base_revision",
                    }
                    if set(payload) != expected:
                        raise ValueError("unexpected-fields")
                except (UnicodeError, ValueError, json.JSONDecodeError):
                    self._json(400, {"ok": False, "problem": "invalid-request"})
                    return
                result = state.source_draft("save", payload)
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path == "/api/authoring/mapping":
                try:
                    payload = self._read_json(maximum=8_192)
                    if set(payload) != {"expected_revision", "display_name"}:
                        raise ValueError("unexpected-fields")
                except (UnicodeError, ValueError, json.JSONDecodeError):
                    self._json(400, {"ok": False, "problem": "invalid-request"})
                    return
                result = state.preview_source_freeze_mapping(payload)
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path == "/api/authoring/freeze":
                try:
                    payload = self._read_json(maximum=8_192)
                    if set(payload) != {
                        "expected_revision",
                        "display_name",
                        "freeze_basis_digest",
                        "confirmed",
                    }:
                        raise ValueError("unexpected-fields")
                except (UnicodeError, ValueError, json.JSONDecodeError):
                    self._json(400, {"ok": False, "problem": "invalid-request"})
                    return
                result = state.freeze_source_identity(payload)
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path == "/api/identities/select":
                try:
                    payload = self._read_json(maximum=8_192)
                    if set(payload) != {"identity_id", "confirmed"}:
                        raise ValueError("unexpected-fields")
                except (UnicodeError, ValueError, json.JSONDecodeError):
                    self._json(400, {"ok": False, "problem": "invalid-request"})
                    return
                result = state.select_local_identity(payload)
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path != "/api/turn":
                self._json(404, {"error": "not-found"})
                return
            try:
                body = self._read_json()
            except (UnicodeError, ValueError, json.JSONDecodeError):
                self._json(400, {"error": "invalid-request"})
                return
            text = str(body.get("text", "")).strip()
            if not text:
                self._json(400, {"error": "empty-text"})
                return
            self._json(200, state.submit_turn(text))

        def do_DELETE(self) -> None:  # noqa: N802
            if self.path == "/api/authoring/draft":
                result = state.source_draft("delete")
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path != "/api/credential":
                self._json(404, {"error": "not-found"})
                return
            self._json(200, state.delete_credential())

        def log_message(self, *args: object) -> None:
            del args

    return Handler


def main() -> int:
    state = DesktopState(
        credential_store=WindowsCredentialStore(),
        credential_slot=DEEPSEEK_CREDENTIAL_SLOT,
        verifier=DeepSeekCredentialVerifier(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state))
    port = server.server_address[1]
    print(f"Avery 已就绪：http://127.0.0.1:{port}（Ctrl+C 退出）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

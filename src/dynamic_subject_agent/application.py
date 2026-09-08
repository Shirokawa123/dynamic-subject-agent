"""The sole fresh-root public application Interface for Mature Runtime M0."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from threading import RLock
from time import time_ns
from collections.abc import Callable
from typing import TypeAlias

from dynamic_subject_agent.host import (
    RuntimeAuthorityBinding,
    RuntimeHealth,
    RuntimeHost,
    RuntimeHostConflict,
    RuntimeHostFailedClosed,
    RuntimeHostProblem,
    RuntimeHostRejected,
    RuntimeRoute,
    _LocalFirstSubmissionAuthorization,
)
from dynamic_subject_agent.runtime import (
    CycleFailedClosed,
    RuntimeInterrupted,
    RuntimeResult,
)
from dynamic_subject_agent.timeline import (
    AdmissionFailedClosed,
    AdmissionProblem,
    ConversationTurnRecord,
    LivingMemoryRecord,
    OperationKind,
    OperationRef,
    OperationState,
    PayloadConflict,
    RelationshipStanceInteraction,
    SubjectCommand,
)
from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentRecord
from dynamic_subject_agent.situated_state import SituatedStateRecord, usable_state
from dynamic_subject_agent.medium_state import MediumStateRecord
from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
from dynamic_subject_agent.temporal_grounding import TemporalGrounding
from dynamic_subject_agent.source_character_authoring import (
    LocalIdentityListResponse,
    LocalIdentitySelectResponse,
    LocalIdentityStatus,
    SourceDraftResponse,
    SourceDraftStatus,
    SourceFreezeMappingResponse,
    SourceFreezeMappingStatus,
    SourceIdentityFreezeResponse,
    SourceIdentityFreezeStatus,
    TextSourceCharacterAuthoring,
    TextSourcePreviewResponse,
)
from dynamic_subject_agent.studio import PolicyKernel, StudioRootRef, SubjectStudio


class ApplicationOperationStatus(str, Enum):
    PENDING = "pending"
    TERMINAL = "terminal"
    INTERRUPTED = "interrupted"
    FAILED_CLOSED = "failed-closed"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"
    NOT_FOUND_OR_NOT_AUTHORIZED = "not-found-or-not-authorized"


ApplicationOperationKind = OperationKind


class ApplicationQueryKind(str, Enum):
    CURRENT = "current"
    RUNTIME = "runtime"
    TIMELINE = "timeline"
    LIVING_MEMORY = "living-memory"
    RELATIONSHIP = "relationship"
    PARTICIPANT_GOALS = "participant-goals"
    SITUATED_STATE = "situated-state"
    MEDIUM_STATE = "medium-state"
    KNOWLEDGE = "knowledge"
    CONVERSATION_HISTORY = "conversation-history"


class ApplicationQueryStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FAILED_CLOSED = "failed-closed"
    NOT_FOUND_OR_NOT_AUTHORIZED = "not-found-or-not-authorized"


class ApplicationHostCommandKind(str, Enum):
    START_LOCAL_SERVING = "start-local-serving"
    STOP_LOCAL_SERVING = "stop-local-serving"


class ApplicationHostStatus(str, Enum):
    SERVING = "serving"
    STOPPED = "stopped"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"
    FAILED_CLOSED = "failed-closed"
    NOT_FOUND_OR_NOT_AUTHORIZED = "not-found-or-not-authorized"


@dataclass(frozen=True)
class ApplicationProblemView:
    code: str


@dataclass(frozen=True)
class ApplicationHostCommand:
    kind: ApplicationHostCommandKind
    target_profile_id: str
    target_timeline_id: str

    @classmethod
    def start_local_serving(
        cls,
        *,
        target_profile_id: str,
        target_timeline_id: str,
    ) -> ApplicationHostCommand:
        return cls(
            kind=ApplicationHostCommandKind.START_LOCAL_SERVING,
            target_profile_id=target_profile_id,
            target_timeline_id=target_timeline_id,
        )

    @classmethod
    def stop_local_serving(
        cls,
        *,
        target_profile_id: str,
        target_timeline_id: str,
    ) -> ApplicationHostCommand:
        return cls(
            kind=ApplicationHostCommandKind.STOP_LOCAL_SERVING,
            target_profile_id=target_profile_id,
            target_timeline_id=target_timeline_id,
        )


@dataclass(frozen=True)
class AuthorizedOperationProjection:
    operation_kind: OperationKind
    operation_state: ApplicationOperationStatus
    timeline_outcome_id: str | None
    timeline_head_sequence: int | None
    expression_text: str | None
    expression_language: str | None
    failure_stage: str | None
    failure_code: str | None
    living_memory_status: str | None = None
    living_memory_recalled_ids: tuple[str, ...] = ()
    memory_withdrawal_status: str | None = None
    knowledge_status: str | None = None
    knowledge_citation_ids: tuple[str, ...] = ()
    relationship_status: str | None = None
    relationship_event: str | None = None
    relationship_candidate_event: str | None = None
    relationship_reason_code: str | None = None
    participant_goal_commitment_status: str | None = None
    participant_goal_commitment_action: str | None = None
    participant_goal_commitment_reason_code: str | None = None
    participant_goal_commitment_selected_count: int = 0
    situated_state_status: str | None = None
    situated_state_action: str | None = None
    situated_state_posture: str | None = None
    situated_state_reason_code: str | None = None
    medium_state_status: str | None = None
    medium_state_baseline: str | None = None
    medium_state_before_baseline: str | None = None
    medium_state_reason_code: str | None = None
    medium_state_signal: str | None = None


@dataclass(frozen=True)
class ApplicationOperationResponse:
    status: ApplicationOperationStatus
    operation_ref: OperationRef | None
    projection: AuthorizedOperationProjection | None
    problem: ApplicationProblemView | None
    replayed: bool = False


@dataclass(frozen=True)
class ApplicationQuery:
    kind: ApplicationQueryKind
    target_profile_id: str
    target_timeline_id: str


@dataclass(frozen=True)
class CurrentApplicationProjection:
    profile_id: str
    timeline_id: str
    binding_id: str
    binding_revision: int
    binding_epoch: int


@dataclass(frozen=True)
class RuntimeApplicationProjection:
    binding_id: str
    lane_id: str | None
    healthy: bool
    serving: bool
    gate_state: str


@dataclass(frozen=True)
class ApplicationHostResponse:
    status: ApplicationHostStatus
    projection: RuntimeApplicationProjection | None
    problem: ApplicationProblemView | None


@dataclass(frozen=True)
class TimelineApplicationProjection:
    timeline_id: str
    head_sequence: int
    published_outcome_digest: str | None
    revision_head_digest: str


@dataclass(frozen=True)
class LivingMemoryApplicationProjection:
    memories: tuple[LivingMemoryRecord, ...]


@dataclass(frozen=True)
class RelationshipApplicationProjection:
    interactions: tuple[RelationshipStanceInteraction, ...]


@dataclass(frozen=True)
class ParticipantGoalCommitmentApplicationProjection:
    records: tuple[ParticipantGoalCommitmentRecord, ...]


@dataclass(frozen=True)
class SituatedStateApplicationProjection:
    state: SituatedStateRecord | None


@dataclass(frozen=True)
class MediumStateApplicationProjection:
    state: MediumStateRecord


@dataclass(frozen=True)
class KnowledgeApplicationEntry:
    entry_id: str
    title: str


@dataclass(frozen=True)
class KnowledgeApplicationProjection:
    entries: tuple[KnowledgeApplicationEntry, ...]


@dataclass(frozen=True)
class ConversationHistoryApplicationProjection:
    turns: tuple[ConversationTurnRecord, ...]


ApplicationProjection: TypeAlias = (
    CurrentApplicationProjection
    | RuntimeApplicationProjection
    | TimelineApplicationProjection
    | LivingMemoryApplicationProjection
    | RelationshipApplicationProjection
    | ParticipantGoalCommitmentApplicationProjection
    | SituatedStateApplicationProjection
    | MediumStateApplicationProjection
    | KnowledgeApplicationProjection
    | ConversationHistoryApplicationProjection
)


@dataclass(frozen=True)
class ApplicationQueryResponse:
    status: ApplicationQueryStatus
    projection: ApplicationProjection | None
    problem: ApplicationProblemView | None


@dataclass
class _ActiveOperation:
    operation_ref: OperationRef
    future: Future[RuntimeResult]
    key_digest: str | None
    payload_fingerprint: str


class _ApplicationRouter:
    """Private in-process routing state; canonical operation state stays below Host."""

    def __init__(
        self,
        host: RuntimeHost,
        binding: RuntimeAuthorityBinding,
        *,
        single_command_authorization: _LocalFirstSubmissionAuthorization | None = None,
        start_runtime: Callable[[], RuntimeRoute] | None = None,
        stop_runtime: Callable[[], RuntimeHealth] | None = None,
        query_runtime: Callable[[], RuntimeHealth] | None = None,
        follow_runtime: Callable[[OperationRef], RuntimeResult] | None = None,
        source_authoring: TextSourceCharacterAuthoring | None = None,
        source_studio_location: StudioRootRef | None = None,
        source_identity_freezer: Callable[[object], SourceIdentityFreezeResponse]
        | None = None,
        local_identity_lister: Callable[[], LocalIdentityListResponse] | None = None,
        local_identity_selector: Callable[[object], LocalIdentitySelectResponse]
        | None = None,
        knowledge_entries: tuple[KnowledgeEntry, ...] = (),
    ) -> None:
        if single_command_authorization is not None and type(
            single_command_authorization
        ) is not _LocalFirstSubmissionAuthorization:
            raise TypeError("application submission authorization is invalid")
        self._host = host
        self._binding = binding
        self._single_command_authorization = single_command_authorization
        self._start_runtime = start_runtime
        self._stop_runtime = stop_runtime
        self._query_runtime = query_runtime
        self._follow_runtime = follow_runtime
        if source_authoring is not None and not isinstance(
            source_authoring,
            TextSourceCharacterAuthoring,
        ):
            raise TypeError("source_authoring must be TextSourceCharacterAuthoring")
        self._source_authoring = source_authoring
        if source_studio_location is not None and not isinstance(
            source_studio_location,
            StudioRootRef,
        ):
            raise TypeError("source_studio_location must be StudioRootRef")
        self._source_studio_location = source_studio_location
        if source_identity_freezer is not None and not callable(
            source_identity_freezer
        ):
            raise TypeError("source_identity_freezer must be callable")
        self._source_identity_freezer = source_identity_freezer
        self._local_identity_lister = local_identity_lister
        self._local_identity_selector = local_identity_selector
        if not isinstance(knowledge_entries, tuple) or any(
            not isinstance(entry, KnowledgeEntry) for entry in knowledge_entries
        ):
            raise TypeError("knowledge_entries must be sealed KnowledgeEntry values")
        self._knowledge_entries = knowledge_entries
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"m0-application-{binding.binding_id[:8]}",
        )
        self._lock = RLock()
        self._active_by_operation: dict[str, _ActiveOperation] = {}
        self._active_by_key: dict[str, _ActiveOperation] = {}
        self._closed = False

    @property
    def binding(self) -> RuntimeAuthorityBinding:
        return self._binding

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeHostRejected(
                "application-closed",
                "the fresh ApplicationFacade lifecycle is closed",
            )

    def _lease(self):
        return self._host.lease(
            profile_id=self._binding.profile_id,
            timeline_id=self._binding.timeline_id,
        )

    def _operation_ref_authority_matches(self, operation_ref: object) -> bool:
        timeline_root = self._binding.timeline_root
        return (
            type(operation_ref) is OperationRef
            and operation_ref.contract_version == "M0-CONTRACT-1.0"
            and operation_ref.root_id == timeline_root.root_id
            and operation_ref.timeline_store_id == timeline_root.timeline_store_id
            and operation_ref.authority_scope_id == self._binding.authority_scope_id
        )

    def _resume(self, operation_ref: OperationRef) -> RuntimeResult:
        with self._lease() as lease:
            return lease.resume(operation_ref)

    def _start_resume(
        self,
        operation_ref: OperationRef,
        *,
        key_digest: str | None,
        payload_fingerprint: str,
    ) -> _ActiveOperation:
        active = self._active_by_operation.get(operation_ref.operation_id)
        if active is not None and not active.future.done():
            return active
        future = self._executor.submit(self._resume, operation_ref)
        active = _ActiveOperation(
            operation_ref=operation_ref,
            future=future,
            key_digest=key_digest,
            payload_fingerprint=payload_fingerprint,
        )
        self._active_by_operation[operation_ref.operation_id] = active
        if key_digest is not None:
            self._active_by_key[key_digest] = active
        return active

    def _discard_active(self, active: _ActiveOperation) -> None:
        current = self._active_by_operation.get(active.operation_ref.operation_id)
        if current is active:
            self._active_by_operation.pop(active.operation_ref.operation_id, None)
        if active.key_digest is not None:
            keyed = self._active_by_key.get(active.key_digest)
            if keyed is active:
                self._active_by_key.pop(active.key_digest, None)

    def submit(
        self,
        command: SubjectCommand,
        *,
        idempotency_key: str,
    ) -> ApplicationOperationResponse:
        self._require_open()
        if type(command) is not SubjectCommand:
            return _unavailable("typed-subject-command-required")
        if (
            command.target_profile_id != self._binding.profile_id
            or command.target_timeline_id != self._binding.timeline_id
        ):
            return _not_found_or_not_authorized()
        if not isinstance(idempotency_key, str) or not idempotency_key:
            return _unavailable("idempotency-key-invalid")
        if self._single_command_authorization is not None and not (
            self._single_command_authorization.matches(
                self._binding,
                command,
                idempotency_key,
            )
        ):
            return _unavailable("local-interaction-plan-mismatch")
        key_digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
        with self._lock:
            existing = self._active_by_key.get(key_digest)
            if existing is not None and existing.future.done():
                self._discard_active(existing)
                existing = None
            if existing is not None:
                if existing.payload_fingerprint != command.payload_fingerprint:
                    return _conflict(existing.operation_ref)
                return _pending(existing.operation_ref, replayed=True)
            try:
                with self._lease() as lease:
                    admitted = lease.admit(
                        command,
                        idempotency_key=idempotency_key,
                    )
            except PayloadConflict as error:
                return _conflict(error.existing_operation_ref)
            except Exception as error:
                return _map_problem(error)
            response = _from_runtime_result(admitted)
            if response.status is ApplicationOperationStatus.PENDING:
                self._start_resume(
                    admitted.operation_ref,
                    key_digest=key_digest,
                    payload_fingerprint=command.payload_fingerprint,
                )
            return response

    def control(self, command: object) -> ApplicationHostResponse:
        self._require_open()
        if type(command) is not ApplicationHostCommand:
            return _host_unavailable("typed-host-command-required")
        assert isinstance(command, ApplicationHostCommand)
        if (
            command.target_profile_id != self._binding.profile_id
            or command.target_timeline_id != self._binding.timeline_id
        ):
            return _host_not_found_or_not_authorized()
        try:
            if command.kind is ApplicationHostCommandKind.START_LOCAL_SERVING:
                if self._start_runtime is None:
                    return _host_unavailable("local-serving-authorization-unavailable")
                route = self._start_runtime()
                self._binding = route.binding
                return _host_from_health(route.health)
            if command.kind is ApplicationHostCommandKind.STOP_LOCAL_SERVING:
                if self._stop_runtime is None:
                    return _host_unavailable("local-serving-authorization-unavailable")
                health = self._stop_runtime()
                return _host_from_health(health)
        except Exception as error:
            return _map_host_problem(error)
        return _host_unavailable("host-command-unavailable")

    def follow(self, operation_ref: object) -> ApplicationOperationResponse:
        self._require_open()
        if not self._operation_ref_authority_matches(operation_ref):
            return _not_found_or_not_authorized()
        assert isinstance(operation_ref, OperationRef)
        if operation_ref.operation_kind is OperationKind.HOST:
            return _unavailable("host-operation-unavailable")
        with self._lock:
            active = self._active_by_operation.get(operation_ref.operation_id)
            if active is not None and not active.future.done():
                return _pending(operation_ref)
            if active is not None:
                self._discard_active(active)
            used_stopped_follow = False
            try:
                with self._lease() as lease:
                    result = lease.follow(operation_ref)
            except RuntimeHostRejected as error:
                if (
                    error.code == "runtime-lane-unavailable"
                    and self._follow_runtime is not None
                ):
                    try:
                        result = self._follow_runtime(operation_ref)
                        used_stopped_follow = True
                    except Exception as follow_error:
                        return _map_follow_problem(follow_error)
                else:
                    return _map_follow_problem(error)
            except Exception as error:
                return _map_follow_problem(error)
            response = _from_runtime_result(result)
            if response.status is ApplicationOperationStatus.PENDING:
                if used_stopped_follow:
                    return _unavailable("operation-not-terminal-while-stopped")
                self._start_resume(
                    operation_ref,
                    key_digest=None,
                    payload_fingerprint=operation_ref.admitted_payload_fingerprint,
                )
            return response

    def wait(
        self,
        operation_ref: object,
        *,
        timeout_seconds: float,
    ) -> ApplicationOperationResponse:
        self._require_open()
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 0
            or timeout_seconds > 30
        ):
            return _unavailable("wait-timeout-invalid")
        if not self._operation_ref_authority_matches(operation_ref):
            return _not_found_or_not_authorized()
        assert isinstance(operation_ref, OperationRef)
        if operation_ref.operation_kind is OperationKind.HOST:
            return _unavailable("host-operation-unavailable")
        with self._lock:
            active = self._active_by_operation.get(operation_ref.operation_id)
        if active is None:
            first = self.follow(operation_ref)
            if first.status is not ApplicationOperationStatus.PENDING:
                return first
            with self._lock:
                active = self._active_by_operation.get(operation_ref.operation_id)
        if active is None:
            return _pending(operation_ref)
        try:
            active.future.result(timeout=float(timeout_seconds))
        except TimeoutError:
            return _pending(operation_ref)
        except RuntimeInterrupted as error:
            with self._lock:
                self._discard_active(active)
            return ApplicationOperationResponse(
                status=ApplicationOperationStatus.INTERRUPTED,
                operation_ref=error.operation_ref,
                projection=None,
                problem=ApplicationProblemView("operation-interrupted"),
            )
        except Exception:
            pass
        return self.follow(operation_ref)

    def query(self, query: object) -> ApplicationQueryResponse:
        self._require_open()
        if type(query) is not ApplicationQuery:
            return _query_unavailable("typed-application-query-required")
        if (
            query.target_profile_id != self._binding.profile_id
            or query.target_timeline_id != self._binding.timeline_id
        ):
            return _query_not_found_or_not_authorized()
        try:
            binding = self._host.query_binding(
                profile_id=self._binding.profile_id,
                timeline_id=self._binding.timeline_id,
            )
            health = (
                self._query_runtime()
                if self._query_runtime is not None
                else self._host.health(
                    profile_id=self._binding.profile_id,
                    timeline_id=self._binding.timeline_id,
                )
            )
            memories = (
                None
                if query.kind is not ApplicationQueryKind.LIVING_MEMORY
                else self._list_living_memories()
            )
            relationship_interactions = (
                None
                if query.kind is not ApplicationQueryKind.RELATIONSHIP
                else self._list_relationship_interactions()
            )
            participant_goal_commitments = (
                None
                if query.kind is not ApplicationQueryKind.PARTICIPANT_GOALS
                else self._list_participant_goal_commitments()
            )
            situated_state = (
                None
                if query.kind is not ApplicationQueryKind.SITUATED_STATE
                else self._current_situated_state()
            )
            medium_state = (
                None
                if query.kind is not ApplicationQueryKind.MEDIUM_STATE
                else self._current_medium_state()
            )
            knowledge_entries = (
                tuple(
                    KnowledgeApplicationEntry(entry.entry_id, entry.title)
                    for entry in self._knowledge_entries
                )
                if query.kind is ApplicationQueryKind.KNOWLEDGE
                else None
            )
            conversation_turns = (
                self._list_conversation_turns()
                if query.kind is ApplicationQueryKind.CONVERSATION_HISTORY
                else None
            )
        except RuntimeHostRejected:
            return _query_not_found_or_not_authorized()
        except Exception:
            return _query_failed_closed()
        return _from_query(
            query.kind,
            binding,
            health,
            memories=memories,
            relationship_interactions=relationship_interactions,
            participant_goal_commitments=participant_goal_commitments,
            situated_state=situated_state,
            medium_state=medium_state,
            knowledge_entries=knowledge_entries,
            conversation_turns=conversation_turns,
        )

    def preview_character_source(self, request: object) -> TextSourcePreviewResponse:
        with self._lock:
            self._require_open()
            source_authoring = self._source_authoring
        if source_authoring is None:
            return TextSourcePreviewResponse.unavailable()
        return source_authoring.preview(request)

    def source_draft(self, command: object) -> SourceDraftResponse:
        with self._lock:
            self._require_open()
            source_studio_location = self._source_studio_location
        if source_studio_location is None:
            return SourceDraftResponse(
                status=SourceDraftStatus.UNAVAILABLE,
                problem_code="source-draft-unavailable",
            )
        source_studio = SubjectStudio.open(
            source_studio_location,
            policy_kernel=PolicyKernel(),
        )
        try:
            return source_studio.source_draft(command)
        finally:
            source_studio.close()

    def preview_source_freeze_mapping(
        self,
        request: object,
    ) -> SourceFreezeMappingResponse:
        with self._lock:
            self._require_open()
            source_studio_location = self._source_studio_location
        if source_studio_location is None:
            return SourceFreezeMappingResponse(
                status=SourceFreezeMappingStatus.UNAVAILABLE,
                problem_code="source-freeze-mapping-unavailable",
            )
        source_studio = SubjectStudio.open(
            source_studio_location,
            policy_kernel=PolicyKernel(),
        )
        try:
            return source_studio.preview_source_freeze_mapping(request)
        finally:
            source_studio.close()

    def freeze_source_identity(self, request: object) -> SourceIdentityFreezeResponse:
        with self._lock:
            self._require_open()
            source_identity_freezer = self._source_identity_freezer
        if source_identity_freezer is None:
            return SourceIdentityFreezeResponse(
                SourceIdentityFreezeStatus.UNAVAILABLE,
                problem_code="source-identity-freeze-unavailable",
            )
        try:
            return source_identity_freezer(request)
        except Exception:
            return SourceIdentityFreezeResponse(
                SourceIdentityFreezeStatus.FAILED_CLOSED,
                problem_code="source-identity-freeze-failed-closed",
            )

    def local_identities(self) -> LocalIdentityListResponse:
        with self._lock:
            self._require_open()
            lister = self._local_identity_lister
        if lister is None:
            return LocalIdentityListResponse(LocalIdentityStatus.UNAVAILABLE)
        return lister()

    def select_local_identity(self, request: object) -> LocalIdentitySelectResponse:
        with self._lock:
            self._require_open()
            selector = self._local_identity_selector
        if selector is None:
            return LocalIdentitySelectResponse(LocalIdentityStatus.UNAVAILABLE)
        return selector(request)

    def _list_living_memories(self) -> tuple[LivingMemoryRecord, ...]:
        with self._lease() as lease:
            records = lease.list_living_memories(active_only=False, limit=100)
        observed_at_us = time_ns() // 1_000
        return tuple(
            (
                record
                if record.temporal_anchor is None
                else replace(
                    record,
                    content=_TEMPORAL_GROUNDING.render(
                        record.content,
                        record.temporal_anchor,
                        observed_at_us=observed_at_us,
                    ),
                )
            )
            for record in records
        )

    def _list_conversation_turns(self) -> tuple[ConversationTurnRecord, ...]:
        with self._lease() as lease:
            return lease.list_conversation_turns(limit=20)

    def _list_relationship_interactions(
        self,
    ) -> tuple[RelationshipStanceInteraction, ...]:
        with self._lease() as lease:
            return lease.list_relationship_interactions(limit=100)

    def _list_participant_goal_commitments(
        self,
    ) -> tuple[ParticipantGoalCommitmentRecord, ...]:
        with self._lease() as lease:
            records = lease.list_participant_goal_commitments(
                active_only=False,
                limit=100,
            )
        observed_at_us = time_ns() // 1_000
        return tuple(
            (
                record
                if record.temporal_anchor is None
                else replace(
                    record,
                    terms=_TEMPORAL_GROUNDING.render(
                        record.terms,
                        record.temporal_anchor,
                        observed_at_us=observed_at_us,
                    ),
                )
            )
            for record in records
        )

    def _current_situated_state(self) -> SituatedStateRecord | None:
        with self._lease() as lease:
            states = lease.list_situated_states(active_only=True, limit=1)
        return (
            usable_state(states[0], now_us=time_ns() // 1_000)
            if states
            else None
        )

    def _current_medium_state(self) -> MediumStateRecord:
        with self._lease() as lease:
            return lease.current_medium_state()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)


_APPLICATION_FACADE_TOKEN = object()
_TEMPORAL_GROUNDING = TemporalGrounding()


class ApplicationFacade:
    """Only public application authority for runtime and bounded authoring work."""

    def __init__(
        self,
        router: _ApplicationRouter,
        *,
        _token: object,
    ) -> None:
        if (
            _token is not _APPLICATION_FACADE_TOKEN
            or type(router) is not _ApplicationRouter
        ):
            raise TypeError("ApplicationFacade is created only by compose_application")
        self.__router = router

    def submit(
        self,
        command: SubjectCommand,
        *,
        idempotency_key: str,
    ) -> ApplicationOperationResponse:
        return self.__router.submit(command, idempotency_key=idempotency_key)

    def control(self, command: object) -> ApplicationHostResponse:
        return self.__router.control(command)

    def follow(self, operation_ref: object) -> ApplicationOperationResponse:
        return self.__router.follow(operation_ref)

    def wait(
        self,
        operation_ref: object,
        *,
        timeout_seconds: float,
    ) -> ApplicationOperationResponse:
        return self.__router.wait(
            operation_ref,
            timeout_seconds=timeout_seconds,
        )

    def query(self, query: object) -> ApplicationQueryResponse:
        return self.__router.query(query)

    def preview_character_source(self, request: object) -> TextSourcePreviewResponse:
        return self.__router.preview_character_source(request)

    def source_draft(self, command: object) -> SourceDraftResponse:
        return self.__router.source_draft(command)

    def preview_source_freeze_mapping(
        self,
        request: object,
    ) -> SourceFreezeMappingResponse:
        return self.__router.preview_source_freeze_mapping(request)

    def freeze_source_identity(self, request: object) -> SourceIdentityFreezeResponse:
        return self.__router.freeze_source_identity(request)

    def local_identities(self) -> LocalIdentityListResponse:
        return self.__router.local_identities()

    def select_local_identity(self, request: object) -> LocalIdentitySelectResponse:
        return self.__router.select_local_identity(request)


def _create_application_facade(
    host: RuntimeHost,
    binding: RuntimeAuthorityBinding,
    *,
    _single_command_authorization: _LocalFirstSubmissionAuthorization | None = None,
    _start_runtime: Callable[[], RuntimeRoute] | None = None,
    _stop_runtime: Callable[[], RuntimeHealth] | None = None,
    _query_runtime: Callable[[], RuntimeHealth] | None = None,
    _follow_runtime: Callable[[OperationRef], RuntimeResult] | None = None,
    _source_authoring: TextSourceCharacterAuthoring | None = None,
    _source_studio_location: StudioRootRef | None = None,
    _source_identity_freezer: Callable[[object], SourceIdentityFreezeResponse]
    | None = None,
    _local_identity_lister: Callable[[], LocalIdentityListResponse] | None = None,
    _local_identity_selector: Callable[[object], LocalIdentitySelectResponse]
    | None = None,
    _knowledge_entries: tuple[KnowledgeEntry, ...] = (),
) -> tuple[ApplicationFacade, _ApplicationRouter]:
    router = _ApplicationRouter(
        host,
        binding,
        single_command_authorization=_single_command_authorization,
        start_runtime=_start_runtime,
        stop_runtime=_stop_runtime,
        query_runtime=_query_runtime,
        follow_runtime=_follow_runtime,
        source_authoring=_source_authoring,
        source_studio_location=_source_studio_location,
        source_identity_freezer=_source_identity_freezer,
        local_identity_lister=_local_identity_lister,
        local_identity_selector=_local_identity_selector,
        knowledge_entries=_knowledge_entries,
    )
    return (
        ApplicationFacade(router, _token=_APPLICATION_FACADE_TOKEN),
        router,
    )


def _from_runtime_result(result: RuntimeResult) -> ApplicationOperationResponse:
    state = result.snapshot.operation_state
    if state is OperationState.COMPLETED and result.outcome is not None:
        projection = AuthorizedOperationProjection(
            operation_kind=OperationKind.SUBJECT,
            operation_state=ApplicationOperationStatus.TERMINAL,
            timeline_outcome_id=result.outcome.outcome_id,
            timeline_head_sequence=result.outcome.head_sequence,
            expression_text=result.outcome.expression.text,
            expression_language=result.outcome.expression.language,
            failure_stage=None,
            failure_code=None,
            living_memory_status=(
                result.outcome.experience_outcome.living_memory_status.value
            ),
            living_memory_recalled_ids=(
                result.outcome.experience_outcome.living_memory_recalled_ids
            ),
            memory_withdrawal_status=result.outcome.experience_outcome.memory_withdrawal_status,
            knowledge_status=result.outcome.experience_outcome.knowledge_status,
            knowledge_citation_ids=(
                result.outcome.experience_outcome.knowledge_citation_ids
            ),
            relationship_status=(
                result.outcome.relationship_outcome.relationship_status
            ),
            relationship_event=(
                result.outcome.relationship_outcome.relationship_event or None
            ),
            relationship_candidate_event=(
                result.outcome.relationship_outcome.relationship_candidate_event
            ),
            relationship_reason_code=(
                result.outcome.relationship_outcome.relationship_reason_code
            ),
            participant_goal_commitment_status=(
                result.outcome.experience_outcome.participant_goal_commitment_status
            ),
            participant_goal_commitment_action=(
                result.outcome.experience_outcome.participant_goal_commitment_action
            ),
            participant_goal_commitment_reason_code=(
                result.outcome.experience_outcome.participant_goal_commitment_reason_code
            ),
            participant_goal_commitment_selected_count=(
                result.outcome.experience_outcome.participant_goal_commitment_selected_count
            ),
            situated_state_status=(
                result.outcome.subject_state_outcome.situated_state_status
            ),
            situated_state_action=(
                result.outcome.subject_state_outcome.situated_state_action
            ),
            situated_state_posture=(
                result.outcome.subject_state_outcome.situated_state_posture
            ),
            situated_state_reason_code=(
                result.outcome.subject_state_outcome.situated_state_reason_code
            ),
            medium_state_status=(
                result.outcome.subject_state_outcome.medium_state_status
            ),
            medium_state_baseline=(
                result.outcome.subject_state_outcome.medium_state_baseline
            ),
            medium_state_before_baseline=(
                result.outcome.subject_state_outcome.medium_state_before_baseline
            ),
            medium_state_reason_code=(
                result.outcome.subject_state_outcome.medium_state_reason_code
            ),
            medium_state_signal=(
                result.outcome.subject_state_outcome.medium_state_signal
            ),
        )
        return ApplicationOperationResponse(
            status=ApplicationOperationStatus.TERMINAL,
            operation_ref=result.operation_ref,
            projection=projection,
            problem=None,
            replayed=result.admission_replayed or result.publication_replayed,
        )
    if state is OperationState.FAILED_CLOSED:
        failure = result.failure
        projection = AuthorizedOperationProjection(
            operation_kind=OperationKind.SUBJECT,
            operation_state=ApplicationOperationStatus.FAILED_CLOSED,
            timeline_outcome_id=None,
            timeline_head_sequence=result.snapshot.timeline_head_sequence,
            expression_text=None,
            expression_language=None,
            failure_stage=None if failure is None else failure.stage,
            failure_code=None if failure is None else failure.code,
        )
        return ApplicationOperationResponse(
            status=ApplicationOperationStatus.FAILED_CLOSED,
            operation_ref=result.operation_ref,
            projection=projection,
            problem=ApplicationProblemView("operation-failed-closed"),
            replayed=result.admission_replayed,
        )
    if state is OperationState.INTERRUPTED:
        return ApplicationOperationResponse(
            status=ApplicationOperationStatus.INTERRUPTED,
            operation_ref=result.operation_ref,
            projection=AuthorizedOperationProjection(
                operation_kind=OperationKind.SUBJECT,
                operation_state=ApplicationOperationStatus.INTERRUPTED,
                timeline_outcome_id=None,
                timeline_head_sequence=result.snapshot.timeline_head_sequence,
                expression_text=None,
                expression_language=None,
                failure_stage=None,
                failure_code=None,
            ),
            problem=ApplicationProblemView("operation-interrupted"),
            replayed=result.admission_replayed,
        )
    return _pending(result.operation_ref, replayed=result.admission_replayed)


def _pending(
    operation_ref: OperationRef,
    *,
    replayed: bool = False,
) -> ApplicationOperationResponse:
    return ApplicationOperationResponse(
        status=ApplicationOperationStatus.PENDING,
        operation_ref=operation_ref,
        projection=None,
        problem=None,
        replayed=replayed,
    )


def _unavailable(code: str) -> ApplicationOperationResponse:
    return ApplicationOperationResponse(
        status=ApplicationOperationStatus.UNAVAILABLE,
        operation_ref=None,
        projection=None,
        problem=ApplicationProblemView(code),
    )


def _conflict(
    operation_ref: OperationRef | None = None,
) -> ApplicationOperationResponse:
    return ApplicationOperationResponse(
        status=ApplicationOperationStatus.CONFLICT,
        operation_ref=operation_ref,
        projection=None,
        problem=ApplicationProblemView("operation-conflict"),
    )


def _not_found_or_not_authorized() -> ApplicationOperationResponse:
    return ApplicationOperationResponse(
        status=ApplicationOperationStatus.NOT_FOUND_OR_NOT_AUTHORIZED,
        operation_ref=None,
        projection=None,
        problem=ApplicationProblemView("not-found-or-not-authorized"),
    )


def _failed_closed(
    operation_ref: OperationRef | None = None,
) -> ApplicationOperationResponse:
    return ApplicationOperationResponse(
        status=ApplicationOperationStatus.FAILED_CLOSED,
        operation_ref=operation_ref,
        projection=None,
        problem=ApplicationProblemView("application-failed-closed"),
    )


def _map_problem(error: Exception) -> ApplicationOperationResponse:
    if isinstance(error, PayloadConflict):
        return _conflict(error.existing_operation_ref)
    if isinstance(error, RuntimeHostConflict):
        return _conflict()
    if isinstance(error, RuntimeInterrupted):
        return ApplicationOperationResponse(
            status=ApplicationOperationStatus.INTERRUPTED,
            operation_ref=error.operation_ref,
            projection=None,
            problem=ApplicationProblemView("operation-interrupted"),
        )
    if isinstance(error, CycleFailedClosed):
        return _failed_closed(error.operation_ref)
    if isinstance(error, RuntimeHostFailedClosed | AdmissionFailedClosed):
        return _failed_closed()
    if isinstance(error, RuntimeHostRejected | AdmissionProblem):
        return _unavailable(error.code)
    return _failed_closed()


def _map_follow_problem(error: Exception) -> ApplicationOperationResponse:
    if isinstance(error, RuntimeHostConflict):
        return _conflict()
    if isinstance(error, RuntimeHostRejected):
        return _not_found_or_not_authorized()
    if isinstance(error, AdmissionProblem):
        return _not_found_or_not_authorized()
    if isinstance(error, RuntimeHostProblem):
        return _failed_closed()
    return _failed_closed()


def _host_from_health(health: RuntimeHealth) -> ApplicationHostResponse:
    return ApplicationHostResponse(
        status=(
            ApplicationHostStatus.SERVING
            if health.serving
            else ApplicationHostStatus.STOPPED
        ),
        projection=RuntimeApplicationProjection(
            binding_id=health.binding_id,
            lane_id=health.lane_id,
            healthy=health.healthy,
            serving=health.serving,
            gate_state=health.gate_state,
        ),
        problem=None,
    )


def _host_unavailable(code: str) -> ApplicationHostResponse:
    return ApplicationHostResponse(
        status=ApplicationHostStatus.UNAVAILABLE,
        projection=None,
        problem=ApplicationProblemView(code),
    )


def _host_not_found_or_not_authorized() -> ApplicationHostResponse:
    return ApplicationHostResponse(
        status=ApplicationHostStatus.NOT_FOUND_OR_NOT_AUTHORIZED,
        projection=None,
        problem=ApplicationProblemView("not-found-or-not-authorized"),
    )


def _map_host_problem(error: Exception) -> ApplicationHostResponse:
    if isinstance(error, RuntimeHostConflict):
        return ApplicationHostResponse(
            status=ApplicationHostStatus.CONFLICT,
            projection=None,
            problem=ApplicationProblemView(error.code),
        )
    if isinstance(error, RuntimeHostRejected):
        return _host_unavailable(error.code)
    if isinstance(error, RuntimeHostProblem):
        return ApplicationHostResponse(
            status=ApplicationHostStatus.FAILED_CLOSED,
            projection=None,
            problem=ApplicationProblemView(error.code),
        )
    return ApplicationHostResponse(
        status=ApplicationHostStatus.FAILED_CLOSED,
        projection=None,
        problem=ApplicationProblemView("host-command-failed-closed"),
    )


def _from_query(
    kind: ApplicationQueryKind,
    binding: RuntimeAuthorityBinding,
    health: RuntimeHealth,
    *,
    memories: tuple[LivingMemoryRecord, ...] | None = None,
    relationship_interactions: tuple[RelationshipStanceInteraction, ...] | None = None,
    participant_goal_commitments: tuple[ParticipantGoalCommitmentRecord, ...]
    | None = None,
    situated_state: SituatedStateRecord | None = None,
    medium_state: MediumStateRecord | None = None,
    knowledge_entries: tuple[KnowledgeApplicationEntry, ...] | None = None,
    conversation_turns: tuple[ConversationTurnRecord, ...] | None = None,
) -> ApplicationQueryResponse:
    if kind is ApplicationQueryKind.CURRENT:
        projection: ApplicationProjection = CurrentApplicationProjection(
            profile_id=binding.profile_id,
            timeline_id=binding.timeline_id,
            binding_id=binding.binding_id,
            binding_revision=binding.binding_revision,
            binding_epoch=binding.binding_epoch,
        )
    elif kind is ApplicationQueryKind.RUNTIME:
        projection = RuntimeApplicationProjection(
            binding_id=binding.binding_id,
            lane_id=health.lane_id,
            healthy=health.healthy,
            serving=health.serving,
            gate_state=health.gate_state,
        )
    elif kind is ApplicationQueryKind.TIMELINE:
        projection = TimelineApplicationProjection(
            timeline_id=binding.timeline_id,
            head_sequence=health.timeline_basis.head_sequence,
            published_outcome_digest=health.timeline_basis.published_outcome_digest,
            revision_head_digest=health.timeline_basis.revision_head_digest,
        )
    elif kind is ApplicationQueryKind.LIVING_MEMORY and memories is not None:
        projection = LivingMemoryApplicationProjection(memories=memories)
    elif (
        kind is ApplicationQueryKind.RELATIONSHIP
        and relationship_interactions is not None
    ):
        projection = RelationshipApplicationProjection(
            interactions=relationship_interactions
        )
    elif (
        kind is ApplicationQueryKind.PARTICIPANT_GOALS
        and participant_goal_commitments is not None
    ):
        projection = ParticipantGoalCommitmentApplicationProjection(
            records=participant_goal_commitments
        )
    elif kind is ApplicationQueryKind.SITUATED_STATE:
        projection = SituatedStateApplicationProjection(state=situated_state)
    elif kind is ApplicationQueryKind.MEDIUM_STATE and medium_state is not None:
        projection = MediumStateApplicationProjection(state=medium_state)
    elif kind is ApplicationQueryKind.KNOWLEDGE and knowledge_entries is not None:
        projection = KnowledgeApplicationProjection(entries=knowledge_entries)
    elif (
        kind is ApplicationQueryKind.CONVERSATION_HISTORY
        and conversation_turns is not None
    ):
        projection = ConversationHistoryApplicationProjection(
            turns=conversation_turns
        )
    else:
        return _query_unavailable("query-kind-unavailable")
    return ApplicationQueryResponse(
        status=ApplicationQueryStatus.AVAILABLE,
        projection=projection,
        problem=None,
    )


def _query_unavailable(code: str) -> ApplicationQueryResponse:
    return ApplicationQueryResponse(
        status=ApplicationQueryStatus.UNAVAILABLE,
        projection=None,
        problem=ApplicationProblemView(code),
    )


def _query_failed_closed() -> ApplicationQueryResponse:
    return ApplicationQueryResponse(
        status=ApplicationQueryStatus.FAILED_CLOSED,
        projection=None,
        problem=ApplicationProblemView("query-failed-closed"),
    )


def _query_not_found_or_not_authorized() -> ApplicationQueryResponse:
    return ApplicationQueryResponse(
        status=ApplicationQueryStatus.NOT_FOUND_OR_NOT_AUTHORIZED,
        projection=None,
        problem=ApplicationProblemView("not-found-or-not-authorized"),
    )


__all__ = [
    "ApplicationFacade",
    "ConversationHistoryApplicationProjection",
    "ApplicationHostCommand",
    "ApplicationHostCommandKind",
    "ApplicationHostResponse",
    "ApplicationHostStatus",
    "ApplicationOperationKind",
    "ApplicationOperationResponse",
    "ApplicationOperationStatus",
    "ApplicationProblemView",
    "ApplicationQuery",
    "ApplicationQueryKind",
    "ApplicationQueryResponse",
    "ApplicationQueryStatus",
    "LivingMemoryApplicationProjection",
    "KnowledgeApplicationProjection",
    "KnowledgeApplicationEntry",
    "RelationshipApplicationProjection",
    "ParticipantGoalCommitmentApplicationProjection",
    "SituatedStateApplicationProjection",
    "MediumStateApplicationProjection",
    "AuthorizedOperationProjection",
    "CurrentApplicationProjection",
    "RuntimeApplicationProjection",
    "TimelineApplicationProjection",
]

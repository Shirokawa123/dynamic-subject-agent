"""The sole fresh-root public application Interface for Mature Runtime M0."""

from __future__ import annotations

from dynamic_subject_agent.character_dialogue import CharacterDialogueSession, DialogueView
from dynamic_subject_agent.conversation_basis import ConversationBasisPreview, BasisPreview
from dynamic_subject_agent.character_reply_candidate import CharacterReplyProducer, CharacterReplyCandidateView, preview_reply
from dynamic_subject_agent.character_evidence_model import CharacterEvidenceModel, CharacterModelView, CharacterContextRequest, CharacterContextView
from dynamic_subject_agent.evidence_extraction import EvidenceExtractionLab, EvidenceExtractionView
from dynamic_subject_agent.reply_protocol_trial import ReplyProtocolTrial
from dynamic_subject_agent.character_chat_context import (
    CharacterChatContextView, prepare_context, valid_request,
)
from dynamic_subject_agent.character_evidence_model import CharacterModelRequest
from dynamic_subject_agent.character_identity_preparation import CharacterIdentityPreparationView, CharacterDefinitionPreparationRequest, prepare_character_identity

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, asdict, replace
from enum import Enum
from hashlib import sha256
import json
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
    PreAdmissionRejected,
    RelationshipStanceInteraction,
    SubjectCommand,
)
from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentRecord
from dynamic_subject_agent.subject_tasks import SubjectTaskCommand, SubjectTaskRecord, TASK_INTENT
from dynamic_subject_agent.text_artifacts import TextSaveApproval, TextArtifactResponse, TEXT_EFFECT_INTENT
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
    UNKNOWN = "unknown"
    FAILED_CLOSED = "failed-closed"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"
    NOT_FOUND_OR_NOT_AUTHORIZED = "not-found-or-not-authorized"


class SubjectRequestLookupStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not-found"
    UNAVAILABLE = "unavailable"
    FAILED_CLOSED = "failed-closed"


@dataclass(frozen=True)
class SubjectRequestLookupRequest:
    command: SubjectCommand
    idempotency_key: str


@dataclass(frozen=True)
class SubjectRequestLookupResponse:
    query_status: SubjectRequestLookupStatus
    operation: ApplicationOperationResponse | None = None
    problem: ApplicationProblemView | None = None


ApplicationOperationKind = OperationKind


class ApplicationQueryKind(str, Enum):
    SUBJECT_TASKS = "subject-tasks"
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
    subject_task: SubjectTaskRecord | None = None
    committed_effect_count: int = 0


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
class SubjectTasksApplicationProjection:
    records: tuple[SubjectTaskRecord, ...]
    enabled: bool
    effects_enabled: bool = False
    saved_paths: tuple[tuple[str,str], ...] = ()


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
    | SubjectTasksApplicationProjection
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
        first_life_freezer=None,
        first_life_budget=None,
        first_life_clock=None,
        first_life_day=None,
        first_life_development=False,
        reviewed_chat_status=None,
        character_basis_reader=None,
        whole_scope_reader=None,
        whole_archive_reader=None,
        reviewed_history_setter=None,
        local_identity_lister: Callable[[], LocalIdentityListResponse] | None = None,
        local_identity_selector: Callable[[object], LocalIdentitySelectResponse]
        | None = None,
        knowledge_entries: tuple[KnowledgeEntry, ...] = (),
        character_dialogue: CharacterDialogueSession | None = None,
        basis_preview: ConversationBasisPreview | None = None,
        character_model: CharacterEvidenceModel | None = None,
        character_reply_lab: CharacterReplyProducer | None = None,
        evidence_extraction: EvidenceExtractionLab | None = None,
        reply_protocol_trial: ReplyProtocolTrial | None = None,
    ) -> None:
        if single_command_authorization is not None and type(
            single_command_authorization
        ) is not _LocalFirstSubmissionAuthorization:
            raise TypeError("application submission authorization is invalid")
        self._host = host
        self._binding = binding
        self._character_basis_reader = character_basis_reader
        self._whole_scope_reader = whole_scope_reader
        self._whole_archive_reader = whole_archive_reader
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
        if character_dialogue is not None and not isinstance(character_dialogue, CharacterDialogueSession):
            raise TypeError("typed character dialogue session required")
        if basis_preview is not None and not isinstance(basis_preview, ConversationBasisPreview):
            raise TypeError("typed basis preview required")
        if character_model is not None and not isinstance(character_model, CharacterEvidenceModel):
            raise TypeError("typed character evidence model required")
        if evidence_extraction is not None and not isinstance(evidence_extraction, EvidenceExtractionLab):
            raise TypeError("typed evidence extraction required")
        self._evidence_extraction = evidence_extraction
        if reply_protocol_trial is not None and type(reply_protocol_trial) is not ReplyProtocolTrial:
            raise TypeError("typed reply protocol trial required")
        self._reply_protocol_trial = reply_protocol_trial
        if character_reply_lab is not None and not isinstance(character_reply_lab, CharacterReplyProducer):
            raise TypeError("typed character reply lab required")
        self._character_reply_lab = character_reply_lab
        self._character_model = character_model
        self._basis_preview = basis_preview
        self._character_dialogue = character_dialogue
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
        self._first_life_freezer = first_life_freezer
        self._life_budget, self._life_clock, self._life_day, self._life_development = first_life_budget, first_life_clock, first_life_day, first_life_development
        self._last_life_basis = None
        self._last_life_query = None
        self._reviewed_chat_status = reviewed_chat_status
        self._reviewed_history_setter = reviewed_history_setter
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

    def lookup_subject_request(self, request: object) -> SubjectRequestLookupResponse:
        self._require_open()
        if type(request) is not SubjectRequestLookupRequest or type(request.command) is not SubjectCommand:
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.UNAVAILABLE,
                problem=ApplicationProblemView('typed-subject-request-lookup-required'))
        command = request.command
        if (command.target_profile_id != self._binding.profile_id or command.target_timeline_id != self._binding.timeline_id):
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.NOT_FOUND,
                problem=ApplicationProblemView('subject-request-not-found-or-not-authorized'))
        from dynamic_subject_agent.original_whole_chat import WHOLE_AUTHORITIES
        if (self._binding.provider_authority not in WHOLE_AUTHORITIES or command.declared_intent != 'ask-collaborator-status'
            or command.language != 'zh' or command.provenance != 'project-original' or len(command.utterance) > 1000
            or not isinstance(request.idempotency_key, str)):
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.UNAVAILABLE,
                problem=ApplicationProblemView('subject-request-lookup-invalid'))
        try:
            SubjectCommand(**asdict(command))
            observed = self._host.lookup_subject_request(self._binding, command, request.idempotency_key)
            if observed is None:
                return SubjectRequestLookupResponse(SubjectRequestLookupStatus.NOT_FOUND,
                    problem=ApplicationProblemView('subject-request-not-found-or-not-authorized'))
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.FOUND, operation=_from_runtime_result(observed))
        except PreAdmissionRejected as error:
            safe = {'subject-request-payload-mismatch', 'malformed-idempotency-key', 'subject-request-lookup-invalid'}
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.UNAVAILABLE,
                problem=ApplicationProblemView(error.code if error.code in safe else 'subject-request-lookup-invalid'))
        except Exception:
            return SubjectRequestLookupResponse(SubjectRequestLookupStatus.FAILED_CLOSED,
                problem=ApplicationProblemView('subject-request-lookup-unverified'))

    def query_shared_activity(self, request=None):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse, SharedExperienceRequest, SharedActivityStepRequest
        self._require_open()
        if request is not None and (type(request) not in (SharedExperienceRequest, SharedActivityStepRequest)
            or request.target_profile_id != self._binding.profile_id or request.target_timeline_id != self._binding.timeline_id
            or type(request.expected_revision) is not int or request.expected_revision < 0
            or type(request) is SharedExperienceRequest and request.confirmed is not True):
            return SharedActivityResponse('unavailable', problem_code='shared-request-invalid')
        try:
            return self._host.query_shared_activity(self._binding, request=request)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='shared-state-unverified')

    def _working_request_valid(self, request):
        from dynamic_subject_agent.working_understanding import WorkingUnderstandingRequest, validate_sources
        if (type(request) is not WorkingUnderstandingRequest or request.target_profile_id != self._binding.profile_id
            or request.target_timeline_id != self._binding.timeline_id or type(request.expected_revision) is not int
            or request.expected_revision < 0 or type(request.request_id) is not str or request.action not in ('form','disable')
            or type(request.confirmed) is not bool):
            return False
        try:
            from dynamic_subject_agent.timeline import _validate_idempotency_key
            _validate_idempotency_key(request.request_id)
            if request.action == 'form':
                validate_sources(request.sources)
            elif request.sources != ():
                return False
            return True
        except Exception:
            return False

    def query_working_understanding(self, request=None):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        if request is not None and not self._working_request_valid(request):
            return SharedActivityResponse('unavailable',problem_code='working-request-invalid')
        try:
            return self._host.query_working_understanding(self._binding,request)
        except Exception:
            return SharedActivityResponse('failed-closed',problem_code='working-state-unverified')

    def preview_working_understanding(self, request):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        if not self._working_request_valid(request) or request.action != 'form':
            return SharedActivityResponse('unavailable',problem_code='working-request-invalid')
        try:
            return self._host.query_working_understanding(self._binding,request,preview=True)
        except PreAdmissionRejected as error:
            return SharedActivityResponse('unavailable',problem_code=error.code)
        except Exception:
            return SharedActivityResponse('failed-closed',problem_code='working-preview-unverified')

    def apply_working_understanding(self, request):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        if not self._working_request_valid(request):
            return SharedActivityResponse('unavailable',problem_code='working-request-invalid')
        if request.confirmed is not True:
            return SharedActivityResponse('cancelled')
        try:
            return self._host.apply_working_understanding(self._binding,request)
        except PreAdmissionRejected as error:
            return SharedActivityResponse('unavailable',problem_code=error.code)
        except Exception:
            return SharedActivityResponse('failed-closed',problem_code='working-operation-unverified')

    def preview_working_activity(self, purpose='choice', text=''):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        if purpose not in ('choice','reply') or purpose == 'reply' and (type(text) is not str or not text.strip() or len(text)>1000 or '\x00' in text):
            return SharedActivityResponse('unavailable',problem_code='working-preview-purpose-invalid')
        try:
            return self._host.query_working_understanding(self._binding,preview=True,purpose=purpose,message=text)
        except Exception:
            return SharedActivityResponse('failed-closed',problem_code='working-preview-unverified')

    def advance_working_activity(self, request):
        from dynamic_subject_agent.shared_activity import WORKING_AUTHORITIES, SharedActivityStepRequest, SharedActivityResponse
        if self._binding.provider_authority not in WORKING_AUTHORITIES:
            return SharedActivityResponse('unavailable',problem_code='independent-working-authority-required')
        return self._apply_shared_activity(request,SharedActivityStepRequest)

    def preview_shared_activity_step(self):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        try:
            return self._host.query_shared_activity(self._binding, preview=True)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='shared-preview-unverified')

    def query_living_activity(self, request=None):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        if request is not None and not self._living_request_valid(request):
            return SharedActivityResponse('unavailable', problem_code='living-request-invalid')
        try:
            return self._host.query_living_activity(self._binding, request)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='living-state-unverified')

    def query_living_controls(self):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        try:
            return self._host.query_living_controls(self._binding)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='living-permission-query-unverified')

    def preview_living_activity(self, purpose='choice', text=''):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        if purpose not in ('choice', 'share', 'reply') or purpose == 'reply' and (type(text) is not str or not text.strip() or len(text) > 1000 or '\x00' in text):
            return SharedActivityResponse('unavailable', problem_code='living-preview-purpose-invalid')
        try:
            return self._host.query_living_activity(self._binding, preview=purpose, message=text)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='living-preview-unverified')

    def _living_request_valid(self, request):
        from dynamic_subject_agent.living_activity import LivingActionRequest
        return (type(request) is LivingActionRequest and request.target_profile_id == self._binding.profile_id
            and request.target_timeline_id == self._binding.timeline_id and type(request.expected_revision) is int
            and request.expected_revision >= 0 and request.action in ('online', 'simulation', 'manual', 'share')
            and type(request.request_id) is str and type(request.session_id) is str
            and (request.action != 'online' or 16 <= len(request.session_id) <= 256))

    def advance_living_activity(self, request):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        self._require_open()
        if not self._living_request_valid(request):
            return SharedActivityResponse('unavailable', problem_code='living-request-invalid')
        try:
            return self._host.apply_living_activity(self._binding, request)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='living-operation-unverified')

    def heartbeat_living_presence(self, request):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        from dynamic_subject_agent.living_activity import LivingPresenceRequest
        self._require_open()
        if (type(request) is not LivingPresenceRequest or request.target_profile_id != self._binding.profile_id
            or request.target_timeline_id != self._binding.timeline_id or type(request.session_id) is not str
            or not 16 <= len(request.session_id) <= 256 or '\x00' in request.session_id):
            return SharedActivityResponse('unavailable', problem_code='living-presence-invalid')
        try:
            return self._host.heartbeat_living_presence(self._binding, request)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='living-presence-unverified')

    def set_living_controls(self, request):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse
        from dynamic_subject_agent.living_activity import LivingControlRequest
        self._require_open()
        if (type(request) is not LivingControlRequest or request.target_profile_id != self._binding.profile_id
            or request.target_timeline_id != self._binding.timeline_id or type(request.expected_permission_revision) is not int
            or request.expected_permission_revision < 0 or type(request.request_id) is not str
            or any(value is not None and type(value) is not bool for value in (request.paused, request.sharing_enabled))
            or request.paused is None and request.sharing_enabled is None):
            return SharedActivityResponse('unavailable', problem_code='living-control-invalid')
        if request.confirmed is not True:
            return SharedActivityResponse('cancelled')
        try:
            return self._host.set_living_controls(self._binding, request)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='living-control-unverified')

    def set_shared_experience(self, request):
        from dynamic_subject_agent.shared_activity import SharedExperienceRequest, SharedActivityResponse, WORKING_AUTHORITIES
        if self._binding.provider_authority in WORKING_AUTHORITIES:
            return SharedActivityResponse('unavailable',problem_code='working-e1-selection-unavailable')
        return self._apply_shared_activity(request, SharedExperienceRequest)

    def advance_shared_activity(self, request):
        from dynamic_subject_agent.shared_activity import SharedActivityStepRequest
        return self._apply_shared_activity(request, SharedActivityStepRequest)

    def _apply_shared_activity(self, request, expected_type):
        from dynamic_subject_agent.shared_activity import SharedActivityResponse, SharedExperienceRequest
        self._require_open()
        if (type(request) is not expected_type or request.target_profile_id != self._binding.profile_id
            or request.target_timeline_id != self._binding.timeline_id
            or type(request.expected_revision) is not int or request.expected_revision < 0):
            return SharedActivityResponse('unavailable', problem_code='shared-request-invalid')
        if expected_type is SharedExperienceRequest:
            if request.confirmed is False:
                return SharedActivityResponse('cancelled')
            if request.confirmed is not True:
                return SharedActivityResponse('unavailable', problem_code='shared-confirmation-required')
        try:
            return self._host.apply_shared_activity(self._binding, request)
        except PreAdmissionRejected as error:
            return SharedActivityResponse('unavailable', problem_code=error.code)
        except Exception:
            return SharedActivityResponse('failed-closed', problem_code='shared-operation-unverified')

    def query_whole_context_boundary(self, request=None):
        self._require_open()
        try:
            if request is not None:
                from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
                if (type(request) is not WholeContextBoundaryRequest or request.confirmed is not True
                    or type(request.expected_revision) is not int or request.expected_revision < 0
                    or request.target_profile_id != self._binding.profile_id or request.target_timeline_id != self._binding.timeline_id):
                    return dict(status='unavailable', problem_code='whole-context-target-mismatch')
            scope = self._host._read_whole_context(self._binding, request)
            if request is not None:
                existing = scope.pop('existing', dict(status='not-found', receipt=None))
                scope['request_status'], scope['receipt'] = existing['status'], existing['receipt']
            return scope
        except Exception:
            return dict(status='unavailable', problem_code='whole-context-unverified')

    def apply_whole_context_boundary(self, request):
        from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest, WholeContextBoundaryResponse
        self._require_open()
        if type(request) is not WholeContextBoundaryRequest:
            return WholeContextBoundaryResponse('unavailable', problem_code='typed-whole-context-request-required')
        if request.confirmed is False:
            return WholeContextBoundaryResponse('cancelled')
        if (request.confirmed is not True or request.target_profile_id != self._binding.profile_id
            or request.target_timeline_id != self._binding.timeline_id or type(request.expected_revision) is not int or request.expected_revision < 0):
            return WholeContextBoundaryResponse('unavailable', problem_code='whole-context-target-or-confirmation-invalid')
        try:
            return self._host.apply_whole_context_boundary(self._binding, request)
        except RuntimeHostRejected as error:
            return WholeContextBoundaryResponse('unavailable', problem_code=error.code if error.code == 'whole-context-unavailable' else 'whole-context-unverified')
        except Exception:
            return WholeContextBoundaryResponse('failed-closed', problem_code='whole-context-unverified')

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
            subject_tasks = self._list_subject_tasks() if query.kind is ApplicationQueryKind.SUBJECT_TASKS else None
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
            subject_tasks=subject_tasks,
        )

    def subject_task(self, command: object, *, idempotency_key: str) -> ApplicationOperationResponse:
        if type(command) is not SubjectTaskCommand:
            return _unavailable('typed-subject-task-required')
        return self.submit(SubjectCommand.contribute_utterance(target_profile_id=self._binding.profile_id,
            target_timeline_id=self._binding.timeline_id, declared_intent=TASK_INTENT,
            utterance=command.to_json(),language='zh',provenance='project-original'),idempotency_key=idempotency_key)

    def _list_subject_tasks(self):
        with self._lease() as lease:
            return lease.list_subject_tasks()

    def preview_text_artifact(self, task_id, revision):
        try:
            with self._lease() as lease:
                preview=lease.preview_text_artifact(task_id,revision)
            return TextArtifactResponse('available',preview) if preview else TextArtifactResponse('unavailable',message='当前任务不能保存；请确认已接受、正文完整且身份支持保存。')
        except Exception:
            return TextArtifactResponse('failed-closed',message='无法核实保存预览。')

    def approve_text_artifact(self, approval, *, idempotency_key):
        if type(approval) is not TextSaveApproval:
            return _unavailable('typed-text-save-approval-required')
        return self.submit(SubjectCommand.contribute_utterance(target_profile_id=self._binding.profile_id,
            target_timeline_id=self._binding.timeline_id,declared_intent=TEXT_EFFECT_INTENT,
            utterance=approval.to_json(),language='zh',provenance='project-original'),idempotency_key=idempotency_key)

    def recover_text_artifacts(self):
        from dynamic_subject_agent.host import TEXT_EFFECT_CONTRACT_VERSION
        if self._binding.runtime_contract_version!=TEXT_EFFECT_CONTRACT_VERSION:
            return TextArtifactResponse('unavailable',message='此身份尚未启用文本保存。')
        try:
            with self._lease() as lease:
                lease.recover_text_artifacts()
            return TextArtifactResponse('available',message='已核对先前批准的保存操作，请查看任务结果。')
        except Exception:
            return TextArtifactResponse('failed-closed',message='保存结果尚不能核实，没有重复执行未知操作。')

    def extract_character_evidence(self, request: object) -> EvidenceExtractionView:
        with self._lock:
            if self._closed or self._evidence_extraction is None:
                return EvidenceExtractionView("unavailable", "evidence-extraction-unavailable")
            return self._evidence_extraction.extract(request)

    def evaluate_reply_protocol(self, request):
        with self._lock:
            if self._closed or self._reply_protocol_trial is None:
                return _unavailable("reply-protocol-trial-unavailable")
            return self._reply_protocol_trial.evaluate(request)

    def preview_character_reply(self, request: object) -> CharacterReplyCandidateView:
        with self._lock:
            producer = self._character_reply_lab
            context_request = producer.context_request(request) if producer is not None else request
            view = preview_reply(self.preview_character_chat_context(context_request))
            return producer.preview(view, request=request) if producer is not None else view

    def propose_character_reply(self, request: object) -> CharacterReplyCandidateView:
        with self._lock:
            if self._closed or self._character_reply_lab is None:
                return CharacterReplyCandidateView("unavailable", "character-reply-lab-unavailable")
            return self._character_reply_lab.propose(self.preview_character_reply(request))

    def preview_character_chat_context(self, request: object) -> CharacterChatContextView:
        with self._lock:
            if self._closed or self._character_model is None:
                return CharacterChatContextView("unavailable", "character-model-unavailable")
            if not valid_request(request):
                return CharacterChatContextView("rejected", "invalid-chat-context-request")
            model = self._character_model.preview(CharacterModelRequest(request.subject_id, request.anchor_id))
            return prepare_context(model, request.current_message, context_mode=request.context_mode,
                                   max_knowledge_chars=request.max_knowledge_chars)

    def preview_character_model(self, request: object) -> CharacterModelView | CharacterContextView:
        with self._lock:
            if self._closed or self._character_model is None:
                view_type = CharacterContextView if type(request) is CharacterContextRequest else CharacterModelView
                return view_type("unavailable", "character-model-unavailable")
            return self._character_model.preview(request)

    def preview_character_identity_preparation(self, request: object) -> CharacterIdentityPreparationView:
        with self._lock:
            if type(request) is CharacterDefinitionPreparationRequest:
                model = self.preview_character_model(CharacterModelRequest(request.subject_id, request.anchor_id))
                return prepare_character_identity(model, personality_request=request)
            return prepare_character_identity(self.preview_character_model(request))

    def preview_conversation_basis(self, request: object) -> BasisPreview:
        with self._lock:
            if self._closed or self._basis_preview is None:
                return BasisPreview("unavailable", "basis-preview-unavailable")
            return self._basis_preview.preview(request)

    def character_dialogue_status(self) -> DialogueView:
        with self._lock:
            if self._closed or self._character_dialogue is None:
                return DialogueView("unavailable", "character-dialogue-unavailable")
            return self._character_dialogue.status()

    def start_character_dialogue_interactive(self) -> DialogueView:
        with self._lock:
            if self._closed or self._character_dialogue is None:
                return DialogueView("unavailable", "character-dialogue-unavailable")
            return self._character_dialogue.start_interactive()

    def character_dialogue_send(self, request: object) -> DialogueView:
        with self._lock:
            if self._closed or self._character_dialogue is None:
                return DialogueView("unavailable", "character-dialogue-unavailable")
            return self._character_dialogue.send(request)

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

    def freeze_first_life_identity(self, request):
        from dynamic_subject_agent.first_life import FirstLifeIdentityRequest
        if type(request) is not FirstLifeIdentityRequest or self._first_life_freezer is None:
            return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.UNAVAILABLE, problem_code="first-life-freeze-unavailable")
        try: return self._first_life_freezer(request)
        except Exception: return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.FAILED_CLOSED, problem_code="first-life-freeze-unverified")

    def _life_basis(self):
        if self._life_clock is not None and self._life_clock.busy() and self._last_life_basis is not None:
            return self._last_life_basis
        with self._lease() as lease: value = lease.first_life_basis()
        self._last_life_basis = value
        return value

    def first_life_status(self):
        from dynamic_subject_agent.first_life import FirstLifeStatus
        self._require_open()
        if self._life_budget is None: return FirstLifeStatus("unavailable", problem_code="first-life-unavailable")
        try:
            basis = self._life_basis()
            total, used, remaining = self._life_budget.counts()
            decisions, shares, dev_remaining = self._life_budget.life_counts(self._life_day(), development_run=self._life_development)
            chat = self.reviewed_character_chat_status()
            return FirstLifeStatus("needs-attention" if basis.technical_problem else "paused" if basis.record.paused else "active",
                chat.subject_name, basis.record.paused, basis.record.sharing_enabled, chat.history_enabled,
                basis.record.phase, basis.record.revision, basis.record.virtual_minutes, basis.unanswered_share,
                total, used, remaining, decisions, shares, self._life_development, dev_remaining, basis.technical_problem,
                basis.context_start_sequence)
        except Exception: return FirstLifeStatus("failed-closed", problem_code="first-life-status-unverified")

    def query_first_life(self):
        from dynamic_subject_agent.first_life import FirstLifeQuery
        self._require_open()
        if self._life_budget is None: return FirstLifeQuery("unavailable", problem_code="first-life-unavailable")
        if self._life_clock is not None and self._life_clock.busy() and self._last_life_query is not None:
            return self._last_life_query
        try:
            with self._lease() as lease: value = lease.list_first_life()
            self._last_life_query = value
            return value
        except Exception as error:
            if getattr(error, "code", None) == "runtime-lease-contended":
                return FirstLifeQuery("unavailable", problem_code="first-life-query-pending")
            return FirstLifeQuery("failed-closed", problem_code="first-life-query-unverified")

    @staticmethod
    def _life_noop(code):
        return ApplicationOperationResponse(ApplicationOperationStatus.TERMINAL, None, None, ApplicationProblemView(code))

    def _submit_life_input(self, input, request_id):
        handed_off = False
        try:
            digest = sha256(request_id.encode()).hexdigest()
            with self._lease() as lease: admitted = lease.admit_first_life(input, idempotency_key=request_id)
            response = _from_runtime_result(admitted)
            if response.status is ApplicationOperationStatus.PENDING:
                with self._lock:
                    active = self._start_resume(admitted.operation_ref, key_digest=digest, payload_fingerprint=admitted.operation_ref.admitted_payload_fingerprint)
                    active.future.add_done_callback(lambda future: self._life_clock.finished())
                    handed_off = True
            return response
        except PayloadConflict as error: return _conflict(error.existing_operation_ref)
        except Exception as error: return _map_problem(error)
        finally:
            if not handed_off and self._life_clock is not None: self._life_clock.finished()

    @staticmethod
    def _life_request_digest(request):
        return sha256(json.dumps(dict(type=type(request).__name__, **asdict(request)), sort_keys=True).encode()).hexdigest()

    def _replay_life_request(self, request):
        try:
            digest = self._life_request_digest(request)
            with self._lease() as lease: result = lease.replay_first_life_request(request.request_id, digest)
            if result is None: return None
            response = _from_runtime_result(result)
            if response.status is ApplicationOperationStatus.PENDING:
                with self._lock:
                    self._start_resume(result.operation_ref, key_digest=sha256(request.request_id.encode()).hexdigest(),
                        payload_fingerprint=result.operation_ref.admitted_payload_fingerprint)
            return response
        except PayloadConflict as error: return _conflict(error.existing_operation_ref)
        except Exception as error: return _map_problem(error)

    def set_first_life_controls(self, request):
        from dynamic_subject_agent.first_life import FirstLifeControlRequest, FirstLifeInput
        self._require_open()
        if (type(request) is not FirstLifeControlRequest or self._life_budget is None
            or any(value is not None and type(value) is not bool for value in (request.paused, request.sharing_enabled))
            or request.paused is None and request.sharing_enabled is None): return _unavailable("typed-life-control-required")
        replayed = self._replay_life_request(request)
        if replayed is not None: return replayed
        data = self._life_request_digest(request)
        input = FirstLifeInput(self._binding.profile_id, self._binding.timeline_id, "control", "control", self._life_day(), data,
            request.paused, request.sharing_enabled)
        if request.paused is not None:
            self._life_clock.reset_pause()
        return self._submit_life_input(input, request.request_id)

    def reset_first_life_context(self, request):
        from dynamic_subject_agent.first_life import FirstLifeContextResetRequest, FirstLifeInput, CONTEXT_RESET_KIND
        self._require_open()
        if (type(request) is not FirstLifeContextResetRequest or request.confirmed is not True
            or not isinstance(request.request_id, str) or not 1 <= len(request.request_id) <= 256
            or self._life_budget is None):
            return _unavailable("confirmed-chat-context-reset-required")
        replayed = self._replay_life_request(request)
        if replayed is not None:
            return replayed
        input = FirstLifeInput(self._binding.profile_id, self._binding.timeline_id,
            CONTEXT_RESET_KIND, "control", self._life_day(), self._life_request_digest(request))
        return self._submit_life_input(input, request.request_id)

    def simulate_first_life_step(self, request):
        from dynamic_subject_agent.first_life import FirstLifeSimulationRequest
        self._require_open()
        if type(request) is not FirstLifeSimulationRequest or self._life_budget is None: return _unavailable("typed-life-simulation-required")
        replayed = self._replay_life_request(request)
        if replayed is not None: return replayed
        try: basis = self._life_basis()
        except Exception: return _unavailable("first-life-basis-unverified")
        if not self._life_clock.simulation(paused=basis.record.paused): return self._life_noop("life-paused-or-pending")
        return self._schedule_life(request, basis, "advance", "simulation")

    def heartbeat_first_life(self, request):
        from dynamic_subject_agent.first_life import FirstLifeHeartbeatRequest
        self._require_open()
        if (type(request) is not FirstLifeHeartbeatRequest or not isinstance(request.session_id, str)
            or not 16 <= len(request.session_id) <= 256 or self._life_budget is None): return _unavailable("typed-life-heartbeat-required")
        with self._lock:
            pending = any(not active.future.done() for active in self._active_by_operation.values())
            last_basis = self._last_life_basis
        if pending:
            # A renewal is an online presence input, not a new canonical or
            # model operation. Never contend for the writer behind a future.
            paused = True if last_basis is None else last_basis.record.paused
            _, code = self._life_clock.heartbeat(request.session_id, paused=paused, allow_step=False)
            return self._life_noop(code)
        replayed = self._replay_life_request(request)
        if replayed is not None: return replayed
        try: basis = self._life_basis()
        except Exception: return _unavailable("first-life-basis-unverified")
        due, code = self._life_clock.heartbeat(request.session_id, paused=basis.record.paused)
        if code == "another-life-window": return self._life_noop(code)
        if due: return self._schedule_life(request, basis, "advance", "online")
        if (not self._life_clock.busy() and basis.events and basis.has_dialogue and basis.record.sharing_enabled
            and not basis.unanswered_share and not basis.technical_problem):
            event = basis.events[-1]
            if event.event_id not in basis.disclosed_event_ids and event.event_id not in basis.considered_event_ids and self._life_clock.share():
                return self._schedule_life(request, basis, "share", "online", event.event_id)
        return self._life_noop(code)

    def _schedule_life(self, request, basis, kind, trigger, target=""):
        from dynamic_subject_agent.first_life import FirstLifeInput
        try:
            decisions, shares, dev = self._life_budget.life_counts(self._life_day(), development_run=self._life_development)
            if (basis.technical_problem or kind == "advance" and basis.record.phase in ("kept", "deferred")
                or kind == "advance" and decisions >= 6 or kind == "share" and shares >= 2
                or dev is not None and dev <= 0 or self._life_budget.counts()[2] <= 0):
                self._life_clock.finished()
                return self._life_noop("life-no-permitted-boundary")
            data = self._life_request_digest(request)
            input = FirstLifeInput(self._binding.profile_id, self._binding.timeline_id, kind, trigger, self._life_day(), data, target_event_id=target)
            return self._submit_life_input(input, request.request_id)

        except Exception:
            self._life_clock.finished()
            return _unavailable("first-life-scheduling-unverified")

    def reviewed_character_chat_status(self):
        from dynamic_subject_agent.reviewed_character_chat import ReviewedCharacterChatStatus
        with self._lock:
            self._require_open()
            callback = self._reviewed_chat_status
        return callback() if callback is not None else ReviewedCharacterChatStatus("unavailable", problem_code="reviewed-character-chat-unavailable")

    def query_character_basis(self):
        from dynamic_subject_agent.character_basis import CharacterBasisView
        with self._lock:
            if self._closed or self._character_basis_reader is None:
                return CharacterBasisView('unavailable', 'character-basis-unavailable')
            callback = self._character_basis_reader
        try:
            view = callback()
            with self._lock:
                return CharacterBasisView('unavailable', 'character-basis-unavailable') if self._closed else view
        except Exception:
            return CharacterBasisView('failed-closed', 'character-basis-unverified')

    def preview_whole_message_scope(self, request):
        from dynamic_subject_agent.whole_message_scope import WholeMessageScopePreviewRequest, WholeMessageScopePreviewView
        from dynamic_subject_agent.original_whole_chat import projection_for_contract, validate_whole_envelope, digest, contract_variant
        from dynamic_subject_agent.character_chat_context import SelfKnowledge
        if (self._closed or type(request) is not WholeMessageScopePreviewRequest or self._whole_scope_reader is None
            or request.target_profile_id != self._binding.profile_id or request.target_timeline_id != self._binding.timeline_id):
            return WholeMessageScopePreviewView('unavailable','whole-scope-unavailable')
        try:
            command=SubjectCommand.contribute_utterance(target_profile_id=request.target_profile_id,target_timeline_id=request.target_timeline_id,
                declared_intent='ask-collaborator-status',utterance=request.text,language='zh',provenance='project-original')
            if len(command.utterance)>1000:
                return WholeMessageScopePreviewView('unavailable','whole-scope-message-invalid')
            source=self._whole_scope_reader()
            validate_whole_envelope(source['envelope'],source['contract'])
            if contract_variant(source['contract']) == 'followup-legacy':
                return WholeMessageScopePreviewView('unavailable','whole-scope-receipt-only')
            authorization=source['authorization']
            dialogue,basis,context=self._host.preview_whole_message_scope(self._binding,command.utterance,authorization.history_enabled)
            if dialogue.status!='available':
                return WholeMessageScopePreviewView('unavailable','whole-scope-pending-or-restricted')
            projection=projection_for_contract(source['envelope'],source['identity'],command.utterance,dialogue,authorization.history_enabled,source['contract'])
            current=self._whole_scope_reader()
            if current['authorization']!=authorization or current['contract']!=source['contract'] or self._closed:
                return WholeMessageScopePreviewView('unavailable','whole-scope-changed')
            # A final read fences publication/control changes during selection.
            latest_dialogue,latest_basis,latest_context=self._host.preview_whole_message_scope(self._binding,command.utterance,authorization.history_enabled)
            final_source=self._whole_scope_reader()
            if (latest_dialogue.status!='available' or latest_basis!=basis or latest_context!=context
                or final_source['authorization']!=authorization or final_source['contract']!=source['contract'] or self._closed):
                return WholeMessageScopePreviewView('unavailable','whole-scope-changed')
            return WholeMessageScopePreviewView('available',current_message=command.utterance,history_enabled=authorization.history_enabled,
                has_prior_committed_exchange=dialogue.has_prior_committed_exchange,
                character_core=tuple(SelfKnowledge(**row) for row in projection.background['character_core']),
                self_knowledge=tuple(SelfKnowledge(**row) for row in projection.background['self_knowledge']),
                personality_count=len(projection.background['personality']),recent_dialogue=projection.exchange,
                context_revision=context['context_revision'],cutoff_sequence=context['cutoff_sequence'],
                projection_digest=digest(asdict(projection)),snapshot_fingerprint=digest(dict(basis=asdict(basis),authorization=asdict(authorization),
                    context=context,command=command.payload_fingerprint)),
                limitations=('这里展示当前文字和设置对应的参考内容，不说明模型如何思考，也不保证回复真实。',
                    '文字、人物、历史开关或交流边界变化后请重新查看；发送时会按最新状态重新核对。'))
        except RuntimeError as error:
            return WholeMessageScopePreviewView('unavailable','whole-scope-unavailable')
        except PreAdmissionRejected:
            return WholeMessageScopePreviewView('unavailable','whole-scope-message-invalid')
        except Exception:
            return WholeMessageScopePreviewView('failed-closed','whole-scope-unverified')

    def query_whole_chat_archive(self, request):
        from dynamic_subject_agent.whole_chat_archive import WholeChatArchiveRequest, WholeChatArchiveView
        if (self._closed or type(request) is not WholeChatArchiveRequest or self._whole_archive_reader is None
            or request.target_profile_id != self._binding.profile_id or request.target_timeline_id != self._binding.timeline_id):
            return WholeChatArchiveView('unavailable', 'whole-archive-unavailable')
        if (type(request.query) is not str or len(request.query) > 1000 or '\x00' in request.query
            or request.before_sequence is not None and (type(request.before_sequence) is not int or request.before_sequence < 1)):
            return WholeChatArchiveView('unavailable', 'whole-archive-request-invalid')
        try:
            request.query.encode('utf-8')
            authorization = self._whole_archive_reader()
            view = self._host.query_whole_chat_archive(self._binding, request)
            if self._closed or self._whole_archive_reader() != authorization:
                return WholeChatArchiveView('unavailable', 'whole-archive-scope-changed')
            return view
        except PreAdmissionRejected:
            return WholeChatArchiveView('unavailable', 'whole-archive-request-invalid')
        except RuntimeError:
            return WholeChatArchiveView('unavailable', 'whole-archive-unavailable')
        except Exception:
            return WholeChatArchiveView('failed-closed', 'whole-archive-unverified')

    def set_reviewed_character_history(self, enabled):
        from dynamic_subject_agent.reviewed_character_chat import ReviewedCharacterChatStatus
        with self._lock:
            self._require_open()
            callback = self._reviewed_history_setter
        return callback(enabled) if callback is not None else ReviewedCharacterChatStatus("unavailable", problem_code="reviewed-character-chat-unavailable")

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
        if self._character_dialogue is not None:
            self._character_dialogue.close()
        if self._evidence_extraction is not None:
            self._evidence_extraction.close()
        if self._reply_protocol_trial is not None:
            self._reply_protocol_trial.close()
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

    def subject_task(self, command: object, *, idempotency_key: str) -> ApplicationOperationResponse:
        return self.__router.subject_task(command,idempotency_key=idempotency_key)

    def preview_text_artifact(self, task_id, revision):
        return self.__router.preview_text_artifact(task_id,revision)

    def approve_text_artifact(self, approval, *, idempotency_key):
        return self.__router.approve_text_artifact(approval,idempotency_key=idempotency_key)

    def recover_text_artifacts(self):
        return self.__router.recover_text_artifacts()

    def follow(self, operation_ref: object) -> ApplicationOperationResponse:
        return self.__router.follow(operation_ref)

    def lookup_subject_request(self, request: object) -> SubjectRequestLookupResponse:
        return self.__router.lookup_subject_request(request)

    def query_shared_activity(self, request=None):
        return self.__router.query_shared_activity(request)

    def query_working_understanding(self, request=None):
        return self.__router.query_working_understanding(request)

    def preview_working_understanding(self, request):
        return self.__router.preview_working_understanding(request)

    def apply_working_understanding(self, request):
        return self.__router.apply_working_understanding(request)

    def preview_working_activity(self, purpose='choice', text=''):
        return self.__router.preview_working_activity(purpose,text)

    def advance_working_activity(self, request):
        return self.__router.advance_working_activity(request)

    def query_living_activity(self, request=None):
        return self.__router.query_living_activity(request)

    def query_living_controls(self):
        return self.__router.query_living_controls()

    def preview_living_activity(self, purpose='choice', text=''):
        return self.__router.preview_living_activity(purpose, text)

    def advance_living_activity(self, request):
        return self.__router.advance_living_activity(request)

    def heartbeat_living_presence(self, request):
        return self.__router.heartbeat_living_presence(request)

    def set_living_controls(self, request):
        return self.__router.set_living_controls(request)

    def preview_shared_activity_step(self):
        return self.__router.preview_shared_activity_step()

    def set_shared_experience(self, request):
        return self.__router.set_shared_experience(request)

    def advance_shared_activity(self, request):
        return self.__router.advance_shared_activity(request)

    def query_whole_context_boundary(self, request=None):
        return self.__router.query_whole_context_boundary(request)

    def apply_whole_context_boundary(self, request):
        return self.__router.apply_whole_context_boundary(request)

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

    def extract_character_evidence(self, request: object) -> EvidenceExtractionView:
        return self.__router.extract_character_evidence(request)

    def preview_character_model(self, request: object) -> CharacterModelView | CharacterContextView:
        return self.__router.preview_character_model(request)

    def preview_character_identity_preparation(self, request: object) -> CharacterIdentityPreparationView:
        return self.__router.preview_character_identity_preparation(request)

    @staticmethod
    def preview_original_character_whole_use_preparation(request: object):
        """Pure author review; does not create or open a product authority."""
        from dynamic_subject_agent.original_whole_use_preparation import prepare_original_whole_use
        return prepare_original_whole_use(request)

    def evaluate_reply_protocol(self, request):
        return self.__router.evaluate_reply_protocol(request)

    def preview_character_reply(self, request: object) -> CharacterReplyCandidateView:
        return self.__router.preview_character_reply(request)

    def propose_character_reply(self, request: object) -> CharacterReplyCandidateView:
        return self.__router.propose_character_reply(request)

    def preview_character_chat_context(self, request: object) -> CharacterChatContextView:
        return self.__router.preview_character_chat_context(request)

    def preview_conversation_basis(self, request: object) -> BasisPreview:
        return self.__router.preview_conversation_basis(request)

    def character_dialogue_status(self) -> DialogueView:
        return self.__router.character_dialogue_status()

    def start_character_dialogue_interactive(self) -> DialogueView:
        return self.__router.start_character_dialogue_interactive()

    def character_dialogue_send(self, request: object) -> DialogueView:
        return self.__router.character_dialogue_send(request)

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

    def freeze_first_life_identity(self, request):
        return self.__router.freeze_first_life_identity(request)

    def first_life_status(self):
        return self.__router.first_life_status()

    def query_first_life(self):
        return self.__router.query_first_life()

    def set_first_life_controls(self, request):
        return self.__router.set_first_life_controls(request)

    def reset_first_life_context(self, request):
        return self.__router.reset_first_life_context(request)

    def heartbeat_first_life(self, request):
        return self.__router.heartbeat_first_life(request)

    def simulate_first_life_step(self, request):
        return self.__router.simulate_first_life_step(request)

    def reviewed_character_chat_status(self):
        return self.__router.reviewed_character_chat_status()

    def query_character_basis(self):
        return self.__router.query_character_basis()

    def preview_whole_message_scope(self, request):
        return self.__router.preview_whole_message_scope(request)

    def query_whole_chat_archive(self, request):
        return self.__router.query_whole_chat_archive(request)

    def set_reviewed_character_history(self, enabled):
        return self.__router.set_reviewed_character_history(enabled)

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
    _character_dialogue: CharacterDialogueSession | None = None,
    _basis_preview: ConversationBasisPreview | None = None,
    _character_model: CharacterEvidenceModel | None = None,
    _character_reply_lab: CharacterReplyProducer | None = None,
    _evidence_extraction: EvidenceExtractionLab | None = None,
    _reply_protocol_trial: ReplyProtocolTrial | None = None,
    _source_authoring: TextSourceCharacterAuthoring | None = None,
    _source_studio_location: StudioRootRef | None = None,
    _source_identity_freezer: Callable[[object], SourceIdentityFreezeResponse]
    | None = None,
    _first_life_freezer=None,
    _first_life_budget=None,
    _first_life_clock=None,
    _first_life_day=None,
    _first_life_development=False,
    _reviewed_chat_status=None,
    _character_basis_reader=None,
    _whole_scope_reader=None,
    _whole_archive_reader=None,
    _reviewed_history_setter=None,
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
        character_dialogue=_character_dialogue,
        basis_preview=_basis_preview,
        character_model=_character_model,
        character_reply_lab=_character_reply_lab,
        evidence_extraction=_evidence_extraction,
        reply_protocol_trial=_reply_protocol_trial,
        source_authoring=_source_authoring,
        source_studio_location=_source_studio_location,
        source_identity_freezer=_source_identity_freezer,
        first_life_freezer=_first_life_freezer,
        first_life_budget=_first_life_budget,
        first_life_clock=_first_life_clock,
        first_life_day=_first_life_day,
        first_life_development=_first_life_development,
        reviewed_chat_status=_reviewed_chat_status,
        character_basis_reader=_character_basis_reader,
        whole_scope_reader=_whole_scope_reader,
        whole_archive_reader=_whole_archive_reader,
        reviewed_history_setter=_reviewed_history_setter,
        local_identity_lister=_local_identity_lister,
        local_identity_selector=_local_identity_selector,
        knowledge_entries=_knowledge_entries,
    )
    return (
        ApplicationFacade(router, _token=_APPLICATION_FACADE_TOKEN),
        router,
    )


def _subject_task_record(outcome) -> SubjectTaskRecord | None:
    if outcome.decision.rule_version not in ('agency-task-1.0','agency-text-effect-1.0'):
        return None
    record = json.loads(outcome.decision.reason)['subject_task']
    return SubjectTaskRecord.from_dict(record) if record is not None else None


def _from_runtime_result(result: RuntimeResult) -> ApplicationOperationResponse:
    state = result.snapshot.operation_state
    if state is OperationState.COMPLETED and result.outcome is not None:
        projection = AuthorizedOperationProjection(
            committed_effect_count=len(result.outcome.committed_effect_set.reference_ids),
            subject_task=_subject_task_record(result.outcome.agency_outcome),
            operation_kind=result.operation_ref.operation_kind,
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
        reported_status = (ApplicationOperationStatus.UNAVAILABLE if failure is not None and failure.code in ("original-whole-character-credential-unavailable", "reviewed-chat-character-credential-unavailable", "reviewed-chat-budget-unavailable", "first-life-character-credential-unavailable", "first-life-share-character-credential-unavailable", "first-life-budget-unavailable", "first-life-share-not-attempted")
            else ApplicationOperationStatus.UNKNOWN if failure is not None and failure.code in ("original-whole-transport-timeout", "original-whole-transport-delivery-ambiguous", "reviewed-chat-transport-timeout", "reviewed-chat-transport-delivery-ambiguous", "reviewed-chat-attempt-unavailable", "first-life-transport-timeout", "first-life-transport-delivery-ambiguous", "first-life-share-transport-timeout", "first-life-share-transport-delivery-ambiguous")
            else ApplicationOperationStatus.FAILED_CLOSED)
        projection = AuthorizedOperationProjection(
            operation_kind=result.operation_ref.operation_kind,
            operation_state=reported_status,
            timeline_outcome_id=None,
            timeline_head_sequence=result.snapshot.timeline_head_sequence,
            expression_text=None,
            expression_language=None,
            failure_stage=None if failure is None else failure.stage,
            failure_code=None if failure is None else failure.code,
        )
        return ApplicationOperationResponse(
            status=reported_status,
            operation_ref=result.operation_ref,
            projection=projection,
            problem=ApplicationProblemView(failure.code if failure is not None and reported_status in (ApplicationOperationStatus.UNAVAILABLE, ApplicationOperationStatus.UNKNOWN) else "operation-failed-closed"),
            replayed=result.admission_replayed,
        )
    if state is OperationState.INTERRUPTED:
        return ApplicationOperationResponse(
            status=ApplicationOperationStatus.INTERRUPTED,
            operation_ref=result.operation_ref,
            projection=AuthorizedOperationProjection(
                operation_kind=result.operation_ref.operation_kind,
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
    subject_tasks: tuple[SubjectTaskRecord, ...] | None = None,
) -> ApplicationQueryResponse:
    if kind is ApplicationQueryKind.SUBJECT_TASKS and subject_tasks is not None:
        from dynamic_subject_agent.host import SUBJECT_TASK_CONTRACT_VERSION, TEXT_EFFECT_CONTRACT_VERSION
        projection = SubjectTasksApplicationProjection(subject_tasks,binding.runtime_contract_version in (SUBJECT_TASK_CONTRACT_VERSION,TEXT_EFFECT_CONTRACT_VERSION),
            binding.runtime_contract_version==TEXT_EFFECT_CONTRACT_VERSION,
            tuple((r.task_id,str(binding.timeline_root.root/'artifacts'/f'text-{r.task_id}-r{r.revision-2}.txt'))
                for r in subject_tasks if r.status=='completed' and r.reason=='saved'))
    elif kind is ApplicationQueryKind.CURRENT:
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
    "SubjectRequestLookupRequest",
    "SubjectRequestLookupResponse",
    "SubjectRequestLookupStatus",
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

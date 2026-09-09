"""M0-A SubjectRuntime walking skeleton and deterministic Fake Cognition.

SubjectRuntime is the sole owner of the Experience Cycle.  The injected Fake
Cognition adapter and four Domain Modules perform bounded computation only;
the private TimelineEngine remains the only canonical writer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep, time_ns
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    AgencyAdjudicationRequest,
    AgencyDomain,
    AgencyReadView,
    CompleteDomainOutcomeSet,
    DomainAdjudicationFailedClosed,
    DomainOutcomeSetRejected,
    ExperienceAdjudicationRequest,
    ExperienceBasis,
    ExperienceDomain,
    ExperienceImpactEnvelope,
    ExperienceImpactEnvelopeRejected,
    ExperienceReadView,
    RelationshipAdjudicationRequest,
    RelationshipDomain,
    RelationshipReadView,
    SubjectStateAdjudicationRequest,
    SubjectStateDomain,
    SubjectStateReadView,
)
from dynamic_subject_agent.timeline import (
    AdmissionSnapshot,
    CanonicalRootRef,
    CommittedEffectSet,
    ConversationTurnRecord,
    CycleCommitPlan,
    DecisionStatus,
    EffectDispatchState,
    EpistemicOutcome,
    ExperienceRecord,
    Expression,
    FixtureAuthority,
    LivingMemoryRecord,
    RelationshipStanceInteraction,
    OperationFailure,
    OperationRef,
    OperationState,
    PreAdmissionRejected,
    PublicationFailedClosed,
    RevisionSet,
    SubjectCommand,
    TimelineBasis,
    TimelineEngine,
    _ReservedTimelineIdentity,
    TimelineOutcome,
    _HOST_TIMELINE_TOKEN,
    _RuntimeBindingAuthority,
)
from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentRecord
from dynamic_subject_agent.situated_state import SituatedStateRecord, usable_state
from dynamic_subject_agent.medium_state import MediumSignalRecord, MediumStateRecord
from dynamic_subject_agent.temporal_grounding import TemporalGrounding
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
from dynamic_subject_agent.memory_retrieval import MemoryRetrievalUnavailable, select_memory_candidates
from dynamic_subject_agent.subject_time_continuity import (
    SubjectTimeContinuity,
    SubjectTimeHistoryFailedClosed,
    SubjectTimeResult,
)


M0_A_CYCLE_VERSION = "m0-a-cycle-1.0"
M0_A_EPISTEMIC_ROUTE_VERSION = "m0-epistemic-route-1"
M0_A_FAKE_COGNITION_VERSION = "m0-fake-cognition-1.0"
M0_A_PROVIDER_AUTHORITY = "fake-cognition:m0-a-cycle-1.0"
_TEMPORAL_GROUNDING = TemporalGrounding()
M0_A_STAGE_ORDER = (
    "load-exact-canonical-basis",
    "build-experience-basis",
    "fake-cognition-proposal",
    "experience-epistemic-adjudication",
    "subject-state-adjudication",
    "agency-adjudication",
    "relationship-adjudication",
    "validate-complete-outcomes",
    "fake-cognition-expression",
    "build-cycle-commit-plan",
    "atomic-publication",
)
M0_A_DOMAIN_PARTICIPATION = (
    "Experience",
    "SubjectState",
    "Agency",
    "Relationship",
)
_HOST_RUNTIME_TOKEN = object()


class RuntimeFaultPoint(str, Enum):
    """Deterministic orchestration boundaries exposed only to test runners."""

    AFTER_ADMISSION = "after-admission"
    AFTER_CYCLE_PLAN = "after-cycle-plan"
    AFTER_COGNITION = "after-cognition"
    AFTER_DOMAIN_OUTCOMES = "after-domain-outcomes"
    BEFORE_PUBLICATION = "before-publication"
    AFTER_PUBLICATION = "after-publication"


class RuntimeInterrupted(Exception):
    """A test-controlled interruption after canonical Admission."""

    def __init__(
        self,
        fault_point: RuntimeFaultPoint,
        operation_ref: OperationRef,
    ) -> None:
        super().__init__(f"runtime-interrupted: {fault_point.value}")
        self.fault_point = fault_point
        self.operation_ref = operation_ref


class FakeCognitionMode(str, Enum):
    """Explicit modes available only on the injected experimental Fake."""

    VALID = "valid"
    INVALID_OUTPUT = "invalid-output"
    EPISTEMIC_FAILURE = "epistemic-failure"


class RuntimeDomainFault(str, Enum):
    """One-Domain technical failure selector for the isolated test harness."""

    EXPERIENCE = "experience"
    SUBJECT_STATE = "subject-state"
    AGENCY = "agency"
    RELATIONSHIP = "relationship"


class M0AFixtureUnavailable(Exception):
    """The exact versioned project-original M0-A authority is unavailable."""


class CognitionFailedClosed(Exception):
    def __init__(self, stage: str, code: str, detail: str) -> None:
        super().__init__(f"{stage}:{code}: {detail}")
        self.stage = stage
        self.code = code
        self.detail = detail


class CycleFailedClosed(Exception):
    """A cycle reached a canonical failed-closed terminal fact."""

    def __init__(
        self,
        operation_ref: OperationRef,
        failure: OperationFailure,
    ) -> None:
        super().__init__(f"{failure.stage}:{failure.code}: {failure.detail}")
        self.operation_ref = operation_ref
        self.failure = failure


def _runtime_id(operation_id: str, attempt_id: str, name: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"m0-09:{operation_id}:{attempt_id}:{name}",
        )
    )


@dataclass(frozen=True)
class M0AFixture:
    """Versioned project-original authority for the isolated M0-A runner."""

    fixture_id: str
    scenario_id: str
    authority: FixtureAuthority
    declared_intent: str
    utterance: str
    language: str
    provenance: str
    relationship_enabled: bool
    experienced_at_us: int

    @classmethod
    def lantern_zine(cls) -> M0AFixture:
        profile_id = "c627e693-68f0-43f7-b3db-e55490b47b32"
        timeline_id = "471f4fd1-69fd-49df-aa14-3af405d301cf"
        declared_intent = "ask-collaborator-status"
        provenance = "project-original"
        return cls(
            fixture_id="lantern-zine-m0-05-v1",
            scenario_id="lantern-zine-print-slot-v1",
            authority=FixtureAuthority(
                authority_scope_id="91f6a5fc-22dc-482b-b482-5ca9089d1e69",
                profile_id=profile_id,
                timeline_id=timeline_id,
                allowed_intents=(declared_intent,),
                allowed_provenance=(provenance,),
            ),
            declared_intent=declared_intent,
            utterance=(
                "Could you check whether the lantern issue can still make "
                "Friday's print slot?"
            ),
            language="en",
            provenance=provenance,
            relationship_enabled=False,
            experienced_at_us=1_800_000_000_000_000,
        )

    def require_authority(self) -> None:
        if self != type(self).lantern_zine():
            raise M0AFixtureUnavailable(
                "only lantern-zine-m0-05-v1 has M0-A fixture authority"
            )

    def command(self) -> SubjectCommand:
        return SubjectCommand.contribute_utterance(
            target_profile_id=self.authority.profile_id,
            target_timeline_id=self.authority.timeline_id,
            declared_intent=self.declared_intent,
            utterance=self.utterance,
            language=self.language,
            provenance=self.provenance,
        )

    def validate_command(self, command: SubjectCommand) -> None:
        if command != self.command():
            raise PreAdmissionRejected(
                "fixture-command-unavailable",
                "M0-A accepts only the frozen project-original fixture command",
            )


@dataclass(frozen=True)
class _RuntimeContext:
    runtime_authority_id: str
    authority: FixtureAuthority | _RuntimeBindingAuthority
    kind: str
    relationship_enabled: bool
    experienced_at_us: int
    runtime_identity: RuntimeIdentityProjection | None
    fixture: M0AFixture | None = None

    @classmethod
    def from_fixture(cls, fixture: M0AFixture) -> _RuntimeContext:
        fixture.require_authority()
        return cls(
            runtime_authority_id=fixture.fixture_id,
            authority=fixture.authority,
            kind="m0-a-fixture",
            relationship_enabled=fixture.relationship_enabled,
            experienced_at_us=fixture.experienced_at_us,
            runtime_identity=None,
            fixture=fixture,
        )

    @classmethod
    def from_binding(
        cls,
        authority: _RuntimeBindingAuthority,
        *,
        experienced_at_us: int,
        runtime_identity: RuntimeIdentityProjection | None,
        relationship_enabled: bool = False,
        _host_token: object,
    ) -> _RuntimeContext:
        if _host_token is not _HOST_RUNTIME_TOKEN:
            raise TypeError("RuntimeHost authority is required")
        return cls(
            runtime_authority_id=authority.binding_id,
            authority=authority,
            kind="published-qri-binding",
            relationship_enabled=relationship_enabled,
            experienced_at_us=experienced_at_us,
            runtime_identity=runtime_identity,
        )

    def validate_command(self, command: SubjectCommand) -> None:
        if self.fixture is not None:
            self.fixture.validate_command(command)
            return
        if (
            command.target_profile_id != self.authority.profile_id
            or command.target_timeline_id != self.authority.timeline_id
        ):
            raise PreAdmissionRejected(
                "binding-target-mismatch",
                "command target is outside the RuntimeAuthorityBinding",
            )

    def cognition_view(self) -> CognitionRuntimeView:
        return CognitionRuntimeView(
            runtime_authority_id=self.runtime_authority_id,
            profile_id=self.authority.profile_id,
            timeline_id=self.authority.timeline_id,
            provider_authority=(
                M0_A_PROVIDER_AUTHORITY
                if self.fixture is not None
                else self.authority.provider_authority
            ),
            relationship_enabled=self.relationship_enabled,
            fixture=self.fixture is not None,
            runtime_identity=self.runtime_identity,
        )


@dataclass(frozen=True)
class CyclePlan:
    cycle_plan_id: str
    cycle_version: str
    operation_ref: OperationRef
    attempt_id: str
    subject_event_id: str
    command_fingerprint: str
    expected_basis: TimelineBasis
    runtime_authority_id: str
    stage_order: tuple[str, ...]
    domain_participation: tuple[str, ...]
    committed_effects_available: bool


@dataclass(frozen=True)
class CognitionRuntimeView:
    runtime_authority_id: str
    profile_id: str
    timeline_id: str
    provider_authority: str
    relationship_enabled: bool
    fixture: bool
    active_memories: tuple[LivingMemoryRecord, ...] = ()
    living_memory_history: tuple[LivingMemoryRecord, ...] = ()
    relationship_stance_summary: str = ""
    participant_goal_commitments: tuple[ParticipantGoalCommitmentRecord, ...] = ()
    situated_state: SituatedStateRecord | None = None
    observed_at_us: int = 0
    medium_state: MediumStateRecord | None = None
    medium_signals: tuple[MediumSignalRecord, ...] = ()
    runtime_identity: RuntimeIdentityProjection | None = None
    subject_time_result: SubjectTimeResult = SubjectTimeResult.no_op()
    load_recent_dialogue: Callable[[], tuple[RecentDialogueTurn, ...]] | None = None
    load_withheld_memory_ids: Callable[[], tuple[str, ...]] | None = None
    memory_control_complete: bool = True
    canonical_memory_history: tuple[LivingMemoryRecord, ...] = ()
    memory_retrieval_unavailable: bool = False


@dataclass(frozen=True)
class CognitiveProposal:
    adapter_version: str
    experience_summary: str
    epistemic_outcome: EpistemicOutcome
    impact_envelope: ExperienceImpactEnvelope
    expression_candidate: ExpressionCandidate
    # Ephemeral composition information; never Provider input or canonical state.
    memory_write_requested: bool = False
    memory_continuation: ExpressionCandidate | None = None
    knowledge_continuation: ExpressionCandidate | None = None


@dataclass(frozen=True)
class ExpressionCandidate:
    text: str
    language: str
    # Ephemeral permission checked by capability cognition, never a state fact.
    is_creative: bool = False
    # A locally selected contextual reply or its honest restatement fallback.
    dialogue_priority: bool = False
    # Ephemeral capability-local rendering, not a persisted state or permission.
    is_memory_answer: bool = False


class CognitionEngine(ABC):
    """Bounded Cognition seam; implementations have no canonical write authority."""

    adapter_version: str
    provider_authority: str
    experimental: bool
    test_only: bool

    def preflight(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> None:
        del context, command

    def reserved_operation_id(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> str | None:
        del context, command
        return None

    @abstractmethod
    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        raise NotImplementedError

    def express(
        self,
        *,
        proposal: CognitiveProposal,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        outcomes: CompleteDomainOutcomeSet,
    ) -> ExpressionCandidate:
        del context, command, outcomes
        return proposal.expression_candidate

    def _bounded_noop_proposal(
        self,
        *,
        context: CognitionRuntimeView,
        basis: ExperienceBasis,
        experience_summary: str,
        expression_candidate: ExpressionCandidate,
    ) -> CognitiveProposal:
        epistemic = EpistemicOutcome(
            epistemic_outcome_id=basis.epistemic_outcome_id,
            status=DecisionStatus.NO_OP,
            reason="the bounded Cognition route preserved the verified prefix",
            route_version=M0_A_EPISTEMIC_ROUTE_VERSION,
            verified_prefix_digest=basis.verified_prefix_digest,
            completed_stages=(),
        )
        envelope = ExperienceImpactEnvelope(
            experience=ExperienceAdjudicationRequest(
                basis=basis,
                current_state=ExperienceReadView(
                    verified_prefix_digest=basis.verified_prefix_digest,
                    memory_trace_refs=(),
                ),
                candidates=(),
            ),
            subject_state=SubjectStateAdjudicationRequest(
                basis=basis,
                current_state=SubjectStateReadView(
                    subject_core_revision_refs=(),
                    development_revision_refs=(),
                ),
                situated_effect_candidates=(),
                development_candidates=(),
            ),
            agency=AgencyAdjudicationRequest(
                basis=basis,
                current_state=AgencyReadView(
                    intention_refs=(),
                    project_refs=(),
                    commitment_refs=(),
                    action_refs=(),
                ),
                candidates=(),
            ),
            relationship=RelationshipAdjudicationRequest(
                basis=basis,
                relationship_enabled=context.relationship_enabled,
                relationship_target_id=context.profile_id,
                current_state=RelationshipReadView(
                    relationship_target_id=context.profile_id,
                    subject_stance_revision_refs=(),
                    interaction_norm_revision_refs=(),
                    mutual_commitment_revision_refs=(),
                    narrative_revision_refs=(),
                    authored_origin_refs=(),
                    earned_evidence_refs=(),
                ),
                candidates=(),
            ),
        )
        return CognitiveProposal(
            adapter_version=self.adapter_version,
            experience_summary=experience_summary,
            epistemic_outcome=epistemic,
            impact_envelope=envelope,
            expression_candidate=expression_candidate,
        )


class _DormantArtifactCognition(CognitionEngine):
    """No-submit marker for an accepted-artifact dormant authority."""

    adapter_version = "post-m0-accepted-artifact-dormant-1.0"
    provider_authority = "dormant-artifact:no-cognition-1.0"
    experimental = True
    test_only = True

    def preflight(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> None:
        del context, command
        raise PreAdmissionRejected(
            "dormant-artifact-no-submit",
            "the accepted-artifact authority has no command or Cognition capability",
        )

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        del plan, context, command, basis
        raise CognitionFailedClosed(
            "cognition",
            "dormant-artifact-no-submit",
            "the accepted-artifact authority cannot produce a proposal",
        )


_LOCAL_FIRST_TEST_COGNITION_TOKEN = object()


@dataclass(frozen=True)
class _UserConfirmedContextBrief:
    brief_id: str
    text: str
    content_digest: str

    @classmethod
    def _confirmed_for_test(
        cls,
        text: str,
        *,
        _authority: object,
    ) -> _UserConfirmedContextBrief:
        if _authority is not _LOCAL_FIRST_TEST_COGNITION_TOKEN:
            raise TypeError("confirmed brief requires local test-plan authority")
        if not isinstance(text, str):
            raise TypeError("confirmed context brief must be text")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized or len(normalized) > 4096 or "\x00" in normalized:
            raise ValueError("confirmed context brief is invalid")
        digest = sha256(normalized.encode("utf-8")).hexdigest()
        return cls(
            brief_id=str(uuid5(NAMESPACE_URL, f"post-m0-04-brief:{digest}")),
            text=normalized,
            content_digest=digest,
        )

    @classmethod
    def _confirmed_for_local(
        cls,
        text: str,
        *,
        _authority: object,
    ) -> _UserConfirmedContextBrief:
        if _authority is not _LOCAL_LLAMA_COGNITION_TOKEN:
            raise TypeError("confirmed brief requires local llama authority")
        if not isinstance(text, str):
            raise TypeError("confirmed context brief must be text")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized or len(normalized) > 4096 or "\x00" in normalized:
            raise ValueError("confirmed context brief is invalid")
        digest = sha256(normalized.encode("utf-8")).hexdigest()
        return cls(
            brief_id=str(uuid5(NAMESPACE_URL, f"post-m0-04-local-brief:{digest}")),
            text=normalized,
            content_digest=digest,
        )


class _DeterministicLocalCognitionDouble(CognitionEngine):
    """Phase-1-only local Cognition double selected by RuntimeHost assembly.

    It performs no discovery, process launch, credential access, transport, or
    network operation.  It is not evidence for a qualified OS model runner.
    """

    adapter_version = "post-m0-04-deterministic-local-test-double-1.0"
    provider_authority = "local-first:deterministic-test-double-1.0"
    experimental = True
    test_only = True

    def __init__(
        self,
        *,
        confirmed_brief: _UserConfirmedContextBrief,
        expected_command_fingerprint: str,
        _authority: object,
    ) -> None:
        if _authority is not _LOCAL_FIRST_TEST_COGNITION_TOKEN:
            raise TypeError(
                "local Cognition test double requires Host assembly authority"
            )
        if type(confirmed_brief) is not _UserConfirmedContextBrief:
            raise TypeError("local Cognition requires an exact confirmed brief")
        if (
            not isinstance(expected_command_fingerprint, str)
            or len(expected_command_fingerprint) != 64
            or expected_command_fingerprint.casefold()
            != expected_command_fingerprint
        ):
            raise TypeError("local Cognition requires an exact command fingerprint")
        self._confirmed_brief = confirmed_brief
        self._expected_command_fingerprint = expected_command_fingerprint

    @classmethod
    def _for_host_assembly(
        cls,
        *,
        confirmed_brief: _UserConfirmedContextBrief,
        expected_command_fingerprint: str,
        _authority: object,
    ) -> _DeterministicLocalCognitionDouble:
        return cls(
            confirmed_brief=confirmed_brief,
            expected_command_fingerprint=expected_command_fingerprint,
            _authority=_authority,
        )

    def preflight(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> None:
        if (
            command.payload_fingerprint != self._expected_command_fingerprint
            or command.target_profile_id != context.profile_id
            or command.target_timeline_id != context.timeline_id
            or context.provider_authority != self.provider_authority
        ):
            raise PreAdmissionRejected(
                "local-interaction-plan-mismatch",
                "command is not the single confirmed local interaction",
            )

    def _matches_phase1_plan(
        self,
        *,
        command_fingerprint: str,
        confirmed_brief_digest: str,
    ) -> bool:
        return (
            self._expected_command_fingerprint == command_fingerprint
            and self._confirmed_brief.content_digest == confirmed_brief_digest
        )

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        del plan
        expression = ExpressionCandidate(
            text=(
                "本地确定性测试认知仅处理了这条当前命令；没有读取历史、记忆或外部来源。"
                if command.language.lower().startswith("zh")
                else (
                    "The deterministic local test cognition handled only this "
                    "current command; it read no history, memory, or external source."
                )
            ),
            language=command.language,
        )
        return self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=(
                "Phase-1 deterministic local Cognition test-double proposal; "
                f"confirmed-brief={self._confirmed_brief.content_digest}."
            ),
            expression_candidate=expression,
        )


_LOCAL_LLAMA_COGNITION_TOKEN = object()


class FakeCognition(CognitionEngine):
    """Explicit deterministic experimental adapter; it has no write authority."""

    adapter_version = M0_A_FAKE_COGNITION_VERSION
    provider_authority = M0_A_PROVIDER_AUTHORITY
    experimental = True
    test_only = True

    def __init__(
        self,
        *,
        mode: FakeCognitionMode = FakeCognitionMode.VALID,
    ) -> None:
        if not isinstance(mode, FakeCognitionMode):
            raise TypeError("FakeCognition mode must be explicit and typed")
        self._mode = mode

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        if self._mode is FakeCognitionMode.EPISTEMIC_FAILURE:
            raise CognitionFailedClosed(
                "epistemic",
                "epistemic-route-failed",
                "the injected Fake epistemic route could not verify its prefix",
            )
        del plan
        expression = ExpressionCandidate(
            text=(
                "I can check the lantern issue's Friday print-slot status "
                "within this original fixture."
                if context.fixture
                else "The qualified runtime completed this bounded Fake Cognition cycle."
            ),
            language=command.language,
        )
        return self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=(
                ""
                if self._mode is FakeCognitionMode.INVALID_OUTPUT
                else (
                    "The admitted Lantern Zine contribution entered the bounded "
                    "M0-A Experience Cycle."
                    if context.fixture
                    else (
                        "The admitted qualified-runtime contribution entered the "
                        "bounded M0 Experience Cycle."
                    )
                )
            ),
            expression_candidate=expression,
        )


@dataclass(frozen=True)
class RuntimeResult:
    operation_ref: OperationRef
    snapshot: AdmissionSnapshot
    outcome: TimelineOutcome | None
    admission_replayed: bool
    publication_replayed: bool
    failure: OperationFailure | None = None


class SubjectRuntime:
    """Deep M0-A Module owning one complete Experience Cycle."""

    def __init__(
        self,
        engine: TimelineEngine,
        *,
        fixture: M0AFixture | None,
        cognition: CognitionEngine,
        _context: _RuntimeContext | None = None,
        _host_token: object | None = None,
        interrupt_at: RuntimeFaultPoint | None = None,
        domain_fault: RuntimeDomainFault | None = None,
        fault_hook: Callable[[RuntimeFaultPoint, OperationRef], None] | None = None,
    ) -> None:
        if not isinstance(engine, TimelineEngine):
            raise TypeError("SubjectRuntime requires its private TimelineEngine")
        if isinstance(fixture, M0AFixture) and _context is None:
            context = _RuntimeContext.from_fixture(fixture)
        elif (
            fixture is None
            and isinstance(_context, _RuntimeContext)
            and _host_token is _HOST_RUNTIME_TOKEN
            and _context.kind == "published-qri-binding"
        ):
            context = _context
        else:
            raise TypeError(
                "SubjectRuntime requires either M0AFixture or RuntimeHost authority"
            )
        if not isinstance(cognition, CognitionEngine):
            raise TypeError("SubjectRuntime requires an explicit CognitionEngine")
        if cognition.provider_authority != context.cognition_view().provider_authority:
            raise TypeError(
                "CognitionEngine authority does not match runtime authority"
            )
        if interrupt_at is not None and not isinstance(
            interrupt_at,
            RuntimeFaultPoint,
        ):
            raise TypeError("interrupt_at must be a RuntimeFaultPoint")
        if domain_fault is not None and not isinstance(
            domain_fault,
            RuntimeDomainFault,
        ):
            raise TypeError("domain_fault must be a RuntimeDomainFault")
        if fault_hook is not None and not callable(fault_hook):
            raise TypeError("fault_hook must be callable")
        self._engine = engine
        self._context = context
        self._cognition = cognition
        self._interrupt_at = interrupt_at
        self._domain_fault = domain_fault
        self._fault_hook = fault_hook
        self._closed = False

    @classmethod
    def create_test(
        cls,
        test_base: Path,
        *,
        fixture: M0AFixture,
        cognition: CognitionEngine,
        interrupt_at: RuntimeFaultPoint | None = None,
        domain_fault: RuntimeDomainFault | None = None,
        fault_hook: Callable[[RuntimeFaultPoint, OperationRef], None] | None = None,
    ) -> SubjectRuntime:
        if not isinstance(fixture, M0AFixture):
            raise TypeError("SubjectRuntime requires a typed M0AFixture")
        fixture.require_authority()
        return cls(
            TimelineEngine.create_test(test_base, fixture.authority),
            fixture=fixture,
            cognition=cognition,
            interrupt_at=interrupt_at,
            domain_fault=domain_fault,
            fault_hook=fault_hook,
        )

    @classmethod
    def open(
        cls,
        location: CanonicalRootRef,
        *,
        fixture: M0AFixture,
        cognition: CognitionEngine,
        interrupt_at: RuntimeFaultPoint | None = None,
        domain_fault: RuntimeDomainFault | None = None,
        fault_hook: Callable[[RuntimeFaultPoint, OperationRef], None] | None = None,
    ) -> SubjectRuntime:
        if not isinstance(fixture, M0AFixture):
            raise TypeError("SubjectRuntime requires a typed M0AFixture")
        fixture.require_authority()
        return cls(
            TimelineEngine.open(
                location,
                expected_authority=fixture.authority,
            ),
            fixture=fixture,
            cognition=cognition,
            interrupt_at=interrupt_at,
            domain_fault=domain_fault,
            fault_hook=fault_hook,
        )

    @classmethod
    def _create_bound(
        cls,
        test_base: Path,
        *,
        authority: _RuntimeBindingAuthority,
        cognition: CognitionEngine,
        experienced_at_us: int,
        runtime_identity: RuntimeIdentityProjection | None,
        root_kind: str,
        relationship_enabled: bool = False,
        _host_token: object,
        _reserved_timeline_identity: _ReservedTimelineIdentity | None = None,
        interrupt_at: RuntimeFaultPoint | None = None,
        domain_fault: RuntimeDomainFault | None = None,
        fault_hook: Callable[[RuntimeFaultPoint, OperationRef], None] | None = None,
    ) -> SubjectRuntime:
        context = _RuntimeContext.from_binding(
            authority,
            experienced_at_us=experienced_at_us,
            runtime_identity=runtime_identity,
            relationship_enabled=relationship_enabled,
            _host_token=_host_token,
        )
        engine = TimelineEngine._create_bound(
            test_base,
            authority,
            root_kind=root_kind,
            _host_token=_HOST_TIMELINE_TOKEN,
            _reserved_identity=_reserved_timeline_identity,
        )
        return cls(
            engine,
            fixture=None,
            cognition=cognition,
            _context=context,
            _host_token=_host_token,
            interrupt_at=interrupt_at,
            domain_fault=domain_fault,
            fault_hook=fault_hook,
        )

    @classmethod
    def _open_bound(
        cls,
        location: CanonicalRootRef,
        *,
        authority: _RuntimeBindingAuthority,
        cognition: CognitionEngine,
        experienced_at_us: int,
        runtime_identity: RuntimeIdentityProjection | None,
        root_kind: str,
        relationship_enabled: bool = False,
        _host_token: object,
        interrupt_at: RuntimeFaultPoint | None = None,
        domain_fault: RuntimeDomainFault | None = None,
        fault_hook: Callable[[RuntimeFaultPoint, OperationRef], None] | None = None,
    ) -> SubjectRuntime:
        context = _RuntimeContext.from_binding(
            authority,
            experienced_at_us=experienced_at_us,
            runtime_identity=runtime_identity,
            relationship_enabled=relationship_enabled,
            _host_token=_host_token,
        )
        if location.root_kind != root_kind:
            raise TypeError("RuntimeHost and Timeline root kinds must match")
        engine = TimelineEngine.open(
            location,
            expected_authority=authority,
            _host_token=_HOST_TIMELINE_TOKEN,
        )
        return cls(
            engine,
            fixture=None,
            cognition=cognition,
            _context=context,
            _host_token=_host_token,
            interrupt_at=interrupt_at,
            domain_fault=domain_fault,
            fault_hook=fault_hook,
        )

    @property
    def location(self) -> CanonicalRootRef:
        return self._engine.location

    def _cognition_view(
        self,
        *,
        observed_at_us: int | None = None,
        query_text: object | None = None,
        dialogue_operation: OperationRef | None = None,
        dialogue_head: int | None = None,
    ) -> CognitionRuntimeView:
        observed_at_us = (
            time_ns() // 1_000
            if observed_at_us is None
            else observed_at_us
        )
        interactions = self._engine.list_relationship_interactions(limit=20)
        memory_history = self._engine.list_living_memories(
            active_only=False,
            limit=100,
        )
        participant_goals = self._engine.list_participant_goal_commitments(
            active_only=True,
            limit=20,
        )
        situated_records = self._engine.list_situated_states(
            active_only=True,
            limit=1,
        )
        situated_state = (
            usable_state(situated_records[0], now_us=observed_at_us)
            if situated_records
            else None
        )
        medium_state = self._engine.current_medium_state()
        medium_signals = self._engine.list_medium_signals(limit=7)
        def load_last_committed_at_us() -> int | None:
            try:
                turns = self._engine.list_conversation_turns(limit=1)
            except PublicationFailedClosed as error:
                raise SubjectTimeHistoryFailedClosed from error
            return turns[-1].published_at_us if turns else None

        subject_time_result = SubjectTimeContinuity().evaluate(
            query_text=query_text,
            current_admitted_at_us=observed_at_us,
            load_last_committed_at_us=load_last_committed_at_us,
        )
        projected_memory_history = tuple(
            (
                memory
                if memory.temporal_anchor is None
                else replace(
                    memory,
                    content=_TEMPORAL_GROUNDING.render(
                        memory.content,
                        memory.temporal_anchor,
                        observed_at_us=observed_at_us,
                    ),
                )
            )
            for memory in memory_history
        )
        projected_participant_goals = tuple(
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
            for record in participant_goals
        )
        memory_retrieval_unavailable = False
        try:
            active_memories = select_memory_candidates(projected_memory_history, query_text)
        except MemoryRetrievalUnavailable:
            active_memories = ()
            memory_retrieval_unavailable = True
        if interactions:
            accepted = [i for i in interactions if i.status == "accepted"]
            stance_summary = (
                f"立场互动 {len(accepted)} 条已接受；最近事件："
                f"{interactions[-1].event}（{interactions[-1].status}）。"
            )
        else:
            stance_summary = ""
        return replace(
            self._context.cognition_view(),
            active_memories=active_memories,
            memory_retrieval_unavailable=memory_retrieval_unavailable,
            living_memory_history=projected_memory_history,
            canonical_memory_history=memory_history,
            memory_control_complete=len(memory_history) < 100,
            relationship_stance_summary=stance_summary,
            participant_goal_commitments=projected_participant_goals,
            situated_state=situated_state,
            observed_at_us=observed_at_us,
            medium_state=medium_state,
            medium_signals=medium_signals,
            subject_time_result=subject_time_result,
            load_recent_dialogue=(
                (lambda: self._engine.recent_dialogue_before(dialogue_operation, expected_head=dialogue_head))
                if dialogue_operation is not None and dialogue_head is not None else None
            ),
            load_withheld_memory_ids=(
                (lambda: self._engine.withheld_memory_ids_before(dialogue_operation, expected_head=dialogue_head))
                if dialogue_operation is not None and dialogue_head is not None else None
            ),
        )

    def list_living_memories(
        self,
        *,
        active_only: bool = False,
        limit: int = 100,
    ) -> tuple[LivingMemoryRecord, ...]:
        return self._engine.list_living_memories(
            active_only=active_only,
            limit=limit,
        )

    def list_conversation_turns(
        self,
        *,
        limit: int = 20,
    ) -> tuple[ConversationTurnRecord, ...]:
        return self._engine.list_conversation_turns(limit=limit)

    def list_relationship_interactions(
        self,
        *,
        limit: int = 100,
    ) -> tuple[RelationshipStanceInteraction, ...]:
        return self._engine.list_relationship_interactions(limit=limit)

    def list_participant_goal_commitments(
        self,
        *,
        active_only: bool = False,
        limit: int = 100,
    ) -> tuple[ParticipantGoalCommitmentRecord, ...]:
        return self._engine.list_participant_goal_commitments(
            active_only=active_only,
            limit=limit,
        )

    def list_situated_states(
        self,
        *,
        active_only: bool = False,
        limit: int = 100,
    ) -> tuple[SituatedStateRecord, ...]:
        return self._engine.list_situated_states(
            active_only=active_only,
            limit=limit,
        )

    def current_medium_state(self) -> MediumStateRecord:
        return self._engine.current_medium_state()

    def list_medium_signals(self, *, limit: int = 7) -> tuple[MediumSignalRecord, ...]:
        return self._engine.list_medium_signals(limit=limit)

    def _activate_binding_gate(self, *, _host_token: object) -> None:
        if _host_token is not _HOST_RUNTIME_TOKEN:
            raise TypeError("RuntimeHost authority is required")
        self._engine._activate_binding_gate(_host_token=_HOST_TIMELINE_TOKEN)

    def _close_binding_gate(self, *, retire: bool, _host_token: object) -> None:
        if _host_token is not _HOST_RUNTIME_TOKEN:
            raise TypeError("RuntimeHost authority is required")
        self._engine._close_binding_gate(
            retire=retire,
            _host_token=_HOST_TIMELINE_TOKEN,
        )

    def _binding_health(
        self,
        *,
        _host_token: object,
    ) -> tuple[str, int, TimelineBasis, bool]:
        if _host_token is not _HOST_RUNTIME_TOKEN:
            raise TypeError("RuntimeHost authority is required")
        return self._engine._binding_health(_host_token=_HOST_TIMELINE_TOKEN)

    def close(self) -> None:
        if not self._closed:
            self._engine.close()
            self._closed = True

    def execute(
        self,
        command: SubjectCommand,
        *,
        idempotency_key: str,
    ) -> RuntimeResult:
        admitted = self.admit(command, idempotency_key=idempotency_key)
        if admitted.snapshot.operation_state is not OperationState.ADMITTED_PENDING:
            return admitted
        return self._continue_cycle(
            admitted.operation_ref,
            command,
            admission_replayed=admitted.admission_replayed,
        )

    def admit(
        self,
        command: SubjectCommand,
        *,
        idempotency_key: str,
    ) -> RuntimeResult:
        """Durably admit one command without coupling admission to waiting."""

        self._context.validate_command(command)
        self._cognition.preflight(
            context=self._cognition_view(),
            command=command,
        )
        reserved_operation_id = self._cognition.reserved_operation_id(
            context=self._cognition_view(),
            command=command,
        )
        admitted = self._engine.admit(
            command,
            idempotency_key=idempotency_key,
            _reserved_operation_id=reserved_operation_id,
        )
        self._hit(RuntimeFaultPoint.AFTER_ADMISSION, admitted.operation_ref)
        return self._observe(
            admitted.operation_ref,
            admission_replayed=admitted.replayed,
        )

    def resume(self, operation_ref: OperationRef) -> RuntimeResult:
        command = (
            self._context.fixture.command()
            if self._context.fixture is not None
            else self._engine._query_command(operation_ref)
        )
        self._context.validate_command(command)
        self._cognition.preflight(
            context=self._cognition_view(),
            command=command,
        )
        if command.payload_fingerprint != operation_ref.admitted_payload_fingerprint:
            raise PreAdmissionRejected(
                "fixture-command-unavailable",
                "OperationRef does not name the frozen M0-A fixture command",
            )
        return self._continue_cycle(
            operation_ref,
            command,
            admission_replayed=True,
        )

    def _continue_cycle(
        self,
        operation_ref: OperationRef,
        command: SubjectCommand,
        *,
        admission_replayed: bool,
    ) -> RuntimeResult:
        snapshot = self._engine.query(operation_ref)
        if snapshot.operation_state is OperationState.COMPLETED:
            return RuntimeResult(
                operation_ref=operation_ref,
                snapshot=snapshot,
                outcome=self._engine.query_outcome(operation_ref),
                admission_replayed=admission_replayed,
                publication_replayed=True,
            )
        if snapshot.operation_state is OperationState.FAILED_CLOSED:
            return RuntimeResult(
                operation_ref=operation_ref,
                snapshot=snapshot,
                outcome=None,
                admission_replayed=admission_replayed,
                publication_replayed=False,
                failure=self._engine.query_failure(operation_ref),
            )
        if snapshot.operation_state is OperationState.INTERRUPTED:
            return RuntimeResult(
                operation_ref=operation_ref,
                snapshot=snapshot,
                outcome=None,
                admission_replayed=admission_replayed,
                publication_replayed=False,
            )

        frozen_basis = self._engine.freeze_attempt_basis(operation_ref)
        cycle_plan = self._build_cycle_plan(
            operation_ref,
            snapshot.attempt_id,
            snapshot,
            command,
            frozen_basis,
        )
        self._hit(RuntimeFaultPoint.AFTER_CYCLE_PLAN, operation_ref)
        experience_basis = self._build_experience_basis(
            cycle_plan,
            command,
            snapshot,
        )
        try:
            proposal = self._cognition.propose(
                plan=cycle_plan,
                context=self._cognition_view(
                    observed_at_us=experience_basis.observed_at_us,
                    query_text=command.utterance,
                    dialogue_operation=operation_ref,
                    dialogue_head=frozen_basis.head_sequence,
                ),
                command=command,
                basis=experience_basis,
            )
        except CognitionFailedClosed as error:
            self._fail_cycle(
                operation_ref,
                stage=error.stage,
                code=error.code,
                detail=error.detail,
            )
        try:
            self._validate_proposal(proposal, experience_basis)
        except (
            DomainAdjudicationFailedClosed,
            ExperienceImpactEnvelopeRejected,
            TypeError,
            ValueError,
        ):
            self._fail_cycle(
                operation_ref,
                stage="cognition",
                code="invalid-cognition-output",
                detail="Fake Cognition output violated the frozen M0-A contract",
            )
        self._hit(RuntimeFaultPoint.AFTER_COGNITION, operation_ref)
        try:
            outcomes = self._adjudicate_domains(proposal.impact_envelope)
        except DomainAdjudicationFailedClosed as error:
            self._fail_cycle(
                operation_ref,
                stage=error.domain.casefold().replace("_", "-"),
                code=error.code,
                detail=f"{error.domain} Domain could not prove a safe adjudication",
            )
        except DomainOutcomeSetRejected:
            self._fail_cycle(
                operation_ref,
                stage="domains",
                code="incomplete-domain-outcome-set",
                detail="the four Domain outcomes did not form one complete set",
            )
        self._hit(RuntimeFaultPoint.AFTER_DOMAIN_OUTCOMES, operation_ref)
        expression_candidate = self._cognition.express(
            proposal=proposal,
            context=self._cognition_view(
                observed_at_us=experience_basis.observed_at_us,
            ),
            command=command,
            outcomes=outcomes,
        )
        try:
            self._validate_expression(expression_candidate, command)
        except (TypeError, ValueError):
            self._fail_cycle(
                operation_ref,
                stage="cognition",
                code="invalid-expression-output",
                detail="Fake Cognition Expression violated the frozen M0-A contract",
            )
        commit_plan = self._build_commit_plan(
            cycle_plan,
            proposal,
            outcomes,
            expression_candidate,
        )
        self._hit(RuntimeFaultPoint.BEFORE_PUBLICATION, operation_ref)
        published = self._engine.publish(commit_plan)
        self._hit(RuntimeFaultPoint.AFTER_PUBLICATION, operation_ref)
        return RuntimeResult(
            operation_ref=operation_ref,
            snapshot=self._engine.query(operation_ref),
            outcome=published.outcome,
            admission_replayed=admission_replayed,
            publication_replayed=published.replayed,
        )

    def follow(
        self,
        operation_ref: OperationRef,
        *,
        timeout_seconds: float = 0.0,
    ) -> RuntimeResult:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 0
            or timeout_seconds > 30
        ):
            raise ValueError("timeout_seconds must be between 0 and 30")
        deadline = monotonic() + float(timeout_seconds)
        while True:
            snapshot = self._engine.query(operation_ref)
            if snapshot.operation_state in {
                OperationState.COMPLETED,
                OperationState.FAILED_CLOSED,
                OperationState.INTERRUPTED,
            }:
                break
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(0.01, remaining))
        return self._observe(
            operation_ref,
            admission_replayed=True,
            snapshot=snapshot,
        )

    def _observe(
        self,
        operation_ref: OperationRef,
        *,
        admission_replayed: bool,
        snapshot: AdmissionSnapshot | None = None,
    ) -> RuntimeResult:
        if snapshot is None:
            snapshot = self._engine.query(operation_ref)
        outcome = (
            self._engine.query_outcome(operation_ref)
            if snapshot.operation_state is OperationState.COMPLETED
            else None
        )
        failure = (
            self._engine.query_failure(operation_ref)
            if snapshot.operation_state is OperationState.FAILED_CLOSED
            else None
        )
        return RuntimeResult(
            operation_ref=operation_ref,
            snapshot=snapshot,
            outcome=outcome,
            admission_replayed=admission_replayed,
            publication_replayed=outcome is not None,
            failure=failure,
        )

    def _validate_proposal(
        self,
        proposal: object,
        basis: ExperienceBasis,
    ) -> None:
        if type(proposal) is not CognitiveProposal:
            raise TypeError("CognitionEngine must return CognitiveProposal")
        if (
            proposal.adapter_version != self._cognition.adapter_version
            or not proposal.experience_summary.strip()
            or type(proposal.epistemic_outcome) is not EpistemicOutcome
            or proposal.epistemic_outcome.status is not DecisionStatus.NO_OP
            or proposal.epistemic_outcome.route_version != M0_A_EPISTEMIC_ROUTE_VERSION
            or proposal.epistemic_outcome.verified_prefix_digest
            != basis.verified_prefix_digest
            or proposal.epistemic_outcome.completed_stages != ()
            or type(proposal.impact_envelope) is not ExperienceImpactEnvelope
            or proposal.impact_envelope.basis != basis
        ):
            raise ValueError("Cognition proposal is outside runtime authority")

    def _validate_expression(
        self,
        candidate: object,
        command: SubjectCommand,
    ) -> None:
        if (
            type(candidate) is not ExpressionCandidate
            or not candidate.text.strip()
            or candidate.language != command.language
        ):
            raise ValueError("Cognition Expression is outside runtime authority")

    def _adjudicate_domains(
        self,
        envelope: ExperienceImpactEnvelope,
    ) -> CompleteDomainOutcomeSet:
        outcomes: list[object] = []
        participants = (
            (
                RuntimeDomainFault.EXPERIENCE,
                ExperienceDomain(),
                envelope.experience,
            ),
            (
                RuntimeDomainFault.SUBJECT_STATE,
                SubjectStateDomain(),
                envelope.subject_state,
            ),
            (
                RuntimeDomainFault.AGENCY,
                AgencyDomain(),
                envelope.agency,
            ),
            (
                RuntimeDomainFault.RELATIONSHIP,
                RelationshipDomain(),
                envelope.relationship,
            ),
        )
        for domain, module, request in participants:
            if self._domain_fault is domain:
                raise DomainAdjudicationFailedClosed(
                    domain.value,
                    "injected-technical-failure",
                    "the isolated runner injected one Domain technical failure",
                )
            outcomes.append(module.adjudicate(request))
        return CompleteDomainOutcomeSet.collect(outcomes)

    def _fail_cycle(
        self,
        operation_ref: OperationRef,
        *,
        stage: str,
        code: str,
        detail: str,
    ) -> None:
        failure = self._engine.fail_operation(
            operation_ref,
            stage=stage,
            code=code,
            detail=detail,
        )
        raise CycleFailedClosed(operation_ref, failure)

    def _hit(
        self,
        fault_point: RuntimeFaultPoint,
        operation_ref: OperationRef,
    ) -> None:
        if self._fault_hook is not None:
            self._fault_hook(fault_point, operation_ref)
        if self._interrupt_at is fault_point:
            raise RuntimeInterrupted(fault_point, operation_ref)

    def _build_cycle_plan(
        self,
        operation_ref: OperationRef,
        attempt_id: str,
        snapshot: AdmissionSnapshot,
        command: SubjectCommand,
        expected_basis: TimelineBasis,
    ) -> CyclePlan:
        return CyclePlan(
            cycle_plan_id=_runtime_id(
                operation_ref.operation_id,
                attempt_id,
                "cycle-plan",
            ),
            cycle_version=M0_A_CYCLE_VERSION,
            operation_ref=operation_ref,
            attempt_id=attempt_id,
            subject_event_id=snapshot.subject_event_id,
            command_fingerprint=command.payload_fingerprint,
            expected_basis=expected_basis,
            runtime_authority_id=self._context.runtime_authority_id,
            stage_order=M0_A_STAGE_ORDER,
            domain_participation=M0_A_DOMAIN_PARTICIPATION,
            committed_effects_available=False,
        )

    def _build_experience_basis(
        self,
        plan: CyclePlan,
        command: SubjectCommand,
        snapshot: AdmissionSnapshot,
    ) -> ExperienceBasis:
        return ExperienceBasis(
            operation_id=plan.operation_ref.operation_id,
            attempt_id=plan.attempt_id,
            subject_event_id=plan.subject_event_id,
            experience_id=_runtime_id(
                plan.operation_ref.operation_id,
                plan.attempt_id,
                "experience",
            ),
            profile_id=self._context.authority.profile_id,
            timeline_id=self._context.authority.timeline_id,
            epistemic_outcome_id=_runtime_id(
                plan.operation_ref.operation_id,
                plan.attempt_id,
                "epistemic-outcome",
            ),
            verified_prefix_digest=plan.expected_basis.verified_prefix_digest,
            source_provenance=command.provenance,
            integrity_verified=True,
            observed_at_us=snapshot.admitted_at_us,
        )

    def _build_commit_plan(
        self,
        cycle_plan: CyclePlan,
        proposal: CognitiveProposal,
        outcomes: CompleteDomainOutcomeSet,
        expression_candidate: ExpressionCandidate,
    ) -> CycleCommitPlan:
        operation_id = cycle_plan.operation_ref.operation_id
        attempt_id = cycle_plan.attempt_id
        decisions = (
            outcomes.experience.decision,
            outcomes.subject_state.decision,
            outcomes.subject_state.subject_core.decision,
            outcomes.subject_state.development.decision,
            outcomes.agency.decision,
            outcomes.relationship.decision,
        )
        return CycleCommitPlan(
            plan_id=_runtime_id(operation_id, attempt_id, "commit-plan"),
            cycle_plan_id=cycle_plan.cycle_plan_id,
            operation_ref=cycle_plan.operation_ref,
            attempt_id=attempt_id,
            subject_event_id=cycle_plan.subject_event_id,
            profile_id=self._context.authority.profile_id,
            timeline_id=self._context.authority.timeline_id,
            expected_basis=cycle_plan.expected_basis,
            experience=ExperienceRecord(
                experience_id=proposal.impact_envelope.basis.experience_id,
                summary=proposal.experience_summary,
                experienced_at_us=(
                    proposal.impact_envelope.basis.observed_at_us
                ),
            ),
            epistemic_outcome=proposal.epistemic_outcome,
            experience_outcome=outcomes.experience,
            subject_state_outcome=outcomes.subject_state,
            agency_outcome=outcomes.agency,
            relationship_outcome=outcomes.relationship,
            revision_set=RevisionSet(
                revision_set_id=_runtime_id(
                    operation_id,
                    attempt_id,
                    "revision-set",
                ),
                revision_ids=(),
            ),
            expression=Expression(
                expression_id=_runtime_id(
                    operation_id,
                    attempt_id,
                    "expression",
                ),
                text=expression_candidate.text,
                language=expression_candidate.language,
                grounding_decision_ids=tuple(
                    decision.decision_id for decision in decisions
                ),
            ),
            committed_effect_set=CommittedEffectSet(
                effect_set_id=_runtime_id(
                    operation_id,
                    attempt_id,
                    "committed-effect-set",
                ),
                reference_ids=(),
                dispatch_state=EffectDispatchState.UNAVAILABLE,
                reason="real committed-effect dispatch is unavailable in M0-A",
            ),
        )


__all__ = [
    "CognitionEngine",
    "CycleFailedClosed",
    "CyclePlan",
    "FakeCognition",
    "FakeCognitionMode",
    "M0AFixture",
    "M0AFixtureUnavailable",
    "RuntimeDomainFault",
    "RuntimeFaultPoint",
    "RuntimeInterrupted",
    "RuntimeResult",
    "SubjectRuntime",
]

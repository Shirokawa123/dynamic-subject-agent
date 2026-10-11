"""S150 exact human-approved uses, separate audit and one-use delivery tickets."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock, get_ident

from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.model_gateway import ModelTask
from dynamic_subject_agent.shared_activity import digest
from dynamic_subject_agent.natural_feedback import feedback_contract, FEEDBACK_POLICY, feedback_choice_policy

APPROVED_FEEDBACK_REVIEW = 'f09dd24a840082d19dea10c0e0f8cce3bf8b31764d3f151be20f0c86d3e518f6'
FEEDBACK_APPROVAL = 'user-approved-natural-feedback-use-2026-10-11'
FEEDBACK_LIVE_VERSION = 'natural-feedback-live-s150-1'
APPROVED_FEEDBACK_MATERIAL = '30715f56be4a693835739645f7d8c07be264f3a2396790f82113503a00f0b44c'
APPROVED_FEEDBACK_LOCAL_CONTRACT = '77ffcfa56f7448c6f127caaf79cdb9891ccc920b1cb70877e96890bd05e7fa06'
APPROVED_FEEDBACK_PROTOCOL = 'bef335fb20256959ee8bb38708625d626bb46931b8d634eff90354de30e6672c'
FEEDBACK_POLICY_HASHES = ('25f6dd629eca8b00157f89f055f25eb6113d9e5a69e5969a1e027462135b2292',
    '363026832e5c421d97a91b47804afc7ebfdca60cb5253e1c364b3801463e60fb')
PURPOSES = frozenset(('natural-activity-feedback', 'shared-activity-choice'))


@dataclass(frozen=True)
class ApprovedNaturalFeedbackGrant:
    review_basis: str
    confirmed: bool = False

    def __post_init__(self):
        if self.review_basis != APPROVED_FEEDBACK_REVIEW or self.confirmed is not True:
            raise ValueError('exact confirmed S150 human approval required')

    def validate(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
        self.__post_init__()
        if digest(APPROVED_BINDING) != APPROVED_FEEDBACK_MATERIAL:
            raise ValueError('S150 approval does not cover changed material binding')
        if (digest(feedback_contract(APPROVED_BINDING)) != APPROVED_FEEDBACK_LOCAL_CONTRACT
            or tuple(sha256(p.encode()).hexdigest() for p in (FEEDBACK_POLICY, feedback_choice_policy())) != FEEDBACK_POLICY_HASHES
            or digest(communication_protocol('thinking-high', 'low')) != APPROVED_FEEDBACK_PROTOCOL):
            raise ValueError('approved S150 contract, policy or protocol changed')


def feedback_live_contract(binding):
    ApprovedNaturalFeedbackGrant(APPROVED_FEEDBACK_REVIEW, True).validate()
    base = feedback_contract(binding)
    return dict(base, version=FEEDBACK_LIVE_VERSION, authorization=FEEDBACK_APPROVAL,
        provider='deepseek', credential_use='existing-Windows-slot-HTTPS-Bearer-only',
        technical_variant=dict(base['technical_variant'], name='feedback-live',
            approved_review_basis=APPROVED_FEEDBACK_REVIEW, protocol_sha=APPROVED_FEEDBACK_PROTOCOL))


def feedback_grant_variant(grant):
    if type(grant) is ApprovedNaturalFeedbackGrant:return 'baseline'
    from dynamic_subject_agent.natural_feedback_budget import NaturalFeedbackBudgetDevelopmentGrant
    if type(grant) is NaturalFeedbackBudgetDevelopmentGrant:return 'direct-final'
    from dynamic_subject_agent.natural_feedback_scoped import NaturalFeedbackScopedDevelopmentGrant
    if type(grant) is NaturalFeedbackScopedDevelopmentGrant:return 'scoped'
    from dynamic_subject_agent.natural_feedback_intent import NaturalFeedbackIntentDevelopmentGrant
    if type(grant) is NaturalFeedbackIntentDevelopmentGrant:return 'intent-only'
    from dynamic_subject_agent.natural_feedback_multispan import NaturalFeedbackMultispanDevelopmentGrant
    if type(grant) is NaturalFeedbackMultispanDevelopmentGrant:return 'multi-span'
    raise ValueError('exact approved feedback grant required')


def feedback_live_contract_for_variant(binding,technical_variant='baseline'):
    if technical_variant=='baseline':return feedback_live_contract(binding)
    if technical_variant=='direct-final':
        from dynamic_subject_agent.natural_feedback_budget import feedback_budget_contract
        return feedback_budget_contract(binding)
    if technical_variant=='scoped':
        from dynamic_subject_agent.natural_feedback_frame import scoped_contract
        return scoped_contract(binding)
    if technical_variant=='intent-only':
        from dynamic_subject_agent.natural_feedback_intent import intent_contract
        return intent_contract(binding)
    if technical_variant=='multi-span':
        from dynamic_subject_agent.natural_feedback_multispan import multispan_contract
        return multispan_contract(binding)
    raise ValueError('closed feedback LIVE variant required')


def feedback_variant_for_contract(contract):
    from dynamic_subject_agent.original_whole_chat import contract_variant
    if contract_variant(contract) not in ('feedback-live','feedback-scoped-live'):raise ValueError('exact feedback LIVE contract required')
    if contract['version']=='natural-feedback-scoped-live-s152-1':return 'scoped'
    if contract['version']=='natural-feedback-intent-live-s153-1':return 'intent-only'
    if contract['version']=='natural-feedback-multispan-live-s154-1':return 'multi-span'
    from dynamic_subject_agent.natural_feedback_budget import BUDGET_VERSION
    return 'direct-final' if contract['version']==BUDGET_VERSION else 'baseline'


class NaturalFeedbackCallAudit(DevelopmentCallAudit):
    purposes = PURPOSES

    @staticmethod
    def configuration():
        return dict(version='natural-feedback-call-audit-s150-1', authorization=FEEDBACK_APPROVAL,
            review_basis=APPROVED_FEEDBACK_REVIEW, provider='deepseek', purposes=sorted(PURPOSES), limit=None)

    def snapshot(self):
        fields = ('ordinal', 'attempt_id', 'request_digest', 'purpose', 'run_digest', 'status', 'output_digest')
        with self._transaction() as db:
            return tuple(dict(zip(fields, row[:-1], strict=True)) for row in self._verified(db))


class NaturalFeedbackBudgetCallAudit(NaturalFeedbackCallAudit):
    @staticmethod
    def configuration():
        from dynamic_subject_agent.natural_feedback_budget import BUDGET_DEVELOPMENT,BUDGET_PROTOCOL_SHA
        return dict(NaturalFeedbackCallAudit.configuration(),version='natural-feedback-direct-final-call-audit-s151-1',
            development_authorization=BUDGET_DEVELOPMENT,protocol_sha=BUDGET_PROTOCOL_SHA)


class NaturalFeedbackScopedCallAudit(NaturalFeedbackBudgetCallAudit):
    @staticmethod
    def configuration():
        from dynamic_subject_agent.natural_feedback_scoped import SCOPED_POLICY_SHA
        from dynamic_subject_agent.natural_feedback_frame import SCOPED_DEVELOPMENT
        return dict(NaturalFeedbackBudgetCallAudit.configuration(),version='natural-feedback-scoped-audit-s152-1',
            development_authorization=SCOPED_DEVELOPMENT,feedback_policy_sha=SCOPED_POLICY_SHA)


class NaturalFeedbackIntentCallAudit(NaturalFeedbackScopedCallAudit):
    @staticmethod
    def configuration():
        from dynamic_subject_agent.natural_feedback_intent import INTENT_DEVELOPMENT,INTENT_POLICY_SHA
        return dict(NaturalFeedbackScopedCallAudit.configuration(),version='natural-feedback-intent-audit-s153-1',
            development_authorization=INTENT_DEVELOPMENT,feedback_policy_sha=INTENT_POLICY_SHA)


class NaturalFeedbackMultispanCallAudit(NaturalFeedbackIntentCallAudit):
    @staticmethod
    def configuration():
        from dynamic_subject_agent.natural_feedback_multispan import MULTISPAN_DEVELOPMENT
        return dict(NaturalFeedbackIntentCallAudit.configuration(),version='natural-feedback-multispan-audit-s154-1',
            development_authorization=MULTISPAN_DEVELOPMENT,edit_construction='complete-bounded-unique-interval-cover-1')


def _audit_type(technical_variant):
    if technical_variant not in ('baseline','direct-final','scoped','intent-only','multi-span'):raise ValueError('closed feedback audit variant required')
    return NaturalFeedbackMultispanCallAudit if technical_variant=='multi-span' else NaturalFeedbackIntentCallAudit if technical_variant=='intent-only' else NaturalFeedbackScopedCallAudit if technical_variant=='scoped' else NaturalFeedbackBudgetCallAudit if technical_variant=='direct-final' else NaturalFeedbackCallAudit


def open_natural_feedback_audit(path, *, initialize=False, technical_variant='baseline'):
    audit_type=_audit_type(technical_variant)
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError('absolute independent feedback audit required')
    witness = path.with_name(path.name + '-initialized')
    if witness.exists():
        if not witness.is_dir() or not path.is_dir():
            raise ValueError('feedback audit witness missing')
        return audit_type(path)
    if path.exists() or not initialize:
        raise ValueError('feedback audit cannot be recreated or repurposed')
    witness.mkdir(parents=True, exist_ok=False)
    return audit_type(path, initialize=True)


@dataclass(frozen=True)
class _FeedbackTicket:
    attempt: str
    request_digest: str
    kind: object
    thread_id: int
    rebuild: object


class NaturalFeedbackDelivery:
    def __init__(self, *, grant, audit, contract, state_path):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        self.technical_variant=feedback_grant_variant(grant)
        expected_audit=_audit_type(self.technical_variant)
        if type(audit) is not expected_audit:
            raise ValueError('approved feedback grant and independent audit required')
        grant.validate()
        if contract != feedback_live_contract_for_variant({key: contract[key] for key in APPROVED_BINDING},self.technical_variant):
            raise ValueError('exact feedback LIVE contract required')
        self.grant, self.audit, self.contract = grant, audit, deepcopy(contract)
        self.run_digest = digest(dict(contract=contract, state_path=str(state_path.resolve()), audit_path=str(audit.path.resolve())))
        self._lock, self._ticket, self._pending, self._poisoned = RLock(), None, None, False

    def _validate_contract(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if self.contract != feedback_live_contract_for_variant({key: self.contract[key] for key in APPROVED_BINDING},self.technical_variant):
            raise ValueError('current approved feedback contract changed')

    def claim(self, operation, task, rebuild):
        self.grant.validate()
        self._validate_contract()
        if type(task) is not ModelTask or task.kind.value not in PURPOSES or not callable(rebuild):
            raise ValueError('exact approved feedback task required')
        with self._lock:
            if self._poisoned or self._pending is not None:
                raise ValueError('feedback delivery already pending or unverified')
            if task.payload != rebuild():
                raise ValueError('feedback request differs from canonical material')
            from dynamic_subject_agent.natural_feedback_remote_preview import natural_feedback_remote_request_preview
            natural_feedback_remote_request_preview(task,technical_variant=self.technical_variant)
            request = digest(task.payload)
            attempt = digest(dict(run=self.run_digest, operation=operation, purpose=task.kind.value))
            self.audit.claim(attempt, request, purpose=task.kind.value, run_digest=self.run_digest)
            self._pending = self._ticket = _FeedbackTicket(attempt, request, task.kind, get_ident(), rebuild)

    def consume(self, task):
        with self._lock:
            ticket, self._ticket = self._ticket, None
            if (self._poisoned or ticket is None or ticket.thread_id != get_ident() or type(task) is not ModelTask
                or task.kind is not ticket.kind or digest(task.payload) != ticket.request_digest):
                raise ValueError('one current same-thread feedback ticket required')
            self.grant.validate()
            self._validate_contract()
            actual = deepcopy(ticket.rebuild())
            if digest(actual) != ticket.request_digest or actual != task.payload:
                raise ValueError('canonical source or authorization changed before delivery')
            return ModelTask(task.kind, actual)

    def record(self, status, value=None):
        with self._lock:
            if self._pending is None or self._pending.thread_id != get_ident() or self._ticket is not None:
                raise ValueError('consumed feedback claim required')
            try:
                self.audit.record(self._pending.attempt, status=status, output_digest=None if value is None else digest(value))
            except Exception:
                self._poisoned = True
                raise
            self._pending = None

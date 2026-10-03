"""The exact S139 human-approved use, independent metadata audit and tickets."""
from dataclasses import dataclass
from pathlib import Path
from copy import deepcopy
from threading import RLock, get_ident

from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.shared_activity import shared_contract, digest, CHOICE_POLICY

APPROVED_SHARED_REVIEW = '8bb95a501eb44827e939ea41376cbda0eea6463a266b2983581d36f65494301a'
SHARED_APPROVAL = 'user-approved-shared-activity-use-2026-10-03'
APPROVED_SHARED_MATERIAL_DIGEST = '30715f56be4a693835739645f7d8c07be264f3a2396790f82113503a00f0b44c'
PURPOSES = frozenset(('shared-activity-choice', 'shared-activity-reply'))
POLICY_HASHES = ('38e151620ff9e59eaa948fd378d0a70d917b47d73c585aca59490cca76018a21',
    '03f1e741159fc5a18e8fedc49aa56b17ed1ad48ec457baf64d2d3c5cf1fd800a')


@dataclass(frozen=True)
class ApprovedSharedActivityGrant:
    review_basis: str
    confirmed: bool = False

    def __post_init__(self):
        if self.review_basis != APPROVED_SHARED_REVIEW or self.confirmed is not True:
            raise ValueError('exact confirmed S139 human approval required')

    def validate(self):
        from hashlib import sha256
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING, whole_contract, policy_for_contract
        from dynamic_subject_agent.shared_activity import CHAT_POLICY
        from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
        self.__post_init__()
        if digest(APPROVED_BINDING) != APPROVED_SHARED_MATERIAL_DIGEST:
            raise ValueError('S139 approval does not cover a changed material binding')
        reply = policy_for_contract(whole_contract(APPROVED_BINDING, technical_variant='grounded')).replace(
            '本拟用途不接生活系统，evidence的活动、方案和事件均为空，不依据时间或聊天轮数造经历。', CHAT_POLICY)
        protocol = communication_protocol('thinking-high', 'low')
        if ((sha256(CHOICE_POLICY.encode()).hexdigest(), sha256(reply.encode()).hexdigest()) != POLICY_HASHES
            or protocol['model'] != 'deepseek-flash'
            or protocol['expression'] != dict(max_tokens=4096, thinking={'type': 'enabled'}, reasoning_effort='high',
                response_format={'type': 'json_object'}, stream=False)):
            raise ValueError('approved S139 policy or protocol changed')


def shared_live_contract(binding):
    ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True).validate()
    base = shared_contract(binding)
    return dict(base, version='shared-activity-live-s139-1', authorization=SHARED_APPROVAL,
        provider='deepseek', credential_use='existing-Windows-slot-HTTPS-Bearer-only',
        excluded='automatic-life-sharing-persona-rewrite-cloud-migration',
        technical_variant=dict(base['technical_variant'], name='shared-live', approved_review_basis=APPROVED_SHARED_REVIEW))


class SharedActivityCallAudit(DevelopmentCallAudit):
    purposes = PURPOSES

    @staticmethod
    def configuration():
        return dict(version='shared-activity-call-audit-s139-1', authorization=SHARED_APPROVAL,
            review_basis=APPROVED_SHARED_REVIEW, provider='deepseek', purposes=sorted(PURPOSES), limit=None)

    def snapshot(self):
        fields = ('ordinal', 'attempt_id', 'request_digest', 'purpose', 'run_digest', 'status', 'output_digest')
        with self._transaction() as db:
            return tuple(dict(zip(fields, row[:-1], strict=True)) for row in self._verified(db))


def open_shared_activity_audit(path, *, initialize=False):
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError('absolute independent shared activity audit required')
    witness = path.with_name(path.name + '-initialized')
    if witness.exists():
        if not witness.is_dir() or not path.is_dir():
            raise ValueError('shared audit witness missing')
        return SharedActivityCallAudit(path)
    if path.exists() or not initialize:
        raise ValueError('shared audit cannot be recreated or repurposed')
    witness.mkdir(parents=True, exist_ok=False)
    return SharedActivityCallAudit(path, initialize=True)


@dataclass(frozen=True)
class _SharedTicket:
    attempt: str
    request_digest: str
    kind: ModelTaskKind
    thread_id: int
    rebuild: object


class SharedActivityDelivery:
    def __init__(self, *, grant, audit, contract, state_path):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if type(grant) is not ApprovedSharedActivityGrant or type(audit) is not SharedActivityCallAudit:
            raise ValueError('approved grant and independent audit required')
        grant.validate()
        if contract != shared_live_contract({key: contract[key] for key in APPROVED_BINDING}):
            raise ValueError('exact shared live contract required')
        self.grant, self.audit, self.contract = grant, audit, deepcopy(contract)
        self.run_digest = digest(dict(contract=contract, state_path=str(state_path.resolve()), audit_path=str(audit.path.resolve())))
        self._lock, self._ticket, self._pending, self._poisoned = RLock(), None, None, False

    def claim(self, operation, task, rebuild):
        self.grant.validate()
        if type(task) is not ModelTask or task.kind.value not in PURPOSES or not callable(rebuild):
            raise ValueError('exact manual shared request required')
        with self._lock:
            if self._poisoned or self._pending is not None:
                raise ValueError('shared delivery already pending or unverified')
            # Fresh canonical reconstruction before the claim ensures a bad
            # scope or stale material never consumes a new Provider attempt.
            if task.payload != rebuild():
                raise ValueError('shared request differs from canonical material')
            request = digest(task.payload)
            attempt = digest(dict(run=self.run_digest, operation=operation, purpose=task.kind.value))
            self.audit.claim(attempt, request, purpose=task.kind.value, run_digest=self.run_digest)
            self._pending = self._ticket = _SharedTicket(attempt, request, task.kind, get_ident(), rebuild)

    def consume(self, task):
        with self._lock:
            ticket, self._ticket = self._ticket, None
            if (self._poisoned or ticket is None or ticket.thread_id != get_ident() or type(task) is not ModelTask
                or task.kind is not ticket.kind or digest(task.payload) != ticket.request_digest):
                raise ValueError('one current same-thread shared ticket required')
            self.grant.validate()
            actual = deepcopy(ticket.rebuild())
            if digest(actual) != ticket.request_digest or actual != task.payload:
                raise ValueError('canonical source or authorization changed before delivery')
            return ModelTask(task.kind, actual)

    def record(self, status, value=None):
        with self._lock:
            if self._pending is None or self._pending.thread_id != get_ident() or self._ticket is not None:
                raise ValueError('consumed shared claim required')
            try:
                self.audit.record(self._pending.attempt, status=status, output_digest=None if value is None else digest(value))
            except Exception:
                self._poisoned = True
                raise
            self._pending = None

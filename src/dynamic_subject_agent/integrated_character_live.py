"""S158 approved combined uses with independent qualification and one-use delivery."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock, get_ident

from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.shared_activity import digest
from dynamic_subject_agent.integrated_character import integrated_contract
from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview
from dynamic_subject_agent.natural_feedback_live import NaturalFeedbackCallAudit, NaturalFeedbackDelivery
from dynamic_subject_agent.natural_feedback_choice_budget import choice_protocol

APPROVED_INTEGRATED_REVIEW = '35da99cca813588f534a83be0a2fdeab5730f2e2793ba03726fd5f06d50d3d95'
INTEGRATED_APPROVAL = 'user-approved-integrated-character-use-2026-10-13'
INTEGRATED_LIVE_VERSION = 'integrated-character-live-s158-1'
APPROVED_INTEGRATED_MATERIAL = '30715f56be4a693835739645f7d8c07be264f3a2396790f82113503a00f0b44c'
APPROVED_INTEGRATED_LOCAL_CONTRACT = '0aedd5ec87801bab5f38d2a43ef30c2eba91ac780dc9ca6e22c47aaeaba97493'
APPROVED_INTEGRATED_PROTOCOL = '3e57d187aecef5f3f631e24efe09e16357e802c6bb16525a9c81087ae06e199f'
KINDS = (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.LIVING_ACTIVITY_CHOICE, ModelTaskKind.LIVING_ACTIVITY_SHARE)
PURPOSES = frozenset(kind.value for kind in KINDS)


def protocol_witness():
    return {kind.value: choice_protocol(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK
        if kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK else ModelTaskKind.SHARED_ACTIVITY_CHOICE, 'choice-final') for kind in KINDS}


@dataclass(frozen=True)
class ApprovedIntegratedCharacterGrant:
    review_basis: str
    confirmed: bool = False

    def __post_init__(self):
        if self.review_basis != APPROVED_INTEGRATED_REVIEW or self.confirmed is not True:
            raise ValueError('exact confirmed S158 human approval required')

    def validate(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        self.__post_init__()
        if (digest(APPROVED_BINDING) != APPROVED_INTEGRATED_MATERIAL
            or digest(integrated_contract(APPROVED_BINDING)) != APPROVED_INTEGRATED_LOCAL_CONTRACT
            or digest(protocol_witness()) != APPROVED_INTEGRATED_PROTOCOL):
            raise ValueError('approved S158 material, policy, limits or protocol changed')


def integrated_live_contract(binding):
    ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW, True).validate()
    base = integrated_contract(binding)
    return dict(base, version=INTEGRATED_LIVE_VERSION, authorization=INTEGRATED_APPROVAL,
        provider='deepseek', credential_use='existing-Windows-slot-HTTPS-Bearer-only',
        excluded='offline-catchup-notifications-persona-rewrite-reflection-cloud-migration',
        technical_variant=dict(base['technical_variant'], name='integrated-live',
            approved_review_basis=APPROVED_INTEGRATED_REVIEW, protocol_sha=APPROVED_INTEGRATED_PROTOCOL))


class IntegratedCharacterCallAudit(NaturalFeedbackCallAudit):
    purposes = PURPOSES

    @staticmethod
    def configuration():
        return dict(version='integrated-character-call-audit-s158-1', authorization=INTEGRATED_APPROVAL,
            review_basis=APPROVED_INTEGRATED_REVIEW, provider='deepseek', purposes=sorted(PURPOSES), limit=None)


def open_integrated_character_audit(path, *, initialize=False):
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError('absolute independent integrated audit required')
    witness = path.with_name(path.name + '-initialized')
    if witness.exists():
        if not witness.is_dir() or not path.is_dir():
            raise ValueError('integrated audit witness missing')
        return IntegratedCharacterCallAudit(path)
    if path.exists() or not initialize:
        raise ValueError('integrated audit cannot be recreated or repurposed')
    witness.mkdir(parents=True, exist_ok=False)
    return IntegratedCharacterCallAudit(path, initialize=True)


@dataclass(frozen=True)
class _IntegratedTicket:
    attempt: str
    request_digest: str
    kind: object
    thread_id: int
    rebuild: object


class IntegratedCharacterDelivery(NaturalFeedbackDelivery):
    """Reuse consumed-ticket/terminal mechanics, with a separate exact use contract."""
    def __init__(self, *, grant, audit, contract, state_path):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if type(grant) is not ApprovedIntegratedCharacterGrant or type(audit) is not IntegratedCharacterCallAudit:
            raise ValueError('exact S158 grant and independent audit required')
        grant.validate()
        if contract != integrated_live_contract({key: contract[key] for key in APPROVED_BINDING}):
            raise ValueError('exact integrated LIVE contract required')
        self.grant, self.audit, self.contract = grant, audit, deepcopy(contract)
        self.run_digest = digest(dict(contract=contract, state_path=str(state_path.resolve()), audit_path=str(audit.path.resolve())))
        self._lock, self._ticket, self._pending, self._poisoned = RLock(), None, None, False

    def _validate_contract(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if self.contract != integrated_live_contract({key: self.contract[key] for key in APPROVED_BINDING}):
            raise ValueError('current integrated contract differs from approved use')

    def claim(self, operation, task, rebuild):
        self.grant.validate()
        self._validate_contract()
        if type(task) is not ModelTask or task.kind not in KINDS or not callable(rebuild):
            raise ValueError('exact approved integrated task required')
        with self._lock:
            if self._poisoned or self._pending is not None:
                raise ValueError('integrated delivery already pending or unverified')
            if task.payload != rebuild():
                raise ValueError('integrated request differs from actual canonical material')
            integrated_remote_request_preview(task)
            request = digest(task.payload)
            attempt = digest(dict(run=self.run_digest, operation=operation, purpose=task.kind.value))
            self.audit.claim(attempt, request, purpose=task.kind.value, run_digest=self.run_digest)
            self._pending = self._ticket = _IntegratedTicket(attempt, request, task.kind, get_ident(), rebuild)

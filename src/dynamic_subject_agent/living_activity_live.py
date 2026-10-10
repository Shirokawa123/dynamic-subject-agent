"""S142 exact approved use, independent three-purpose audit and one-use tickets."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock, get_ident

from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.shared_activity import digest, shared_choice_policy
from dynamic_subject_agent.living_activity import (living_contract, SHARE_POLICY, REPLY_POLICY,
    living_policies, FINAL_TEXT_LIVE_VERSION, LIVING_TECHNICAL_VARIANTS)

# Each approval object is independent of source-generated witnesses. Changing
# a builder, material, policy or protocol cannot silently grant the new object.
APPROVED_LIVING_REVIEW = '153bc6e8bfe766a8cfc7a852b4ae295ea7acf8e2e20ea960d2ad7d7a91e08f06'
APPROVED_LIVING_MATERIAL_DIGEST = '30715f56be4a693835739645f7d8c07be264f3a2396790f82113503a00f0b44c'
APPROVED_LIVING_LOCAL_CONTRACT_SHA = '5751e5ed7e56f3b1451c683fb96bcc762ca783219f7df72e352458b61930f4b4'
APPROVED_LIVING_PROTOCOL_SHA = '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450'
APPROVED_LIVING_POLICY_HASHES = (
    '7737b3fdacad632414d0f09a29ef1a49f36fa0cea0c17277e7643bb1703ebc4f',
    'eaa2d6877df8edf70282e599049c4faef6b6cf50dfa823c564190e47d4823f4d',
    'ded5c6dd9b06f57ada4f42461c992cea43f9ad328388c4b89e86df4880cf7f00')
LIVING_APPROVAL = 'user-approved-living-sharing-followup-use-2026-10-06'
LIVING_LIVE_VERSION = 'living-activity-live-s142-1'
PURPOSES = frozenset(('living-activity-choice', 'living-activity-share', 'living-activity-reply'))
FINAL_TEXT_DEVELOPMENT_AUTHORIZATION = 'user-continued-same-use-final-text-development-2026-10-07'
FINAL_TEXT_POLICY_HASHES = ('7737b3fdacad632414d0f09a29ef1a49f36fa0cea0c17277e7643bb1703ebc4f',
    '4df535d7abf64f946a721d634efa179ee095f65bb2d29f7aff31e808976de671',
    '7a429342805e6095f425864750ef4047782dd4f354e61d9d64dfc74f01b8534a')
FINAL_TEXT_PROTOCOL_HASHES = ('3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '6cb5917026e0a98048608b2fc8ae7901385e12241d713b54767e1b4020420d31')


def living_protocol_for_kind(kind, *, technical_variant='baseline'):
    if (type(technical_variant) is not str or technical_variant not in LIVING_TECHNICAL_VARIANTS
        or type(kind) is not ModelTaskKind or kind.value not in PURPOSES):
        raise ValueError('closed living purpose and protocol required')
    result = deepcopy(current_living_protocol())
    if technical_variant in ('final-text','action-contract') and kind is ModelTaskKind.LIVING_ACTIVITY_REPLY:
        # Ordinary final content is text by default. No unverified text enum.
        del result['protocol']['response_format']
    return result


def living_grant_variant(grant):
    from dynamic_subject_agent.living_action_contract import LivingActionContractDevelopmentGrant
    if type(grant) is LivingActionContractDevelopmentGrant:
        return 'action-contract'
    if type(grant) is ApprovedLivingActivityGrant:
        return 'baseline'
    if type(grant) is LivingFinalTextDevelopmentGrant:
        return 'final-text'
    raise ValueError('exact independently scoped living grant required')


def current_living_protocol():
    from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
    from dynamic_subject_agent import deepseek, credentials
    protocol = communication_protocol('thinking-high', 'low')
    # Existing transport stores 30.0; the review's integer 30 is the same
    # exact duration. Normalize only this representation after checking it.
    if type(deepseek.DEEPSEEK_TIMEOUT_SECONDS) not in (int, float) or deepseek.DEEPSEEK_TIMEOUT_SECONDS != 30:
        raise ValueError('approved living protocol requires exactly 30 seconds')
    return dict(endpoint=deepseek.DEEPSEEK_ENDPOINT, timeout_seconds=30,
        slot=dict(provider_id=credentials.DEEPSEEK_CREDENTIAL_SLOT.provider_id, account_id=credentials.DEEPSEEK_CREDENTIAL_SLOT.account_id),
        protocol=dict(model=protocol['model'], **protocol['expression']))


@dataclass(frozen=True)
class ApprovedLivingActivityGrant:
    review_basis: str
    confirmed: bool = False

    def __post_init__(self):
        if self.review_basis != APPROVED_LIVING_REVIEW or self.confirmed is not True:
            raise ValueError('exact confirmed S142 human approval required')

    def validate(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        self.__post_init__()
        if (digest(APPROVED_BINDING) != APPROVED_LIVING_MATERIAL_DIGEST
            or digest(living_contract(APPROVED_BINDING)) != APPROVED_LIVING_LOCAL_CONTRACT_SHA):
            raise ValueError('approved living material or frozen local contract changed')
        policies = (shared_choice_policy('self-directed-activity'), SHARE_POLICY, REPLY_POLICY)
        if tuple(sha256(policy.encode()).hexdigest() for policy in policies) != APPROVED_LIVING_POLICY_HASHES:
            raise ValueError('independently pinned living policy changed')
        if digest(current_living_protocol()) != APPROVED_LIVING_PROTOCOL_SHA:
            raise ValueError('independently pinned living protocol or slot changed')


@dataclass(frozen=True)
class LivingFinalTextDevelopmentGrant:
    """Existing human data-use approval plus later same-use development decision.

    The new technical hashes are independently pinned below; they are not an
    assertion that a human separately approved their exact bytes.
    """
    review_basis: str
    development_authorization: str

    def __post_init__(self):
        if (self.review_basis != APPROVED_LIVING_REVIEW
            or self.development_authorization != FINAL_TEXT_DEVELOPMENT_AUTHORIZATION):
            raise ValueError('existing S142 use and exact continued development decision required')

    def validate(self):
        self.__post_init__()
        ApprovedLivingActivityGrant(self.review_basis, True).validate()
        if tuple(sha256(policy.encode()).hexdigest() for policy in living_policies('final-text')) != FINAL_TEXT_POLICY_HASHES:
            raise ValueError('independently pinned final-text policy changed')
        kinds = (ModelTaskKind.LIVING_ACTIVITY_CHOICE, ModelTaskKind.LIVING_ACTIVITY_SHARE, ModelTaskKind.LIVING_ACTIVITY_REPLY)
        if tuple(digest(living_protocol_for_kind(kind, technical_variant='final-text')) for kind in kinds) != FINAL_TEXT_PROTOCOL_HASHES:
            raise ValueError('independently pinned final-text protocol or slot changed')


def living_live_contract(binding):
    ApprovedLivingActivityGrant(APPROVED_LIVING_REVIEW, True).validate()
    base = living_contract(binding)
    return dict(base, version=LIVING_LIVE_VERSION, authorization=LIVING_APPROVAL, provider='deepseek',
        credential_use='existing-Windows-slot-HTTPS-Bearer-only',
        excluded='background-service-notifications-offline-catchup-persona-rewrite-cloud-migration-new-material',
        technical_variant=dict(base['technical_variant'], name='living-live',
            approved_review_basis=APPROVED_LIVING_REVIEW, protocol_sha=APPROVED_LIVING_PROTOCOL_SHA))


def living_final_text_contract(binding):
    LivingFinalTextDevelopmentGrant(APPROVED_LIVING_REVIEW, FINAL_TEXT_DEVELOPMENT_AUTHORIZATION).validate()
    base = living_contract(binding)
    return dict(base, version=FINAL_TEXT_LIVE_VERSION, authorization=LIVING_APPROVAL,
        development_authorization=FINAL_TEXT_DEVELOPMENT_AUTHORIZATION, provider='deepseek',
        credential_use='existing-Windows-slot-HTTPS-Bearer-only',
        excluded='background-service-notifications-offline-catchup-persona-rewrite-cloud-migration-new-material',
        technical_variant=dict(base['technical_variant'], name='living-final-text-live',
            inherited_use_review_basis=APPROVED_LIVING_REVIEW,
            choice_policy_sha=FINAL_TEXT_POLICY_HASHES[0], share_policy_sha=FINAL_TEXT_POLICY_HASHES[1],
            reply_policy_sha=FINAL_TEXT_POLICY_HASHES[2],
            purpose_protocol_sha=dict(zip(('choice', 'share', 'reply'), FINAL_TEXT_PROTOCOL_HASHES, strict=True)),
            final_content='natural-text-original-wrapper-zh'))


def living_live_contract_for_variant(binding, *, technical_variant='baseline'):
    if technical_variant == 'baseline':
        return living_live_contract(binding)
    if technical_variant == 'final-text':
        return living_final_text_contract(binding)
    if technical_variant == 'action-contract':
        from dynamic_subject_agent.living_action_contract import living_action_contract
        return living_action_contract(binding)
    raise ValueError('closed living technical variant required')


class LivingActivityCallAudit(DevelopmentCallAudit):
    purposes = PURPOSES

    @staticmethod
    def configuration():
        return dict(version='living-activity-call-audit-s142-1', authorization=LIVING_APPROVAL,
            review_basis=APPROVED_LIVING_REVIEW, provider='deepseek', purposes=sorted(PURPOSES), limit=None)

    def snapshot(self):
        fields = ('ordinal', 'attempt_id', 'request_digest', 'purpose', 'run_digest', 'status', 'output_digest')
        with self._transaction() as db:
            return tuple(dict(zip(fields, row[:-1], strict=True)) for row in self._verified(db))


class LivingFinalTextCallAudit(LivingActivityCallAudit):
    @staticmethod
    def configuration():
        return dict(version='living-final-text-call-audit-s144-1', authorization=LIVING_APPROVAL,
            development_authorization=FINAL_TEXT_DEVELOPMENT_AUTHORIZATION,
            inherited_use_review_basis=APPROVED_LIVING_REVIEW, provider='deepseek', purposes=sorted(PURPOSES), limit=None)


class LivingActionContractCallAudit(LivingActivityCallAudit):
    @staticmethod
    def configuration():
        from dynamic_subject_agent.living_action_contract import ACTION_DEVELOPMENT_AUTHORIZATION
        return dict(version='living-action-contract-call-audit-s149-1',authorization=LIVING_APPROVAL,
            development_authorization=ACTION_DEVELOPMENT_AUTHORIZATION,
            inherited_use_review_basis=APPROVED_LIVING_REVIEW,provider='deepseek',purposes=sorted(PURPOSES),limit=None)


def living_audit_type(technical_variant):
    return {'baseline':LivingActivityCallAudit,'final-text':LivingFinalTextCallAudit,
        'action-contract':LivingActionContractCallAudit}[technical_variant]


def open_living_activity_audit(path, *, initialize=False, technical_variant='baseline'):
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError('absolute independent living audit required')
    if type(technical_variant) is not str or technical_variant not in LIVING_TECHNICAL_VARIANTS:
        raise ValueError('closed living audit variant required')
    audit_type = living_audit_type(technical_variant)
    witness = path.with_name(path.name + '-initialized')
    if witness.exists():
        if not witness.is_dir() or not path.is_dir():
            raise ValueError('living audit witness missing')
        return audit_type(path)
    if path.exists() or not initialize:
        raise ValueError('living audit cannot be recreated or repurposed')
    witness.mkdir(parents=True, exist_ok=False)
    return audit_type(path, initialize=True)


@dataclass(frozen=True)
class _LivingTicket:
    attempt: str
    request_digest: str
    kind: ModelTaskKind
    thread_id: int
    rebuild: object


class LivingActivityDelivery:
    def __init__(self, *, grant, audit, contract, state_path):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        variant = living_grant_variant(grant)
        expected_audit = living_audit_type(variant)
        if type(audit) is not expected_audit:
            raise ValueError('exact living grant and independent three-purpose audit required')
        grant.validate()
        if contract != living_live_contract_for_variant({key: contract[key] for key in APPROVED_BINDING}, technical_variant=variant):
            raise ValueError('exact living LIVE contract required')
        self.grant, self.audit, self.contract, self.technical_variant = grant, audit, deepcopy(contract), variant
        self.run_digest = digest(dict(contract=contract, state_path=str(state_path.resolve()), audit_path=str(audit.path.resolve())))
        self._lock, self._ticket, self._pending, self._poisoned = RLock(), None, None, False

    def _validate_contract(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if (living_grant_variant(self.grant) != self.technical_variant
            or self.contract != living_live_contract_for_variant({key: self.contract[key] for key in APPROVED_BINDING}, technical_variant=self.technical_variant)):
            raise ValueError('current living contract differs from independently pinned approval')

    def claim(self, operation, task, rebuild):
        from dynamic_subject_agent.living_activity_remote_preview import living_remote_request_preview
        self.grant.validate()
        self._validate_contract()
        if type(task) is not ModelTask or task.kind.value not in PURPOSES or not callable(rebuild):
            raise ValueError('exact approved living purpose and reconstruction required')
        with self._lock:
            if self._poisoned or self._pending is not None:
                raise ValueError('living delivery already pending or unverified')
            if task.payload != rebuild():
                raise ValueError('living task differs from current sealed and canonical input')
            validate_living_request_payload(task)
            living_remote_request_preview(task, technical_variant=self.technical_variant)
            request = digest(task.payload)
            attempt = digest(dict(run=self.run_digest, operation=operation, purpose=task.kind.value))
            self.audit.claim(attempt, request, purpose=task.kind.value, run_digest=self.run_digest)
            self._pending = self._ticket = _LivingTicket(attempt, request, task.kind, get_ident(), rebuild)

    def consume(self, task):
        with self._lock:
            ticket, self._ticket = self._ticket, None
            if (self._poisoned or ticket is None or ticket.thread_id != get_ident() or type(task) is not ModelTask
                or task.kind is not ticket.kind or digest(task.payload) != ticket.request_digest):
                raise ValueError('one current same-client same-thread living ticket required')
            self.grant.validate()
            self._validate_contract()
            actual = deepcopy(ticket.rebuild())
            if actual != task.payload or digest(actual) != ticket.request_digest:
                raise ValueError('living sealed, canonical, permission or day basis changed before delivery')
            validate_living_request_payload(ModelTask(task.kind, actual))
            return ModelTask(task.kind, actual)

    def record(self, status, value=None):
        with self._lock:
            if self._pending is None or self._pending.thread_id != get_ident() or self._ticket is not None:
                raise ValueError('consumed same-thread living claim required')
            try:
                self.audit.record(self._pending.attempt, status=status, output_digest=None if value is None else digest(value))
            except Exception:
                self._poisoned = True
                raise
            self._pending = None


def validate_living_request_payload(task):
    """Closed fields supplement fresh canonical reconstruction, never expand it."""
    from dynamic_subject_agent.original_whole_chat import OriginalWholeProjection, validate_whole_projection
    from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
    from dynamic_subject_agent.shared_activity import allowed_actions
    from dynamic_subject_agent.first_life import validate_plan
    payload = task.payload['payload']
    if type(payload) is not dict:
        raise ValueError('closed living payload required')
    reply = task.kind is ModelTaskKind.LIVING_ACTIVITY_REPLY
    keys = {'background', 'evidence', 'exchange', 'turn'} if reply else {'background', 'shared_experience',
        'current_activity', 'current_plan'} if task.kind is ModelTaskKind.LIVING_ACTIVITY_CHOICE else {'background', 'shared_experience', 'activity_result'}
    if set(payload) != keys:
        raise ValueError('outbound living fields differ from approved projection')
    exchange = tuple(RecentDialogueTurn(**row) for row in payload['exchange']) if reply else ()
    turn = payload['turn'] if reply else dict(current_message='考虑日常构图文字方案。', history_enabled=False, has_prior_committed_exchange=False)
    validate_whole_projection(OriginalWholeProjection(turn, payload['background'], exchange,
        dict(current_activity=None, current_plan=None, related_event=None)))
    evidence = payload['evidence'] if reply else payload
    if reply and (type(evidence) is not dict or set(evidence) != {'shared_experience', 'activity_result', 'latest_share'}):
        raise ValueError('closed living reply evidence required')
    source = evidence['shared_experience']
    if source is not None and (type(source) is not dict or set(source) != {'label', 'quote'} or source['label'] != 'E1'
        or type(source['quote']) is not str or not source['quote'].strip() or len(source['quote']) > 400 or '\x00' in source['quote']):
        raise ValueError('one bounded E1 or null required')
    if task.kind is ModelTaskKind.LIVING_ACTIVITY_CHOICE:
        activity = payload['current_activity']
        if (type(activity) is not dict or set(activity) != {'phase', 'allowed_actions'}
            or tuple(activity['allowed_actions']) != allowed_actions(activity['phase'])):
            raise ValueError('exact current activity phase required')
        if payload['current_plan'] is not None:
            validate_plan(payload['current_plan'])
    else:
        result = evidence['activity_result']
        if result is not None:
            expected = {'kind', 'plan'} if reply else {'action', 'plan'}
            if (type(result) is not dict or set(result) != expected
                or reply and result['kind'] != 'composition-text'
                or not reply and result['action'] not in ('start', 'revise')):
                raise ValueError('one bounded actual text plan required')
            if result['plan'] is not None:
                validate_plan(result['plan'])
            elif not reply:
                raise ValueError('sharing requires actual new plan')
        elif not reply:
            raise ValueError('sharing requires an actual result')
    if reply:
        share = evidence['latest_share']
        if share is not None and (type(share) is not dict or set(share) != {'text'} or type(share['text']) is not str
            or not share['text'].strip() or len(share['text']) > 400 or '\x00' in share['text']):
            raise ValueError('one bounded latest share text required')

"""S146 exact approved three-purpose use, metadata audit and one-use tickets."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock, get_ident

from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.shared_activity import digest
from dynamic_subject_agent.working_understanding import working_contract, working_policies, FORM_POLICY, CHOICE_POLICY, REPLY_POLICY

APPROVED_WORKING_REVIEW = 'e87c9db1f6f52409faee497ca05f0852362add519e461d48f50bee27d760977c'
APPROVED_WORKING_MATERIAL_DIGEST = '30715f56be4a693835739645f7d8c07be264f3a2396790f82113503a00f0b44c'
APPROVED_WORKING_LOCAL_CONTRACT_SHA = 'ddc346d616a434ebb94c5dc45145be8c7c1221266f337b21af687226300239e3'
APPROVED_WORKING_POLICY_HASHES = (
    'a45773c93835e96ecb28510eafe4a6aa8531026bde059ab314f0c10652bb3527',
    'a25327a7b67d90205c9eb281b6afa0a08949cda4a54e051d6c231c44b490ee78',
    'f9ca9cbc083736e3c1500b2cda5e54a7af585f4458400c810054d44391bd0cc6')
APPROVED_WORKING_PROTOCOL_HASHES = (
    '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '6cb5917026e0a98048608b2fc8ae7901385e12241d713b54767e1b4020420d31')
APPROVED_FIRST_SCENE_SHA = 'fbb87ebeec6a0dd0e8049d19bcf661fa5d4ac3064beaf7166f81170f6cc7c00a'
WORKING_APPROVAL = 'user-approved-working-understanding-use-2026-10-09'
WORKING_LIVE_VERSION = 'working-understanding-live-s146-1'
FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION = 'user-continued-entry-reference-grounding-2026-10-09'
FACT_FAITHFUL_LIVE_VERSION = 'working-fact-faithful-live-s147-1'
WORKING_TECHNICAL_VARIANTS = ('baseline','fact-faithful')
FACT_FAITHFUL_POLICY_HASHES = (
    '909d7f6cfbf8fadce1e548f803dcd99cf85b1bfd0337bf759c9c4f8af6529f27',
    '102cd1e31a127e1cadcbc001902873aa1fd3d97473bd4eb8c015e026abdbe02c',
    '174c545df32e46b0709fc55c3f508545b885f2414c5e71771508e39b5fbb5abe')
FACT_FAITHFUL_PROTOCOL_HASHES = (
    '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '6cb5917026e0a98048608b2fc8ae7901385e12241d713b54767e1b4020420d31')
KINDS = (ModelTaskKind.WORKING_UNDERSTANDING_FORM, ModelTaskKind.WORKING_ACTIVITY_CHOICE, ModelTaskKind.WORKING_ACTIVITY_REPLY)
PURPOSES = frozenset(kind.value for kind in KINDS)


def working_protocol_for_kind(kind):
    from dynamic_subject_agent.living_activity_live import current_living_protocol
    if type(kind) is not ModelTaskKind or kind not in KINDS:
        raise ValueError('exact approved working purpose required')
    value = deepcopy(current_living_protocol())
    if kind is ModelTaskKind.WORKING_ACTIVITY_REPLY:
        del value['protocol']['response_format']
    return value


@dataclass(frozen=True)
class ApprovedWorkingUnderstandingGrant:
    review_basis: str
    confirmed: bool = False

    def __post_init__(self):
        if self.review_basis != APPROVED_WORKING_REVIEW or self.confirmed is not True:
            raise ValueError('exact confirmed S145 three-purpose human approval required')

    def validate(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        self.__post_init__()
        if (digest(APPROVED_BINDING) != APPROVED_WORKING_MATERIAL_DIGEST
            or digest(working_contract(APPROVED_BINDING)) != APPROVED_WORKING_LOCAL_CONTRACT_SHA):
            raise ValueError('approved working material or frozen LOCAL contract changed')
        if tuple(sha256(policy.encode()).hexdigest() for policy in (FORM_POLICY, CHOICE_POLICY, REPLY_POLICY)) != APPROVED_WORKING_POLICY_HASHES:
            raise ValueError('independently pinned working policy changed')
        if tuple(digest(working_protocol_for_kind(kind)) for kind in KINDS) != APPROVED_WORKING_PROTOCOL_HASHES:
            raise ValueError('independently pinned working protocol or slot changed')


@dataclass(frozen=True)
class WorkingFactFaithfulDevelopmentGrant:
    """Inherited human data-use approval and independently pinned development.

    No claim that the human approved the candidate's new technical hashes.
    """
    review_basis: str
    development_authorization: str

    def __post_init__(self):
        if (self.review_basis != APPROVED_WORKING_REVIEW
            or self.development_authorization != FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION):
            raise ValueError('existing working use and exact continued development decision required')

    def validate(self):
        self.__post_init__()
        ApprovedWorkingUnderstandingGrant(self.review_basis,True).validate()
        if tuple(sha256(policy.encode()).hexdigest() for policy in working_policies('fact-faithful')) != FACT_FAITHFUL_POLICY_HASHES:
            raise ValueError('independently pinned fact-faithful policy changed')
        if tuple(digest(working_protocol_for_kind(kind)) for kind in KINDS) != FACT_FAITHFUL_PROTOCOL_HASHES:
            raise ValueError('independently pinned fact-faithful protocol or slot changed')


def working_grant_variant(grant):
    if type(grant) is ApprovedWorkingUnderstandingGrant:
        return 'baseline'
    if type(grant) is WorkingFactFaithfulDevelopmentGrant:
        return 'fact-faithful'
    raise ValueError('exact independently scoped working grant required')


def working_variant_for_authority(authority):
    from dynamic_subject_agent.shared_activity import WORKING_LIVE_AUTHORITY,WORKING_FACT_FAITHFUL_AUTHORITY
    if authority == WORKING_LIVE_AUTHORITY:
        return 'baseline'
    if authority == WORKING_FACT_FAITHFUL_AUTHORITY:
        return 'fact-faithful'
    raise ValueError('exact working LIVE authority required')


def working_live_contract(binding):
    ApprovedWorkingUnderstandingGrant(APPROVED_WORKING_REVIEW, True).validate()
    base = working_contract(binding)
    return dict(base, version=WORKING_LIVE_VERSION, authorization=WORKING_APPROVAL, provider='deepseek',
        credential_use='existing-Windows-slot-HTTPS-Bearer-only',
        excluded='automatic-life-sharing-persona-rewrite-reflection-cloud-migration-new-material-new-provider-new-credential-use',
        technical_variant=dict(base['technical_variant'], name='working-live',
            approved_review_basis=APPROVED_WORKING_REVIEW,
            approved_first_scene_sha=APPROVED_FIRST_SCENE_SHA,
            purpose_protocol_sha=dict(zip(('form','choice','reply'),APPROVED_WORKING_PROTOCOL_HASHES,strict=True)),
            final_content='natural-text-original-wrapper-zh'))


def working_fact_faithful_contract(binding):
    WorkingFactFaithfulDevelopmentGrant(APPROVED_WORKING_REVIEW,FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION).validate()
    base=working_contract(binding)
    return dict(base,version=FACT_FAITHFUL_LIVE_VERSION,authorization=WORKING_APPROVAL,
        development_authorization=FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION,provider='deepseek',
        credential_use='existing-Windows-slot-HTTPS-Bearer-only',
        excluded='automatic-life-sharing-persona-rewrite-reflection-cloud-migration-new-material-new-provider-new-credential-use',
        technical_variant=dict(base['technical_variant'],name='working-fact-faithful-live',
            inherited_use_review_basis=APPROVED_WORKING_REVIEW,
            form_policy_sha=FACT_FAITHFUL_POLICY_HASHES[0],choice_policy_sha=FACT_FAITHFUL_POLICY_HASHES[1],
            reply_policy_sha=FACT_FAITHFUL_POLICY_HASHES[2],
            purpose_protocol_sha=dict(zip(('form','choice','reply'),FACT_FAITHFUL_PROTOCOL_HASHES,strict=True)),
            final_content='natural-text-original-wrapper-zh'))


def working_live_contract_for_variant(binding, *, technical_variant='baseline'):
    if technical_variant == 'baseline':
        return working_live_contract(binding)
    if technical_variant == 'fact-faithful':
        return working_fact_faithful_contract(binding)
    raise ValueError('closed working LIVE variant required')


class WorkingUnderstandingCallAudit(DevelopmentCallAudit):
    purposes = PURPOSES

    @staticmethod
    def configuration():
        return dict(version='working-understanding-call-audit-s146-1', authorization=WORKING_APPROVAL,
            review_basis=APPROVED_WORKING_REVIEW, provider='deepseek', purposes=sorted(PURPOSES), limit=None)

    def snapshot(self):
        fields = ('ordinal','attempt_id','request_digest','purpose','run_digest','status','output_digest')
        with self._transaction() as db:
            return tuple(dict(zip(fields,row[:-1],strict=True)) for row in self._verified(db))


class WorkingFactFaithfulCallAudit(WorkingUnderstandingCallAudit):
    @staticmethod
    def configuration():
        return dict(version='working-fact-faithful-call-audit-s147-1',authorization=WORKING_APPROVAL,
            development_authorization=FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION,
            inherited_use_review_basis=APPROVED_WORKING_REVIEW,provider='deepseek',purposes=sorted(PURPOSES),limit=None)


def open_working_understanding_audit(path, *, initialize=False, technical_variant='baseline'):
    if not isinstance(path,Path) or not path.is_absolute():
        raise ValueError('absolute independent working audit required')
    if type(technical_variant) is not str or technical_variant not in WORKING_TECHNICAL_VARIANTS:
        raise ValueError('closed working audit variant required')
    audit_type=WorkingUnderstandingCallAudit if technical_variant=='baseline' else WorkingFactFaithfulCallAudit
    witness=path.with_name(path.name+'-initialized')
    if witness.exists():
        if not witness.is_dir() or not path.is_dir():
            raise ValueError('working audit witness missing')
        return audit_type(path)
    if path.exists() or not initialize:
        raise ValueError('working audit cannot be recreated or repurposed')
    witness.mkdir(parents=True,exist_ok=False)
    return audit_type(path,initialize=True)


@dataclass(frozen=True)
class _WorkingTicket:
    attempt: str
    request_digest: str
    kind: ModelTaskKind
    thread_id: int
    rebuild: object


class WorkingUnderstandingDelivery:
    def __init__(self, *, grant, audit, contract, state_path):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        variant=working_grant_variant(grant)
        if type(audit) is not (WorkingUnderstandingCallAudit if variant=='baseline' else WorkingFactFaithfulCallAudit):
            raise ValueError('exact working approval and three-purpose audit required')
        grant.validate()
        if contract != working_live_contract_for_variant({key:contract[key] for key in APPROVED_BINDING},technical_variant=variant):
            raise ValueError('exact working LIVE contract required')
        self.grant,self.audit,self.contract=grant,audit,deepcopy(contract)
        self.technical_variant=variant
        self.run_digest=digest(dict(contract=contract,state_path=str(state_path.resolve()),audit_path=str(audit.path.resolve())))
        self._lock,self._ticket,self._pending,self._poisoned=RLock(),None,None,False

    def _validate_contract(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if (working_grant_variant(self.grant)!=self.technical_variant
            or self.contract != working_live_contract_for_variant({key:self.contract[key] for key in APPROVED_BINDING},technical_variant=self.technical_variant)):
            raise ValueError('working contract differs from exact approval')

    def claim(self, operation, task, rebuild):
        from dynamic_subject_agent.working_understanding_remote_preview import working_remote_request_preview
        self.grant.validate(); self._validate_contract()
        if type(task) is not ModelTask or task.kind not in KINDS or not callable(rebuild):
            raise ValueError('exact working purpose and canonical reconstruction required')
        with self._lock:
            if self._poisoned or self._pending is not None:
                raise ValueError('working delivery already pending or unverified')
            if task.payload != rebuild():
                raise ValueError('working input differs from sealed canonical source')
            validate_working_request_payload(task)
            working_remote_request_preview(task,technical_variant=self.technical_variant)
            request=digest(task.payload)
            attempt=digest(dict(run=self.run_digest,operation=operation,purpose=task.kind.value))
            self.audit.claim(attempt,request,purpose=task.kind.value,run_digest=self.run_digest)
            self._pending=self._ticket=_WorkingTicket(attempt,request,task.kind,get_ident(),rebuild)

    def consume(self, task):
        with self._lock:
            ticket,self._ticket=self._ticket,None
            if (self._poisoned or ticket is None or ticket.thread_id!=get_ident() or type(task) is not ModelTask
                or task.kind is not ticket.kind or digest(task.payload)!=ticket.request_digest):
                raise ValueError('one current same-client same-thread working ticket required')
            self.grant.validate(); self._validate_contract()
            actual=deepcopy(ticket.rebuild())
            if actual!=task.payload or digest(actual)!=ticket.request_digest:
                raise ValueError('working sealed canonical source or permission changed before delivery')
            validate_working_request_payload(ModelTask(task.kind,actual))
            return ModelTask(task.kind,actual)

    def record(self, status, value=None):
        with self._lock:
            if self._pending is None or self._pending.thread_id!=get_ident() or self._ticket is not None:
                raise ValueError('consumed same-thread working claim required')
            try:
                self.audit.record(self._pending.attempt,status=status,output_digest=None if value is None else digest(value))
            except Exception:
                self._poisoned=True
                raise
            self._pending=None


def _validate_exchanges(value):
    if type(value) is not list or len(value)!=2:
        raise ValueError('exactly two approved user quotes required')
    for index,row in enumerate(value):
        if (type(row) is not dict or set(row)!={'label','quote'} or row['label']!='U'+str(index+1)
            or type(row['quote']) is not str or not row['quote'].strip() or len(row['quote'])>400 or '\x00' in row['quote']):
            raise ValueError('bounded exact user quote projection required')


def _validate_activity_result(value, *, formation=False):
    from dynamic_subject_agent.first_life import validate_plan
    if value is None:
        return
    expected={'label','kind','plan'} if formation else {'kind','plan'}
    if (type(value) is not dict or set(value)!=expected or value['kind']!='composition-text'
        or formation and value['label']!='A1'):
        raise ValueError('bounded committed text result projection required')
    if value['plan'] is not None:
        validate_plan(value['plan'])
    elif formation:
        raise ValueError('A1 requires an actual committed text plan')


def validate_working_request_payload(task):
    from dynamic_subject_agent.original_whole_chat import OriginalWholeProjection,validate_whole_projection
    from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
    from dynamic_subject_agent.first_life import validate_plan
    from dynamic_subject_agent.shared_activity import allowed_actions
    if type(task) is not ModelTask or task.kind not in KINDS:
        raise ValueError('closed working task required')
    payload=task.payload['payload']
    reply=task.kind is ModelTaskKind.WORKING_ACTIVITY_REPLY
    form=task.kind is ModelTaskKind.WORKING_UNDERSTANDING_FORM
    keys=({'turn','background','exchange','evidence'} if reply else {'background','scope','exchanges','activity_result'}
        if form else {'background','shared_experience','current_activity','current_plan','working_understanding'})
    if type(payload) is not dict or set(payload)!=keys:
        raise ValueError('approved working fields required')
    exchange=tuple(RecentDialogueTurn(**row) for row in payload['exchange']) if reply else ()
    turn=payload['turn'] if reply else dict(current_message='考虑日常构图文字方案。',history_enabled=False,has_prior_committed_exchange=False)
    validate_whole_projection(OriginalWholeProjection(turn,payload['background'],exchange,
        dict(current_activity=None,current_plan=None,related_event=None)))
    if form:
        if payload['scope']!='composition-text':
            raise ValueError('fixed working scope required')
        _validate_exchanges(payload['exchanges'])
        _validate_activity_result(payload['activity_result'],formation=True)
        return
    evidence=payload['evidence'] if reply else payload
    if reply and (type(evidence) is not dict or set(evidence)!={'shared_experience','activity_result','working_understanding'}):
        raise ValueError('approved working reply evidence required')
    if evidence['shared_experience'] is not None:
        raise ValueError('legacy E1 is always null in the working grant')
    if reply:
        _validate_activity_result(evidence['activity_result'])
    else:
        activity=payload['current_activity']
        if type(activity) is not dict or set(activity)!={'phase','allowed_actions'}:
            raise ValueError('actual working activity phase and actions required')
        actions=allowed_actions(activity['phase'])
        if tuple(activity['allowed_actions'])!=(('revise','defer') if payload['current_plan'] is None and activity['phase']!='unstarted' else actions):
            raise ValueError('actual working activity phase and actions required')
        if payload['current_plan'] is not None:
            validate_plan(payload['current_plan'])
    understanding=evidence['working_understanding']
    if understanding is not None:
        if (type(understanding) is not dict or set(understanding)!={'label','scope','statement','support'}
            or understanding['label']!='W1' or understanding['scope']!='composition-text'
            or type(understanding['statement']) is not str or not understanding['statement'].strip()
            or len(understanding['statement'])>240 or '\x00' in understanding['statement']
            or type(understanding['support']) is not dict or set(understanding['support'])!={'exchanges','activity_result'}):
            raise ValueError('one bounded tentative W1 projection required')
        _validate_exchanges(understanding['support']['exchanges'])
        _validate_activity_result(understanding['support']['activity_result'],formation=True)

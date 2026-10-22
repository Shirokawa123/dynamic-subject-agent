"""Approved M012 development composition contracts and three-purpose delivery.

One canonical schema6 development Timeline is reused, never upgraded/copied
from the user's schema11. Typed native clicks/schema12 remain unavailable.
"""
from copy import deepcopy
from dataclasses import dataclass,asdict
from datetime import date
from hashlib import sha256
from pathlib import Path
from threading import RLock,get_ident
from uuid import UUID
import json
import os

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind

REVIEW='70b74893b4b3be2258c0ade092396dcd5ba720cace42dd105404748589f1022c'
REVIEW_SHA='c82f227aa8cf6f04bba03c27da5ef7e85ef8db915fdcbef97b3518ab130e8ada'
VERSION='memorie-activity-development-m015-1'
KINDS={ModelTaskKind.LIVING_ACTIVITY_REPLY:'reply',ModelTaskKind.LIVING_ACTIVITY_CHOICE:'choice',ModelTaskKind.LIVING_ACTIVITY_SHARE:'share'}


def digest(value):return sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class ApprovedNativeActivityGrant:
    approval_path: Path

    def validate(self):
        from dynamic_subject_agent.memorie_companion_contract import DEFINITION
        from dynamic_subject_agent import deepseek,credentials
        if (deepseek.DEEPSEEK_ENDPOINT!='https://api.deepseek.com/chat/completions' or deepseek.DEEPSEEK_TIMEOUT_SECONDS!=30
            or (credentials.DEEPSEEK_CREDENTIAL_SLOT.provider_id,credentials.DEEPSEEK_CREDENTIAL_SLOT.account_id)!=('deepseek','default')):
            raise ValueError('approved endpoint, timeout or Windows account slot changed')
        if not isinstance(self.approval_path,Path) or not self.approval_path.is_absolute():raise ValueError('exact private use receipt required')
        raw=self.approval_path.read_bytes()
        if len(raw)>8192:raise ValueError('use receipt oversized')
        value=json.loads(raw)
        expected=dict(version='memorie-native-activity-use-approval-m012-1',review_basis=REVIEW,review_file_sha256=REVIEW_SHA,
            definition_basis=DEFINITION,human_confirmed=True,data_upgrade_included=False,installation_included=False,
            user_reply='同意这份新增模型用途',authorization_source='direct-human-reply:call_99d9a151c007467c94a467ebbaab24c6')
        if value!=expected or any(type(value[k]) is not bool for k in ('human_confirmed','data_upgrade_included','installation_included')):
            raise ValueError('exact M012 human use approval required')
        from dynamic_subject_agent.memorie_activity_use import policies
        if {k:sha256(v.encode()).hexdigest() for k,v in policies().items()}!=POLICY_HASHES:
            raise ValueError('approved M012 policies changed')
        return value


# Immutable hashes copied from the exact review, not recalculated grants.
POLICY_HASHES = {'choice': 'd4ecbf35332d582b23d790e78569461cf2c0bc8f0bf502792df1087757f78e2e', 'reply': '9b0beb02aa0d9478da792d804998d625a6f00ac5e2b265f2bf2824aef85a72ba', 'share': 'd9ff9bd3acdf08a41532db4507e74d9a1c6c1e3dfafb99f542cfa856feaf6eb1'}


def contract(binding):
    from dynamic_subject_agent.memorie_companion_contract import DEFINITION,ASSET
    from dynamic_subject_agent.living_activity import living_contract
    if (binding.get('definition_basis')!=DEFINITION or binding.get('runtime_asset_sha')!=ASSET
        or binding.get('review_basis')!=REVIEW or binding.get('scope_digest')!=REVIEW):
        raise ValueError('same sealed Memorie material required')
    base=living_contract(binding,independent=True,activity_kind='herb-note-outline')
    base.pop('local_preparation',None)
    base.pop('reasoning_effort',None)
    return dict(base,version=VERSION,authorization=REVIEW,scope_digest=REVIEW,review_basis=REVIEW,
        provider='deepseek',credential_use='existing-Windows-slot-HTTPS-Bearer-only',thinking='disabled',policy_sha=POLICY_HASHES.get('reply'),
        memorie_activity_development=True,technical_variant=dict(base['technical_variant'],name='living-live',timeline_schema=6,
            max_share_chars=120,choice_policy_sha=POLICY_HASHES.get('choice'),share_policy_sha=POLICY_HASHES.get('share'),reply_policy_sha=POLICY_HASHES.get('reply')))


def is_contract(value):return type(value) is dict and value.get('version')==VERSION


def build_preview(envelope,view,purpose,*,message=None,dialogue=None,enabled=False):
    from dynamic_subject_agent.memorie_companion_contract import DEFINITION,ASSET
    from dynamic_subject_agent.memorie_native import NativeReplyProjection,wire as old_wire
    from dynamic_subject_agent.memorie_activity_use import policies
    from dynamic_subject_agent.shared_activity import allowed_actions
    from dynamic_subject_agent.living_activity import latest_share
    if envelope['definition_basis']!=DEFINITION or digest(envelope['runtime_asset'])!=ASSET:raise ValueError('sealed material changed')
    asset=envelope['runtime_asset']
    material=dict(character=dict(name='梅莫莉',stage=asset['initial_stage'],knowledge=[{k:i[k] for k in (
        'dimension','kind','statement','event_time','knowledge_time')} for i in asset['eligible']]),personality=asset['personality'])
    source=view['visible_source'];result=view['visible_result']
    experience=None if source is None else dict(label='E1',quote=source.quote)
    activity=None if result is None or result.plan is None else dict(kind='herb-note-outline',plan=asdict(result.plan))
    if purpose=='reply':
        if dialogue.status!='available':raise ValueError('verified dialogue required')
        exchange=[dict(interaction=dict(kind='text',text=t.user_text),assistant_text=t.assistant_text) for t in dialogue.recent_dialogue]
        base=dict(material,interaction=dict(kind='text',text=message),situation=None,exchange=exchange)
        old_wire(NativeReplyProjection(canonical_json(base)))
        share=latest_share(view,enabled)
        payload=dict(base,experience=experience,activity_result=activity,latest_share=None if share is None else dict(text=share['text']))
    elif purpose=='choice':
        payload=dict(material,experience=experience,current_activity=dict(phase=view['phase'],allowed_actions=allowed_actions(view['phase'])),
            current_plan=view['current_plan'] and asdict(view['current_plan']))
    elif purpose=='share':
        if activity is None or result.event.kind not in ('start','revise'):raise ValueError('new committed outline required')
        payload=dict(material,experience=experience,activity_result=activity)
    else:raise ValueError('closed M012 purpose required')
    return dict(policy=policies()[purpose],payload=payload)


def wire(task):
    from dynamic_subject_agent.memorie_activity_use import policies
    from dynamic_subject_agent.memorie_native import NativeReplyProjection,wire as old_wire
    from dynamic_subject_agent.first_life import validate_plan
    from dynamic_subject_agent.shared_activity import allowed_actions
    purpose=KINDS.get(task.kind);value=task.payload
    if purpose is None or type(value) is not dict or set(value)!={'policy','payload'} or value['policy']!=policies()[purpose]:
        raise ValueError('exact M012 task policy required')
    p=value['payload']
    base={k:p[k] for k in ('character','personality')}
    old_wire(NativeReplyProjection(canonical_json(dict(base,interaction=dict(kind='text',text='仅校验人物材料。'),situation=None,exchange=[]))))
    expected={'character','personality','experience'} | ({'interaction','situation','exchange','activity_result','latest_share'} if purpose=='reply' else
        {'current_activity','current_plan'} if purpose=='choice' else {'activity_result'})
    if set(p)!=expected:raise ValueError('closed approved M012 fields required')
    source=p['experience']
    if source is not None and (type(source) is not dict or set(source)!={'label','quote'} or source['label']!='E1'
        or type(source['quote']) is not str or not source['quote'].strip() or len(source['quote'])>400 or '\x00' in source['quote']):raise ValueError('bounded E1 required')
    if purpose=='reply':
        old_wire(NativeReplyProjection(canonical_json({k:p[k] for k in ('character','personality','interaction','situation','exchange')})))
        share=p['latest_share']
        if share is not None and (type(share) is not dict or set(share)!={'text'} or not isinstance(share['text'],str)
            or not share['text'].strip() or len(share['text'])>120 or '\x00' in share['text']):raise ValueError('bounded native share required')
    if purpose=='choice':
        current=p['current_activity']
        if type(current) is not dict or set(current)!={'phase','allowed_actions'} or tuple(current['allowed_actions'])!=allowed_actions(current['phase']):raise ValueError('actual finite phase required')
        if p['current_plan'] is not None:validate_plan(p['current_plan'])
    else:
        result=p['activity_result']
        if result is not None:
            if type(result) is not dict or set(result)!={'kind','plan'} or result['kind']!='herb-note-outline':raise ValueError('actual outline required')
            validate_plan(result['plan'])
        elif purpose=='share':raise ValueError('share requires result')
    body=dict(model='deepseek-flash',messages=[dict(role='system',content=value['policy']),dict(role='user',content=canonical_json(p))],
        thinking=dict(type='disabled'),max_tokens=4096,stream=False)
    if purpose!='reply':body['response_format']=dict(type='json_object')
    raw=canonical_json(body).encode()
    if len(raw)>65536:raise ValueError('wire oversized')
    return raw


class _Purposes:
    def __contains__(self,value):
        try:
            kind,day=value.split('@');return kind in ('reply','choice','share') and date.fromisoformat(day).isoformat()==day
        except Exception:return False


class NativeActivityAudit(DevelopmentCallAudit):
    purposes=_Purposes()
    @staticmethod
    def configuration():return dict(version='memorie-activity-daily-audit-m015-1',authorization=REVIEW,provider='deepseek',limits=dict(choice=4,share=2,reply=None))

    def count(self,purpose,day):
        with self._transaction() as db:return sum(row[3]==purpose+'@'+day for row in self._verified(db))

    def claim_daily(self,attempt,request,*,purpose,day,run):
        combined=purpose+'@'+day
        if combined not in self.purposes:raise ValueError('exact purpose/day required')
        with self._transaction() as db:
            rows=self._verified(db);limit=dict(choice=4,share=2,reply=None)[purpose]
            if any(r[1]==attempt for r in rows) or limit is not None and sum(r[3]==combined for r in rows)>=limit:
                raise ValueError('operation already delivered or daily cap exhausted')
            if any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in (attempt,request,run)):
                raise ValueError('exact attempt metadata required')
            record=[len(rows),attempt,request,combined,run,'claimed',None]
            db.execute('INSERT INTO call_attempt VALUES(?,?,?,?,?,?,?,?)',(*record,self._hash(record)));self._update_head(db)


def audit_path():
    appdata=os.environ.get('LOCALAPPDATA')
    if not appdata or not Path(appdata).is_absolute():raise ValueError('Windows local control directory unavailable')
    return Path(appdata)/'DynamicSubjectAgent'/'memorie-activity-use'/REVIEW


def open_audit(grant):
    grant.validate()
    path=audit_path()
    witness=path.with_name(path.name+'-initialized')
    if witness.exists():
        if not path.is_dir():raise ValueError('daily audit missing; never reset quota')
        return NativeActivityAudit(path)
    if path.exists():raise ValueError('unknown existing daily audit')
    witness.mkdir(parents=True)
    return NativeActivityAudit(path,initialize=True)


class NativeActivityDelivery:
    def __init__(self,*,grant,contract,audit,state_path):
        grant.validate()
        if not is_contract(contract) or type(audit) is not NativeActivityAudit:raise ValueError('exact approved composition required')
        self.grant,self.contract,self.audit=grant,deepcopy(contract),audit
        self.run_digest=digest(dict(contract=contract,state_path=str(state_path.resolve())))
        self.lock=RLock();self.pending=self.ticket=None;self.poisoned=False
        self._validate_contract()

    def _validate_contract(self):
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if self.contract!=contract({key:self.contract[key] for key in APPROVED_BINDING}) or self.audit.path.resolve()!=audit_path().resolve():
            raise ValueError('exact approved contract and shared account audit required')

    def _day(self):
        from dynamic_subject_agent.living_activity import utc8_day
        return utc8_day()

    def available(self,purpose):
        limit=dict(choice=4,share=2,reply=None)[purpose]
        return not self.poisoned and (limit is None or self.audit.count(purpose,self._day())<limit)

    def claim(self,operation,task,rebuild):
        self.grant.validate();self._validate_contract()
        with self.lock:
            if self.poisoned or self.pending is not None or task.payload!=rebuild():raise ValueError('fresh canonical reconstruction required')
            raw=wire(task)
            op=operation.split(':')[0]
            if str(UUID(op))!=op:raise ValueError('canonical operation required')
            attempt=digest(dict(review=REVIEW,operation=op))
            self.audit.claim_daily(attempt,sha256(raw).hexdigest(),purpose=KINDS[task.kind],day=self._day(),run=self.run_digest)
            self.pending=self.ticket=(attempt,get_ident(),task.kind,digest(task.payload),rebuild,self._day())

    def consume(self,task):
        with self.lock:
            ticket,self.ticket=self.ticket,None
            if ticket is None or self.poisoned or ticket[1]!=get_ident() or task.kind!=ticket[2] or digest(task.payload)!=ticket[3]:raise ValueError('one current same-thread ticket required')
            self.grant.validate();self._validate_contract();actual=deepcopy(ticket[4]())
            if actual!=task.payload or self._day()!=ticket[5]:raise ValueError('source or day changed')
            wire(ModelTask(task.kind,actual))
            return ModelTask(task.kind,actual)

    def record(self,status,value=None):
        with self.lock:
            if self.pending is None or self.ticket is not None or self.pending[1]!=get_ident():raise ValueError('consumed ticket required')
            self.grant.validate()
            try:self.audit.record(self.pending[0],status=status,output_digest=None if value is None else digest(value))
            except Exception:self.poisoned=True;raise
            self.pending=None

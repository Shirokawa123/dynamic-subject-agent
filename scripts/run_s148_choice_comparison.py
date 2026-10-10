"""Frozen first-only N/Q/W choices. Diagnostics never publish product state.

--prepare reuses S147's actual independent A1 and related W1, then commits
three pairs of new source turns and their actual forms through the Facade.
--compare sends exactly the frozen subset requests through ModelGateway.
All final proposals/failures stay in the owned ignored directory; no reasoning
or credentials are saved. Neither mode may overwrite or repeat a prior run.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
from random import SystemRandom
import sys
from time import perf_counter
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'app/desktop'))
sys.path.insert(0, str(REPO/'src'))
ROOT = REPO/'.artifacts/s148/first-comparison'
PRIOR = Path('C:/Users/30252/AppData/Local/DynamicSubjectAgent/working-understanding-development/s147/live-entry-first-20261009-1')
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.shared_activity import digest, allowed_actions, adjudicate_choice
from dynamic_subject_agent.working_understanding import working_policies, support_projection, working_choice_for_adjudication
from dynamic_subject_agent.working_understanding_live import (
    WorkingFactFaithfulDevelopmentGrant, FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION,
    APPROVED_WORKING_REVIEW, validate_working_request_payload, working_protocol_for_kind,
    WorkingFactFaithfulCallAudit)
from dynamic_subject_agent.model_gateway import (ModelGateway, ModelTask, ModelTaskKind,
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelResult, ModelGatewayFailure)
from dynamic_subject_agent.deepseek import DeepSeekTransport

SOURCES = {
    'I': ['我说的是书籍封面的标题排字，不是人物画面的构图。我觉得标题字距应该紧一些。',
          '刚才字距紧一些的建议仅限那份文字封面；这次人物画面的空间安排请按你自己的关注决定。'],
    'L': ['只有以后改画雨中撑伞的构图，我才建议把伞上方压暗；这次先不要增加伞或雨景。',
          '那条压暗建议的前提是画面已经是雨中撑伞。现在这个人物构图不满足前提，不要为了用建议改成雨景。'],
    'C': ['就这次人物构图，我先建议主体旁留一块很空的区域。',
          '我收回刚才很空的区域建议。这次要让主体旁有少量纹理和阴影层次，不要一整块空白；只针对这一版。']}
ORDER = [('R','N'),('R','Q'),('R','W'),('I','Q'),('I','W'),('I','N'),
         ('L','W'),('L','N'),('L','Q'),('C','N'),('C','W'),('C','Q')]
POLICY = working_policies('fact-faithful')[1] + (
    '本请求working_understanding的statement若为null，仅有support逐字来源，不提供额外理解陈述；'
    '仍按原话的否定、对象和情境限定决定是否参考。statement非null时同样可不使用。')


def plain(value):
    if is_dataclass(value): return plain(asdict(value))
    if isinstance(value, dict): return {k: plain(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [plain(v) for v in value]
    return value.value if hasattr(value,'value') else value


def require(condition, code):
    if not condition: raise RuntimeError(code)


def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.pending')
    tmp.write_text(canonical_json(value),encoding='utf-8')
    tmp.replace(path)


def source_paths(product,state_path):
    binding=product._composition._host.query_binding(profile_id=product.profile_id,timeline_id=product.timeline_id)
    return dict(state=str(state_path),canonical=str(binding.timeline_root.timeline_database))


def source_stamp(paths):
    """Frozen owned canonical and permission state must remain byte-identical.

    The Facade validated scope when the sources were selected. A byte change
    now rejects the experiment rather than guessing whether it was harmless.
    No second factory/writer is opened while a comparison is being sent.
    """
    value=dict(paths)
    for field in ('state','canonical'):
        path=Path(paths[field]).resolve(strict=True)
        require(path.is_relative_to(ROOT.resolve()) or path.is_relative_to(PRIOR.resolve()),'owned-source-path-required')
        value[field+'_sha256']=sha256(path.read_bytes()).hexdigest()
    wal=Path(paths['canonical']+'-wal')
    value['wal_sha256']=sha256(wal.read_bytes()).hexdigest() if wal.exists() else None
    return value


def verify_sources(manifest,label):
    case=label.split('-')[0]
    for key in ('base',case):
        expected=manifest['source_witnesses'][key]
        require(source_stamp({field:expected[field] for field in ('state','canonical')})==expected,
            'canonical-or-source-permission-changed')


def choice_preview(base, support, arm):
    require(arm in ('N','Q','W'),'closed-arm-required')
    value=deepcopy(base)
    value['policy']=POLICY
    value['payload']['working_understanding']=None if arm=='N' else deepcopy(support)
    if arm=='Q': value['payload']['working_understanding']['statement']=None
    return value


def choice_wire(preview, full_support):
    require(preview['policy']==POLICY,'frozen-common-policy-required')
    validation=deepcopy(preview)
    validation['policy']=working_policies('fact-faithful')[1]
    current=validation['payload']['working_understanding']
    if current is not None:
        require(full_support is not None and current in (full_support,dict(full_support,statement=None)),
                'only-exact-source-statement-ablation-permitted')
        validation['payload']['working_understanding']=deepcopy(full_support)
        if validation['payload']['working_understanding']['statement'] is None:
            # A structural placeholder is never sent, rated or persisted as W1.
            validation['payload']['working_understanding']['statement']='结构校验占位。'
    validate_working_request_payload(ModelTask(ModelTaskKind.WORKING_ACTIVITY_CHOICE,validation))
    protocol=working_protocol_for_kind(ModelTaskKind.WORKING_ACTIVITY_CHOICE)
    body=dict(messages=[dict(role='system',content=POLICY),
        dict(role='user',content=canonical_json(preview['payload']))],**protocol['protocol'])
    wire=canonical_json(body).encode()
    require(len(wire)<=65536,'wire-bound-exceeded')
    return wire


class CapturingTransport(DeepSeekTransport):
    """One exact armed wire; raw final only, never reasoning or key."""
    def __init__(self, report, *, blocked=False):
        self.report,self.blocked,self.expected,self.final=report,blocked,None,None
        self.total=0
        self.delegate=None

    def arm(self,label,wire, *, diagnostic=False):
        payload=json.loads(json.loads(wire)['messages'][1]['content'])
        purpose='working-activity-choice' if 'current_activity' in payload else (
            'working-understanding-form' if 'scope' in payload else 'working-activity-reply')
        self.expected=dict(label=label,wire_sha256=sha256(wire).hexdigest(),diagnostic=diagnostic,purpose=purpose)
        self.final=None

    def post_json(self,**kwargs):
        require(not self.blocked and self.expected is not None,'unarmed-or-blocked-transport')
        require(kwargs['endpoint']=='https://api.deepseek.com/chat/completions' and kwargs['timeout_seconds']==30
            and sha256(kwargs['body']).hexdigest()==self.expected['wire_sha256'],'actual-wire-mismatch')
        expected,self.expected=self.expected,None
        row=dict(expected,status='started',ordinal=self.total)
        self.report['calls'].append(row);self.total+=1
        save(ROOT/'metadata.json',self.report)
        if self.delegate is None:
            from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport,DeepSeekCredentialResolver
            from dynamic_subject_agent.local_product import _WindowsLabResolver
            class Resolver(DeepSeekCredentialResolver):
                def resolve(inner, ref):
                    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
                    require((ref.backend_id,ref.key_id)==(DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID),'existing-slot-required')
                    self.report['credential_read_attempts']+=1
                    save(ROOT/'metadata.json',self.report)
                    return _WindowsLabResolver().resolve(ref)
            self.delegate=DeepSeekUrlLibTransport(credential_resolver=Resolver(),_opener=build_opener(ProxyHandler({})).open)
        started=perf_counter()
        try:
            response=self.delegate.post_json(**kwargs)
            row.update(status='received',http_status=response.status_code,response_sha256=sha256(response.body).hexdigest())
            # Strict production parsing happens separately. Preserve even invalid
            # final strings if JSON outer envelope allows extracting them.
            try:
                envelope=json.loads(response.body)
                self.final=envelope['choices'][0]['message']['content']
                if type(self.final) is str:
                    row['final_sha256']=sha256(self.final.encode()).hexdigest()
                    save(ROOT/'finals'/(expected['label']+'.json'),dict(final=self.final))
                usage=envelope.get('usage')
                row['usage']={key:value for key,value in usage.items()
                    if key in ('prompt_tokens','completion_tokens','total_tokens') and type(value) is int and value>=0} if type(usage) is dict else None
            except (ValueError,KeyError,IndexError,TypeError):
                row['final_extraction']='unavailable'
            return response
        except BaseException as error:
            row.update(status='exception',error_type=type(error).__name__)
            raise
        finally:
            row['elapsed_seconds']=perf_counter()-started
            save(ROOT/'metadata.json',self.report)


class ComparisonAudit(WorkingFactFaithfulCallAudit):
    purposes=frozenset((ModelTaskKind.WORKING_ACTIVITY_CHOICE.value,))
    @staticmethod
    def configuration():
        return dict(version='s148-choice-ablation-audit-1',inherited_use_review_basis=APPROVED_WORKING_REVIEW,
            authorization='user-requested-mechanism-validation-2026-10-10',provider='deepseek',
            purposes=sorted(ComparisonAudit.purposes),limit=None)


class ComparisonAdapter(ProviderAdapter):
    capabilities=ProviderCapabilities('deepseek','deepseek-flash',False,(StructuredOutputMode.JSON_OBJECT,))
    def __init__(self, transport, audit, manifest_sha):
        self.transport,self.audit,self.manifest_sha=transport,audit,manifest_sha
        self.pending=None

    def arm(self,label):
        require(self.pending is None,'candidate-already-armed')
        self.pending=label

    def invoke(self,task):
        from dynamic_subject_agent.cognition import CredentialRef
        from dynamic_subject_agent.deepseek import (_post_json_reply_content,DEEPSEEK_CREDENTIAL_BACKEND_ID,
            DEEPSEEK_CREDENTIAL_KEY_ID,DeepSeekResponseDiagnosticFailure)
        from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
        from dynamic_subject_agent.first_life import validate_plan
        label,self.pending=self.pending,None
        manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
        require(digest(manifest)==self.manifest_sha and label in manifest['requests'],'frozen-request-required')
        expected=manifest['requests'][label]
        require(type(task) is ModelTask and task.kind is ModelTaskKind.WORKING_ACTIVITY_CHOICE
            and task.payload==expected['preview'],'exact-frozen-task-required')
        verify_sources(manifest,label)
        grant=WorkingFactFaithfulDevelopmentGrant(APPROVED_WORKING_REVIEW,FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION)
        grant.validate()
        wire=choice_wire(task.payload,expected['full_support'])
        attempt=digest(dict(manifest=self.manifest_sha,label=label))
        self.audit.claim(attempt,digest(task.payload),purpose=task.kind.value,run_digest=self.manifest_sha)
        # Second disk/source reconstruction immediately before single send.
        require(digest(json.loads((ROOT/'manifest.json').read_text(encoding='utf-8')))==self.manifest_sha,'manifest-changed-before-delivery')
        verify_sources(manifest,label)
        self.transport.arm(label,wire,diagnostic=True)
        status,code,value='failed-closed','structured-choice-invalid',None
        try:
            value=_post_json_reply_content(self.transport,CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
                key_id=DEEPSEEK_CREDENTIAL_KEY_ID),wire,max_output_tokens=4096,require_complete=True,
                discard_reasoning=True,safe_diagnostics=True)
            payload=task.payload['payload']
            normalized,_=working_choice_for_adjudication(value,has_understanding=payload['working_understanding'] is not None)
            current=validate_plan(payload['current_plan'])
            adjudicate_choice(normalized,phase=payload['current_activity']['phase'],current_plan=current,source=None,plan_dependencies=())
            status,code='complete',None
        except CharacterCredentialUnavailable:
            status,code='unavailable','character-credential-unavailable'
        except DeepSeekResponseDiagnosticFailure as error:
            code=error.diagnostic_code
            status='unknown' if code in ('transport-timeout','transport-delivery-ambiguous') else 'failed-closed'
        except Exception:
            pass
        self.audit.record(attempt,status=status,output_digest=digest(value) if code is None else None)
        if code: raise ModelGatewayFailure(code)
        return ModelResult(task.kind,value)


def product_view(product):
    result=product.application.query_working_understanding()
    require(result.status=='available','working-query-unavailable')
    return plain(result.view)


def seed(report):
    from serve_working_understanding_chat import WorkingUnderstandingChatEntry
    transport=CapturingTransport(report,blocked=True)
    entry=WorkingUnderstandingChatEntry(PRIOR/'entry',live=False,transport=transport,audit_path=PRIOR/'audit')
    try:
        view=product_view(entry.product)
        understanding=view['visible_understanding']
        require(understanding is not None and understanding['activity_result'] is not None,'prior-real-support-required')
        source=understanding['activity_result']
        require(source['dependencies']==[],'A1-must-be-independent-of-early-experience')
        original=entry.product.application.preview_working_activity('choice')
        require(original.status=='previewed','prior-choice-preview-unavailable')
        base=plain(original.view)
        base['payload']['current_plan']=deepcopy(source['plan'])
        base['payload']['current_activity']=dict(phase='drafted',allowed_actions=allowed_actions('drafted'))
        base['payload']['working_understanding']=None
        require(not any(token in canonical_json(source['plan']) for token in ('雨','伞')),'limited-condition-already-present-in-A1')
        require(transport.total==0,'seed-produced-model-call')
        return base,support_projection(understanding),source_paths(entry.product,entry.config.state_path)
    finally: entry.close()


def prepared_source(case,report,transport):
    from dynamic_subject_agent.local_product import LocalProductConfig,open_local_product,open_working_understanding_product_live
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.timeline import SubjectCommand
    from dynamic_subject_agent.application import ApplicationQuery,ApplicationQueryKind
    from dynamic_subject_agent.working_understanding import WorkingSourceQuote,WorkingUnderstandingRequest
    from dynamic_subject_agent.working_understanding_remote_preview import working_remote_request_preview
    root=ROOT/('prep-'+case)
    config=LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments',root/'state.json')
    package=REPO/'.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
    with open_local_product(config,cognition=DormantDeepSeekCognition()) as author:
        frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(package.read_text(encoding='utf-8'),
            APPROVED_BINDING['definition_basis'],True,True))
        require(frozen.status=='created','fresh-source-identity-required')
    grant=WorkingFactFaithfulDevelopmentGrant(APPROVED_WORKING_REVIEW,FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION)
    with open_working_understanding_product_live(config,grant=grant,audit_path=root/'audit',
            identity_id=frozen.view.identity_id,_transport=transport) as product:
        heads=[]
        for i,text in enumerate(SOURCES[case]):
            preview=plain(product.application.preview_working_activity('reply',text).view)
            request=working_remote_request_preview(ModelTask(ModelTaskKind.WORKING_ACTIVITY_REPLY,preview),technical_variant='fact-faithful')
            transport.arm(case+'-source-'+str(i+1),canonical_json(request['body']).encode())
            result=product.application.submit(SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
                target_timeline_id=product.timeline_id,declared_intent='ask-collaborator-status',utterance=text,
                language='zh',provenance='project-original'),idempotency_key='s148-'+str(uuid4()))
            deadline=perf_counter()+150
            while plain(result.status)=='pending' and perf_counter()<deadline:
                result=product.application.wait(result.operation_ref,timeout_seconds=30)
            require(plain(result.status)=='terminal' and not getattr(result.projection,'failure_code',None),'source-reply-first-failure')
            history=product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,product.profile_id,product.timeline_id))
            heads.append(history.projection.turns[-1].head_sequence)
            print(canonical_json(dict(stage=case+'-source-'+str(i+1),status='committed')),flush=True)
        request=WorkingUnderstandingRequest(product.profile_id,product.timeline_id,str(uuid4()),product_view(product)['revision'],
            tuple(WorkingSourceQuote(head,text) for head,text in zip(heads,SOURCES[case])),confirmed=True)
        preview=product.application.preview_working_understanding(request)
        require(preview.status=='previewed','form-preview-unavailable')
        wire=working_remote_request_preview(ModelTask(ModelTaskKind.WORKING_UNDERSTANDING_FORM,plain(preview.view)),technical_variant='fact-faithful')
        transport.arm(case+'-form',canonical_json(wire['body']).encode())
        result=product.application.apply_working_understanding(request)
        require(result.status in ('committed','no-op'),'form-first-technical-failure')
        view=product_view(product)
        report['forms'][case]=dict(status=view['formation_status'],source_heads=heads,
            config=str(config.state_path),identity_id=product.profile_id,audit_calls=3,
            source_paths=source_paths(product,config.state_path))
        save(ROOT/'metadata.json',report)
        print(canonical_json(dict(stage=case+'-form',status=view['formation_status'])),flush=True)
        return support_projection(view['visible_understanding'])


def prepare():
    require(not ROOT.exists(),'existing-first-experiment-preserved-no-repeat')
    ROOT.mkdir(parents=True,exist_ok=False)
    report=dict(status='preparing',calls=[],forms={},credential_read_attempts=0,automatic_retries=0,
        product_candidates_published=0,reasoning_saved=False,runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    save(ROOT/'metadata.json',report)
    transport=CapturingTransport(report)
    try:
        base,related,paths=seed(report)
        witnesses={'base':source_stamp(paths),'R':source_stamp(paths)}
        supports={'R':related}
        for case in ('I','L','C'):
            supports[case]=prepared_source(case,report,transport)
            witnesses[case]=source_stamp(report['forms'][case]['source_paths'])
        # Q exists even when form is insufficient. Use exact committed sources,
        # not a hand-authored ideal statement. W remains unavailable in that case.
        requests={}
        for case,arm in ORDER:
            support=supports[case]
            if support is None and arm=='W': continue
            if support is None:
                support=dict(label='W1',scope='composition-text',statement=None,
                    support=dict(exchanges=[dict(label='U'+str(i+1),quote=text) for i,text in enumerate(SOURCES[case])],activity_result=None))
            label=case+'-'+arm
            preview=choice_preview(base,support,arm)
            choice_wire(preview,support)
            requests[label]=dict(preview=preview,full_support=support)
        manifest=dict(version='s148-first-choice-comparison-1',base=base,supports=supports,
            order=[case+'-'+arm for case,arm in ORDER],requests=requests,
            plan_sha256=sha256((REPO/'docs/experiments/s148/PLAN.md').read_bytes()).hexdigest(),
            policy_sha256=sha256(POLICY.encode()).hexdigest(),source_messages=SOURCES)
        manifest['source_witnesses']=witnesses
        save(ROOT/'manifest.json',manifest)
        report.update(status='prepared-awaiting-form-scope-review',manifest_sha256=digest(manifest),remote_calls=transport.total)
        save(ROOT/'metadata.json',report)
        print(canonical_json(dict(status=report['status'],remote_calls=transport.total,manifest_sha256=digest(manifest))),flush=True)
    except BaseException as error:
        report.update(status='prepare-stopped',error_type=type(error).__name__,remote_calls=transport.total)
        if type(transport.final) is str: save(ROOT/'first-failure-final.json',dict(final=transport.final))
        save(ROOT/'metadata.json',report)
        raise


def compare():
    report=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    require(report['status']=='prepared-awaiting-form-scope-review','prepared-first-only-state-required')
    require(report['runner_sha256']==sha256(Path(__file__).read_bytes()).hexdigest(),'runner-changed-after-preparation')
    require(not (ROOT/'results.json').exists(),'first-results-preserved-no-repeat')
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    review=json.loads((ROOT/'form-review.json').read_text(encoding='utf-8'))
    require(digest(manifest)==report['manifest_sha256'] and review['manifest_sha256']==digest(manifest)
        and set(review['eligible'])=={'R','I','L','C'} and all(type(x) is bool for x in review['eligible'].values()),'exact-form-review-required')
    require(manifest['plan_sha256']==sha256((REPO/'docs/experiments/s148/PLAN.md').read_bytes()).hexdigest(),'criteria-changed-before-results')
    transport=CapturingTransport(report)
    adapter=ComparisonAdapter(transport,ComparisonAudit(ROOT/'comparison-audit',initialize=True),digest(manifest))
    gateway=ModelGateway(adapter)
    rows=[]
    save(ROOT/'results.json',dict(status='running',rows=rows))
    stopped=False
    for ordinal,label in enumerate(manifest['order']):
        case,arm=label.split('-')
        row=dict(label=label,blind_id='sample-'+uuid4().hex,status='not-run')
        rows.append(row)
        if stopped: row['reason']='prior-first-technical-failure'
        elif arm=='W' and (label not in manifest['requests'] or not review['eligible'][case]):
            row.update(status='skipped',reason='insufficient-or-out-of-scope-form')
        else:
            try:
                adapter.arm(label)
                value=gateway.execute(ModelTask(ModelTaskKind.WORKING_ACTIVITY_CHOICE,manifest['requests'][label]['preview'])).value
                row.update(status='complete',value=value,output_sha256=digest(value))
            except BaseException as error:
                row.update(status='failed',error_type=type(error).__name__,code=error.code if isinstance(error,ModelGatewayFailure) else 'integrity-unverified')
                stopped=True
        save(ROOT/'results.json',dict(status='stopped' if stopped else 'running',rows=rows))
        print(canonical_json({k:v for k,v in row.items() if k!='value'}),flush=True)
    report.update(status='comparison-stopped' if stopped else 'comparison-complete',comparison_calls=transport.total,
        remote_calls=len(report['calls']))
    save(ROOT/'metadata.json',report)
    save(ROOT/'results.json',dict(status=report['status'],rows=rows))
    # Random IDs/order cannot be recovered from the public dispatch ORDER.
    # Original refs/content remain in results; only structural refs are hidden
    # for initial review. Natural wording can still reveal source usage.
    blinded=[]
    for row in rows:
        value=deepcopy(row.get('value'))
        if value is not None: value.pop('basis_refs',None)
        blinded.append(dict(id=row['blind_id'],case=row['label'].split('-')[0],status=row['status'],value=value))
    SystemRandom().shuffle(blinded)
    save(ROOT/'blind-results.json',dict(base_plan=manifest['base']['payload']['current_plan'],rows=blinded))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','compare'))
    args=parser.parse_args()
    try:
        prepare() if args.mode=='prepare' else compare()
        return 0
    except BaseException as error:
        print(canonical_json(dict(status='stopped',error_type=type(error).__name__,
            code=str(error) if type(error) is RuntimeError else 'unexpected-error')),flush=True)
        return 1


if __name__=='__main__': raise SystemExit(main())

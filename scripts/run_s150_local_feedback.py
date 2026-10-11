"""Complete isolated LOCAL Facade loop, actual sealed package, synthetic proposals.

Never constructs a remote transport or credential resolver. Existing runs cannot
be overwritten. Every local task, synthetic final and exact unsent body is kept.
"""
import argparse
from dataclasses import asdict, is_dataclass
import json
import re
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.application import ApplicationFacade, ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_natural_feedback_product_local
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.shared_activity import SharedActivityStepRequest, digest
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelTaskKind, ModelResult, ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGatewayFailure)
from dynamic_subject_agent.natural_feedback import FEEDBACK_VERSION, feedback_contract
from dynamic_subject_agent.natural_feedback_remote_preview import (
    natural_feedback_remote_request_preview, PendingNaturalFeedbackGrant, UnapprovedNaturalFeedbackAdapter)

ROOT = REPO/'.artifacts/s150/local-loop-first'
PACKAGE = REPO/'.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
FEEDBACK = '主光改暖，冷色只留一点边缘反光，其他照旧。'
PLAN = dict(subject='LOCAL合成人物文字构图', composition='半身侧视。左前方冷色主光照亮脸。枪在左下后景，枪口出画。背景压暗。', focus='先看表情')

def plain(value):
    if is_dataclass(value): return plain(asdict(value))
    if isinstance(value,dict): return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [plain(x) for x in value]
    return value.value if hasattr(value,'value') else value

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(plain(value),ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')

class LocalAdapter(ProviderAdapter):
    capabilities=ProviderCapabilities('local-s150-synthetic','fixed-synthetic',True,(StructuredOutputMode.JSON_OBJECT,))
    def __init__(self): self.calls=[]
    def invoke(self,task):
        payload=task.payload['payload']; number=len(self.calls)+1
        wire=natural_feedback_remote_request_preview(task)
        rejected=False
        try:
            ModelGateway(UnapprovedNaturalFeedbackAdapter(PendingNaturalFeedbackGrant('0'*64))).execute(task)
        except ModelGatewayFailure as error:
            rejected=error.code=='natural-feedback-use-unapproved'
        if not rejected: raise ValueError('pending adapter must refuse all tasks')
        if task.kind is ModelTaskKind.SHARED_ACTIVITY_CHOICE:
            current=payload['current_plan']
            value=dict(action='start' if current is None else 'revise', plan=PLAN if current is None else dict(current,focus='表情与明暗的清晰关系'),
                reason_code='improve-readability',basis_refs=[],decision_note='LOCAL合成活动取舍。')
        else:
            message=payload['turn']['current_message']
            intent='revise' if message==FEEDBACK else 'clarify' if message=='暖一点。' else 'chat'
            edits=[dict(field='composition',before='冷色主光',after='暖色主光'),
                dict(field='composition',before='背景压暗。',after='背景压暗。冷色只留低亮边缘反光。')] if intent=='revise' else []
            value=dict(intent=intent,activity_revision=payload['activity_revision'],edits=edits,
                reason_code='improve-readability' if edits else None,language='zh',
                reply_text='LOCAL合成：已局部修改主光，其他文字保留。' if edits else 'LOCAL合成：你指主光还是背景？' if intent=='clarify' else 'LOCAL合成普通接话。')
        row=dict(number=number,purpose=task.kind.value,preview=task.payload,synthetic_final=value,unsent_wire=wire,pending_refused=True)
        self.calls.append(row);save(ROOT/'tasks'/f'{number:02d}.json',row)
        return ModelResult(task.kind,value)

def history(product):
    response=product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,product.profile_id,product.timeline_id))
    if response.status!='available': raise ValueError('canonical history unavailable')
    return response.projection.turns

def send(product,text,key):
    result=product.application.submit(SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
        target_timeline_id=product.timeline_id,declared_intent='ask-collaborator-status',utterance=text,language='zh',provenance='project-original'),idempotency_key='s150-local-loop-'+key)
    while result.status=='pending': result=product.application.wait(result.operation_ref,timeout_seconds=30)
    save(ROOT/'steps'/f'{key}.json',dict(status=plain(result.status),problem_code=getattr(result,'problem_code',''),
        failure_code=getattr(getattr(result,'projection',None),'failure_code','')))
    if result.status!='terminal': raise ValueError('local-message-uncommitted')
    return result

def view(product):
    response=product.application.query_shared_activity()
    if response.status!='available': raise ValueError('local-state-unverified')
    return response.view

def advance(product,key):
    current=view(product)
    result=product.application.advance_shared_activity(SharedActivityStepRequest(product.profile_id,product.timeline_id,'s150-local-loop-'+key,current['revision']))
    if result.status!='committed': raise ValueError('local-activity-uncommitted')

def main(argv=None):
    global ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name', default='local-loop-first')
    args=parser.parse_args(argv)
    if re.fullmatch('[a-z][a-z0-9-]{0,47}',args.run_name) is None:raise ValueError('bounded run name required')
    base=(REPO/'.artifacts/s150').resolve()
    ROOT=(base/args.run_name).resolve()
    if not ROOT.is_relative_to(base) or ROOT==base:raise ValueError('owned child run required')
    if ROOT.exists(): raise ValueError('existing first LOCAL run preserved; no overwrite')
    ROOT.mkdir(parents=True,exist_ok=False)
    report=dict(status='started',local_synthetic=True,remote_calls=0,credential_reads=0,steps=[],checks={})
    save(ROOT/'metadata.json',report)
    product=None
    try:
        review=ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(
            PACKAGE,APPROVED_BINDING['definition_basis'],APPROVED_BINDING['runtime_asset_sha'],APPROVED_BINDING['persona_digest'],
            APPROVED_BINDING['subject_id'],APPROVED_BINDING['anchor_id']))
        if review.status!='previewed' or review.review_basis!=APPROVED_BINDING['review_basis']: raise ValueError('exact approved package required')
        config=LocalProductConfig(ROOT/'entry/DynamicSubjectAgent/m0/experiments',ROOT/'entry/state.json')
        with open_local_product(config,cognition=DormantDeepSeekCognition()) as author:
            frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(PACKAGE.read_text(encoding='utf-8'),APPROVED_BINDING['definition_basis'],True,True))
            if frozen.status!='created': raise ValueError('new independent identity required')
        adapter=LocalAdapter()
        def opening(): return open_natural_feedback_product_local(config,gateway=ModelGateway(adapter),identity_id=frozen.view.identity_id)
        product=opening(); identity=(product.profile_id,product.timeline_id)
        advance(product,'initial'); before=view(product)['current_plan'];report['steps'].append('independent-activity')
        preview=product.application.preview_natural_feedback(FEEDBACK)
        if preview.status!='previewed':raise ValueError('feedback-preview-unavailable')
        send(product,FEEDBACK,'correction'); updated=view(product)['current_plan'];report['steps'].append('one-natural-feedback')
        report['checks']['preview_matches_execution']=adapter.calls[-1]['preview']==preview.view
        report['checks']['exact_partial_revision']=(updated.subject==before.subject and updated.focus==before.focus
            and updated.composition==before.composition.replace('冷色主光','暖色主光')+'冷色只留低亮边缘反光。')
        for key,text in [('ambiguous','暖一点。'),('conditional','如果以后改画雨景，可以加冷色背景。'),
            ('gap1','换个话题：谈谈故事开头。'),('gap2','现在聊读书的节奏。'),('gap3','再谈一个无关话题：想象的结尾。')]:
            send(product,text,key);report['steps'].append(key)
            if view(product)['current_plan']!=updated:raise ValueError('unrequested-change')
        out=product.application.preview_natural_feedback('接着原来的讨论。').view['payload']
        report['checks']['feedback_outside_recent_window']=FEEDBACK not in json.dumps(plain(out['exchange']),ensure_ascii=False)
        saved=plain(history(product));calls=len(adapter.calls);product.close();product=None
        product=opening();report['steps'].append('actual-close-reopen')
        report['checks']['reopen_zero_model_same_identity']=len(adapter.calls)==calls and identity==(product.profile_id,product.timeline_id) and saved==plain(history(product))
        advance(product,'post-gap-activity');next_plan=view(product)['current_plan'];report['steps'].append('actual-next-activity')
        report['checks']['actual_next_activity_changed']=next_plan.focus!=updated.focus and next_plan.composition==updated.composition and view(product)['activity_revision']==3
        send(product,'现在这一版保留了什么？','current-result');report['steps'].append('current-result-reply')
        report['checks']['reply_receives_current_plan']=adapter.calls[-1]['preview']['payload']['current_plan']==asdict(next_plan)
        if not all(report['checks'].values()):raise ValueError('local-loop-check-failed')
        report.update(status='local-loop-complete',calls=len(adapter.calls),canonical_count=view(product)['revision'],
            identity=identity,contract=feedback_contract(APPROVED_BINDING),final_plan=next_plan,pending_refusals=len(adapter.calls))
        save(ROOT/'canonical-history.json',history(product))
    except Exception as error:
        report.update(status='failed',failure_type=type(error).__name__)
        raise
    finally:
        if product is not None:product.close()
        save(ROOT/'metadata.json',report)
    print(json.dumps(dict(status=report['status'],checks=report['checks'],calls=report['calls'],remote_calls=0,credential_reads=0),ensure_ascii=False),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())

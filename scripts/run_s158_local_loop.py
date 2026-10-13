"""Review the integrated LOCAL loop using the approved character and synthetic outputs.

No transport, key resolver or background server is constructed. Every new run is
exclusive; old roots, failures and scenarios are never opened or overwritten.
"""
import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from dynamic_subject_agent.application import ApplicationFacade, ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_integrated_character_product_local
from dynamic_subject_agent.model_gateway import ModelGateway, ModelResult, ModelTaskKind, ProviderAdapter, ProviderCapabilities, StructuredOutputMode
from dynamic_subject_agent.living_activity import LivingActionRequest, LivingControlRequest
from dynamic_subject_agent.shared_activity import SharedExperienceRequest, digest
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.integrated_character import integrated_contract
from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview

PACKAGE = REPO/'.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
SOURCE = '这次想保留窗边暖光，先看手上的动作。'
FEEDBACK = '把所有“榆台”换成“楠台”，其他照旧。'
PLAN = dict(subject='LOCAL合成晾衣场景', composition='榆台靠近窗边。'+('暖光落在衣褶上，右边留出空地，视点保持半身侧面。'*9)+'远处榆台仍保留木纹。', focus='先看手上的动作')


def plain(value):
    if is_dataclass(value): return plain(asdict(value))
    if isinstance(value, dict): return {key:plain(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)): return [plain(item) for item in value]
    return value.value if hasattr(value,'value') else value


def save(path, value, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusive else 'w', encoding='utf-8') as stream:
        json.dump(plain(value), stream, ensure_ascii=False, sort_keys=True, indent=2)


class SyntheticAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('integrated-s158-synthetic', 'local-only', True, (StructuredOutputMode.JSON_OBJECT,))
    def __init__(self, root): self.root, self.calls = root, []
    def invoke(self, task):
        wire = integrated_remote_request_preview(task)
        data = task.payload['payload']
        if task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
            text = data['turn']['current_message']
            intent = 'revise' if text == FEEDBACK else 'clarify' if text == '那一处也换掉。' else 'chat'
            value = dict(intent=intent, reply_text='LOCAL合成：只按明确文字修订。' if intent=='revise' else
                'LOCAL合成：你指哪一处文字？' if intent=='clarify' else 'LOCAL合成：依据本次实际方案接话。')
        elif task.kind is ModelTaskKind.LIVING_ACTIVITY_SHARE:
            value = dict(share=True, reply_text='LOCAL合成分享：我想让窗边暖光先落在手上的衣褶。', language='zh')
        else:
            current = data['current_plan']
            value = dict(action='start' if current is None else 'revise',
                plan=PLAN if current is None else dict(current, focus='让衣褶明暗服务手上的动作'),
                reason_code='improve-readability', basis_refs=['E1'] if data['shared_experience'] else [], decision_note='LOCAL合成取舍。')
        row = dict(number=len(self.calls)+1, purpose=task.kind.value, preview=task.payload,
            unsent_wire=wire, synthetic_final=value)
        self.calls.append(row)
        save(self.root/'tasks'/f'{len(self.calls):02d}.json', row, exclusive=True)
        return ModelResult(task.kind, value)


def history(product):
    response = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,product.profile_id,product.timeline_id))
    if response.status != 'available': raise ValueError('canonical history unavailable')
    return response.projection.turns


def view(product):
    response = product.application.query_shared_activity()
    if response.status != 'available': raise ValueError('combined state unavailable')
    return response.view


def send(product, text, key):
    result = product.application.submit(SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
        target_timeline_id=product.timeline_id,declared_intent='ask-collaborator-status',utterance=text,language='zh',
        provenance='project-original'),idempotency_key='s158-local-'+key)
    while result.status == 'pending': result=product.application.wait(result.operation_ref,timeout_seconds=30)
    if result.status != 'terminal': raise ValueError('synthetic message did not commit: '+str(result.status))


def act(product, action, key):
    result = product.application.advance_living_activity(LivingActionRequest(product.profile_id,product.timeline_id,
        's158-local-'+key,view(product)['revision'],action))
    if result.status != 'committed': raise ValueError('synthetic activity did not commit: '+str(result))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',required=True)
    name=parser.parse_args(argv).run_name
    if re.fullmatch('[a-z][a-z0-9-]{0,47}',name) is None: raise ValueError('bounded run name required')
    root=(REPO/'.artifacts/s158'/name).resolve()
    if root.exists(): raise ValueError('existing LOCAL run preserved')
    root.mkdir(parents=True,exist_ok=False)
    report=dict(status='started',local_synthetic=True,remote_calls=0,credential_reads=0,checks={})
    save(root/'metadata.json',report)
    product=None
    try:
        review=ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(
            PACKAGE,APPROVED_BINDING['definition_basis'],APPROVED_BINDING['runtime_asset_sha'],APPROVED_BINDING['persona_digest'],
            APPROVED_BINDING['subject_id'],APPROVED_BINDING['anchor_id']))
        if review.status!='previewed' or review.review_basis!=APPROVED_BINDING['review_basis']:
            raise ValueError('exact previously approved character package required')
        config=LocalProductConfig(root/'entry/DynamicSubjectAgent/m0/experiments',root/'entry/state.json')
        with open_local_product(config,cognition=DormantDeepSeekCognition()) as author:
            frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
                PACKAGE.read_text(encoding='utf-8'),APPROVED_BINDING['definition_basis'],True,True))
            if frozen.status!='created': raise ValueError('new independently sealed identity required')
        adapter=SyntheticAdapter(root)
        def opening(): return open_integrated_character_product_local(config,gateway=ModelGateway(adapter),identity_id=frozen.view.identity_id)
        product=opening();identity=(product.profile_id,product.timeline_id)
        controls=product.application.query_living_controls().view
        report['checks']['initial_zero_calls']=not adapter.calls and view(product)['revision']==0
        result=product.application.set_living_controls(LivingControlRequest(product.profile_id,product.timeline_id,
            's158-local-enable-living',controls['revision'],False,True,True))
        if result.status!='committed': raise ValueError('local controls failed')
        send(product,SOURCE,'source-message')
        head=history(product)[-1].head_sequence
        source=product.application.set_shared_experience(SharedExperienceRequest(product.profile_id,product.timeline_id,
            's158-local-source-select',view(product)['revision'],head,SOURCE,True))
        if source.status!='committed': raise ValueError('local source selection failed')
        act(product,'simulation','first-activity');original=view(product)['current_plan']
        act(product,'share','first-share')
        send(product,'那一处也换掉。','clarify')
        report['checks']['clarify_no_effect']=view(product)['current_plan']==original
        before=product.application.preview_natural_feedback(FEEDBACK)
        send(product,FEEDBACK,'feedback')
        updated=view(product)['current_plan']
        report['checks']['preview_matches_actual']=before.status=='previewed' and adapter.calls[-1]['preview']==before.view
        report['checks']['feedback_reads_actual_share']=before.view['payload']['evidence']['latest_share'] is not None
        report['checks']['long_exact_revision']=original.composition.rfind('榆台')-original.composition.find('榆台')>160 and asdict(updated)=={k:v.replace('榆台','楠台') for k,v in asdict(original).items()}
        for index in range(3): send(product,'合成无关话题'+str(index),'topic-'+str(index))
        last=adapter.calls[-1]['preview']['payload']
        report['checks']['expired_share_keeps_plan']=last['evidence']['latest_share'] is None and view(product)['current_plan']==updated
        report['checks']['feedback_outside_recent_window']=FEEDBACK not in json.dumps(plain(last['exchange']),ensure_ascii=False)
        saved=plain(history(product));calls=len(adapter.calls);product.close();product=None
        product=opening()
        report['checks']['reopen_same_identity_zero_model']=identity==(product.profile_id,product.timeline_id) and calls==len(adapter.calls) and saved==plain(history(product))
        act(product,'simulation','next-activity')
        report['checks']['next_choice_reads_feedback']=adapter.calls[-1]['preview']['payload']['current_feedback']==dict(label='F1',quote=FEEDBACK)
        report['checks']['actual_next_choice']=view(product)['activity_revision']==3 and view(product)['current_plan'].composition==updated.composition and view(product)['current_plan'].focus!=updated.focus
        act(product,'share','revised-share')
        report['checks']['share_uses_revised_plan_without_quote']=adapter.calls[-1]['preview']['payload']['activity_result']['plan']==asdict(view(product)['current_plan']) and 'current_feedback' not in adapter.calls[-1]['preview']['payload']
        send(product,'说说这一版的取舍。','result')
        result=product.application.set_shared_experience(SharedExperienceRequest(product.profile_id,product.timeline_id,
            's158-local-disable-source',view(product)['revision'],None,'',True))
        if result.status!='committed': raise ValueError('source disable failed')
        removed=product.application.preview_natural_feedback('换个话题。').view['payload']
        report['checks']['revocation_filters_both_chains']=removed['current_plan'] is None and removed['current_feedback'] is None and removed['evidence']['latest_share'] is None and not removed['exchange']
        if not all(report['checks'].values()): raise ValueError('LOCAL combined loop check failed')
        report.update(status='local-loop-complete',calls=len(adapter.calls),canonical_count=view(product)['revision'],
            identity=identity,contract=integrated_contract(APPROVED_BINDING),tasks_digest=digest(adapter.calls))
        save(root/'canonical-history.json',history(product),exclusive=True)
    except Exception as error:
        report.update(status='failed',failure_type=type(error).__name__,failure=str(error))
        raise
    finally:
        if 'adapter' in locals(): report['calls'] = len(adapter.calls)
        if product is not None: product.close()
        save(root/'metadata.json',report)
    print(json.dumps({k:report[k] for k in ('status','calls','canonical_count','remote_calls','credential_reads','checks')},ensure_ascii=False))
    return 0


if __name__=='__main__': raise SystemExit(main())

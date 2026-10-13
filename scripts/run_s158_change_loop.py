"""One new ordinary scene, with approved current-change evidence and first results."""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import run_s158_live_loop as engine
from run_s158_conversation_loop import reference_checks

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'.artifacts/s158/change-loop-first'
SCENE=REPO/'docs/experiments/s158/CHANGE-SCENE.md'
REVIEW=REPO/'docs/experiments/s158/change-review.json'
REVIEW_BASIS='38ecaf3bd9125456e8cfb3305b8850fc3fe49bbe3399a0bc6ef939f93731ab92'
SOURCE='一起想一幅原创的旧电影院放映室，暂时叫‘映川’，门口一块小牌写着‘映川’。人物正在做什么、放映机的光线怎样穿过房间、从哪里看、哪里留空，都由你挑一个自己想画的安排。现在只是文字构图，不是已经完成的画。'
PAIRS=(('映川','映汀'),)
STAGES=(
    ('initial-chat',SOURCE,None),
    ('initial-activity',None,'simulation'),
    ('first-share',None,'share'),
    ('natural-reference','门口那块牌子的叫法也改一下，其他先保持。',None),
    ('explicit-feedback','$derived',None),
    ('topic-one','画一个人把刚洗好的杯子倒扣在布上，你会怎样用手和杯沿的距离表现动作还没结束？',None),
    ('topic-two','一只猫在台阶上突然停住，你会画耳朵的转向还是后脚没落稳的样子？为什么？',None),
    ('topic-three','画两个人各自拿着一端长围巾，中间的松紧怎样让他们的步调看起来不一样？',None),
    ('next-activity',None,'simulation'),
    ('second-share',None,'share'),
    ('faithful-reply','回头看现在这版放映室，名字是什么时候改的？你后来具体改了哪里，哪些安排仍保持着？',None))

_base_pins=engine.pins
_base_preview=engine.integrated_remote_request_preview
_base_next_stage=engine.next_stage


def pins():
    value=_base_pins()
    for path in (Path(__file__),REPO/'scripts/run_s158_conversation_loop.py',
                 REPO/'docs/experiments/s158/change-approval.json'):
        value[str(path.relative_to(REPO))]=sha256(path.read_bytes()).hexdigest()
    return value


def verify_review():
    value=json.loads(REVIEW.read_text(encoding='utf-8'))
    basis=value.pop('review_basis')
    engine.require(basis==REVIEW_BASIS and engine.digest(value)==basis,'exact-approved-change-review-required')
    from dynamic_subject_agent.integrated_character_live import ApprovedIntegratedCharacterGrant,APPROVED_CHANGE_REVIEW
    engine.require(APPROVED_CHANGE_REVIEW==basis,'change-grant-basis-mismatch')
    ApprovedIntegratedCharacterGrant(basis,True,technical_variant='change-evidence').validate()


def preview(task):
    return _base_preview(task,technical_variant='change-evidence')


def decode_model_final(final,task_preview,kind):
    wire=preview(engine.ModelTask(kind,task_preview))
    if 'response_format' not in wire['body']:
        engine.require(kind is engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,'text-format-only-for-feedback')
        from dynamic_subject_agent.integrated_character_text import conversation_text_proposal,intent_text_proposal
        decoder=intent_text_proposal if wire['output_contract'].get('final_content')=='intent-prefixed-text' else conversation_text_proposal
        return decoder(final,task_preview['payload'])
    return json.loads(final)


def capture_change(report,product):
    response=product.application.query_current_activity_change()
    engine.require(response.status=='available','current-change-view-unavailable')
    engine.require(set(response.view)=={'current_activity_change'},'exact-current-change-view-required')
    label=STAGES[report['next_stage']][0]
    report.setdefault('change_views',{})[label]=deepcopy(response.view['current_activity_change'])


def opening(report,transport):
    from serve_integrated_character_chat import IntegratedCharacterChatEntry
    entry=IntegratedCharacterChatEntry(ROOT/'entry',audit_path=ROOT/'audit',transport=transport,
        observations=report['provider_observations'],package_path=engine.PACKAGE,technical_variant='change-evidence')
    product=entry.product
    try:
        if report.get('timeline_id'):
            engine.require((product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id']),
                'same-identity-timeline-required')
        capture_change(report,product)
        return product
    except Exception:
        product.close()
        raise


def check_projection(task,report):
    payload=task.payload['payload'];label=STAGES[report['next_stage']][0]
    if task.kind is engine.ModelTaskKind.LIVING_ACTIVITY_CHOICE:
        engine.require('current_result_change' not in payload,'choice-must-not-read-change-evidence')
        report['checks']['choice_change_omitted']=True
        return
    engine.require('current_result_change' in payload,'reply-share-change-field-required')
    expected=report['change_views'][label]
    engine.require(payload['current_result_change']==expected,'change-projection-differs-from-visible-source')
    report.setdefault('change_inputs',{})[label]=deepcopy(expected)
    if label in ('initial-chat','first-share'):
        engine.require(expected is None,'initial-plan-has-no-change-evidence')
        report['checks'][label+'_change_null']=True


def next_stage(report):
    previous=engine.integrated_remote_request_preview
    def checked(task):
        check_projection(task,report)
        return preview(task)
    engine.integrated_remote_request_preview=checked
    try:
        result=_base_next_stage(report)
    finally:
        engine.integrated_remote_request_preview=previous
    if result==0 and report['status']=='execution-ended-semantic-review-required':
        inputs=report.get('change_inputs',{})
        actual=report['checks'].get('actual_new_choice') is True
        share=inputs.get('second-share')
        report['checks']['new_revision_change_in_share_and_reply']=(actual and share is not None
            and 'faithful-reply' in inputs and share==inputs['faithful-reply'])
        report['validation_scope']='ordinary-scene-with-current-change-evidence-not-long-span'
        engine.persist(report)
    return result


@contextmanager
def configured():
    changes=dict(ROOT=ROOT,SCENE=SCENE,REVIEW=REVIEW,REVIEW_BASIS=REVIEW_BASIS,SOURCE=SOURCE,PAIRS=PAIRS,
        STAGES=STAGES,opening=opening,integrated_remote_request_preview=preview,verify_review=verify_review,
        pins=pins,decode_model_final=decode_model_final,reference_checks=reference_checks,next_stage=next_stage)
    saved={key:getattr(engine,key) for key in changes};evidence_root=engine.evidence.ROOT
    try:
        for key,value in changes.items():setattr(engine,key,value)
        yield engine
    finally:
        for key,value in saved.items():setattr(engine,key,value)
        engine.evidence.ROOT=evidence_root


def main(argv=None):
    with configured():return engine.main(argv)


if __name__=='__main__':raise SystemExit(main())

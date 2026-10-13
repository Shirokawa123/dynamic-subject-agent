"""Only five first stages for the existing intent-text long-span contract."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import run_s158_live_loop as engine
import run_s158_intent_loop as intent

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'.artifacts/s158/long-span-first'
SCENE=REPO/'docs/experiments/s158/LONG-SPAN.md'
SOURCE='这是一次构图文字的长距工程专项，不代表普通聊天的自然输入。请设计原创山间索道候车室，名字叫‘山信’。构图主体段约220–320字：以近处写着‘山信’的售票窗牌开始，以远处也写着‘山信’的指示牌结束，两处都写出这两个原字，不用‘同名’代替。中间的人物动作、空间层次、观看位置、光线和留白由你具体安排，让近中远能连起来。现在只是文字构图，不是已经完成的画。'
PAIRS=(('山信','山音'),)
STAGES=(('initial-chat',SOURCE,None),('initial-activity',None,'simulation'),
    ('first-share',None,'share'),('natural-reference','远处那个名字也换一下，别的先保持。',None),
    ('explicit-feedback','$derived',None))

_base_next_stage=engine.next_stage
preview=intent.preview
decode_model_final=intent.decode_model_final


def pins():
    value=intent.pins()
    value[str(Path(__file__).relative_to(REPO))]=sha256(Path(__file__).read_bytes()).hexdigest()
    return value


def opening(report,transport):
    from serve_integrated_character_chat import IntegratedCharacterChatEntry
    entry=IntegratedCharacterChatEntry(ROOT/'entry',audit_path=ROOT/'audit',transport=transport,
        observations=report['provider_observations'],package_path=engine.PACKAGE,technical_variant='intent-text')
    product=entry.product
    if report.get('timeline_id'):
        engine.require((product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id']),
            'same-identity-timeline-required')
    return product


def next_stage(report):
    result=_base_next_stage(report)
    if result==0 and report['next_stage']==5 and report['status']=='execution-ended-semantic-review-required':
        passed=(report['long_distance']['eligible'] is True
            and report['long_distance']['status']=='actual-exact-long-revision'
            and report['checks'].get('feedback_exact') is True)
        original=report['stages'][1]['after']['current_plan']
        report['validation_scope']='long-span-only-not-character-effect'
        report['long_span_result']=dict(passed=passed,original_composition_chars=len(original['composition']),
            spans=report['feedback']['spans'],target_occurrences=report['feedback']['occurrences'],
            unchanged_outside_frame=report['checks']['feedback_exact'],person_effect_scored=False)
        report['status']='long-span-passed' if passed else 'long-span-not-met'
        engine.persist(report)
    return result


@contextmanager
def configured():
    changes=dict(ROOT=ROOT,SCENE=SCENE,SOURCE=SOURCE,PAIRS=PAIRS,STAGES=STAGES,opening=opening,
        integrated_remote_request_preview=preview,verify_review=intent.verify_review,pins=pins,
        decode_model_final=decode_model_final,reference_checks=intent.reference_checks,next_stage=next_stage)
    saved={key:getattr(engine,key) for key in changes}
    evidence_root=engine.evidence.ROOT
    try:
        for key,value in changes.items():setattr(engine,key,value)
        yield engine
    finally:
        for key,value in saved.items():setattr(engine,key,value)
        engine.evidence.ROOT=evidence_root


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('check','init','next','inspect'))
    args=parser.parse_args(argv)
    with configured():return engine.main([args.mode])


if __name__=='__main__':raise SystemExit(main())

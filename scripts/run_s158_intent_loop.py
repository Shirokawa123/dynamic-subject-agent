"""New harbor scene: a bounded full loop with an explicit long-span input."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import run_s158_live_loop as engine
from run_s158_conversation_loop import reference_checks

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'.artifacts/s158/intent-loop-first'
SCENE=REPO/'docs/experiments/s158/INTENT-SCENE.md'
SOURCE='一起设计一幅原创海港展览的长画幅，展览叫‘潮序’。近处入口铭牌明确写着‘潮序’，远处旗上也明确写着‘潮序’，这两处请写出实际文字，不要只说同名。中景安排一个人物。作为这次长距专项，请用约250–350字的构图主体段把近、中、远之间的遮挡、视线与空间关系说完整；人物动作、观看位置、光线和哪里留白由你选择。现在只是文字构图，不是已经完成的画。'
PAIRS=(('潮序','潮声'),('海港展览','港口展览'))
STAGES=(
    ('initial-chat',SOURCE,None),
    ('initial-activity',None,'simulation'),
    ('first-share',None,'share'),
    ('natural-reference','旗上那个叫法也换一换，别的先保持。',None),
    ('explicit-feedback','$derived',None),
    ('topic-one','一扇窗外有人刚放开一个气球，你会先画松开的手，还是窗框把气球挡住的一小部分？为什么？',None),
    ('topic-two','画一把折起来的伞，怎样让人感觉它刚从雨里带回来，又不用画出正在下雨？',None),
    ('topic-three','两个人在桌边拼同一块拼图，你会用哪个动作表现他们不同的耐心？',None),
    ('next-activity',None,'simulation'),
    ('second-share',None,'share'),
    ('faithful-reply','回头看现在这幅海港展览，名字是什么时候改的？你后来又做了什么构图取舍，哪些地方仍保持着？',None))

_base_pins=engine.pins
_base_verify_review=engine.verify_review
_base_preview=engine.integrated_remote_request_preview
_base_decode=engine.decode_model_final


def decode_model_final(final,task_preview,kind):
    wire=preview(engine.ModelTask(kind,task_preview))
    if 'response_format' not in wire['body']:
        engine.require(kind is engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,'text-format-only-for-feedback')
        from dynamic_subject_agent.integrated_character_text import conversation_text_proposal,intent_text_proposal
        decoder=intent_text_proposal if wire['output_contract'].get('final_content')=='intent-prefixed-text' else conversation_text_proposal
        return decoder(final,task_preview['payload'])
    return _base_decode(final,task_preview,kind)


def pins():
    value=_base_pins()
    for path in (Path(__file__),REPO/'scripts/run_s158_conversation_loop.py'):
        value[str(path.relative_to(REPO))]=sha256(path.read_bytes()).hexdigest()
    return value


def verify_review():
    _base_verify_review()
    from dynamic_subject_agent.integrated_character_live import ApprovedIntegratedCharacterGrant
    ApprovedIntegratedCharacterGrant(engine.REVIEW_BASIS,True,technical_variant='intent-text').validate()


def preview(task):return _base_preview(task,technical_variant='intent-text')


def opening(report,transport):
    from serve_integrated_character_chat import IntegratedCharacterChatEntry
    entry=IntegratedCharacterChatEntry(ROOT/'entry',audit_path=ROOT/'audit',transport=transport,
        observations=report['provider_observations'],package_path=engine.PACKAGE,technical_variant='intent-text')
    product=entry.product
    if report.get('timeline_id'):
        engine.require((product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id']),
            'same-identity-timeline-required')
    return product


@contextmanager
def configured():
    changes=dict(ROOT=ROOT,SCENE=SCENE,SOURCE=SOURCE,PAIRS=PAIRS,STAGES=STAGES,opening=opening,
        integrated_remote_request_preview=preview,verify_review=verify_review,pins=pins,
        decode_model_final=decode_model_final,reference_checks=reference_checks)
    saved={key:getattr(engine,key) for key in changes}
    evidence_root=engine.evidence.ROOT
    try:
        for key,value in changes.items():setattr(engine,key,value)
        yield engine
    finally:
        for key,value in saved.items():setattr(engine,key,value)
        engine.evidence.ROOT=evidence_root


def main(argv=None):
    with configured():return engine.main(argv)


if __name__=='__main__':raise SystemExit(main())

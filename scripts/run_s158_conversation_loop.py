"""New prop-room scene, preserving plain model text apart from local NoOp DTOs."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import run_s158_live_loop as engine

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'.artifacts/s158/conversation-loop-first'
SCENE=REPO/'docs/experiments/s158/CONVERSATION-SCENE.md'
SOURCE='一起想一幅原创剧场道具间，房间暂叫‘回帆’。近处道具架上的标签写着房间名，远处旧箱上的标签也写着同一个名字，中间留给一个正在整理道具的人。请把近景、中景、远景怎么相互遮挡、视线怎样走、哪里留空说完整；人物动作、观看位置和你最在意的一处安排由你定。现在只是文字构图，不是已经画好的图。'
PAIRS=(('回帆','归帆'),('道具间','道具室'))
STAGES=(
    ('initial-chat',SOURCE,None),
    ('initial-activity',None,'simulation'),
    ('first-share',None,'share'),
    ('natural-reference','箱子那边的字也换一下，别的先保持。',None),
    ('explicit-feedback','$derived',None),
    ('topic-one','一张纸被风掀起一个角，你会先画纸的弯折，还是底下突然露出的东西？为什么？',None),
    ('topic-two','画两个人同时伸手去拿同一本书，哪个瞬间会让你觉得有意思？',None),
    ('topic-three','如果只画一双鞋，怎样让人感觉它们的主人刚刚停下来？',None),
    ('next-activity',None,'simulation'),
    ('second-share',None,'share'),
    ('faithful-reply','回头看现在这版道具间，名字是什么时候改的？你后来又做了什么构图取舍，哪些地方仍保持着？',None))

_base_pins=engine.pins
_base_verify_review=engine.verify_review
_base_preview=engine.integrated_remote_request_preview
_base_decode=engine.decode_model_final


def decode_model_final(final,task_preview,kind):
    """Interpret the saved raw final without changing it or its transport."""
    wire=preview(engine.ModelTask(kind,task_preview))
    if 'response_format' not in wire['body']:
        engine.require(kind is engine.ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,'plain-format-only-for-conversation')
        from dynamic_subject_agent.integrated_character_text import conversation_text_proposal
        return conversation_text_proposal(final,task_preview['payload'])
    return _base_decode(final,task_preview,kind)


def pins():
    value=_base_pins()
    value[str(Path(__file__).relative_to(REPO))]=sha256(Path(__file__).read_bytes()).hexdigest()
    return value


def verify_review():
    _base_verify_review()
    from dynamic_subject_agent.integrated_character_live import ApprovedIntegratedCharacterGrant
    ApprovedIntegratedCharacterGrant(engine.REVIEW_BASIS,True,technical_variant='conversation-text').validate()


def preview(task):return _base_preview(task,technical_variant='conversation-text')


def opening(report,transport):
    from serve_integrated_character_chat import IntegratedCharacterChatEntry
    entry=IntegratedCharacterChatEntry(ROOT/'entry',audit_path=ROOT/'audit',transport=transport,
        observations=report['provider_observations'],package_path=engine.PACKAGE,technical_variant='conversation-text')
    product=entry.product
    if report.get('timeline_id'):
        engine.require((product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id']),
            'same-identity-timeline-required')
    return product


def reference_checks(value,before,after):
    return dict(reference_no_effect=before['current_plan']==after['current_plan']
        and before['activity_revision']==after['activity_revision'],reference_model_intent_not_applicable=True)


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

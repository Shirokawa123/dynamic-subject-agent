"""New tram-terminal first scene; reuse the frozen S158 bounded loop engine."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import run_s158_live_loop as engine

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO/'.artifacts/s158/focused-loop-first'
SCENE = REPO/'docs/experiments/s158/FOCUSED-SCENE.md'
SOURCE = '一起想一幅原创的夜班旧电车终点站，站名暂叫‘迟灯’。近处站牌和远处车尾的目的地标识都写着站名，中间留给一个人物。请把近景、中景、远景之间的遮挡、视线和光线关系说完整，让人看得懂怎么画。人物的动作、观看位置和哪处留空由你决定，我想听一个你自己在意的安排。现在只是文字构图。'
PAIRS = (('迟灯', '微灯'), ('终点站', '末站'))
STAGES = (
    ('initial-chat', SOURCE, None),
    ('initial-activity', None, 'simulation'),
    ('first-share', None, 'share'),
    ('natural-reference', '远处那个也换个叫法吧，别的先不动。', None),
    ('explicit-feedback', '$derived', None),
    ('topic-one', '一只杯子刚被人拿走，桌上还留着水印。你会画水印本身，还是它旁边没有挪动的东西？为什么？', None),
    ('topic-two', '画一个人拆开没有署名的信，你更想先抓手上的动作还是脸上的停顿？', None),
    ('topic-three', '一把椅子空着，但画面里要让人感觉有人刚离开，你会选哪个小细节？', None),
    ('next-activity', None, 'simulation'),
    ('second-share', None, 'share'),
    ('faithful-reply', '回头看现在这版站台，站名是什么时候改的？你后来又做了什么构图取舍，哪些地方还保持着？', None))

_base_pins = engine.pins
_base_verify_review = engine.verify_review
_base_preview = engine.integrated_remote_request_preview


def pins():
    value = _base_pins()
    value[str(Path(__file__).relative_to(REPO))] = sha256(Path(__file__).read_bytes()).hexdigest()
    return value


def verify_review():
    _base_verify_review()
    from dynamic_subject_agent.integrated_character_live import ApprovedIntegratedCharacterGrant
    ApprovedIntegratedCharacterGrant(engine.REVIEW_BASIS, True, technical_variant='focused').validate()


def preview(task):
    return _base_preview(task, technical_variant='focused')


def opening(report, transport):
    from serve_integrated_character_chat import IntegratedCharacterChatEntry
    entry = IntegratedCharacterChatEntry(ROOT/'entry', audit_path=ROOT/'audit',
        transport=transport, observations=report['provider_observations'], package_path=engine.PACKAGE,
        technical_variant='focused')
    product = entry.product
    if report.get('timeline_id'):
        engine.require((product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id']),
            'same-identity-timeline-required')
    return product


@contextmanager
def configured():
    """Keep the baseline module reusable; all overrides are restored on exit."""
    changes = dict(ROOT=ROOT,SCENE=SCENE,SOURCE=SOURCE,PAIRS=PAIRS,STAGES=STAGES,
        opening=opening,integrated_remote_request_preview=preview,verify_review=verify_review,pins=pins)
    saved = {key:getattr(engine,key) for key in changes}
    evidence_root = engine.evidence.ROOT
    try:
        for key,value in changes.items():setattr(engine,key,value)
        yield engine
    finally:
        for key,value in saved.items():setattr(engine,key,value)
        engine.evidence.ROOT = evidence_root


def main(argv=None):
    with configured():return engine.main(argv)


if __name__=='__main__':raise SystemExit(main())

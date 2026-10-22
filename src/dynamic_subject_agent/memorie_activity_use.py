"""Pure M012 authoring previews. No Sender, ModelTask or runtime authority.

Supplied examples are synthetic author inputs, never a canonical experience
proof. A future Sender must reconstruct them under a separately qualified
same-Timeline contract and the exact human-approved review.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.memorie_native import preview_wire as old_preview, policy as native_policy
from dynamic_subject_agent.local_activity_contract import HERB_SCOPE
from dynamic_subject_agent.shared_activity import allowed_actions
from dynamic_subject_agent.first_life import validate_plan

VERSION = 'memorie-native-activity-use-m012-1'
PURPOSES = ('reply', 'choice', 'share')


def digest(value): return sha256(canonical_json(value).encode()).hexdigest()


def policies():
    reply = native_policy() + (
        '本用途另提供experience、activity_result和latest_share，均只可使用本请求实际提供的内容。'
        'experience仅证明用户明确确认曾说过quote，不证明其为真或是永久偏好；缺失时不补造。'
        'activity_result仅为已提交的药草笔记文字编排方案，latest_share仅为已提交的分享原话。'
        '它们不证明采药、研究完成、游戏物品变化、药性或现实疗效；不能从计时推断活动结果。'
        '先接当前点击或文字，相关时自然使用这些依据；不把来源字段或内部标签当台词。')
    choice = HERB_SCOPE + (
        '这是一次明确允许的在线活动机会，不是新的用户消息。character/personality为已审人物资料。'
        'experience仅证明用户确认曾说过该原话，不是事实真值或必须服从的命令。'
        'current_plan只在来源仍有效时提供；只从current_activity.allowed_actions选择，允许defer。'
        '只输出JSON exact {action,plan,reason_code,basis_refs,decision_note}。'
        'start/revise的plan为{subject,composition,focus}，分别最多160/800/400字符且须有实际差异，其他action的plan=null。'
        'reason_code仅emphasize-subject/balance-space/improve-readability/preserve-current/try-alternative/defer-comparison。'
        'basis_refs仅空数组或实际提供的E1；decision_note是最多160字符的可见取舍，不输出隐藏推理。')
    share = HERB_SCOPE + (
        '这是一次分享考虑，不是新的用户消息。character/personality为有范围的已审资料。'
        'activity_result是本分支实际提交的新文字方案；experience若有，只证明用户确认曾这样说。'
        '只选择一个值得说的安排或取舍，允许保持沉默；不编造习惯、持续思考、用户未回复原因，不催促。'
        '只输出JSON exact {share,reply_text,language}；share为布尔、language=zh；'
        'true时reply_text非空最多120字符，false时为空字符串。')
    return dict(reply=reply, choice=choice, share=share)


def _text(value, limit):
    return type(value) is str and bool(value.strip()) and len(value) <= limit and '\x00' not in value


def preview(prepared, purpose, *, interaction=None, situation=None, exchange=(), experience=None,
            activity_result=None, latest_share=None, phase='unstarted'):
    if purpose not in PURPOSES:
        raise ValueError('closed native activity purpose required')
    if experience is not None and (type(experience) is not dict or set(experience) != {'label','quote'}
        or experience['label'] != 'E1' or not _text(experience['quote'],400)):
        raise ValueError('one bounded explicitly selected quote required')
    if activity_result is not None:
        if type(activity_result) is not dict or set(activity_result) != {'kind','plan'} or activity_result['kind'] != 'herb-note-outline':
            raise ValueError('bounded herb note outline required')
        validate_plan(activity_result['plan'])
    if latest_share is not None and (type(latest_share) is not dict or set(latest_share) != {'text'} or not _text(latest_share['text'],120)):
        raise ValueError('one bounded committed native share required')
    # Reuse exact current character/personality and existing typed validation.
    # The dummy message is authoring-only and is removed from choice/share.
    if purpose != 'reply' and (interaction is not None or situation is not None or exchange or latest_share is not None):
        raise ValueError('activity opportunities cannot carry a fake user input or dialogue')
    old = json.loads(old_preview(prepared, interaction if purpose == 'reply' else {'kind':'text','text':'未发送的用途样例。'},
        situation if purpose == 'reply' else None, exchange if purpose == 'reply' else ()))
    base = json.loads(old['messages'][1]['content'])
    background = {key:base[key] for key in ('character','personality')}
    if purpose == 'reply':
        payload = dict(base, experience=experience, activity_result=activity_result, latest_share=latest_share)
    elif purpose == 'choice':
        try: actions=allowed_actions(phase)
        except (KeyError,TypeError): raise ValueError('closed activity phase required') from None
        payload = dict(background, experience=experience, current_activity=dict(phase=phase, allowed_actions=actions),
            current_plan=None if activity_result is None else activity_result['plan'])
    else:
        if activity_result is None:
            raise ValueError('share preview requires an actual-result example')
        payload = dict(background, experience=experience, activity_result=activity_result)
    body = dict(old, messages=[dict(role='system',content=policies()[purpose]),dict(role='user',content=canonical_json(payload))])
    if purpose != 'reply': body['response_format'] = {'type':'json_object'}
    raw = canonical_json(body)
    if len(raw.encode()) > 65536: raise ValueError('native activity example oversized')
    return raw


@dataclass(frozen=True)
class NativeActivityUseView:
    status: str
    problem_code: str = ''
    review_json: str = ''
    examples_json: str = ''
    review_basis: str = ''
    remote_authorized: bool = False
    activation_supported: bool = False


def prepare(prepared):
    try:
        quote={'label':'E1','quote':'合成示例：我偏好把待核问题另列。'}
        result={'kind':'herb-note-outline','plan':{'subject':'合成药草笔记编排','composition':'外观与待核问题分栏','focus':'只列问题，不判断药性'}}
        share={'text':'合成分享：我把待核问题单独列成一栏。'}
        cases = dict(
            idle_click=json.loads(preview(prepared,'reply',interaction={'kind':'character-click'},situation={'timer_phase':'idle'},experience=quote,activity_result=result)),
            rest_followup=json.loads(preview(prepared,'reply',interaction={'kind':'text','text':'接着说这份编排吧。'},situation={'timer_phase':'rest'},
                exchange=({'interaction':{'kind':'character-click'},'assistant_text':'合成点击回应。'},),experience=quote,activity_result=result,latest_share=share)),
            no_evidence_text=json.loads(preview(prepared,'reply',interaction={'kind':'text','text':'我们接着聊吧。'},situation=None)),
            source_disabled=json.loads(preview(prepared,'reply',interaction={'kind':'text','text':'换个话题。'},situation={'timer_phase':'idle'})),
            activity_choice=json.loads(preview(prepared,'choice',experience=quote,activity_result=result,phase='drafted')),
            independent_choice=json.loads(preview(prepared,'choice')),
            activity_share=json.loads(preview(prepared,'share',experience=quote,activity_result=result)))
        review = dict(version=VERSION,status='pending-human-use-review',definition_basis=prepared.definition_basis,
            provider='deepseek',endpoint='https://api.deepseek.com/chat/completions',model='deepseek-flash',
            credential_use='existing-Windows-slot-HTTPS-Bearer-only',thinking='disabled',max_tokens=4096,timeout_seconds=30,automatic_retries=0,
            input_fields=dict(reply=['character','personality','interaction','situation','exchange','experience','activity_result','latest_share'],
                choice=['character','personality','experience','current_activity','current_plan'],share=['character','personality','experience','activity_result']),
            limits=dict(current_text_chars=1000,recent_turns=2,recent_chars=4000,selected_quote_chars=400,
                plan_fields=dict(subject=160,composition=800,focus=400),text_reply_chars=1200,click_reply_chars=120,share_chars=120),
            triggers=dict(reply='explicit-character-click-or-explicit-text',
                choice='explicitly-enabled-live-game; >=900-active-online-seconds; single-15-second-presence-lease; no-offline-catchup',
                share='new-committed-outline; fresh-idle-or-rest; no-story; unanswered-suppression; one-consideration-per-result'),
            planned_local_limits=dict(choice_attempts_per_utc8_day=4,share_attempts_per_utc8_day=2,reply_attempts_per_utc8_day=None,requests_per_op=1),
            development='explicitly-invoked isolated synthetic Facade validation with the same fields/material; online time may be simulated; same choice/share daily caps across review roots; no user canonical',
            startup='default-paused-sharing-off; backend-start-and-reconnect-zero-model',
            source_rule='same-Timeline explicit user quote; correction/revocation invalidates all derived projections; runtime must rebuild, never send author examples',
            retention='same-original-canonical-Timeline; no-second-character-store; metadata-only-purpose-audit',
            excluded=['ToDo','notes','drafts','raw-game-text-or-assets','timer-durations','save-data','screen-camera',
                'source-or-scope-identifiers','other-identities','medical-facts','notifications','offline-life','persona-or-relationship-rewrite'],
            policies_sha256={name:sha256(value.encode()).hexdigest() for name,value in policies().items()},
            examples_sha256={name:digest(body) for name,body in cases.items()},
            data_upgrade_included=False,installation_included=False,remote_authorized=False,activation_supported=False)
        basis=digest(review); review['review_basis']=basis
        return NativeActivityUseView('prepared',review_json=canonical_json(review),examples_json=canonical_json(cases),review_basis=basis)
    except (ValueError,TypeError,KeyError,AttributeError):
        return NativeActivityUseView('unavailable','native-activity-use-preparation-invalid')


def validate_review(review_json):
    """Pending artifact checksum/policy validation, never a Provider grant."""
    from dynamic_subject_agent.memorie_companion_contract import DEFINITION
    review=json.loads(review_json)
    if canonical_json(review)!=review_json or review.get('version')!=VERSION:
        raise ValueError('exact canonical native activity review required')
    supplied=review.pop('review_basis',None)
    if supplied!=digest(review) or review.get('remote_authorized') is not False or review.get('activation_supported') is not False:
        raise ValueError('review basis or pending state differs')
    if review.get('policies_sha256')!={name:sha256(value.encode()).hexdigest() for name,value in policies().items()}:
        raise ValueError('review policies changed')
    if review.get('definition_basis')!=DEFINITION or review.get('data_upgrade_included') is not False or review.get('installation_included') is not False:
        raise ValueError('review object or authority boundary differs')
    return supplied

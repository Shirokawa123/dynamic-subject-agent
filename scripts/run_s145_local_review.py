"""S145 LOCAL Facade review: synthetic output, simulated next day, no credentials.

Exact task contents stay in the newly owned ignored review directory. Public
evidence contains only safe status/count/hash metadata, never character text.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelResult, ProviderAdapter, ProviderCapabilities,
    StructuredOutputMode,
)

REPO = Path(__file__).resolve().parents[1]
SCENE = REPO / 'docs/experiments/s145/scene.json'


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value.value if hasattr(value, 'value') else value


def digest(value):
    return sha256(canonical_json(plain(value)).encode()).hexdigest()


class SyntheticAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('local-s145-review', 'synthetic-fixed-output',
        True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, scene):
        self.calls = []
        self.scene = scene
        self.corrected = False

    def invoke(self, task):
        attempt = dict(kind=task.kind.value, preview=deepcopy(plain(task.payload)),
            status='started', output=None, error_type=None)
        self.calls.append(attempt)
        try:
            payload = plain(task.payload)['payload']
            if task.kind.name == 'WORKING_UNDERSTANDING_FORM':
                value = dict(status='formed', scope='composition-text',
                    statement=self.scene['corrected_understanding' if self.corrected else 'initial_understanding'],
                    basis_refs=['U1', 'U2'] + (['A1'] if payload['activity_result'] else []))
            elif task.kind.name == 'WORKING_ACTIVITY_CHOICE':
                understanding = payload['working_understanding']
                actions = payload['current_activity']['allowed_actions']
                action = 'start' if 'start' in actions else 'revise'
                if action not in actions:
                    raise ValueError('Expected a bounded composition change stage.')
                focus = ('阴影靠近主体' if self.corrected else '安静角落与光影') if understanding else '先比较主体与背景'
                value = dict(action=action, plan=dict(subject='LOCAL合成窗边静物',
                    composition='固定合成方案：' + focus + '。', focus=focus),
                    reason_code='balance-space', basis_refs=['W1'] if understanding else [],
                    decision_note='固定合成取舍，仅验证工作理解接入和真实字段变化。')
            elif task.kind.name == 'WORKING_ACTIVITY_REPLY':
                value = dict(reply_text='固定合成回复，仅验证有效工作理解和已提交文字方案的接入。', language='zh')
            else:
                raise ValueError('Unexpected model task; no remote or fallback exists.')
            attempt.update(status='complete', output=deepcopy(value))
            return ModelResult(task.kind, value)
        except Exception as error:
            attempt.update(status='failed', error_type=type(error).__name__)
            raise


def query(product):
    response = product.application.query_working_understanding()
    if response.status != 'available' or not isinstance(response.view, dict):
        raise ValueError('Verified working view required.')
    return plain(response.view)


def history(product):
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    response = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    if response.status.value != 'available' or response.projection is None:
        raise ValueError('Canonical history unavailable.')
    return response.projection.turns


def send(product, text, adapter):
    from dynamic_subject_agent.timeline import SubjectCommand
    preview = product.application.preview_working_activity('reply', text)
    if preview.status != 'previewed':
        raise ValueError('Exact ordinary reply preview unavailable.')
    count = len(adapter.calls)
    response = product.application.submit(SubjectCommand.contribute_utterance(
        target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status', utterance=text, language='zh',
        provenance='project-original'), idempotency_key='s145-local-' + str(uuid4()))
    if response.status.value == 'pending':
        response = product.application.wait(response.operation_ref, timeout_seconds=30)
    if (response.status.value != 'terminal' or response.projection is None
        or response.projection.failure_code):
        raise ValueError('Synthetic ordinary exchange did not commit.')
    if len(adapter.calls) != count+1 or adapter.calls[-1]['preview'] != plain(preview.view):
        raise ValueError('Ordinary reply preview/model mismatch.')
    return history(product)[-1]


def run(base, scene):
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.application import ApplicationFacade
    from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_working_understanding_product_local
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
    from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
    from dynamic_subject_agent.shared_activity import SharedActivityStepRequest
    from dynamic_subject_agent.working_understanding import WorkingSourceQuote, WorkingUnderstandingRequest
    from dynamic_subject_agent.working_understanding import working_contract

    base = base.resolve()
    allowed = (REPO / '.local_indexes/s145').resolve()
    if not base.is_relative_to(allowed) or base.exists():
        raise ValueError('A new owned s145 review root is required; existing evidence is retained.')
    package = REPO / '.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
    review = ApplicationFacade.preview_original_character_whole_use_preparation(
        OriginalWholeUsePreparationRequest(package, APPROVED_BINDING['definition_basis'],
            APPROVED_BINDING['runtime_asset_sha'], APPROVED_BINDING['persona_digest'],
            APPROVED_BINDING['subject_id'], APPROVED_BINDING['anchor_id']))
    if review.status != 'previewed' or review.review_basis != APPROVED_BINDING['review_basis']:
        raise ValueError('Existing exact reviewed character package is required.')
    base.mkdir(parents=True, exist_ok=False)
    config = LocalProductConfig(base/'branch/DynamicSubjectAgent/m0/experiments', base/'branch/state.json')
    adapter = SyntheticAdapter(scene)
    stages, checks = [], {}
    product = None
    day = [scene['first_day']]
    runner_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    contract_sha = digest(working_contract(APPROVED_BINDING))

    def checkpoint(status='running', error=None):
        exact = dict(version='s145-local-exact-1', status=status,
            synthetic_outputs=True, simulated_day=True, tasks=adapter.calls,
            runner_sha256_at_execution=runner_sha, local_contract_sha256_at_execution=contract_sha)
        safe = dict(version='s145-local-review-metadata-1', status=status,
            error_type=None if error is None else type(error).__name__,
            synthetic_outputs=True, simulated_day=True, remote_calls=0,
            real_cross_day_verified=False, day_boundary_logic_verified=False,
            credential_reads=0, scene_sha256=digest(scene), stages=stages,
            runner_sha256_at_execution=runner_sha, local_contract_sha256_at_execution=contract_sha,
            local_model_tasks=len(adapter.calls), checks=checks,
            tasks=[dict(kind=call['kind'], preview_sha256=digest(call['preview']),
                status=call['status'], error_type=call['error_type'],
                output_sha256=None if call['output'] is None else digest(call['output'])) for call in adapter.calls],
            exact_unsent_previews_sha256=digest(exact), raw_text_exported=False)
        (base/'exact-unsent-previews.json').write_text(json.dumps(exact, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        (base/'metadata.json').write_text(json.dumps(safe, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return safe

    def stage(label, action):
        entry = dict(stage=label, status='running', before=len(adapter.calls), after=None)
        stages.append(entry)
        checkpoint()
        try:
            value = action()
            entry.update(status='complete', after=len(adapter.calls))
            checkpoint()
            return value
        except Exception as error:
            entry.update(status='failed', after=len(adapter.calls), error_type=type(error).__name__)
            checkpoint('failed-partial', error)
            raise

    def opening():
        return open_working_understanding_product_local(config, gateway=ModelGateway(adapter),
            identity_id=identity_id, day=lambda: day[0])

    def step(key):
        request = SharedActivityStepRequest(product.profile_id, product.timeline_id,
            key, query(product)['revision'])
        preview = product.application.preview_working_activity('choice')
        if preview.status != 'previewed':
            raise ValueError('Exact choice preview unavailable.')
        before = len(adapter.calls)
        response = product.application.advance_working_activity(request)
        if response.status != 'committed' or len(adapter.calls) != before+1:
            raise ValueError('Synthetic choice did not commit exactly once.')
        if adapter.calls[-1]['preview'] != plain(preview.view):
            raise ValueError('Preview differed from actual ModelTask.')
        return request

    def form(sources, *, disable=False, expected_activity_plan=None):
        request = WorkingUnderstandingRequest(product.profile_id, product.timeline_id,
            str(uuid4()), query(product)['revision'],
            tuple(WorkingSourceQuote(head, quote) for head, quote in sources),
            action='disable' if disable else 'form', confirmed=True)
        preview = None if disable else product.application.preview_working_understanding(request)
        if preview is not None and preview.status != 'previewed':
            raise ValueError('Exact form preview unavailable.')
        if preview is not None:
            payload = plain(preview.view)['payload']
            expected_exchanges = [dict(label='U'+str(i+1), quote=quote)
                for i,(_,quote) in enumerate(sources)]
            expected_activity = None if expected_activity_plan is None else dict(
                label='A1', kind='composition-text', plan=expected_activity_plan)
            if (payload['scope'] != 'composition-text' or payload['exchanges'] != expected_exchanges
                or payload['activity_result'] != expected_activity):
                raise ValueError('Form input does not match the selected actual sources.')
        count = len(adapter.calls)
        response = product.application.apply_working_understanding(request)
        if response.status != 'committed':
            raise ValueError('Working understanding mutation did not commit.')
        if disable:
            if len(adapter.calls) != count:
                raise ValueError('Disable invoked a model.')
        elif len(adapter.calls) != count+1 or adapter.calls[-1]['preview'] != plain(preview.view):
            raise ValueError('Form preview/model mismatch.')
        return request

    try:
        with open_local_product(config, cognition=DormantDeepSeekCognition()) as author:
            frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
                package.read_text(encoding='utf-8'), APPROVED_BINDING['definition_basis'], True, True))
            if frozen.status != 'created':
                raise ValueError('A new dormant identity was not created.')
            identity_id = frozen.view.identity_id
        product = opening()
        heads = [stage('source-exchange-'+str(i+1), lambda text=text: send(product, text, adapter)).head_sequence
            for i,text in enumerate(scene['source_messages'])]
        stage('independent-first-plan', lambda: step(str(uuid4())))
        first_plan = query(product)['current_plan']
        stage('form-two-quotes-and-actual-plan', lambda: form(list(zip(heads,scene['source_quotes'])), expected_activity_plan=first_plan))
        formed = query(product)['visible_understanding']
        if formed is None:
            raise ValueError('The formed working understanding is unavailable.')
        for i,text in enumerate(scene['gap_messages']):
            stage('unrelated-exchange-'+str(i+1), lambda text=text: send(product,text,adapter))
        checks['source_heads_outside_recent_two'] = all(row.head_sequence not in heads for row in history(product)[-2:])
        if not checks['source_heads_outside_recent_two']:
            raise ValueError('Selected sources did not leave the recent window.')
        previous, count = query(product), len(adapter.calls)
        stage('close-before-next-day', product.close)
        day[0] = scene['next_day']
        product = stage('reopen-simulated-next-day', opening)
        checks['reopen_zero_model_same_view'] = query(product)==previous and len(adapter.calls)==count
        if not checks['reopen_zero_model_same_view']:
            raise ValueError('Reopen changed business state or invoked a model.')
        request = stage('next-choice-uses-working-understanding', lambda: step(str(uuid4())))
        second_plan = query(product)['current_plan']
        checks['next_choice_plan_changed'] = second_plan != first_plan
        checks['choice_includes_working_understanding'] = adapter.calls[-1]['preview']['payload']['working_understanding'] is not None
        if not all(checks.values()):
            raise ValueError('The expected synthetic continuity did not hold.')
        count = len(adapter.calls)
        replay = stage('same-nonce-zero-model', lambda: product.application.advance_working_activity(request))
        checks['same_nonce_zero_model'] = replay.status == 'replayed' and len(adapter.calls)==count
        stage('result-back-to-exchange', lambda: send(product,scene['result_question'],adapter))
        reply_payload = adapter.calls[-1]['preview']['payload']
        checks['reply_same_committed_plan'] = reply_payload['evidence']['activity_result']['plan'] == second_plan
        stage('disable-understanding-zero-model', lambda: form([],disable=True))
        disabled = query(product)
        checks['disabled_whole_derived_chain_hidden'] = (disabled['visible_understanding'] is None
            and disabled['current_plan'] is None and disabled['visible_result'] is None)
        preview = product.application.preview_working_activity('reply',scene['result_question'])
        if preview.status != 'previewed':
            raise ValueError('Disabled reply preview unavailable.')
        disabled_preview_payload = plain(preview.view)['payload']
        checks['disabled_preview_no_working_understanding'] = disabled_preview_payload['evidence']['working_understanding'] is None
        checks['disabled_preview_no_old_result_or_history'] = (disabled_preview_payload['evidence']['activity_result'] is None
            and disabled_preview_payload['evidence']['shared_experience'] is None
            and disabled_preview_payload['exchange'] == [])
        if not all(checks.values()):
            raise ValueError('Disabled input chain was not fully filtered.')
        stage('disabled-actual-reply-no-old-chain',lambda: send(product,scene['result_question'],adapter))
        disabled_payload = adapter.calls[-1]['preview']['payload']
        checks['disabled_actual_reply_no_old_chain'] = (disabled_payload['evidence']['working_understanding'] is None
            and disabled_payload['evidence']['activity_result'] is None
            and disabled_payload['evidence']['shared_experience'] is None and disabled_payload['exchange'] == [])
        adapter.corrected = True
        corrected_heads = [stage('correction-exchange-'+str(i+1), lambda text=text: send(product,text,adapter)).head_sequence
            for i,text in enumerate(scene['correction_messages'])]
        stage('rebuild-from-new-committed-quotes',lambda: form(list(zip(corrected_heads,scene['correction_quotes']))))
        stage('corrected-understanding-new-plan',lambda: step(str(uuid4())))
        corrected_plan = query(product)['current_plan']
        checks['correction_new_understanding_and_plan'] = (query(product)['visible_understanding'] != formed
            and corrected_plan != second_plan)
        stage('corrected-result-back-to-exchange',lambda: send(product,scene['result_question'],adapter))
        checks['corrected_reply_same_plan'] = adapter.calls[-1]['preview']['payload']['evidence']['activity_result']['plan'] == corrected_plan
        if not all(checks.values()):
            raise ValueError('A safe continuity check did not hold.')
        return checkpoint('complete')
    except Exception as error:
        checkpoint('failed-partial',error)
        raise
    finally:
        if product is not None:
            product.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--root', type=Path)
    args=parser.parse_args()
    scene=json.loads(SCENE.read_text(encoding='utf-8'))
    for text,quote in zip(scene['source_messages']+scene['correction_messages'],
        scene['source_quotes']+scene['correction_quotes']):
        if not quote or quote not in text or len(quote)>400 or len(text)>1000:
            raise SystemExit('Scene source boundary invalid.')
    if args.self_check and not args.execute:
        print(json.dumps(dict(status='self-check-complete',scene_sha256=digest(scene),
            product_roots_created=0,model_tasks=0,remote_calls=0,credential_reads=0)))
        return
    if not args.execute or args.root is None:
        raise SystemExit('Use --self-check or explicit --execute --root; no implicit run.')
    try:
        result=run(args.root,scene)
    except Exception as error:
        raise SystemExit('LOCAL review stopped; first partial evidence retained; '+type(error).__name__) from None
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()

"""Exercise the local shared-activity Facade and freeze exact, unsent previews.

All model outputs are deliberately synthetic. This is engineering evidence,
never an assessment of character quality or a remote Provider permission.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelResult, ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
)

REPO = Path(__file__).resolve().parents[1]


def plain(value):
    return asdict(value) if is_dataclass(value) else value


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


class LocalReviewAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('local-s139-review', 'synthetic-fixed-output', True,
        (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls = []

    def invoke(self, task):
        self.calls.append(dict(kind=task.kind.value, preview=deepcopy(plain(task.payload))))
        if task.kind.name == 'SHARED_ACTIVITY_CHOICE':
            payload = plain(task.payload)['payload']
            value = dict(action='start', plan=dict(subject='合成验收用窗边静物',
                composition='固定合成文字方案：主体位于中央，背景保持简单。',
                focus='只检查本地方案及来源依赖，不据此判断人物选择效果。'),
                reason_code='balance-space', basis_refs=['E1'] if payload['shared_experience'] else [],
                decision_note='这是固定的合成输出，仅用于验证工程接缝。')
        elif task.kind.name == 'SHARED_ACTIVITY_REPLY':
            value = dict(reply_text='这是本地固定合成回复，不是人物体验验收。', language='zh')
        else:
            raise ValueError('Unexpected task; no fallback or remote adapter exists.')
        return ModelResult(task.kind, value)


def query(product):
    response = product.application.query_shared_activity()
    if response.status != 'available' or type(response.view) is not dict:
        raise ValueError('Verified local shared-activity view required.')
    return response.view


def history(product):
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    response = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    if response.status.value != 'available' or response.projection is None:
        raise ValueError('Verified canonical conversation history required.')
    return response.projection.turns


def send(product, text, key):
    from dynamic_subject_agent.timeline import SubjectCommand
    response = product.application.submit(SubjectCommand.contribute_utterance(
        target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status', utterance=text, language='zh',
        provenance='project-original'), idempotency_key=key)
    if response.status.value == 'pending':
        response = product.application.wait(response.operation_ref, timeout_seconds=30)
    if response.status.value != 'terminal':
        raise ValueError('Local conversation did not commit: ' + response.status.value)
    return response


def run_branch(base, branch, scenario):
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.application import ApplicationFacade
    from dynamic_subject_agent.local_product import (
        LocalProductConfig, open_local_product, open_shared_activity_product_local,
    )
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
    from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
    from dynamic_subject_agent.shared_activity import SharedExperienceRequest, SharedActivityStepRequest

    package = REPO / '.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
    review = ApplicationFacade.preview_original_character_whole_use_preparation(
        OriginalWholeUsePreparationRequest(package, APPROVED_BINDING['definition_basis'],
            APPROVED_BINDING['runtime_asset_sha'], APPROVED_BINDING['persona_digest'],
            APPROVED_BINDING['subject_id'], APPROVED_BINDING['anchor_id']))
    if review.status != 'previewed' or review.review_basis != APPROVED_BINDING['review_basis']:
        raise ValueError('Existing exact material approval must match before local authoring.')
    root = base / branch['name']
    if root.exists():
        raise ValueError('Existing branch retained; no overwrite or automatic retry.')
    config = LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments', root/'state.json')
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as author:
        frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            package.read_text(encoding='utf-8'), APPROVED_BINDING['definition_basis'], True, True))
        if frozen.status != 'created':
            raise ValueError('New dormant identity required.')
        identity_id = frozen.view.identity_id
    adapter = LocalReviewAdapter()
    def opening():
        return open_shared_activity_product_local(config, gateway=ModelGateway(adapter), identity_id=identity_id)
    product = opening()
    try:
        send(product, branch['source_message'], 's139-local-source')
        source_turn = history(product)[-1]
        selected = product.application.set_shared_experience(SharedExperienceRequest(
            product.profile_id, product.timeline_id, str(uuid4()), query(product)['revision'],
            source_turn.head_sequence, branch['selected_quote'], True))
        if selected.status != 'committed':
            raise ValueError('Exact source was not selected: ' + selected.status)
        for index, text in enumerate(scenario['unrelated_messages_after_selection']):
            send(product, text, 's139-local-gap-' + str(index))
        previous_history, previous_view, count = history(product), query(product), len(adapter.calls)
        if any(turn.head_sequence == source_turn.head_sequence for turn in previous_history[-2:]):
            raise ValueError('Selected source has not left the two-turn window.')
        product.close()
        product = opening()
        if history(product) != previous_history or query(product) != previous_view or len(adapter.calls) != count:
            raise ValueError('Reopen changed state or invoked a model.')
        if branch['source_action_after_selection'] == 'deactivate-before-advance':
            response = product.application.set_shared_experience(SharedExperienceRequest(
                product.profile_id, product.timeline_id, str(uuid4()), query(product)['revision'],
                None, '', True))
            if response.status != 'committed':
                raise ValueError('Exact source was not deactivated.')
        response = product.application.preview_shared_activity_step()
        if response.status != 'previewed' or type(response.view) is not dict:
            raise ValueError('Exact unsent step preview required.')
        choice_preview = deepcopy(response.view)
        count = len(adapter.calls)
        request = SharedActivityStepRequest(product.profile_id, product.timeline_id,
            str(uuid4()), query(product)['revision'])
        advanced = product.application.advance_shared_activity(request)
        if advanced.status != 'committed' or len(adapter.calls) != count + 1:
            raise ValueError('Single local activity step was not committed once.')
        if adapter.calls[-1]['preview'] != choice_preview:
            raise ValueError('Preview and invoked model task differ.')
        replay = product.application.advance_shared_activity(request)
        if replay.status != 'replayed' or len(adapter.calls) != count + 1:
            raise ValueError('Repeated request did not replay without a model.')
        after_activity = query(product)
        send(product, scenario['followup_message'], 's139-local-followup')
        reply_preview = deepcopy(adapter.calls[-1]['preview'])
        result = plain(after_activity['visible_result'])
        if result is None or reply_preview['payload']['evidence']['activity_result'] != {
            'kind': result['kind'], 'plan': result['plan']
        }:
            raise ValueError('Next reply did not receive the same committed activity result.')
        return dict(branch=branch['name'], local_model_calls=len(adapter.calls),
            source_outside_two_turn_window=True, reopen_zero_calls=True,
            step_preview_equals_task=True, repeated_step_zero_calls=True,
            reply_uses_committed_result=True,
            activity_phase=after_activity['phase'],
            choice_preview=choice_preview, result_reply_preview=reply_preview)
    finally:
        product.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default=str(uuid4()))
    args = parser.parse_args()
    if any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for character in args.run_id):
        raise SystemExit('Simple nonempty run id required.')
    if not args.run_id:
        raise SystemExit('Simple nonempty run id required.')
    base = Path(os.environ['LOCALAPPDATA']) / 'DynamicSubjectAgent/shared-activity-development/s139' / args.run_id
    if base.exists():
        raise SystemExit('Existing local review retained; choose a new explicit run id after investigating.')
    scenario_path = REPO/'docs/experiments/s139/scenarios.json'
    scenario = json.loads(scenario_path.read_text(encoding='utf-8'))
    rows = [run_branch(base, branch, scenario) for branch in scenario['branches']]
    common = []
    for row, branch in zip(rows, scenario['branches'], strict=True):
        value = deepcopy(row['choice_preview'])
        source = value['payload'].pop('shared_experience')
        expected = None if branch['source_action_after_selection'] == 'deactivate-before-advance' else {
            'label': 'E1', 'quote': branch['selected_quote']
        }
        if source != expected:
            raise ValueError('Activity did not receive the exact active user quote or null.')
        common.append(value)
    if not all(value == common[0] for value in common):
        raise ValueError('Activity preconditions differ outside the intended source variable.')
    preview = dict(version='s139-local-exact-review-1', simulated_outputs=True, remote_calls=0,
        scenario_sha256=sha256(scenario_path.read_bytes()).hexdigest(), branches=rows)
    output = base/'exact-unsent-previews.json'
    with output.open('x', encoding='utf-8') as target:
        json.dump(preview, target, ensure_ascii=False, indent=2)
    metadata = dict(version=preview['version'], simulated_outputs=True, remote_calls=0,
        activity_preconditions_equal_except_source=True,
        scenario_sha256=preview['scenario_sha256'], review_sha256=digest(preview),
        exact_local_preview_path=str(output), branches=[
            {**{key: value for key, value in row.items() if not key.endswith('_preview')},
             'choice_preview_sha256': digest(row['choice_preview']),
             'reply_preview_sha256': digest(row['result_reply_preview'])} for row in rows])
    with (base/'metadata.json').open('x', encoding='utf-8') as target:
        json.dump(metadata, target, ensure_ascii=False, indent=2)
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == '__main__':
    main()

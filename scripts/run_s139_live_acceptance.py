"""Approved S139 first live branches: one request per action, no automatic retry.

Only metadata reaches stdout and this report. Actual text remains canonical;
subsequent qualitative assessment reads that canonical state through the Facade.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from observe_whole_reply_boundaries import response_metadata
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.application import ApplicationFacade, ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekUrlLibTransport
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, _WindowsLabResolver
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.shared_activity import SharedActivityStepRequest, SharedExperienceRequest
from dynamic_subject_agent.timeline import SubjectCommand

REPO = Path(__file__).resolve().parents[1]
REVIEW_BASIS = '8bb95a501eb44827e939ea41376cbda0eea6463a266b2983581d36f65494301a'
BASE = Path(os.environ['LOCALAPPDATA'])/'DynamicSubjectAgent/shared-activity-development/s139/live-first-20261003'
OUTPUT = REPO/'docs/reports/2026-10-03-slice-139/live-first-metadata.json'


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def state(product):
    result = product.application.query_shared_activity()
    if result.status != 'available' or type(result.view) is not dict:
        raise ValueError('Verified shared state unavailable.')
    return result.view


def history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    if result.status.value != 'available' or result.projection is None:
        raise ValueError('Verified canonical history unavailable.')
    return result.projection.turns


def shared_metadata(view):
    decision, result = view['decision'], view['visible_result']
    return dict(phase=view['phase'], activity_revision=view['activity_revision'],
        source_visible=view['visible_source'] is not None,
        decision_action=None if decision is None else decision.action,
        basis_refs=[] if decision is None else list(decision.basis_refs),
        reason_code=None if decision is None else decision.reason_code,
        decision_note_sha256=None if decision is None else digest(decision.decision_note),
        result_kind=None if result is None else result.kind,
        plan_sha256=None if result is None or result.plan is None else digest(asdict(result.plan)))


class LiveObservedTransport(DeepSeekTransport):
    """Observe approved bytes unchanged, never retain body or reasoning text."""
    def __init__(self):
        self.delegate = DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        self.rows = []

    def post_json(self, **kwargs):
        row = dict(request_metadata_valid=False)
        try:
            body = json.loads(kwargs['body'])
            payload = json.loads(body['messages'][1]['content'])
            choice = 'current_activity' in payload
            source = payload['shared_experience'] if choice else payload['evidence']['shared_experience']
            plan = payload['current_plan'] if choice else (payload['evidence']['activity_result'] or {}).get('plan')
            common = deepcopy(payload)
            if choice:
                common.pop('shared_experience')
            row.update(request_metadata_valid=True, task='choice' if choice else 'reply',
                wire_sha256=sha256(kwargs['body']).hexdigest(), payload_sha256=digest(payload),
                shared_quote_chars=0 if source is None else len(source['quote']),
                shared_quote_sha256=None if source is None else digest(source['quote']),
                supplied_plan_sha256=None if plan is None else digest(plan),
                recent_dialogue_turns=0 if choice else len(payload['exchange']),
                common_choice_payload_sha256=digest(common) if choice else None)
        except (KeyError, ValueError, TypeError):
            pass
        self.rows.append(row)
        response = self.delegate.post_json(**kwargs)
        row['response_boundary'] = response_metadata(response)
        return response


def new_identity(root):
    package = REPO/'.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
    preview = ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(
        package, APPROVED_BINDING['definition_basis'], APPROVED_BINDING['runtime_asset_sha'],
        APPROVED_BINDING['persona_digest'], APPROVED_BINDING['subject_id'], APPROVED_BINDING['anchor_id']))
    if preview.status != 'previewed' or preview.review_basis != APPROVED_BINDING['review_basis']:
        raise ValueError('Exact approved character package required.')
    config = LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments', root/'state.json')
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as author:
        frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            package.read_text(encoding='utf-8'), APPROVED_BINDING['definition_basis'], True, True))
        if frozen.status != 'created':
            raise ValueError('New independent dormant identity required.')
    return config, frozen.view.identity_id


def run_branch(branch, scenario, report):
    from dynamic_subject_agent.local_product import open_shared_activity_product_live
    from dynamic_subject_agent.shared_activity_live import ApprovedSharedActivityGrant
    row = dict(branch=branch['name'], stages=[], completed=False, stopped_on_failure=False)
    report['branches'].append(row)
    def save():
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    config, identity_id = new_identity(BASE/branch['name'])
    transport, observations = LiveObservedTransport(), []
    grant = ApprovedSharedActivityGrant(review_basis=REVIEW_BASIS, confirmed=True)
    def opening():
        return open_shared_activity_product_live(config, identity_id=identity_id, grant=grant,
            audit_path=BASE/'audit', _transport=transport, observations=observations)
    product = opening()
    try:
        def chat(message, label):
            transport.rows.clear(); observations.clear()
            before, started = len(history(product)), perf_counter()
            result = product.application.submit(SubjectCommand.contribute_utterance(
                target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
                declared_intent='ask-collaborator-status', utterance=message, language='zh',
                provenance='project-original'), idempotency_key='s139-live-'+str(uuid4()))
            deadline = perf_counter()+120
            while result.status.value == 'pending' and perf_counter() < deadline:
                result = product.application.wait(result.operation_ref, timeout_seconds=30)
            expression = getattr(result.projection, 'expression_text', '') or ''
            item = dict(stage=label, status=result.status.value,
                failure_code=getattr(result.projection, 'failure_code', None),
                elapsed_seconds=perf_counter()-started, committed_before=before,
                committed_after=len(history(product)), reply_chars=len(expression),
                reply_sha256=None if not expression else sha256(expression.encode()).hexdigest(),
                observations=list(observations), transport=list(transport.rows))
            if transport.rows and transport.rows[0].get('response_boundary', {}).get('reply_sha256'):
                item['final_expression_matches_raw_reply'] = item['reply_sha256'] == transport.rows[0]['response_boundary']['reply_sha256']
            row['stages'].append(item); save(); print(json.dumps(dict(branch=branch['name'], **item), ensure_ascii=False), flush=True)
            if result.status.value == 'terminal' and item.get('final_expression_matches_raw_reply') is False:
                row['stopped_on_failure'] = True
                item['integrity_status'] = 'raw-canonical-reply-mismatch'
                report['stopped_for_integrity'] = True
                save()
                raise RuntimeError('raw-canonical-reply-mismatch; all further live calls stopped')
            if result.status.value != 'terminal':
                row['stopped_on_failure'] = True; save()
                return False
            return True
        if not chat(branch['source_message'], 'source-conversation'):
            return
        source = history(product)[-1]
        result = product.application.set_shared_experience(SharedExperienceRequest(
            product.profile_id, product.timeline_id, str(uuid4()), state(product)['revision'],
            source.head_sequence, branch['selected_quote'], True))
        row['source_selected'] = result.status == 'committed'; save()
        if result.status != 'committed':
            raise ValueError('Source selection failed without a model.')
        for index, message in enumerate(scenario['unrelated_messages_after_selection']):
            if not chat(message, 'unrelated-'+str(index+1)):
                return
        previous = history(product), state(product)
        assert all(turn.head_sequence != source.head_sequence for turn in previous[0][-2:])
        transport.rows.clear(); observations.clear()
        product.close(); product = opening()
        assert (history(product), state(product)) == previous and not observations and not transport.rows
        row['source_outside_two_turn_window'] = row['pre_activity_reopen_zero_calls'] = True
        if branch['source_action_after_selection'] == 'deactivate-before-advance':
            result = product.application.set_shared_experience(SharedExperienceRequest(
                product.profile_id, product.timeline_id, str(uuid4()), state(product)['revision'], None, '', True))
            if result.status != 'committed':
                raise ValueError('Explicit local source deactivation failed.')
            row['source_deactivated'] = True
        preview = product.application.preview_shared_activity_step()
        if preview.status != 'previewed':
            raise ValueError('Exact current activity preview unavailable.')
        row['choice_preview_sha256'] = digest(preview.view)
        request = SharedActivityStepRequest(product.profile_id, product.timeline_id, str(uuid4()), state(product)['revision'])
        transport.rows.clear(); observations.clear(); started = perf_counter()
        advanced = product.application.advance_shared_activity(request)
        item = dict(stage='activity', status=advanced.status, failure_code=advanced.problem_code,
            elapsed_seconds=perf_counter()-started, observations=list(observations), transport=list(transport.rows))
        row['stages'].append(item); save(); print(json.dumps(dict(branch=branch['name'], **item), ensure_ascii=False), flush=True)
        if advanced.status != 'committed':
            row['stopped_on_failure'] = True; save()
            return
        row['activity_result'] = shared_metadata(state(product))
        transport.rows.clear(); observations.clear()
        replayed = product.application.advance_shared_activity(request)
        assert replayed.status == 'replayed' and not observations and not transport.rows
        row['same_activity_nonce_zero_calls'] = True
        previous = history(product), state(product)
        product.close(); product = opening()
        assert (history(product), state(product)) == previous and not observations and not transport.rows
        row['post_activity_reopen_zero_calls'] = True
        if not chat(scenario['followup_message'], 'result-followup'):
            return
        delivered_plan = transport.rows[0]['supplied_plan_sha256'] if len(transport.rows) == 1 else 'unverified'
        if delivered_plan != row['activity_result']['plan_sha256']:
            raise ValueError('Actual next reply wire differs from committed plan.')
        row['reply_uses_same_committed_result'] = True
        row['completed'] = True; save()
    finally:
        product.close()


def main():
    if BASE.exists() or OUTPUT.exists():
        raise SystemExit('First live branches already exist; retained without retry or overwrite.')
    approval = json.loads((REPO/'docs/experiments/s139/review.json').read_text(encoding='utf-8'))
    if approval['review_basis'] != REVIEW_BASIS or digest(approval['review']) != REVIEW_BASIS:
        raise ValueError('Exact human-approved immutable review required.')
    scenario_bytes = (REPO/'docs/experiments/s139/scenarios.json').read_bytes()
    if sha256(scenario_bytes).hexdigest() != approval['review']['scenario_sha256']:
        raise ValueError('Exact reviewed first-branch scenarios required before any activation.')
    scenario = json.loads(scenario_bytes.decode('utf-8'))
    report = dict(version='s139-first-live-1', review_basis=REVIEW_BASIS, automatic_retries=0,
        raw_text_exported=False, independent_branches=True, branches=[])
    for branch in scenario['branches']:
        run_branch(branch, scenario, report)
    report['completed_branches'] = sum(row['completed'] for row in report['branches'])
    report['transport_invocations'] = sum(len(stage['transport']) for row in report['branches'] for stage in row['stages'])
    choices = [stage['transport'][0]['common_choice_payload_sha256'] for row in report['branches']
        for stage in row['stages'] if stage['stage']=='activity' and len(stage['transport'])==1]
    report['activity_preconditions_equal_except_source'] = len(choices)==3 and len(set(choices))==1
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'branches'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

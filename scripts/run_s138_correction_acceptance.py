"""One authorized fresh chain, no automatic retry; responses only in canonical."""
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from observe_whole_reply_boundaries import BoundaryObservedTransport
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.application import ApplicationFacade, ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_original_whole_product, _WindowsLabResolver
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.original_whole_chat_provider import OriginalWholeObservations
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.timeline import SubjectCommand

REPO = Path(__file__).resolve().parents[1]


def history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    if result.status.value != 'available' or result.projection is None:
        raise ValueError('canonical history unavailable')
    return result.projection.turns


def main():
    root = Path(os.environ['LOCALAPPDATA']) / 'DynamicSubjectAgent/character-whole-development/s138/context-boundary/correction-chain-1'
    if root.exists():
        raise SystemExit('Existing actual chain retained; this script never retries it.')
    package = REPO / '.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
    review = ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(
        package, APPROVED_BINDING['definition_basis'], APPROVED_BINDING['runtime_asset_sha'],
        APPROVED_BINDING['persona_digest'], APPROVED_BINDING['subject_id'], APPROVED_BINDING['anchor_id']))
    if review.status != 'previewed' or review.review_basis != APPROVED_BINDING['review_basis']:
        raise ValueError('exact existing approval required')
    config = LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments', root/'state.json')
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as author:
        frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            package.read_text(encoding='utf-8'), APPROVED_BINDING['definition_basis'], True, True))
        if frozen.status != 'created':
            raise ValueError('new independent approved identity required')
    transport = BoundaryObservedTransport(DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver()))
    observations = OriginalWholeObservations()
    options = {key: APPROVED_BINDING[key] for key in ('definition_basis', 'runtime_asset_sha', 'persona_digest', 'review_basis')}
    options.update(technical_variant='context-boundary', _transport=transport, observations=observations)
    product = open_original_whole_product(config, **options, identity_id=frozen.view.identity_id)
    messages = json.loads((REPO/'docs/experiments/s138/chains.json').read_text(encoding='utf-8'))['correction']
    metadata = dict(version='s138-correction-actual-1', automatic_retries=0, raw_text_exported=False, turns=[])
    output = REPO/'docs/reports/2026-10-02-slice-138/correction-metadata.json'
    try:
        for index, message in enumerate(messages):
            if index == 4:
                prior = history(product)
                product.close()
                product = open_original_whole_product(config, **options)
                if history(product) != prior:
                    raise ValueError('reopen changed previous chat')
                metadata['reopen_preserved_history'] = True
            transport.rows.clear(); observations.clear()
            before = history(product)
            started = perf_counter()
            command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
                target_timeline_id=product.timeline_id, declared_intent='ask-collaborator-status',
                utterance=message, language='zh', provenance='project-original')
            result = product.application.submit(command, idempotency_key='s138-owned-'+str(uuid4()))
            deadline = perf_counter()+120
            while result.status.value == 'pending' and perf_counter() < deadline:
                result = product.application.wait(result.operation_ref, timeout_seconds=30)
            text = getattr(result.projection, 'expression_text', '') or ''
            row = dict(step=index+1, status=result.status.value,
                failure_code=getattr(result.projection, 'failure_code', None), observations=list(observations),
                raw_boundary=list(transport.rows), elapsed_seconds=perf_counter()-started,
                reply_chars=len(text), reply_sha256=sha256(text.encode()).hexdigest() if text else None,
                committed_before=len(before), committed_after=len(history(product)))
            if len(transport.rows) == 1 and transport.rows[0].get('reply_sha256') is not None:
                row['final_expression_matches_raw_reply'] = row['reply_sha256'] == transport.rows[0]['reply_sha256']
            metadata['turns'].append(row)
            output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if text:
                print(text, flush=True)  # Local judgment only; never copied into report files.
            if result.status.value != 'terminal':
                metadata['stopped_on_failure'] = True
                output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
                return
        metadata['full_chain_completed'] = True
        output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        product.close()


if __name__ == '__main__':
    main()

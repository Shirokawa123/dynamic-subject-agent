"""Isolated real character chains; canonical text only, metadata observations only."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from time import perf_counter
from uuid import uuid4

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind, ApplicationFacade
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_original_whole_product
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.original_whole_chat_provider import OriginalWholeObservations
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.timeline import SubjectCommand

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / '.local_indexes/eromanga-sensei/s102/full-definition-v2.json'


def canonical_history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    if result.status.value != 'available' or result.projection is None:
        raise ValueError('canonical history unavailable')
    return result.projection.turns


def prepare(config, marker):
    if marker.exists():
        if json.loads(marker.read_text(encoding='utf-8')) != APPROVED_BINDING:
            raise ValueError('branch approved binding changed')
        return
    if config.state_path.exists():
        raise ValueError('partial existing branch preserved')
    review = ApplicationFacade.preview_original_character_whole_use_preparation(
        OriginalWholeUsePreparationRequest(PACKAGE, APPROVED_BINDING['definition_basis'],
            APPROVED_BINDING['runtime_asset_sha'], APPROVED_BINDING['persona_digest'],
            APPROVED_BINDING['subject_id'], APPROVED_BINDING['anchor_id']))
    if review.review_basis != APPROVED_BINDING['review_basis']:
        raise ValueError('exact approved original package required')
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as product:
        result = product.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            PACKAGE.read_text(encoding='utf-8'), APPROVED_BINDING['definition_basis'], True, True))
        if result.status != 'created':
            raise ValueError('new approved identity required')
        if product.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True)).status != 'selected':
            raise ValueError('new approved identity selection failed')
    marker.write_text(json.dumps(APPROVED_BINDING, sort_keys=True), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slice', required=True)
    parser.add_argument('--variant', default='baseline')
    parser.add_argument('--case', required=True)
    args = parser.parse_args()
    if any(re.fullmatch(r'[a-z0-9-]{1,48}', value) is None for value in vars(args).values()):
        raise ValueError('bounded branch names required')
    messages = json.loads((REPO / f'docs/experiments/{args.slice}/chains.json').read_text(encoding='utf-8'))[args.case]
    if not messages or any(type(text) is not str or not text.strip() or len(text)>1000 or '\x00' in text for text in messages):
        raise ValueError('explicit bounded authored messages required')
    root = Path(os.environ['LOCALAPPDATA']) / 'DynamicSubjectAgent/character-whole-development' / args.slice / args.variant / args.case
    root.mkdir(parents=True, exist_ok=True)
    config = LocalProductConfig(root / 'DynamicSubjectAgent/m0/experiments', root / 'state.json')
    prepare(config, root / 'approved.json')
    observations = OriginalWholeObservations()
    options = {key:APPROVED_BINDING[key] for key in ('definition_basis','runtime_asset_sha','persona_digest','review_basis')}
    if args.variant != 'baseline':
        options['technical_variant'] = args.variant
    product = open_original_whole_product(config, **options, observations=observations)
    try:
        saved = canonical_history(product)
        if len(saved)>len(messages) or any(row.user_text!=messages[i] for i,row in enumerate(saved)):
            raise ValueError('existing branch history does not match authored chain')
        metadata_path = root / 'metadata.json'
        metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else []
        for i,row in enumerate(metadata):
            if row.get('status')!='terminal':
                turn=row['turn']
                if turn>len(saved) or saved[turn-1].user_text!=messages[turn-1]:
                    raise ValueError('failed chain preserved; no automatic retry')
                # Only a committed canonical result can resolve a prior local
                # wait observation. Never regenerate from an observation file.
                row['initial_observation']=row['status']
                row['status']='terminal'
                row['canonical_recovered_zero_model']=True
                row['reply_sha256']=sha256(saved[turn-1].assistant_text.encode()).hexdigest()
                row['reply_chars']=len(saved[turn-1].assistant_text)
                metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        for i,message in enumerate(messages):
            if i<len(saved):
                print(json.dumps(dict(turn=i+1,replayed_canonical=True), ensure_ascii=False),flush=True)
                print(saved[i].assistant_text,flush=True)
                continue
            nonce = f'whole-development-{args.slice}-{args.variant}-{args.case}-{i+1}'
            started = perf_counter()
            result = product.application.submit(SubjectCommand.contribute_utterance(
                target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
                declared_intent='ask-collaborator-status',utterance=message,language='zh',provenance='project-original'),idempotency_key=nonce)
            deadline=perf_counter()+120
            while result.status.value=='pending' and perf_counter()<deadline:
                result=product.application.wait(result.operation_ref,timeout_seconds=30)
            record=dict(turn=i+1,status=result.status.value,replayed=result.replayed,
                elapsed_seconds=round(perf_counter()-started,3),observations=list(observations))
            observations.clear()
            if result.projection and result.projection.expression_text:
                text=result.projection.expression_text
                record.update(reply_chars=len(text),reply_sha256=sha256(text.encode()).hexdigest())
            else:
                text=''
                record['failure_code']=getattr(result.projection,'failure_code',None)
            metadata.append(record)
            metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(record,ensure_ascii=False),flush=True)
            print(text,flush=True)
            if result.status.value!='terminal':
                raise SystemExit(2)
        previous=canonical_history(product)
        product.close()
        product=open_original_whole_product(config,**options,observations=observations)
        assert canonical_history(product)==previous and not observations
        print(json.dumps(dict(reopen_zero_model=True,canonical_turns=len(previous))),flush=True)
    finally:
        product.close()


if __name__=='__main__':
    main()

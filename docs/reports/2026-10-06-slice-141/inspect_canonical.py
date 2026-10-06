"""Read the completed S141 first roots through the Facade, without model calls.

Canonical text may be displayed explicitly for local assessment and is never
written by this helper. Existing first-run metadata is read without modification.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from run_s140_live_entry_acceptance import EntryObservedTransport, digest
from serve_original_whole_chat import history
from serve_shared_activity_chat import SharedActivityChatEntry as S141Entry
from dynamic_subject_agent.shared_activity_live import open_shared_activity_audit


def plain(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=asdict))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--show-text', action='store_true')
    args = parser.parse_args()
    base = args.base.resolve()
    metadata = json.loads((Path(__file__).parent / 'live-metadata.json').read_text(encoding='utf-8'))
    if not metadata.get('scheduled_first_runs_finished'):
        raise SystemExit('Existing scheduled first runs must be finished.')
    for row in metadata['branches']:
        root, audit_path = base / row['name'], base / (row['name'] + '-audit')
        if not root.is_dir() or not audit_path.is_dir():
            raise SystemExit('Exact existing root and audit required; nothing created.')
        audit = open_shared_activity_audit(audit_path)
        before = list(audit.snapshot())
        if before != row['audit']:
            raise SystemExit('Existing audit differs from the completed first-run metadata.')
        transport = EntryObservedTransport()
        entry = S141Entry(root, live=False, transport=transport, audit_path=audit_path,
                         technical_variant=row['technical_variant'])
        try:
            response = entry.product.application.query_shared_activity()
            if response.status != 'available' or response.view is None:
                raise SystemExit('Verified canonical activity unavailable.')
            turns = [asdict(turn) for turn in history(entry.product)]
            state = plain(dict(activity=response.view, history=turns))
            entry.reopen()
            reopened = entry.product.application.query_shared_activity()
            recovered = plain(dict(activity=reopened.view,
                                   history=[asdict(turn) for turn in history(entry.product)]))
            unchanged = reopened.status == 'available' and digest(state) == digest(recovered)
            if not unchanged or transport.rows or list(audit.snapshot()) != before:
                raise SystemExit('Read/reopen changed canonical state or made a model request.')
            result = response.view['visible_result']
            plan = response.view['current_plan']
            previous = None
            if result is not None and result.differences:
                # Reconstruct the prior plan only from the canonical difference
                # values already exposed by the Facade, never from model COT.
                prior = asdict(plan)
                for difference in result.differences:
                    prior[difference.field] = difference.before
                if any(prior.values()):
                    previous = prior
            final_sha = None if plan is None else digest(asdict(plan))
            activities = [stage for stage in row['stages'] if 'action' in stage]
            if activities and final_sha != activities[-1]['plan_sha256']:
                raise SystemExit('Final canonical plan differs from the original first-run metadata.')
            if previous is not None and digest(previous) != activities[0]['plan_sha256']:
                raise SystemExit('Canonical difference basis differs from the first committed plan.')
            if row['plan_reply_loop_completed']:
                if len(turns) != 1 or sha256(turns[0]['assistant_text'].encode()).hexdigest() != row['stages'][-1]['reply_sha256']:
                    raise SystemExit('Canonical reply differs from the original first-run metadata.')
            output = dict(branch=row['name'], zero_model_read_reopen=True,
                audit_matches_first_metadata=True, visible_source_is_null=response.view['visible_source'] is None,
                activity_revision=response.view['activity_revision'], history_turns=len(turns),
                previous_plan_sha256=None if previous is None else digest(previous),
                final_plan_sha256=final_sha, canonical_plan_reply_hashes_match=True)
            if args.show_text:
                output.update(canonical_state=state,
                    previous_plan_reconstructed_from_canonical_differences=previous)
            print(json.dumps(output, ensure_ascii=False, default=asdict), flush=True)
        finally:
            entry.close()


if __name__ == '__main__':
    main()

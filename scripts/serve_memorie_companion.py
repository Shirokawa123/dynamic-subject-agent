"""Explicit S160 entry: exact freeze, qualified composition and loopback only."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'app/desktop'))

from dynamic_subject_agent.local_product import LocalProductConfig, open_or_create_memorie_companion_product, open_memorie_companion_product
from dynamic_subject_agent.memorie_companion_contract import load_approval, DEFINITION, USE_REVIEW, REVIEW_SHA, VERSION, INTENT_VERSION
from dynamic_subject_agent.frozen_attempt import canonical_json
from memorie_companion import memorie_companion_server


def entry_target(review, policy):
    parent = Path(review['trial']['new_identity_root']).resolve()
    if policy == 'baseline':
        return parent, VERSION
    if policy == 'intent':
        return parent.with_name(parent.name + '-intent'), INTENT_VERSION
    raise ValueError('unknown entry policy')


def entry_descriptor(approval_path, policy, root=None):
    approval = load_approval(approval_path)
    approval_raw = approval_path.read_bytes()
    if json.loads(approval_raw) != approval:
        raise ValueError('approval receipt changed during preparation')
    review_raw = approval_path.with_name('review.json').read_bytes()
    if sha256(review_raw).hexdigest() != REVIEW_SHA:
        raise ValueError('frozen consolidated review changed')
    review = json.loads(review_raw)
    expected_root, version = entry_target(review, policy)
    if root is not None and root.resolve() != expected_root:
        raise ValueError('approved independent entry root required')
    approval_sha = sha256(approval_raw).hexdigest()
    key = sha256((expected_root.as_posix().casefold() + '\n' + version + '\n' + approval_sha).encode()).hexdigest()
    return dict(review=review, root=expected_root, contract_version=version, entry_key=key, approval_sha256=approval_sha)


class MemorieCompanionEntry:
    def __init__(self, *, root, approval_path, preparation_path, policy='baseline'):
        self.approval_path = approval_path.resolve()
        descriptor = entry_descriptor(self.approval_path, policy, root)
        review = descriptor['review']
        self.root, self.contract_version, self.entry_key = descriptor['root'], descriptor['contract_version'], descriptor['entry_key']
        raw = preparation_path.read_bytes()
        if sha256(raw).hexdigest() != review['preparation_sha256']:
            raise ValueError('frozen preparation changed')
        prepared = json.loads(raw)
        if prepared['definition_basis'] != DEFINITION or prepared['review_basis'] != USE_REVIEW:
            raise ValueError('approved preparation required')
        witness = dict(version='memorie-entry-s160-1', definition_basis=DEFINITION,
            approval_sha256=descriptor['approval_sha256'])
        if policy != 'baseline':
            witness.update(contract_version=self.contract_version, technical_parent_root=review['trial']['new_identity_root'])
        marker = self.root / 'entry.json'
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=False)
            marker.write_text(canonical_json(witness), encoding='utf-8')
        elif not marker.is_file() or json.loads(marker.read_text('utf-8')) != witness:
            raise ValueError('entry initialization witness missing or changed')
        self.config = LocalProductConfig(self.root / 'DynamicSubjectAgent/m0/experiments', self.root / 'state.json')
        self.product = open_or_create_memorie_companion_product(self.config, approval_path=self.approval_path,
            audit_path=self.root / 'provider-audit', preparation_json=prepared['definition_json'], contract_version=self.contract_version)
        self.product._memorie_entry_key = self.entry_key

    def open(self):
        product = open_memorie_companion_product(self.config, approval_path=self.approval_path,
            audit_path=self.root / 'provider-audit', contract_version=self.contract_version)
        product._memorie_entry_key = self.entry_key
        return product

    def reopen(self):
        self.product.close()
        self.product = self.open()
        return self.product


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path)
    parser.add_argument('--policy', choices=('baseline', 'intent'), default='baseline')
    parser.add_argument('--approval', type=Path, default=ROOT / '.artifacts/s160/approval.json')
    parser.add_argument('--preparation', type=Path, default=ROOT / '.artifacts/s160/preparation.json')
    parser.add_argument('--port', type=int, default=8798)
    parser.add_argument('--initialize-only', action='store_true')
    parser.add_argument('--describe-entry', action='store_true')
    args = parser.parse_args()
    if args.describe_entry:
        descriptor = entry_descriptor(args.approval.resolve(), args.policy, args.root)
        print(canonical_json({key: descriptor[key] for key in ('contract_version', 'entry_key')}))
        return
    entry = MemorieCompanionEntry(root=args.root, approval_path=args.approval, preparation_path=args.preparation, policy=args.policy)
    try:
        status = entry.product.application.reviewed_character_chat_status()
        if status.status != 'active':
            raise ValueError('qualified Memorie status unavailable')
        if args.initialize_only:
            print(canonical_json(dict(status='initialized', contract_version=entry.contract_version,
                model_attempts=status.budget_used, profile_id=entry.product.profile_id, timeline_id=entry.product.timeline_id)))
            return
        server = memorie_companion_server(entry.product, reopen=entry.reopen, port=args.port)
        print(canonical_json(dict(status='serving', host='127.0.0.1', port=server.server_port, pid=os.getpid())), flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    finally:
        entry.product.close()


if __name__ == '__main__':
    main()

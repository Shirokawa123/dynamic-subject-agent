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
from dynamic_subject_agent.memorie_companion_contract import load_approval, DEFINITION, USE_REVIEW, REVIEW_SHA
from dynamic_subject_agent.frozen_attempt import canonical_json
from memorie_companion import memorie_companion_server


class MemorieCompanionEntry:
    def __init__(self, *, root, approval_path, preparation_path):
        self.root, self.approval_path = root.resolve(), approval_path.resolve()
        approval = load_approval(self.approval_path)
        review_raw = self.approval_path.with_name('review.json').read_bytes()
        if sha256(review_raw).hexdigest() != REVIEW_SHA:
            raise ValueError('frozen consolidated review changed')
        review = json.loads(review_raw)
        if self.root != Path(review['trial']['new_identity_root']).resolve():
            raise ValueError('approved independent entry root required')
        raw = preparation_path.read_bytes()
        if sha256(raw).hexdigest() != review['preparation_sha256']:
            raise ValueError('frozen preparation changed')
        prepared = json.loads(raw)
        if prepared['definition_basis'] != DEFINITION or prepared['review_basis'] != USE_REVIEW:
            raise ValueError('approved preparation required')
        witness = dict(version='memorie-entry-s160-1', definition_basis=DEFINITION,
            approval_sha256=sha256(self.approval_path.read_bytes()).hexdigest())
        marker = self.root / 'entry.json'
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=False)
            marker.write_text(canonical_json(witness), encoding='utf-8')
        elif not marker.is_file() or json.loads(marker.read_text('utf-8')) != witness:
            raise ValueError('entry initialization witness missing or changed')
        self.config = LocalProductConfig(self.root / 'DynamicSubjectAgent/m0/experiments', self.root / 'state.json')
        self.product = open_or_create_memorie_companion_product(self.config, approval_path=self.approval_path,
            audit_path=self.root / 'provider-audit', preparation_json=prepared['definition_json'])

    def open(self):
        return open_memorie_companion_product(self.config, approval_path=self.approval_path,
            audit_path=self.root / 'provider-audit')

    def reopen(self):
        self.product.close()
        self.product = self.open()
        return self.product


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT / '.artifacts/s160/experience')
    parser.add_argument('--approval', type=Path, default=ROOT / '.artifacts/s160/approval.json')
    parser.add_argument('--preparation', type=Path, default=ROOT / '.artifacts/s160/preparation.json')
    parser.add_argument('--port', type=int, default=8798)
    parser.add_argument('--initialize-only', action='store_true')
    args = parser.parse_args()
    entry = MemorieCompanionEntry(root=args.root, approval_path=args.approval, preparation_path=args.preparation)
    try:
        status = entry.product.application.reviewed_character_chat_status()
        if status.status != 'active':
            raise ValueError('qualified Memorie status unavailable')
        if args.initialize_only:
            print(canonical_json(dict(status='initialized', model_attempts=status.budget_used)))
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

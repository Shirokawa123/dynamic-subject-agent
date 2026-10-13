"""Independent S158 LIVE entry. Initialization never sends or starts a service."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID

from serve_original_whole_chat import OriginalWholeChatEntry, DEFAULT_PACKAGE, history, ROOT
from serve_shared_activity_chat import default_entry_root as shared_root
from serve_original_context_chat import default_entry_root as context_root
from serve_living_activity_chat import default_entry_root as living_root, final_text_entry_root
from serve_living_action_contract_chat import default_entry_root as action_root
from serve_working_understanding_chat import default_entry_root as working_root
from integrated_character_chat import integrated_character_server, LIVE_APPLICATION_ID, integrated_live_application_id
from dynamic_subject_agent.local_product import (
    LocalProductConfig, open_local_product, open_integrated_character_product_live,
    validate_integrated_character_entry)
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.shared_activity import SHARED_TECHNICAL_VARIANTS
from dynamic_subject_agent.integrated_character_live import (
    ApprovedIntegratedCharacterGrant, APPROVED_INTEGRATED_REVIEW, open_integrated_character_audit)
from dynamic_subject_agent.frozen_attempt import canonical_json

ENTRY_VERSION = 'integrated-character-entry-s158-1'
APPLICATION_ID = LIVE_APPLICATION_ID


def default_entry_root(technical_variant='baseline'):
    if technical_variant not in ('baseline', 'focused', 'conversation-text', 'intent-text'):
        raise ValueError('closed integrated entry variant required')
    name = {'baseline': 'experience-live', 'focused': 'experience-focused',
        'conversation-text': 'experience-conversation', 'intent-text': 'experience-intent'}[technical_variant]
    return ROOT / '.artifacts/s158' / name / 'entry'


def default_audit_root(technical_variant='baseline'):
    return default_entry_root(technical_variant).with_name('audit')


def _overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


class IntegratedCharacterChatEntry(OriginalWholeChatEntry):
    ENTRY_VERSION = ENTRY_VERSION
    default_entry_root = staticmethod(default_entry_root)

    def __init__(self, root, *, live=True, package_path=DEFAULT_PACKAGE,
                 transport=None, audit_path=None, observations=None, clock=None, day=None,
                 technical_variant='baseline'):
        if technical_variant not in ('baseline', 'focused', 'conversation-text', 'intent-text'):
            raise ValueError('closed integrated entry variant required')
        self.technical_variant = technical_variant
        root = Path(root).resolve()
        audit = default_audit_root(technical_variant).resolve() if audit_path is None else Path(audit_path).resolve()
        protected = [OriginalWholeChatEntry.default_entry_root(), context_root(), living_root(),
            final_text_entry_root(), action_root(), working_root(),
            *(shared_root(variant) for variant in SHARED_TECHNICAL_VARIANTS),
            *(ROOT / '.artifacts' / ('s' + str(number)) for number in range(148, 158))]
        protected = [path.resolve() for path in protected]
        productions = tuple(default_entry_root(variant).resolve().parent
            for variant in ('baseline', 'focused', 'conversation-text', 'intent-text'))
        temporary = Path(tempfile.gettempdir()).resolve()
        development = (root.is_relative_to((ROOT / '.artifacts/s158').resolve())
            and not any(_overlaps(path, production) for path in (root, audit) for production in productions)
            and root.name == 'entry'
            and root.parent != (ROOT / '.artifacts/s158').resolve()
            and audit == root.parent / 'audit' and audit_path is not None)
        exact_production = (root == default_entry_root(technical_variant).resolve() and audit_path is None
            and transport is None and clock is None and day is None)
        if (type(live) is not bool or _overlaps(root, audit)
            or any(_overlaps(path, old) for path in (root, audit) for old in protected)
            or live and not (exact_production or development)
            or not live and (transport is None or audit_path is None
                or any(not path.is_relative_to(temporary) for path in (root, audit))
                or any(_overlaps(path, production) for path in (root, audit) for production in productions))):
            raise ValueError('exact independent integrated entry required')
        self.root, self.product = root, None
        self.transport, self.observations, self.clock, self.day = transport, observations, clock, day
        self.config = LocalProductConfig(root / 'DynamicSubjectAgent/m0/experiments', root / 'state.json')
        self.audit_path = audit
        self.grant = ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW, True,
            technical_variant=technical_variant)
        fresh = not root.exists()
        if fresh and (audit.exists() or audit.with_name(audit.name + '-initialized').exists()):
            raise ValueError('orphan audit preserved; cannot attach a new identity')
        content = self._review_package(Path(package_path).resolve()) if fresh else None
        try:
            if fresh:
                root.mkdir(parents=True, exist_ok=False)
                (root / 'initialized').mkdir(exist_ok=False)
                with open_local_product(self.config, cognition=DormantDeepSeekCognition()) as author:
                    frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
                        content, APPROVED_BINDING['definition_basis'], True, True))
                    if frozen.status != 'created':
                        raise ValueError('new independent integrated identity required')
                    self._fresh_identity_id = frozen.view.identity_id
                self.product = self._open()
                state = self.product.application.query_shared_activity()
                controls = self.product.application.query_living_controls()
                if (history(self.product) or state.status != 'available' or state.view['revision'] != 0
                    or state.view['current_plan'] is not None or controls.status != 'available'
                    or not controls.view['paused'] or controls.view['sharing_enabled']):
                    raise ValueError('new integrated entry must be empty, paused and unshared')
                value = dict(version=ENTRY_VERSION, binding=dict(APPROVED_BINDING),
                    profile_id=self.product.profile_id, timeline_id=self.product.timeline_id,
                    audit_path=str(self.audit_path))
                if technical_variant != 'baseline':
                    value['technical_variant'] = technical_variant
                with (root / 'current.json').open('x', encoding='utf-8') as output:
                    output.write(canonical_json(value)); output.flush(); os.fsync(output.fileno())
            value = self._read_pointer()
            self.identity = value['profile_id'], value['timeline_id']
            self._validate_current_identity()
            if self.product is None:
                self.product = self._open()
            if (self.product.profile_id, self.product.timeline_id) != self.identity:
                raise ValueError('integrated entry identity changed')
            self._history_state(self.product)
        except Exception:
            self.close()
            raise

    def _read_pointer(self):
        pointer = self.root / 'current.json'
        if (not (self.root / 'initialized').is_dir() or not self.config.state_path.is_file()
            or not pointer.is_file()):
            raise ValueError('partial integrated entry preserved; cannot recreate')
        value = json.loads(pointer.read_text(encoding='utf-8'))
        keys = {'version', 'binding', 'profile_id', 'timeline_id', 'audit_path'}
        if self.technical_variant != 'baseline':
            keys.add('technical_variant')
        if (type(value) is not dict or set(value) != keys
            or value.get('technical_variant', 'baseline') != self.technical_variant
            or value['version'] != ENTRY_VERSION or value['binding'] != APPROVED_BINDING
            or value['audit_path'] != str(self.audit_path)
            or any(type(value[key]) is not str or str(UUID(value[key])) != value[key]
                for key in ('profile_id', 'timeline_id'))):
            raise ValueError('exact integrated entry pointer required')
        return value

    def _validate_current_identity(self):
        validate_integrated_character_entry(self.config, profile_id=self.identity[0],
            timeline_id=self.identity[1], live=True, technical_variant=self.technical_variant)

    @staticmethod
    def _history_state(product):
        response = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            product.profile_id, product.timeline_id))
        if response.status.value == 'available' and response.projection is not None:
            return 'available', response.projection.turns
        if response.status.value == 'failed-closed':
            return 'failed-closed', None
        raise ValueError('integrated entry history state unverified')

    def _open(self):
        if self.clock is not None:
            self.clock.reset_session()
        return open_integrated_character_product_live(self.config,
            identity_id=self.__dict__.pop('_fresh_identity_id', self.identity[0] if hasattr(self, 'identity') else None),
            grant=self.grant, audit_path=self.audit_path, _transport=self.transport,
            observations=self.observations, clock=self.clock, day=self.day)

    def reopen(self):
        value = self._read_pointer()
        if (value['profile_id'], value['timeline_id']) != self.identity:
            raise ValueError('integrated identity witness changed')
        self._validate_current_identity()
        previous = self._history_state(self.product)
        state = self.product.application.query_shared_activity()
        self.product.close()
        self.product = None
        reopened = self._open()
        try:
            if self._history_state(reopened) != previous or reopened.application.query_shared_activity() != state:
                raise ValueError('integrated cold recovery changed canonical state')
        except Exception:
            reopened.close()
            raise
        self.product = reopened
        return reopened


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize-only', action='store_true')
    parser.add_argument('--port', type=int, default=8797)
    parser.add_argument('--technical-variant', choices=('baseline', 'focused', 'conversation-text', 'intent-text'), default='baseline')
    args = parser.parse_args()
    application_id = integrated_live_application_id(args.technical_variant)
    if args.port != 8797:
        raise SystemExit('Only the reviewed independent port is accepted.')
    if not args.initialize_only:
        try:
            with urlopen('http://127.0.0.1:8797/health', timeout=4) as response:
                existing = json.loads(response.read(1024))
        except URLError as error:
            if not isinstance(error.reason, ConnectionRefusedError):
                raise SystemExit('Port state unverified; no entry started.') from None
        except ConnectionRefusedError:
            pass
        else:
            if existing != dict(application=application_id):
                raise SystemExit('Unknown service; no entry opened.')
            return
    entry = IntegratedCharacterChatEntry(default_entry_root(args.technical_variant), technical_variant=args.technical_variant)
    try:
        if args.initialize_only:
            audit = open_integrated_character_audit(entry.audit_path)
            print(canonical_json(dict(status='initialized', application=application_id,
                audit_attempts=len(audit.snapshot()), chat_turns=len(history(entry.product)),
                activity_revision=entry.product.application.query_shared_activity().view['activity_revision'],
                root=str(entry.root))), flush=True)
            return
        server = integrated_character_server(entry.product, reopen=entry.reopen, port=8797,
            live=True, technical_variant=args.technical_variant)
        print('Integrated character chat: http://127.0.0.1:8797', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        entry.close()


if __name__ == '__main__':
    main()

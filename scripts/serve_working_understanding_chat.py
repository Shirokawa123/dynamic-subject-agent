"""Independent S147 empty working chat; opening and recovery never send."""
import argparse
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler
from uuid import UUID
import webbrowser

from serve_original_whole_chat import OriginalWholeChatEntry, DEFAULT_PACKAGE, history
from serve_original_context_chat import default_entry_root as context_entry_root
from serve_shared_activity_chat import default_entry_root as shared_entry_root
from serve_living_activity_chat import default_entry_root as living_entry_root, final_text_entry_root
from working_understanding_chat import working_understanding_server, APPLICATION_ID
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import (LocalProductConfig, open_local_product,
    open_working_understanding_product_live, validate_working_understanding_entry)
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.shared_activity import SHARED_TECHNICAL_VARIANTS
from dynamic_subject_agent.working_understanding_live import (APPROVED_WORKING_REVIEW,
    WorkingFactFaithfulDevelopmentGrant, FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION)

ENTRY_VERSION = 'working-understanding-chat-entry-s147-1'
TECHNICAL_VARIANT = 'fact-faithful'
urlopen = build_opener(ProxyHandler({})).open


def default_entry_root():
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    return local / 'DynamicSubjectAgent/working-understanding-chat/entry'


class WorkingUnderstandingChatEntry(OriginalWholeChatEntry):
    ENTRY_VERSION = ENTRY_VERSION
    default_entry_root = staticmethod(default_entry_root)

    def __init__(self, entry_root, *, live=True, package_path=DEFAULT_PACKAGE, transport=None, audit_path=None, observations=None):
        root = Path(entry_root).resolve()
        protected = (default_entry_root(), OriginalWholeChatEntry.default_entry_root(), context_entry_root(),
            living_entry_root(), final_text_entry_root(), *(shared_entry_root(variant) for variant in SHARED_TECHNICAL_VARIANTS))
        protected = tuple(path.resolve() for path in protected)
        audit = None if audit_path is None else Path(audit_path).resolve()
        if (type(live) is not bool or live and (root != default_entry_root().resolve() or transport is not None or audit_path is not None)
            or not live and (transport is None or audit is None or any(root.is_relative_to(path) or path.is_relative_to(root)
                or audit.is_relative_to(path) or path.is_relative_to(audit) for path in protected))):
            raise ValueError('exact independent working understanding entry required')
        self.root, self.product = root, None
        self.config = LocalProductConfig(root / 'DynamicSubjectAgent/m0/experiments', root / 'state.json')
        self.transport, self.observations = transport, observations
        self.audit_path = root / 'provider-audit' if live else audit
        self.grant = WorkingFactFaithfulDevelopmentGrant(APPROVED_WORKING_REVIEW, FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION)
        fresh = not root.exists()
        content = self._review_package(Path(package_path).resolve()) if fresh else None
        try:
            if fresh:
                root.mkdir(parents=True, exist_ok=False)
                (root / 'initialized').mkdir(exist_ok=False)
                with open_local_product(self.config, cognition=DormantDeepSeekCognition()) as author:
                    self._freeze_identity(author, content)
                self.product = self._open()
                working = self.product.application.query_working_understanding()
                if (history(self.product) or working.status != 'available' or working.view['revision'] != 0
                    or working.view['formation_status'] != 'initial' or working.view['understanding'] is not None
                    or working.view['current_plan'] is not None or working.view['phase'] != 'unstarted'):
                    raise ValueError('new working entry must start empty and unstarted')
                value = dict(version=self.ENTRY_VERSION, technical_variant=TECHNICAL_VARIANT, binding=dict(APPROVED_BINDING),
                    profile_id=self.product.profile_id, timeline_id=self.product.timeline_id)
                with (root / 'current.json').open('x', encoding='utf-8') as output:
                    output.write(canonical_json(value)); output.flush(); os.fsync(output.fileno())
            value = self._read_pointer()
            self.identity = value['profile_id'], value['timeline_id']
            if self.product is None:
                self._validate_current_identity()
                self.product = self._open()
            if (self.product.profile_id, self.product.timeline_id) != self.identity:
                raise ValueError('working entry identity changed')
            self._history_state(self.product)
        except Exception:
            self.close()
            raise

    def _read_pointer(self):
        pointer = self.root / 'current.json'
        if not (self.root / 'initialized').is_dir() or not pointer.is_file() or not self.config.state_path.is_file():
            raise ValueError('working entry initialization incomplete; existing data preserved')
        value = json.loads(pointer.read_text(encoding='utf-8'))
        if (type(value) is not dict or set(value) != {'version', 'technical_variant', 'binding', 'profile_id', 'timeline_id'}
            or value['version'] != self.ENTRY_VERSION or value['technical_variant'] != TECHNICAL_VARIANT
            or value['binding'] != APPROVED_BINDING or any(type(value[key]) is not str or str(UUID(value[key])) != value[key]
                for key in ('profile_id', 'timeline_id'))):
            raise ValueError('working entry pointer changed')
        return value

    def _freeze_identity(self, author, content):
        frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            content, APPROVED_BINDING['definition_basis'], True, True))
        if frozen.status != 'created':
            raise ValueError('new working identity not created')
        self._fresh_identity_id = frozen.view.identity_id

    def _open(self):
        return open_working_understanding_product_live(self.config, grant=self.grant, audit_path=self.audit_path,
            identity_id=self.__dict__.pop('_fresh_identity_id', self.identity[0] if hasattr(self, 'identity') else None),
            _transport=self.transport, observations=self.observations)

    def _validate_current_identity(self):
        validate_working_understanding_entry(self.config, profile_id=self.identity[0], timeline_id=self.identity[1],
            technical_variant=TECHNICAL_VARIANT)

    @staticmethod
    def _history_state(product):
        response = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            product.profile_id, product.timeline_id))
        if response.status.value == 'available' and response.projection is not None:
            return 'available', response.projection.turns
        if response.status.value == 'failed-closed':
            return 'failed-closed', None
        raise ValueError('working entry history status unverified')

    def reopen(self):
        value = self._read_pointer()
        if (value['profile_id'], value['timeline_id']) != self.identity:
            raise ValueError('working entry identity witness changed')
        self._validate_current_identity()
        previous = self._history_state(self.product)
        self.product.close()
        self.product = None
        reopened = self._open()
        try:
            if (reopened.profile_id, reopened.timeline_id) != self.identity or self._history_state(reopened) != previous:
                raise ValueError('working entry cold recovery changed canonical history')
        except Exception:
            reopened.close()
            raise
        self.product = reopened
        return reopened


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8794)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    absent = False
    try:
        with urlopen(f'http://127.0.0.1:{args.port}/health', timeout=6) as response:
            existing = json.loads(response.read(1024))
    except URLError as error:
        if not isinstance(error.reason, ConnectionRefusedError):
            raise SystemExit('此端口健康状态不能确认，未创建工作理解入口。') from None
        absent = True
    except ConnectionRefusedError:
        absent = True
    except Exception:
        raise SystemExit('此端口健康状态不能确认，未创建工作理解入口。') from None
    if not absent and existing == dict(application=APPLICATION_ID):
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{args.port}')
        return
    if not absent:
        raise SystemExit('此端口已有其他服务，请检查工作理解启动入口。')
    entry = None
    try:
        entry = WorkingUnderstandingChatEntry(default_entry_root())
        server = working_understanding_server(entry.product, reopen=entry.reopen, port=args.port)
        print(f'纱雾工作理解聊天已启动：http://127.0.0.1:{server.server_port}', flush=True)
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit('工作理解入口未能安全启动，现有记录保持。') from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == '__main__':
    main()

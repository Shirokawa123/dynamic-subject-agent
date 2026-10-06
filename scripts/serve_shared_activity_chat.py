"""Independent empty-history shared experience chat; opening never sends."""
import argparse
import json
import os
from pathlib import Path
from uuid import UUID
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler
import webbrowser

from serve_original_whole_chat import OriginalWholeChatEntry, DEFAULT_PACKAGE, history
from serve_original_context_chat import default_entry_root as context_entry_root
from shared_activity_chat import shared_activity_server, shared_activity_application_id, APPLICATION_ID
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_shared_activity_product_live, validate_shared_activity_entry
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.shared_activity_live import ApprovedSharedActivityGrant, APPROVED_SHARED_REVIEW
from dynamic_subject_agent.shared_activity import SHARED_TECHNICAL_VARIANTS

ENTRY_VERSION = 'shared-activity-chat-entry-s140-1'
# Fixed loopback health must not inherit a user/system HTTP proxy. This local
# opener is never installed globally and is not used by Provider delivery.
urlopen = build_opener(ProxyHandler({})).open


def default_entry_root(technical_variant='baseline'):
    if type(technical_variant) is not str or technical_variant not in SHARED_TECHNICAL_VARIANTS:
        raise ValueError('closed shared entry variant required')
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    branch = local / 'DynamicSubjectAgent/shared-activity-chat'
    return branch / 'entry' if technical_variant == 'baseline' else branch / technical_variant / 'entry'


class SharedActivityChatEntry(OriginalWholeChatEntry):
    ENTRY_VERSION = ENTRY_VERSION
    default_entry_root = staticmethod(default_entry_root)

    def __init__(self, entry_root, *, live=True, package_path=DEFAULT_PACKAGE, transport=None, audit_path=None,
                 technical_variant='baseline'):
        root = Path(entry_root).resolve()
        if (type(technical_variant) is not str or technical_variant not in SHARED_TECHNICAL_VARIANTS or type(live) is not bool
            or live and root != default_entry_root(technical_variant).resolve()
            or not live and (transport is None or audit_path is None
                or any(root.is_relative_to(path.resolve()) for path in (
                    *(default_entry_root(variant) for variant in SHARED_TECHNICAL_VARIANTS),
                    OriginalWholeChatEntry.default_entry_root(), context_entry_root())))):
            raise ValueError('exact independent shared activity entry required')
        self.root, self.technical_variant, self.product = root, technical_variant, None
        if technical_variant == 'self-directed-activity':
            self.ENTRY_VERSION = 'shared-activity-chat-entry-s141-1'
        self.config = LocalProductConfig(root / 'DynamicSubjectAgent/m0/experiments', root / 'state.json')
        self.transport = transport
        self.audit_path = root / 'provider-audit' if live else Path(audit_path).resolve()
        fresh = not root.exists()
        # Review before creating a root. A partial root is never recreated.
        content = super()._review_package(Path(package_path).resolve()) if fresh else None
        try:
            if fresh:
                root.mkdir(parents=True, exist_ok=False)
                (root / 'initialized').mkdir(exist_ok=False)
                with open_local_product(self.config, cognition=DormantDeepSeekCognition()) as author:
                    self._freeze_identity(author, content)
                self.product = self._open()
                if history(self.product):
                    raise ValueError('new shared entry must have empty history')
                value = dict(version=self.ENTRY_VERSION, binding=dict(APPROVED_BINDING), technical_variant=technical_variant,
                    profile_id=self.product.profile_id, timeline_id=self.product.timeline_id)
                with (root / 'current.json').open('x', encoding='utf-8') as output:
                    output.write(canonical_json(value)); output.flush(); os.fsync(output.fileno())
            value = self._read_pointer()
            self.identity = value['profile_id'], value['timeline_id']
            if self.product is None:
                self._validate_current_identity()
                self.product = self._open()
            if (self.product.profile_id, self.product.timeline_id) != self.identity:
                raise ValueError('shared entry identity changed')
            history(self.product)
        except Exception:
            self.close()
            raise

    def _read_pointer(self):
        pointer = self.root / 'current.json'
        if (not (self.root / 'initialized').is_dir() or not pointer.is_file() or not self.config.state_path.is_file()):
            raise ValueError('shared entry initialization incomplete; existing data preserved')
        value = json.loads(pointer.read_text(encoding='utf-8'))
        if (type(value) is not dict or set(value) != {'version', 'binding', 'profile_id', 'timeline_id', 'technical_variant'}
            or value['version'] != self.ENTRY_VERSION or value['binding'] != APPROVED_BINDING
            or value['technical_variant'] != self.technical_variant
            or any(type(value[key]) is not str or str(UUID(value[key])) != value[key] for key in ('profile_id', 'timeline_id'))):
            raise ValueError('shared entry pointer changed')
        return value

    def _freeze_identity(self, author, content):
        frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            content, APPROVED_BINDING['definition_basis'], True, True))
        if frozen.status != 'created':
            raise ValueError('new shared activity identity not created')
        self._fresh_identity_id = frozen.view.identity_id

    def _open(self):
        return open_shared_activity_product_live(self.config,
            identity_id=self.__dict__.pop('_fresh_identity_id', self.identity[0] if hasattr(self, 'identity') else None),
            grant=ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True, technical_variant=self.technical_variant),
            technical_variant=self.technical_variant, audit_path=self.audit_path, _transport=self.transport)

    def _validate_current_identity(self):
        validate_shared_activity_entry(self.config, profile_id=self.identity[0], timeline_id=self.identity[1],
            technical_variant=self.technical_variant)

    def reopen(self):
        value = self._read_pointer()
        if (value['profile_id'], value['timeline_id']) != self.identity:
            raise ValueError('shared entry identity witness changed')
        self._validate_current_identity()
        return super().reopen()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8790)
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--technical-variant', choices=SHARED_TECHNICAL_VARIANTS, default='baseline')
    args = parser.parse_args()
    application_id = shared_activity_application_id(args.technical_variant)
    absent = False
    try:
        with urlopen(f'http://127.0.0.1:{args.port}/health', timeout=6) as response:
            existing = json.loads(response.read(1024))
    except URLError as error:
        if not isinstance(error.reason, ConnectionRefusedError):
            raise SystemExit('此端口健康状态不能确认，未创建共同经历入口。') from None
        absent = True
    except ConnectionRefusedError:
        absent = True
    except Exception:
        raise SystemExit('此端口健康状态不能确认，未创建共同经历入口。') from None
    if not absent and existing == dict(application=application_id):
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{args.port}')
        return
    if not absent:
        raise SystemExit('此端口已有其他服务，请检查共同经历启动入口。')
    entry = None
    try:
        entry = SharedActivityChatEntry(default_entry_root(args.technical_variant), technical_variant=args.technical_variant)
        server = shared_activity_server(entry.product, reopen=entry.reopen, port=args.port, technical_variant=args.technical_variant)
        print(f'纱雾共同经历聊天已启动：http://127.0.0.1:{server.server_port}', flush=True)
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit('共同经历入口未能安全启动，现有记录保持。') from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == '__main__':
    main()

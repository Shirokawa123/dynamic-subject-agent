"""Independent empty-history context chat entry; opening never sends."""
import argparse
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from serve_original_whole_chat import OriginalWholeChatEntry, DEFAULT_PACKAGE
from original_whole_chat import original_whole_server
from dynamic_subject_agent.local_product import open_original_whole_product, validate_original_context_entry
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest


APPLICATION_ID = 'original-character-context-chat-s136'
ENTRY_VERSION = 'original-context-chat-entry-s136-1'


def default_entry_root():
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    return local / 'DynamicSubjectAgent/original-whole-context-chat/entry'


class OriginalContextChatEntry(OriginalWholeChatEntry):
    ENTRY_VERSION = ENTRY_VERSION
    default_entry_root = staticmethod(default_entry_root)

    def __init__(self, entry_root, *, live=True, package_path=DEFAULT_PACKAGE, transport=None, audit_path=None):
        root = Path(entry_root).resolve()
        if (type(live) is not bool or live and root != default_entry_root().resolve()
            or not live and (root.is_relative_to(default_entry_root().resolve())
                or root.is_relative_to(OriginalWholeChatEntry.default_entry_root().resolve())
                or transport is None or audit_path is None)):
            raise ValueError('exact isolated context chat entry required')
        # Only a genuinely absent root is eligible for a new freeze. A missing
        # package therefore leaves no empty partial root to block a later open.
        if not root.exists():
            self._prepared_content = super()._review_package(Path(package_path).resolve())
        try:
            super().__init__(root, live=live, package_path=package_path, transport=transport, audit_path=audit_path)
        finally:
            self.__dict__.pop('_prepared_content', None)

    def _review_package(self, package_path):
        return self.__dict__.pop('_prepared_content')

    def _freeze_identity(self, author, content):
        frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            content, APPROVED_BINDING['definition_basis'], True, True))
        if frozen.status != 'created':
            raise ValueError('new context identity not created')
        self._fresh_identity_id = frozen.view.identity_id

    def _open(self):
        return open_original_whole_product(self.config, **self.options, technical_variant='context-boundary',
            identity_id=self.__dict__.pop('_fresh_identity_id', self.identity[0] if hasattr(self, 'identity') else None),
            audit_path=self.audit_path, _transport=self.transport)

    def _validate_current_identity(self):
        validate_original_context_entry(self.config, profile_id=self.identity[0], timeline_id=self.identity[1])

    def reopen(self):
        value = self._read_pointer()
        if (value['profile_id'], value['timeline_id']) != self.identity:
            raise ValueError('context entry identity witness changed')
        self._validate_current_identity()
        return super().reopen()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8788)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    absent = False
    try:
        with urlopen(f'http://127.0.0.1:{args.port}/health', timeout=6) as response:
            existing = json.loads(response.read(1024))
    except URLError as error:
        if not isinstance(error.reason, ConnectionRefusedError):
            raise SystemExit('此端口健康状态不能确认，未创建新交流入口。') from None
        absent = True
    except ConnectionRefusedError:
        absent = True
    except Exception:
        raise SystemExit('此端口健康状态不能确认，未创建新交流入口。') from None
    if not absent and existing == dict(application=APPLICATION_ID):
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{args.port}')
        return
    if not absent:
        raise SystemExit('此端口已有其他服务，请检查新交流启动入口。')
    entry = None
    try:
        entry = OriginalContextChatEntry(default_entry_root())
        server = original_whole_server(entry.product, reopen=entry.reopen, port=args.port, application_id=APPLICATION_ID)
        print(f'纱雾新交流聊天已启动：http://127.0.0.1:{server.server_port}', flush=True)
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit('原人物新交流入口未能安全启动，现有记录保持。') from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == '__main__':
    main()

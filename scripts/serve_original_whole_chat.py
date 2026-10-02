"""New empty-history entry for the exact approved character; opening never sends."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.request import urlopen
from uuid import UUID
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app/desktop"))

from original_whole_chat import original_whole_server, APPLICATION_ID
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind, ApplicationFacade
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_original_whole_product
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest

ENTRY_VERSION = "original-whole-chat-entry-s127-1"
DEFAULT_PACKAGE = ROOT / ".local_indexes/eromanga-sensei/s102/full-definition-v2.json"


def default_entry_root():
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    return local / "DynamicSubjectAgent/original-whole-chat/entry"


def history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    if result.status.value != "available" or result.projection is None:
        raise ValueError("original whole canonical history unavailable")
    return result.projection.turns


class OriginalWholeChatEntry:
    """Own just this new root; a partial initialization is never silently recreated."""
    ENTRY_VERSION = ENTRY_VERSION
    default_entry_root = staticmethod(default_entry_root)

    def __init__(self, entry_root, *, live=True, package_path=DEFAULT_PACKAGE, transport=None, audit_path=None):
        self.root = Path(entry_root).resolve()
        if (type(live) is not bool or live and self.root != self.default_entry_root().resolve()
            or not live and (self.root.is_relative_to(self.default_entry_root().resolve())
                or transport is None or audit_path is None)):
            raise ValueError("exact isolated whole chat entry required")
        self.product = None
        self.config = LocalProductConfig(self.root / "DynamicSubjectAgent/m0/experiments", self.root / "state.json")
        self.options = {key: APPROVED_BINDING[key] for key in (
            "definition_basis", "runtime_asset_sha", "persona_digest", "review_basis")}
        self.transport, self.audit_path = transport, audit_path
        pointer = self.root / "current.json"
        fresh = not self.root.exists()
        try:
            if fresh:
                self.root.mkdir(parents=True, exist_ok=False)
                (self.root / "initialized").mkdir(exist_ok=False)
                package_path = Path(package_path).resolve()
                content = self._review_package(package_path)
                with open_local_product(self.config, cognition=DormantDeepSeekCognition()) as author:
                    self._freeze_identity(author, content)
                self.product = self._open()
                if history(self.product):
                    raise ValueError("new original whole entry must have empty history")
                value = dict(version=self.ENTRY_VERSION, binding=dict(APPROVED_BINDING),
                    profile_id=self.product.profile_id, timeline_id=self.product.timeline_id)
                with pointer.open("x", encoding="utf-8") as output:
                    output.write(canonical_json(value)); output.flush(); os.fsync(output.fileno())
            value = self._read_pointer()
            self.identity = value["profile_id"], value["timeline_id"]
            if self.product is None:
                self._validate_current_identity()
                self.product = self._open()
            if (self.product.profile_id, self.product.timeline_id) != self.identity:
                raise ValueError("whole entry identity changed")
            history(self.product)
        except Exception:
            self.close()
            raise

    def _review_package(self, package_path):
        review = ApplicationFacade.preview_original_character_whole_use_preparation(
            OriginalWholeUsePreparationRequest(package_path, APPROVED_BINDING["definition_basis"],
                APPROVED_BINDING["runtime_asset_sha"], APPROVED_BINDING["persona_digest"],
                APPROVED_BINDING["subject_id"], APPROVED_BINDING["anchor_id"]))
        if review.status != "previewed" or review.review_basis != APPROVED_BINDING["review_basis"]:
            raise ValueError("exact approved original whole package required")
        return package_path.read_text(encoding="utf-8")

    def _freeze_identity(self, author, content):
        frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            content, APPROVED_BINDING["definition_basis"], True, True))
        if frozen.status != "created":
            raise ValueError("new original whole identity not created")
        selected = author.application.select_local_identity(LocalIdentitySelectRequest(frozen.view.identity_id, True))
        if selected.status != "selected":
            raise ValueError("new original whole identity not selected")

    def _read_pointer(self):
        pointer = self.root / 'current.json'
        if (not (self.root / "initialized").is_dir() or not pointer.is_file()
            or not self.config.state_path.is_file()):
            raise ValueError("whole entry initialization incomplete; existing data preserved")
        value = json.loads(pointer.read_text(encoding="utf-8"))
        if (type(value) is not dict or set(value) != {"version", "binding", "profile_id", "timeline_id"}
            or value["version"] != self.ENTRY_VERSION or value["binding"] != APPROVED_BINDING
            or any(type(value[key]) is not str or str(UUID(value[key])) != value[key]
                for key in ("profile_id", "timeline_id"))):
            raise ValueError("whole entry pointer changed")
        return value

    def _open(self):
        return open_original_whole_product(self.config, **self.options,
            audit_path=self.audit_path, _transport=self.transport)

    def _validate_current_identity(self):
        pass

    def reopen(self):
        if self.product is None:
            raise ValueError("whole entry unavailable")
        previous = history(self.product)
        self.product.close()
        self.product = None
        reopened = self._open()
        try:
            if (reopened.profile_id, reopened.timeline_id) != self.identity or history(reopened) != previous:
                raise ValueError("whole entry cold recovery changed canonical history")
        except Exception:
            reopened.close()
            raise
        self.product = reopened
        return reopened

    def close(self):
        if self.product is not None:
            self.product.close()
            self.product = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8785)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    try:
        with urlopen(f"http://127.0.0.1:{args.port}/health", timeout=1) as response:
            existing = json.loads(response.read(1024))
    except Exception:
        existing = None
    if existing == dict(application=APPLICATION_ID):
        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{args.port}")
        return
    if existing is not None:
        raise SystemExit("此端口已有其他服务，请检查启动入口。")
    entry = None
    try:
        entry = OriginalWholeChatEntry(default_entry_root())
        server = original_whole_server(entry.product, reopen=entry.reopen, port=args.port)
        print(f"纱雾整体回复聊天已启动：http://127.0.0.1:{server.server_port}", flush=True)
        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{server.server_port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit("原人物整体回复入口未能安全启动，现有记录保持。") from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == "__main__":
    main()

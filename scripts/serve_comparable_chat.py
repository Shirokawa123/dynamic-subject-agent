"""One presentation, four independent Facade-backed conversations."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import urlopen
import webbrowser

from serve_s119_whole_chat import FreeInputChatEntry, SCENARIOS_PATH
from whole_reply_chat import chat_server
from dynamic_subject_agent.first_life_free_input_trial import open_free_input_reply_trial
from dynamic_subject_agent.reply_protocol_trial import fixed_development_root
from dynamic_subject_agent.frozen_attempt import canonical_json


APPLICATION_ID = "whole-reply-comparable-chat-s125"
VARIANTS = {"current-topic": "原话题版", "conversation": "来源核对候选"}


class VersionedEntry(FreeInputChatEntry):
    def __init__(self, root, *, variant, live, transport=None):
        if type(variant) is not str or variant not in VARIANTS:
            raise ValueError("known comparison version required")
        self.variant = variant
        self.entry_version = "s125-comparable-entry-" + variant
        super().__init__(root, live=live, transport=transport)

    def validate_entry_trial(self):
        if self.trial.read().get("expression_variant", "baseline") != self.variant:
            raise ValueError("comparison pointer does not match its displayed variant")

    def entry_path(self):
        return fixed_development_root() / "comparable-chat-entry" / self.variant

    def open_trial(self, root, *, live):
        return open_free_input_reply_trial(root, SCENARIOS_PATH, live=live, confirmed=True,
            expression_variant=self.variant)


class ComparableChat:
    def __init__(self, root, *, live, transport=None):
        self.entries, self.products, self.choices, self.owners = {}, {}, {}, {}
        try:
            for variant, title in VARIANTS.items():
                entry = VersionedEntry(root / variant, variant=variant, live=live, transport=transport)
                self.entries[variant] = entry
                if len({item.trial.root.resolve() for item in self.entries.values()}) != len(self.entries):
                    raise ValueError("comparison versions require independent canonical roots")
                for scene, product in entry.products.items():
                    key = variant + ":" + scene
                    self.owners[key] = (variant, scene)
                    self.products[key] = product
                    self.choices[key] = dict(entry.choices[scene], title=title + " · " + entry.choices[scene]["title"])
            self.scope_key = sha256(canonical_json({key:value.trial.manifest_digest
                for key,value in self.entries.items()}).encode()).hexdigest()
        except Exception:
            self.close()
            raise

    def reopen(self, key):
        if key not in self.owners:
            raise ValueError("known comparison conversation required")
        variant, scene = self.owners[key]
        product = self.entries[variant].reopen(scene)
        self.products[key] = product
        return product

    def close(self):
        for entry in self.entries.values():
            entry.close()
        self.products.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8784)
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
        entry = ComparableChat(fixed_development_root() / "comparable-chat-entry", live=True)
        server = chat_server(entry.products, choices=entry.choices, scope_key=entry.scope_key,
            reopen=entry.reopen, port=args.port, application_id=APPLICATION_ID, page_name="comparable_chat.html")
        print(f"小林对照聊天已启动：http://127.0.0.1:{server.server_port}", flush=True)
        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{server.server_port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit("对照入口未能安全启动，现有记录保持。") from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == "__main__":
    main()

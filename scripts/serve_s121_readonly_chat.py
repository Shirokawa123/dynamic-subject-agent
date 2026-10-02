"""An isolated current-topic trial using the corrected readonly question boundary."""
import argparse
import json
import webbrowser
from urllib.request import urlopen

from serve_s120_topic_chat import TopicChatEntry
from whole_reply_chat import chat_server
from dynamic_subject_agent.reply_protocol_trial import fixed_development_root


APPLICATION_ID = "whole-reply-readonly-plan-chat-s121"


class ReadonlyChatEntry(TopicChatEntry):
    entry_version = "s121-readonly-plan-chat-entry-1"

    @staticmethod
    def entry_path():
        return fixed_development_root() / "whole-reply-readonly-entry"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8783)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    try:
        with urlopen(f"http://127.0.0.1:{args.port}/health", timeout=1) as response:
            existing = json.loads(response.read(1024))
    except Exception:
        existing = None
    if existing == dict(application=APPLICATION_ID):
        print(f"小林聊天已在运行：http://127.0.0.1:{args.port}", flush=True)
        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{args.port}")
        return
    # Never open this canonical store while another service occupies its port.
    if existing is not None:
        raise SystemExit("此端口已有其他服务，请检查启动入口。")
    entry = None
    try:
        entry = ReadonlyChatEntry(ReadonlyChatEntry.entry_path(), live=True)
        server = chat_server(entry.products, choices=entry.choices, scope_key=entry.trial.manifest_digest,
            reopen=entry.reopen, port=args.port, application_id=APPLICATION_ID, page_name="whole_reply_topic_chat.html")
        print(f"小林聊天已启动：http://127.0.0.1:{server.server_port}", flush=True)
        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{server.server_port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit("聊天未能安全启动，现有记录保持。") from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == "__main__":
    main()

"""Resume the separately approved free-input purpose on its own local service."""
import argparse
import json
import webbrowser
from urllib.request import urlopen

from serve_s118_whole_reply import TrialEntry, SCENARIOS_PATH
from whole_reply_chat import chat_server, APPLICATION_ID
from dynamic_subject_agent.reply_protocol_trial import fixed_development_root
from dynamic_subject_agent.first_life_free_input_trial import (FreeInputReplyTrial,
    fixed_free_input_runs_root, open_free_input_reply_trial)
from dynamic_subject_agent.local_product import open_first_life_free_input_trial


class FreeInputChatEntry(TrialEntry):
    entry_version = "s119-whole-free-input-entry-1"
    trial_type = FreeInputReplyTrial
    open_product = staticmethod(open_first_life_free_input_trial)
    runs_root = staticmethod(fixed_free_input_runs_root)

    @staticmethod
    def entry_path():
        return fixed_development_root()/"whole-reply-free-input-entry"

    @staticmethod
    def open_trial(root, *, live):
        return open_free_input_reply_trial(root, SCENARIOS_PATH, live=live, confirmed=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=8781)
    parser.add_argument("--open-browser",action="store_true")
    args=parser.parse_args()
    if args.port:
        try:
            with urlopen(f"http://127.0.0.1:{args.port}/health",timeout=1) as response:
                existing=json.loads(response.read(1024))
        except Exception:
            existing=None
        if existing==dict(application=APPLICATION_ID):
            print(f"小林自由聊天已在运行：http://127.0.0.1:{args.port}",flush=True)
            if args.open_browser:webbrowser.open(f"http://127.0.0.1:{args.port}")
            return
    entry=None
    try:
        entry=FreeInputChatEntry(FreeInputChatEntry.entry_path(),live=True)
        server=chat_server(entry.products,choices=entry.choices,scope_key=entry.trial.manifest_digest,
            reopen=entry.reopen,port=args.port)
        print(f"小林自由聊天已启动：http://127.0.0.1:{server.server_port}",flush=True)
        if args.open_browser:webbrowser.open(f"http://127.0.0.1:{server.server_port}")
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
    except Exception:
        raise SystemExit("自由聊天未能安全启动；现有记录保留，请检查授权或记录完整性。") from None
    finally:
        if entry is not None:entry.close()


if __name__=="__main__":main()

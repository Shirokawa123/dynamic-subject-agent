"""An independent same-purpose expression trial, leaving 8781 unchanged."""
import argparse
import json
import webbrowser
from urllib.request import urlopen

from serve_s119_whole_chat import FreeInputChatEntry,SCENARIOS_PATH
from whole_reply_chat import chat_server
from dynamic_subject_agent.reply_protocol_trial import fixed_development_root
from dynamic_subject_agent.first_life_free_input_trial import open_free_input_reply_trial


APPLICATION_ID="whole-reply-current-topic-chat-s120"


class TopicChatEntry(FreeInputChatEntry):
    entry_version="s120-topic-chat-entry-1"

    @staticmethod
    def entry_path():
        return fixed_development_root()/"whole-reply-topic-entry"

    @staticmethod
    def open_trial(root,*,live):
        return open_free_input_reply_trial(root,SCENARIOS_PATH,live=live,confirmed=True,expression_variant="current-topic")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=8782)
    parser.add_argument("--open-browser",action="store_true")
    args=parser.parse_args()
    if args.port:
        try:
            with urlopen(f"http://127.0.0.1:{args.port}/health",timeout=1) as response:existing=json.loads(response.read(1024))
        except Exception:existing=None
        if existing==dict(application=APPLICATION_ID):
            print(f"小林表达试用已在运行：http://127.0.0.1:{args.port}",flush=True)
            if args.open_browser:webbrowser.open(f"http://127.0.0.1:{args.port}")
            return
    entry=None
    try:
        entry=TopicChatEntry(TopicChatEntry.entry_path(),live=True)
        server=chat_server(entry.products,choices=entry.choices,scope_key=entry.trial.manifest_digest,
            reopen=entry.reopen,port=args.port,application_id=APPLICATION_ID,page_name="whole_reply_topic_chat.html")
        print(f"小林表达试用已启动：http://127.0.0.1:{server.server_port}",flush=True)
        if args.open_browser:webbrowser.open(f"http://127.0.0.1:{server.server_port}")
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
    except Exception:
        raise SystemExit("表达试用未能安全启动，现有记录保持。") from None
    finally:
        if entry is not None:entry.close()


if __name__=="__main__":main()

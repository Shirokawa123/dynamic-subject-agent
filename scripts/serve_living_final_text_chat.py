"""Independent S144 final-text living entry, with the existing approved data use."""
import argparse
import json
from urllib.error import URLError
import webbrowser

from serve_living_activity_chat import LivingActivityChatEntry, final_text_entry_root, urlopen
from living_activity_chat import living_activity_server, FINAL_TEXT_APPLICATION_ID

ENTRY_VERSION = 'living-final-text-chat-entry-s144-1'
APPLICATION_ID = FINAL_TEXT_APPLICATION_ID


class FinalTextLivingActivityChatEntry(LivingActivityChatEntry):
    ENTRY_VERSION = ENTRY_VERSION
    TECHNICAL_VARIANT = 'final-text'
    default_entry_root = staticmethod(final_text_entry_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8793)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    absent = False
    try:
        with urlopen(f'http://127.0.0.1:{args.port}/health', timeout=6) as response:
            existing = json.loads(response.read(1024))
    except URLError as error:
        if not isinstance(error.reason, ConnectionRefusedError):
            raise SystemExit('此端口健康状态不能确认，未创建正文生活聊天入口。') from None
        absent = True
    except ConnectionRefusedError:
        absent = True
    except Exception:
        raise SystemExit('此端口健康状态不能确认，未创建正文生活聊天入口。') from None
    if not absent and existing == dict(application=APPLICATION_ID):
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{args.port}')
        return
    if not absent:
        raise SystemExit('此端口已有其他服务，请检查正文生活聊天启动入口。')
    entry = None
    try:
        entry = FinalTextLivingActivityChatEntry(final_text_entry_root())
        server = living_activity_server(entry.product, reopen=entry.reopen, port=args.port, application_id=APPLICATION_ID)
        print(f'纱雾正文生活聊天已启动：http://127.0.0.1:{server.server_port}', flush=True)
        if args.open_browser:
            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit('正文生活聊天入口未能安全启动，现有记录保持。') from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == '__main__':
    main()

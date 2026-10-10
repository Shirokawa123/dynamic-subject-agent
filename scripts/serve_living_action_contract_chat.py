"""S149 independent empty entry, inheriting only the approved living data use."""
import os
import argparse
import json
from pathlib import Path
from urllib.error import URLError
import webbrowser

from serve_living_activity_chat import LivingActivityChatEntry,urlopen
from living_activity_chat import living_activity_server
from dynamic_subject_agent.local_product import open_living_activity_product_live
from dynamic_subject_agent.living_activity_live import APPROVED_LIVING_REVIEW
from dynamic_subject_agent.living_action_contract import LivingActionContractDevelopmentGrant,ACTION_DEVELOPMENT_AUTHORIZATION

ENTRY_VERSION='living-action-contract-chat-entry-s149-1'
APPLICATION_ID='living-action-contract-chat-s149'


def default_entry_root():
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')/'DynamicSubjectAgent/living-action-contract-chat/entry'


class ActionContractLivingChatEntry(LivingActivityChatEntry):
    ENTRY_VERSION=ENTRY_VERSION
    TECHNICAL_VARIANT='action-contract'
    default_entry_root=staticmethod(default_entry_root)

    def _open(self):
        if self.clock is not None: self.clock.reset_session()
        return open_living_activity_product_live(self.config,
            identity_id=self.__dict__.pop('_fresh_identity_id',self.identity[0] if hasattr(self,'identity') else None),
            grant=LivingActionContractDevelopmentGrant(APPROVED_LIVING_REVIEW,ACTION_DEVELOPMENT_AUTHORIZATION),
            audit_path=self.audit_path,_transport=self.transport,clock=self.clock,day=self.day,observations=self.observations)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8795)
    parser.add_argument('--open-browser',action='store_true');args=parser.parse_args()
    absent=False
    try:
        with urlopen(f'http://127.0.0.1:{args.port}/health',timeout=6) as response:
            existing=json.loads(response.read(1024))
    except URLError as error:
        if not isinstance(error.reason,ConnectionRefusedError):raise SystemExit('此入口健康状态不能确认，未启动新应用。') from None
        absent=True
    except ConnectionRefusedError:absent=True
    if not absent:
        if existing!=dict(application=APPLICATION_ID):raise SystemExit('端口已有其他服务，未创建或覆盖入口。')
        if args.open_browser:webbrowser.open(f'http://127.0.0.1:{args.port}')
        return
    entry=None
    try:
        entry=ActionContractLivingChatEntry(default_entry_root())
        server=living_activity_server(entry.product,reopen=entry.reopen,port=args.port,application_id=APPLICATION_ID)
        print(f'新的返工接续聊天已启动：http://127.0.0.1:{server.server_port}',flush=True)
        if args.open_browser:webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
    finally:
        if entry is not None:entry.close()


if __name__=='__main__':main()

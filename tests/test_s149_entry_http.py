import importlib
from contextlib import closing
from threading import Thread
from types import SimpleNamespace
from urllib.request import urlopen
import json

from test_living_activity_chat_entry import living_entry_setup,approved,personality_fixture,model_fixture,entry_setup
from test_living_action_contract import ActionTransport


def test_new_empty_entry_actual_hidden_http_zero_model_and_same_identity_reopen(living_entry_setup):
    _,desktop,root,options,_,_,_=living_entry_setup
    script=importlib.import_module('serve_living_action_contract_chat')
    transport=ActionTransport();options=dict(options,transport=transport)
    entry=script.ActionContractLivingChatEntry(root.with_name('action-contract-entry'),**options)
    identity=entry.identity
    server=desktop.living_activity_server(entry.product,reopen=entry.reopen,application_id=script.APPLICATION_ID)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        origin=f'http://127.0.0.1:{server.server_port}'
        with urlopen(origin+'/health',timeout=3) as r:assert json.loads(r.read())==dict(application=script.APPLICATION_ID)
        with urlopen(origin+'/status',timeout=3) as r:
            value=json.loads(r.read())
            assert value['chat_messages']==[] and value['living_controls']['view']['paused']
            assert not value['living_controls']['view']['sharing_enabled']
        with urlopen(origin+'/',timeout=3) as r:assert b'TOKEN=' in r.read()
        assert not transport.calls
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
    try:
        entry.reopen();assert entry.identity==identity and not transport.calls
    finally:entry.close()

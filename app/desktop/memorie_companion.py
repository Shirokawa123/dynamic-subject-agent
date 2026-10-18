"""Native game client Adapter. Product and model authority remain in the Facade."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets

from original_whole_chat import OriginalWholeChatAdapter
from dynamic_subject_agent.memorie_companion_contract import contract, SCOPE, USE_REVIEW


APPLICATION_ID = 'memorie-companion-s160'


class MemorieCompanionAdapter(OriginalWholeChatAdapter):
    def __init__(self, product, *, reopen):
        witness = getattr(product, '_memorie_composition_witness', None)
        if witness != contract(witness or {}, SCOPE, USE_REVIEW):
            raise ValueError('qualified Memorie production composition required')
        super().__init__(product, reopen=reopen)

    def _scoped_message(self, payload):
        if type(payload) is not dict or set(payload) != {'text', 'request_id', 'scope_key'}:
            raise ValueError('invalid-request')
        message = {key: payload[key] for key in ('text', 'request_id')}
        self._validate_message(message)
        scope = sha256((self.product.profile_id + ':' + self.product.timeline_id).encode()).hexdigest()
        return message, type(payload['scope_key']) is str and payload['scope_key'] == scope

    @staticmethod
    def _wrong_scope():
        return dict(ok=False, settled=False, pending=None, message='当前人物已变化，原消息与草稿保留。',
            state=dict(ready=False, subject_name='梅莫莉', scope_key='', turns=[],
                message='请重新连接后核对当前人物。'))

    def snapshot(self):
        with self.lock:
            status = self.product.application.reviewed_character_chat_status()
            if status.status != 'active' or status.subject_name != '梅莫莉':
                return dict(ready=False, subject_name='梅莫莉', scope_key='', turns=[],
                    message='自由交流尚未启用，输入的文字会保留。')
            value = super().snapshot()
            if value['history']['status'] != 'available':
                return dict(ready=False, subject_name='梅莫莉', scope_key='', turns=[],
                    message='暂时无法核对交流记录，输入的文字会保留。')
            return dict(ready=True, subject_name='梅莫莉', scope_key=value['scope_key'],
                turns=value['history']['turns'], message='')

    def send(self, payload):
        with self.lock:
            message, correct_scope = self._scoped_message(payload)
            if not correct_scope:
                return self._wrong_scope()
            if not self.snapshot()['ready']:
                return dict(ok=False, settled=False, pending=None, message='自由交流尚未启用。', state=self.snapshot())
            return super().send(message)

    def lookup(self, payload):
        with self.lock:
            message, correct_scope = self._scoped_message(payload)
            if not correct_scope:
                return self._wrong_scope()
            if not self.snapshot()['ready']:
                return dict(ok=False, settled=False, pending=None, message='暂时无法核对原请求。', state=self.snapshot())
            return super().lookup(message)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate field')
        value[key] = item
    return value


def memorie_companion_server(product, *, reopen, port=0):
    adapter = MemorieCompanionAdapter(product, reopen=reopen)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def reject(self):
            # Drain a bounded native request before closing so Windows clients
            # receive the HTTP rejection rather than a reset with unread input.
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if 0 < length <= 16384:
                    self.connection.settimeout(1)
                    self.rfile.read(length)
            except (OSError, ValueError):
                pass
            return self.respond(403, dict(error='request-rejected'))

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, dict(error='request-rejected'))
            if self.path == '/health':
                return self.respond(200, dict(application=APPLICATION_ID, protocol=1))
            if self.path == '/session':
                return self.respond(200, dict(application=APPLICATION_ID, protocol=1, token=token))
            if self.path == '/status':
                try:
                    return self.respond(200, adapter.snapshot())
                except Exception:
                    return self.respond(503, dict(error='chat-unavailable'))
            return self.respond(404, dict(error='not-found'))

        def do_POST(self):
            routes = {'/send': adapter.send, '/result': adapter.lookup}
            if (not self.valid_host() or self.path not in routes
                or self.headers.get('X-Chat-Token') != token
                or self.headers.get('Content-Type') != 'application/json'
                or self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}')):
                return self.reject()
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 16384:
                    return self.respond(413, dict(error='invalid-request'))
                value = json.loads(self.rfile.read(length).decode('utf-8'), object_pairs_hook=_unique_object)
                result = routes[self.path](value)
            except ValueError:
                return self.respond(400, dict(error='invalid-request'))
            except Exception:
                return self.respond(503, dict(error='chat-unavailable'))
            return self.respond(200, result)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)

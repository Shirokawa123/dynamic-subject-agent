"""Private loopback chat Adapter; business authority stays in ApplicationFacade."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
from threading import RLock
from uuid import UUID

from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.local_product import LocalProductConfig
from dynamic_subject_agent.timeline import SubjectCommand

DEFINITION_BASIS = '8b492ec9f7a047a4b0f4ae3fdb4eaa4326348f1607d89bd0abe96ae56924769c'
SCOPE_DIGEST = '4a843dc82b8ebd82d3fd058c6b91811fdf2eecfcfb6064a52b1f556cde9b40ce'
REVIEW_REQUEST_BASIS = '4fa287fc4f12b5c4fb2608d0e58fa914d486013b2eaccfb8daed3279f14f631e'
APPLICATION_ID = 'reviewed-character-chat-v1'


def default_config():
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    root = local / 'DynamicSubjectAgent/character-chat-v1'
    return LocalProductConfig(root / 'DynamicSubjectAgent/m0/experiments', root / 'state.json', 'off')


class CharacterChatAdapter:
    def __init__(self, product):
        self.product = product
        self.lock = RLock()

    def snapshot(self):
        with self.lock:
            state = self.product.application.reviewed_character_chat_status()
            history = self.product.application.query(ApplicationQuery(
                kind=ApplicationQueryKind.CONVERSATION_HISTORY,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id))
            turns = []
            if history.status.value == 'available' and history.projection is not None:
                turns = [dict(user_text=turn.user_text, assistant_text=turn.assistant_text)
                         for turn in history.projection.turns]
            return dict(character=asdict(state), history=dict(status=history.status.value, turns=turns))

    def set_history(self, payload):
        if type(payload) is not dict or set(payload) != {'enabled'} or type(payload['enabled']) is not bool:
            raise ValueError('invalid-request')
        with self.lock:
            result = self.product.application.set_reviewed_character_history(payload['enabled'])
            return dict(ok=result.status == 'active' and result.history_enabled == payload['enabled'], state=self.snapshot())

    def send(self, payload):
        if (type(payload) is not dict or set(payload) != {'text', 'request_id'}
                or not isinstance(payload['text'], str) or not payload['text'].strip()
                or len(payload['text']) > 1000 or '\x00' in payload['text']
                or not isinstance(payload['request_id'], str)
                or str(UUID(payload['request_id'])) != payload['request_id']):
            raise ValueError('invalid-request')
        with self.lock:
            command = SubjectCommand.contribute_utterance(
                target_profile_id=self.product.profile_id, target_timeline_id=self.product.timeline_id,
                declared_intent='ask-collaborator-status', utterance=payload['text'], language='zh',
                provenance='project-original')
            result = self.product.application.submit(command, idempotency_key='character-chat-' + payload['request_id'])
            for _ in range(3):
                if result.status.value != 'pending' or result.operation_ref is None:
                    break
                result = self.product.application.wait(result.operation_ref, timeout_seconds=30)
            projection = result.projection
            ok = (result.status.value == 'terminal' and projection is not None
                  and not projection.failure_code and bool(projection.expression_text))
            message = '' if ok else ('这一轮仍在处理中，请稍后刷新查看记录，避免重复发送。'
                if result.status.value == 'pending' else '这一轮没有完成，消息草稿已保留。请检查模型额度或连接后再试。')
            return dict(ok=ok, message=message, state=self.snapshot())


def create_server(product, *, port=0):
    adapter = CharacterChatAdapter(product)
    token = secrets.token_urlsafe(32)
    page = (Path(__file__).parent / 'static/character_chat.html').read_text(encoding='utf-8').replace('__SESSION_TOKEN__', token)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, value, content_type='application/json; charset=utf-8'):
            body = (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, dict(error='request-rejected'))
            if self.path == '/':
                return self.respond(200, page, 'text/html; charset=utf-8')
            if self.path == '/health':
                return self.respond(200, dict(application=APPLICATION_ID))
            if self.path == '/status':
                try:
                    return self.respond(200, adapter.snapshot())
                except Exception:
                    return self.respond(503, dict(error='chat-unavailable'))
            self.respond(404, dict(error='not-found'))

        def do_POST(self):
            if (not self.valid_host() or self.path not in ('/send', '/history')
                    or self.headers.get('X-Chat-Token') != token
                    or self.headers.get('Content-Type') != 'application/json'
                    or self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}')):
                return self.respond(403, dict(error='request-rejected'))
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('invalid-request')
                payload = json.loads(self.rfile.read(length))
                result = adapter.send(payload) if self.path == '/send' else adapter.set_history(payload)
            except (ValueError, TypeError, UnicodeError):
                return self.respond(400, dict(error='invalid-request'))
            except Exception:
                return self.respond(503, dict(error='chat-unavailable'))
            self.respond(200, result)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    if args.port:
        from urllib.request import urlopen
        try:
            with urlopen(f'http://127.0.0.1:{args.port}/health', timeout=1) as response:
                existing = json.loads(response.read(1024))
        except Exception:
            existing = None
        if existing == dict(application=APPLICATION_ID):
            url = f'http://127.0.0.1:{args.port}'
            print('人物聊天已在运行：' + url, flush=True)
            if args.open_browser:
                import webbrowser
                webbrowser.open(url)
            return
    from dynamic_subject_agent.local_product import open_reviewed_character_chat_product
    config = default_config()
    if not config.state_path.is_file():
        raise SystemExit('尚未创建获准人物，请先完成角色创建。')
    try:
        product = open_reviewed_character_chat_product(config, definition_basis=DEFINITION_BASIS,
            scope_digest=SCOPE_DIGEST, review_request_basis=REVIEW_REQUEST_BASIS,
            budget_total=200, initial_budget_used=61)
    except Exception:
        raise SystemExit('人物聊天未能安全启动。身份或调用配置需要检查，现有记录未删除。') from None
    try:
        server = create_server(product, port=args.port)
        url = f'http://127.0.0.1:{server.server_port}'
        print('人物聊天已启动：' + url, flush=True)
        if args.open_browser:
            import webbrowser
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        product.close()


if __name__ == '__main__':
    main()

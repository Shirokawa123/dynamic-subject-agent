"""Loopback Adapter for the separately approved first-life branch."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from character_chat import CharacterChatAdapter, create_server, DEFINITION_BASIS
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.first_life import CONTEXT_RESET_CONFIRMATION, FirstLifeContextResetRequest
from dynamic_subject_agent.local_product import LocalProductConfig
from dynamic_subject_agent.timeline import SubjectCommand

APPLICATION_ID = 'reviewed-character-first-life-v1'
REASONS = {'emphasize-subject':'突出主体', 'balance-space':'调整留白', 'improve-readability':'保持可辨识',
    'preserve-current':'保留当前', 'try-alternative':'尝试替代方案', 'defer-comparison':'稍后比较'}


def default_config():
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    root = local / 'DynamicSubjectAgent/character-life-v1'
    return LocalProductConfig(root / 'DynamicSubjectAgent/m0/experiments', root / 'state.json', 'off')


class FirstLifeAdapter(CharacterChatAdapter):
    def __init__(self, product):
        super().__init__(product)
        self.pending = {}
        self.inflight = set()
        self._last_snapshot = None
        self.snapshot()

    def snapshot(self):
        with self.lock:
            if self.inflight and self._last_snapshot is not None:
                return dict(self._last_snapshot, presentation_pending=True,
                    pending_handle=next(iter(self.inflight)))
            c = self.product.application.first_life_status()
            q = self.product.application.query_first_life()
            history = self.product.application.query(ApplicationQuery(kind=ApplicationQueryKind.CONVERSATION_HISTORY,
                target_profile_id=self.product.profile_id, target_timeline_id=self.product.timeline_id))
            messages = []
            if history.status.value == 'available' and history.projection is not None:
                messages = [dict(kind='dialogue', head_sequence=t.head_sequence,
                    user_text=t.user_text, assistant_text=t.assistant_text) for t in history.projection.turns]
            data = asdict(q)
            if q.status == 'available':
                messages.extend(dict(kind='share', head_sequence=s['head_sequence'], assistant_text=s['text'])
                    for s in data['shares'])
            messages.sort(key=lambda m: m['head_sequence'])
            project = data.get('project')
            current = None if not project or not project.get('current_plan') else dict(revision=project['current_revision'], **project['current_plan'])
            versions = [dict(revision=v['revision'], reason=REASONS.get(v['reason_code'], '创作选择'), **v['plan'])
                for v in data.get('versions', [])]
            events = [dict(summary=e['summary'], simulated=e.get('simulated', False)) for e in data.get('events', [])]
            result = dict(character=asdict(c), history=dict(status=history.status.value), life_status=q.status,
                project=current, versions=versions, events=events, messages=messages,
                context_reset_confirmation=CONTEXT_RESET_CONFIRMATION,
                presentation_pending=False, pending_handle=None)
            if c.status in ('active', 'paused', 'needs-attention') and history.status.value == q.status == 'available':
                self._last_snapshot = result
            return result

    def set_history(self, payload):
        if type(payload) is not dict or set(payload) != {'enabled'} or type(payload['enabled']) is not bool:
            raise ValueError('invalid-request')
        with self.lock:
            result = self.product.application.set_reviewed_character_history(payload['enabled'])
            ok = result.status == 'active' and result.history_enabled == payload['enabled']
            if ok and self._last_snapshot is not None:
                self._last_snapshot = dict(self._last_snapshot,
                    character=dict(self._last_snapshot['character'], history_enabled=result.history_enabled))
            return dict(ok=ok, state=self.snapshot())

    @staticmethod
    def _request_id(payload):
        request_id = payload.get('request_id')
        if not isinstance(request_id, str) or str(UUID(request_id)) != request_id:
            raise ValueError('invalid-request')
        return request_id

    def _result(self, response, *, handle=None):
        pending = response.status.value == 'pending' and response.operation_ref is not None
        if pending:
            if handle is None:
                handle = str(uuid4())
                self.pending[handle] = response.operation_ref
            self.inflight.add(handle)
            return dict(ok=True, pending=handle, state=self.snapshot())
        if handle is not None:
            self.inflight.discard(handle)
        projection = response.projection
        ok = response.status.value == 'terminal' and (projection is None or not projection.failure_code)
        code = (projection.failure_code if projection is not None else None) or (
            response.problem.code if response.problem is not None else None)
        messages = {
            'first-life-history-unverified': '聊天上下文的使用范围或资料完整性尚未确认，已停止本轮生成。可查看“从新消息继续”的说明，确认后尝试恢复；若记录仍无法安全核验，会继续停止。草稿保留。',
            'first-life-share-history-unverified': '主动分享的历史使用范围或资料完整性尚未确认。可查看“从新消息继续”的说明，确认新的交流范围；若记录仍无法安全核验，会继续停止。',
            'first-life-history-changed': '聊天上下文设置已变化，本轮未继续生成。请确认当前设置后再发送，草稿保留。',
            'confirmed-chat-context-reset-required': '尚未确认新的聊天上下文范围。请先阅读“从新消息继续”的说明，再明确确认。',
            'first-life-basis-unverified': '当前记录的完整性尚未确认，暂时无法恢复。现有记录和草稿保留。',
        }
        return dict(ok=ok, pending=None, message='' if ok else messages.get(code, '本次处理未完成，现有记录和草稿保留。'),
            state=self.snapshot())

    def poll(self, payload):
        if type(payload) is not dict or set(payload) != {'handle'} or not isinstance(payload['handle'], str):
            raise ValueError('invalid-request')
        with self.lock:
            ref = self.pending.get(payload['handle'])
            if ref is None: raise ValueError('unknown-operation')
            response = self.product.application.wait(ref, timeout_seconds=0)
            return self._result(response, handle=payload['handle'])

    def send(self, payload):
        if (type(payload) is not dict or set(payload) != {'text','request_id'} or not isinstance(payload['text'], str)
                or not payload['text'].strip() or len(payload['text']) > 1000 or '\x00' in payload['text']):
            raise ValueError('invalid-request')
        request_id = self._request_id(payload)
        with self.lock:
            command = SubjectCommand.contribute_utterance(target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id, declared_intent='ask-collaborator-status',
                utterance=payload['text'], language='zh', provenance='project-original')
            return self._result(self.product.application.submit(command, idempotency_key='first-life-chat-'+request_id))

    def controls(self, payload):
        from dynamic_subject_agent.first_life import FirstLifeControlRequest
        if (type(payload) is not dict or not set(payload) <= {'request_id','paused','sharing_enabled'}
                or not set(payload) & {'paused','sharing_enabled'}
                or any(type(v) is not bool for k,v in payload.items() if k != 'request_id')):
            raise ValueError('invalid-request')
        self._request_id(payload)
        with self.lock:
            return self._result(self.product.application.set_first_life_controls(FirstLifeControlRequest(**payload)))

    def reset_context(self, payload):
        if (type(payload) is not dict or set(payload) != {'request_id', 'confirmed'}
                or type(payload['confirmed']) is not bool):
            raise ValueError('invalid-request')
        self._request_id(payload)
        with self.lock:
            return self._result(self.product.application.reset_first_life_context(FirstLifeContextResetRequest(**payload)))

    def heartbeat(self, payload):
        from dynamic_subject_agent.first_life import FirstLifeHeartbeatRequest
        if type(payload) is not dict or set(payload) != {'session_id','request_id'}: raise ValueError('invalid-request')
        self._request_id(payload)
        if not isinstance(payload['session_id'], str) or str(UUID(payload['session_id'])) != payload['session_id']:
            raise ValueError('invalid-request')
        with self.lock:
            return self._result(self.product.application.heartbeat_first_life(FirstLifeHeartbeatRequest(**payload)))

    def simulate(self, payload):
        from dynamic_subject_agent.first_life import FirstLifeSimulationRequest
        if type(payload) is not dict or set(payload) != {'request_id'}: raise ValueError('invalid-request')
        self._request_id(payload)
        with self.lock:
            return self._result(self.product.application.simulate_first_life_step(FirstLifeSimulationRequest(**payload)))


def life_server(product, *, port=0):
    adapter = FirstLifeAdapter(product)
    return create_server(product, port=port, adapter=adapter, page_name='first_life.html', application_id=APPLICATION_ID,
        post_routes={'/send':adapter.send, '/history':adapter.set_history, '/controls':adapter.controls,
            '/heartbeat':adapter.heartbeat, '/simulate':adapter.simulate, '/operation':adapter.poll,
            '/context-reset':adapter.reset_context})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    url = f'http://127.0.0.1:{args.port}'
    from urllib.request import urlopen
    try:
        with urlopen(url+'/health', timeout=1) as response: existing=json.loads(response.read(1024))
    except Exception: existing=None
    if existing == dict(application=APPLICATION_ID):
        print('生活试验已在运行：'+url, flush=True)
        if args.open_browser:
            import webbrowser
            webbrowser.open(url)
        return
    config = default_config()
    if not config.state_path.is_file(): raise SystemExit('尚未创建获准的独立生活分支。')
    from dynamic_subject_agent.local_product import open_first_life_product
    from dynamic_subject_agent.first_life import first_life_scope
    from dynamic_subject_agent.frozen_attempt import canonical_json
    scope_digest = sha256(canonical_json(first_life_scope(DEFINITION_BASIS)).encode()).hexdigest()
    budget_path = config.state_path.parent.parent / 'character-chat-v1/provider-budget'
    try:
        product = open_first_life_product(config, definition_basis=DEFINITION_BASIS,
            life_scope_digest=scope_digest, budget_path=budget_path, development_run=False)
    except Exception:
        raise SystemExit('生活试验未能安全启动，现有聊天和资料未删除。') from None
    try:
        server=life_server(product, port=args.port)
        url = f'http://127.0.0.1:{server.server_port}'
        print('生活试验已启动：'+url, flush=True)
        if args.open_browser:
            import webbrowser
            webbrowser.open(url)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
    finally: product.close()


if __name__ == '__main__': main()

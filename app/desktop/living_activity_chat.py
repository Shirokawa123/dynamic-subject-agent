"""S143 thin online presentation; the Facade owns life and delivery decisions."""
from threading import Thread
from uuid import UUID
from hashlib import sha256

from character_chat import create_server
from shared_activity_chat import SharedActivityChatAdapter
from dynamic_subject_agent.living_activity import LivingActionRequest, LivingControlRequest, LivingPresenceRequest
from dynamic_subject_agent.shared_activity import SharedActivityResponse
from dynamic_subject_agent.whole_chat_archive import WholeChatArchiveRequest

APPLICATION_ID = 'living-activity-chat-s143'


class LivingActivityChatAdapter(SharedActivityChatAdapter):
    def __init__(self, product, *, reopen, allow_simulation=False):
        if type(allow_simulation) is not bool:
            raise ValueError('explicit simulation setting required')
        super().__init__(product, reopen=reopen)
        self.allow_simulation = allow_simulation
        self.living_requests, self.living_results = {}, {}
        self.living_kind = None

    def snapshot(self):
        with self.lock:
            result = super().snapshot()
            if self.shared_inflight is not None or self.inflight:
                return dict(result, living_pending=self.living_kind is not None,
                    living_kind=self.living_kind,
                    living_request=self._plain(self.living_requests.get(self.shared_inflight)),
                    simulation_enabled=self.allow_simulation)
            controls = self._plain(self.product.application.query_living_controls())
            if controls['status'] != 'available':
                controls = dict(status=controls['status'])
            if not self.shared_inflight and not self.inflight:
                living = self._plain(self.product.application.query_living_activity())
                if living['status'] != 'available':
                    living = dict(status=living['status'])
                archive = self._plain(self.product.application.query_whole_chat_archive(
                    WholeChatArchiveRequest(self.product.profile_id, self.product.timeline_id)))
                blocked = living['status'] != 'available' or archive['status'] != 'available'
                messages = list(reversed(archive['rows'])) if not blocked else []
                result = dict(result, living_activity=living, chat_messages=messages,
                    chat_messages_status=living['status'] if living['status'] != 'available' else archive['status'],
                    presentation_blocked=blocked)
            result = dict(result, living_controls=controls,
                living_pending=self.living_kind is not None,
                living_kind=self.living_kind,
                living_request=self._plain(self.living_requests.get(self.shared_inflight)),
                simulation_enabled=self.allow_simulation)
            if not self.shared_inflight and not self.inflight and result['character']['status'] == 'active':
                self.last_snapshot = result
            return result

    @staticmethod
    def _uuid(value):
        return type(value) is str and str(UUID(value)) == value

    def _living_request(self, payload, kind):
        fields = {'request_id', 'expected_revision'} | ({'session_id'} if kind == 'online' else set())
        if (type(payload) is not dict or set(payload) != fields or not self._uuid(payload['request_id'])
            or type(payload['expected_revision']) is not int or payload['expected_revision'] < 0
            or kind == 'online' and not self._uuid(payload['session_id'])):
            raise ValueError('invalid-request')
        return LivingActionRequest(self.product.profile_id, self.product.timeline_id,
            payload['request_id'], payload['expected_revision'], kind, payload.get('session_id', ''))

    def _living_result(self, response, request):
        status = response.status
        ok = status == 'no-op' or status in ('committed', 'replayed') and response.receipt is not None
        message = {
            'busy': '正在考虑分享…' if request.action == 'share' else '正在进行本次活动选择…',
            'committed': '本次分享考虑已提交。' if request.action == 'share' else '本次活动选择已提交。',
            'replayed': '已读回本次已提交结果。',
            'unknown': '原动作的交付尚不能确认；已暂停生活，请先检查原结果。没有自动重试。',
            'not-found': '尚未找到原动作；这里只查读，没有重新执行。',
            'conflict': '原动作与当前状态发生冲突；请查读后再明确开启。',
        }.get(status, '本次动作没有形成可提交结果；请先检查原结果和设置。')
        if status == 'no-op':
            message = {
                'online-baseline': '本页开始计时，满15分钟才提供一次活动机会。',
                'no-decision-boundary': '本页正在累计在线活动机会。',
                'another-life-window': '另一页持有在线机会；本页不会重复推进。',
                'paused': '生活已暂停。',
            }.get(response.problem_code, '这次没有新的活动或分享；没有请求模型。')
        return dict(ok=ok or status == 'busy', living_status=status, living_kind=request.action,
            living_request_id=request.request_id,
            living_started=self.living_requests.get(request.request_id) == request,
            living_settled=status in ('committed', 'replayed', 'no-op', 'failed-closed', 'unavailable', 'conflict', 'cancelled'),
            living_receipt=self._plain(response.receipt), living_problem_code=response.problem_code,
            message=message, state=self.snapshot())

    def living_request_result(self, payload):
        if (type(payload) is not dict or set(payload) != {'kind', 'request'}
            or payload['kind'] not in ('online', 'share', 'simulation')):
            raise ValueError('invalid-request')
        with self.lock:
            request = self._living_request(payload['request'], payload['kind'])
            original = self.living_requests.get(request.request_id)
            if original is not None and original != request:
                response = SharedActivityResponse('conflict')
            elif self.shared_inflight is not None or self.inflight:
                # Other pages may observe a pending stage, but must not take
                # its short admission/history lock with an unrelated query.
                response = SharedActivityResponse('busy')
            else:
                # Canonical read only: this never refreshes the page's lease.
                response = self.product.application.query_living_activity(request)
                if response.status == 'not-found' and original == request:
                    response = self.living_results.get(request.request_id, response)
            return self._living_result(response, request)

    def _living_start(self, payload, kind):
        with self.lock:
            request = self._living_request(payload, kind)
            if kind == 'simulation' and not self.allow_simulation:
                return self._living_result(SharedActivityResponse('unavailable', problem_code='living-simulation-disabled'), request)
            original = self.living_requests.get(request.request_id)
            if original is not None and original != request:
                return self._living_result(SharedActivityResponse('conflict'), request)
            if self.shared_inflight is not None or self.inflight:
                return self._living_result(SharedActivityResponse('busy'), request)
            response = self.product.application.query_living_activity(request)
            if response.status != 'not-found':
                return self._living_result(response, request)
            if original == request and request.request_id in self.living_results:
                return self._living_result(self.living_results[request.request_id], request)
            self.snapshot()
            self.living_requests[request.request_id] = request
            self.shared_inflight, self.living_kind = request.request_id, kind
            product = self.product
            def execute():
                try:
                    response = product.application.advance_living_activity(request)
                except Exception:
                    response = SharedActivityResponse('failed-closed', problem_code='living-operation-unverified')
                with self.lock:
                    self.living_results[request.request_id] = response
                    self.shared_inflight = self.living_kind = None
            Thread(target=execute, name='living-' + kind, daemon=True).start()
            return self._living_result(SharedActivityResponse('busy'), request)

    def living_heartbeat(self, payload):
        return self._living_start(payload, 'online')

    def living_presence(self, payload):
        if type(payload) is not dict or set(payload) != {'session_id'} or not self._uuid(payload['session_id']):
            raise ValueError('invalid-request')
        with self.lock:
            product = self.product
            response = product.application.heartbeat_living_presence(LivingPresenceRequest(
                product.profile_id, product.timeline_id, payload['session_id']))
            return dict(ok=response.status == 'available', presence_status=response.status,
                presence_problem_code=response.problem_code,
                presence=self._plain(response.view) if response.status == 'available' else None,
                scope_key=sha256((product.profile_id + ':' + product.timeline_id).encode()).hexdigest())

    def living_share(self, payload):
        return self._living_start(payload, 'share')

    def living_simulation(self, payload):
        return self._living_start(payload, 'simulation')

    def living_controls_query(self, payload):
        self._validate_empty(payload)
        return dict(ok=True, state=self.snapshot())

    def living_controls(self, payload):
        fields = {'request_id', 'expected_permission_revision', 'paused', 'sharing_enabled', 'confirmed'}
        if (type(payload) is not dict or set(payload) != fields or not self._uuid(payload['request_id'])
            or type(payload['expected_permission_revision']) is not int or payload['expected_permission_revision'] < 0
            or any(value is not None and type(value) is not bool for value in (payload['paused'], payload['sharing_enabled']))
            or payload['paused'] is None and payload['sharing_enabled'] is None or payload['confirmed'] is not True):
            raise ValueError('invalid-request')
        with self.lock:
            # Permission changes remain available during a model stage. Its
            # final fence will reject a proposal whose permission has changed.
            request = LivingControlRequest(self.product.profile_id, self.product.timeline_id,
                payload['request_id'], payload['expected_permission_revision'],
                payload['paused'], payload['sharing_enabled'], True)
            response = self.product.application.set_living_controls(request)
            if self.last_snapshot is not None and response.view is not None:
                self.last_snapshot = dict(self.last_snapshot,
                    living_controls=dict(status='available', view=self._plain(response.view)))
            return dict(ok=response.status in ('committed', 'replayed'), control_status=response.status,
                message='生活设置已保存；没有发送草稿。' if response.status in ('committed', 'replayed') else '设置尚未确认，请先读取状态。',
                state=self.snapshot())

    def shared_advance(self, payload):
        # This entry has online/simulation opportunity semantics, never the
        # old manual shared sender even though its source UI is reused.
        self._shared_request(payload, kind='advance')
        return dict(ok=False, shared_status='unavailable', message='此入口通过在线机会推进活动。', state=self.snapshot())

    def shared_request_result(self, payload):
        with self.lock:
            if self.living_kind is not None:
                if (type(payload) is not dict or set(payload) != {'kind', 'request'}
                    or payload['kind'] not in ('advance', 'experience')):
                    raise ValueError('invalid-request')
                request = self._shared_request(payload['request'], kind=payload['kind'])
                return self._shared_result(SharedActivityResponse('busy'), request, payload['kind'])
            return super().shared_request_result(payload)

    def message_scope(self, payload):
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False, message_scope=dict(status='unavailable'), state=self.snapshot())
            result = super().message_scope(payload)
            if result['ok']:
                preview = self._plain(self.product.application.preview_living_activity('reply', payload['text']))
                if preview['status'] != 'previewed':
                    return dict(result, ok=False, message_scope=dict(status='failed-closed'))
                result['message_scope']['latest_share'] = preview['view']['payload']['evidence']['latest_share']
            return result

    def reload(self, payload):
        with self.lock:
            result = super().reload(payload)
            if result['ok']:
                self.living_requests.clear(); self.living_results.clear()
            return result


def living_activity_server(product, *, reopen, port=0, allow_simulation=False):
    adapter = LivingActivityChatAdapter(product, reopen=reopen, allow_simulation=allow_simulation)
    return create_server(None, port=port, adapter=adapter, page_name='living_activity_chat.html', application_id=APPLICATION_ID,
        post_routes={'/send': adapter.send, '/operation': adapter.poll, '/request-result': adapter.lookup,
            '/context-boundary-query': adapter.boundary_query, '/context-boundary': adapter.boundary_apply,
            '/character-basis': adapter.character_basis, '/message-scope': adapter.message_scope,
            '/chat-archive': adapter.chat_archive, '/history': adapter.set_history, '/reload': adapter.reload,
            '/shared-activity': adapter.shared_state, '/shared-experience': adapter.shared_experience,
            '/shared-activity-preview': adapter.shared_preview, '/shared-activity-request': adapter.shared_request_result,
            '/living-controls-query': adapter.living_controls_query, '/living-controls': adapter.living_controls,
            '/living-presence': adapter.living_presence,
            '/living-heartbeat': adapter.living_heartbeat, '/living-share': adapter.living_share,
            '/living-simulation': adapter.living_simulation, '/living-request': adapter.living_request_result})

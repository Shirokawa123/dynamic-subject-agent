"""Thin shared-live presentation; all state and delivery remain in the Facade."""
from threading import Thread
from uuid import UUID

from character_chat import create_server
from original_whole_chat import OriginalWholeChatAdapter
from dynamic_subject_agent.shared_activity import SharedExperienceRequest, SharedActivityStepRequest, SharedActivityResponse, SHARED_TECHNICAL_VARIANTS

APPLICATION_ID = 'shared-activity-chat-s140'


def shared_activity_application_id(technical_variant='baseline'):
    if type(technical_variant) is not str or technical_variant not in SHARED_TECHNICAL_VARIANTS:
        raise ValueError('closed shared entry variant required')
    if technical_variant == 'self-directed-activity':
        return 'shared-activity-chat-s141-self-directed-activity'
    return APPLICATION_ID if technical_variant == 'baseline' else APPLICATION_ID + '-natural-expression'


class SharedActivityChatAdapter(OriginalWholeChatAdapter):
    def __init__(self, product, *, reopen):
        super().__init__(product, reopen=reopen)
        self.shared_inflight = None
        self.shared_requests, self.shared_results = {}, {}

    def snapshot(self):
        with self.lock:
            if self.shared_inflight is not None and self.last_snapshot is not None:
                return dict(self.last_snapshot, presentation_pending=True, shared_pending=True,
                    shared_request_id=self.shared_inflight, pending_handle=None, pending_request_id=None,
                    context_boundary=dict(self.last_snapshot['context_boundary'], pending=True))
            result = super().snapshot()
            if self.inflight:
                return dict(result, shared_pending=False, shared_request_id=None)
            response = self.product.application.query_shared_activity()
            shared = self._plain(response)
            if shared.get('status') != 'available':
                shared = dict(status=shared.get('status', 'failed-closed'))
            result = dict(result, shared_activity=shared, shared_pending=False, shared_request_id=None)
            if result['history']['status'] == 'available' and result['character']['status'] == 'active':
                self.last_snapshot = result
            return result

    @staticmethod
    def _validate_empty(payload):
        if type(payload) is not dict or payload:
            raise ValueError('invalid-request')

    def shared_state(self, payload):
        self._validate_empty(payload)
        return dict(ok=True, state=self.snapshot())

    def shared_preview(self, payload):
        self._validate_empty(payload)
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False, shared_status='busy', message='原请求仍在处理，请先核实结果。', state=self.snapshot())
            response = self.product.application.preview_shared_activity_step()
            value = self._plain(response)
            # Show the actual bounded next-step material in ordinary language;
            # policy/background/protocol are neither changed nor assembled here.
            payload = value.get('view', {}).get('payload', {}) if value['status'] == 'previewed' else {}
            return dict(ok=value['status'] == 'previewed', shared_status=value['status'],
                shared_preview={key: payload.get(key) for key in ('shared_experience', 'current_activity', 'current_plan')},
                state=self.snapshot())

    def _shared_request(self, payload, *, kind):
        fields = {'request_id', 'expected_revision'}
        if kind == 'experience':
            fields |= {'source_head_sequence', 'quote', 'confirmed'}
        if (type(payload) is not dict or set(payload) != fields or type(payload['request_id']) is not str
            or str(UUID(payload['request_id'])) != payload['request_id']
            or type(payload['expected_revision']) is not int or payload['expected_revision'] < 0):
            raise ValueError('invalid-request')
        if kind == 'experience':
            head, quote = payload['source_head_sequence'], payload['quote']
            if (payload['confirmed'] is not True or type(quote) is not str or '\x00' in quote or len(quote) > 400
                or head is None and quote != '' or head is not None and (
                    type(head) is not int or head < 1 or not quote.strip())):
                raise ValueError('invalid-request')
            return SharedExperienceRequest(self.product.profile_id, self.product.timeline_id,
                payload['request_id'], payload['expected_revision'], head, quote, True)
        return SharedActivityStepRequest(self.product.profile_id, self.product.timeline_id,
            payload['request_id'], payload['expected_revision'])

    def _shared_result(self, response, request, kind):
        status = response.status
        ok = status in ('committed', 'replayed') and response.receipt is not None
        settled = status in ('committed', 'replayed', 'failed-closed', 'conflict', 'cancelled', 'unavailable')
        message = ('已提交本次文字构图结果，可以接着聊。' if kind == 'advance' else
            '已停用这条经历；依赖它的内容不再参与之后的选择与交流。' if request.source_head_sequence is None else
            '已选定这段用户原话作为经历依据。') if ok else {
                'busy': '原请求仍在处理；可以写草稿，请等待结果后再发送。',
                'not-found': '未找到已开始的原动作。没有重新执行；可明确开始原动作或放下它。',
                'unknown': '原动作的交付尚不能确认；没有重试，草稿保留。',
                'conflict': '原动作与当前状态发生冲突；没有改写结果，请查读后重新确认。',
            }.get(status, '这次动作未形成可提交结果；没有自动重试，原记录与草稿保留。')
        return dict(ok=ok or status == 'busy', shared_status=status, shared_kind=kind,
            shared_request_id=request.request_id, shared_settled=settled,
            shared_receipt=self._plain(response.receipt), shared_problem_code=response.problem_code,
            message=message, state=self.snapshot())

    def shared_request_result(self, payload):
        if type(payload) is not dict or set(payload) != {'kind', 'request'} or payload['kind'] not in ('advance', 'experience'):
            raise ValueError('invalid-request')
        kind = payload['kind']
        with self.lock:
            request = self._shared_request(payload['request'], kind=kind)
            original = self.shared_requests.get(request.request_id)
            if original is not None and original != request:
                response = SharedActivityResponse('conflict')
            elif original == request and self.shared_inflight == request.request_id:
                # The presentation owns this still-running exact action. A
                # concurrent canonical reader may be unavailable mid-claim;
                # that is not a terminal result of the running worker.
                response = SharedActivityResponse('busy')
            else:
                # Query is intentionally read-only, including missing nonces.
                response = self.product.application.query_shared_activity(request)
                if response.status == 'not-found':
                    if self.shared_inflight == request.request_id:
                        response = SharedActivityResponse('busy')
                    elif original == request:
                        response = self.shared_results.get(request.request_id, response)
            return self._shared_result(response, request, kind)

    def shared_experience(self, payload):
        with self.lock:
            request = self._shared_request(payload, kind='experience')
            if self.shared_inflight is not None or self.inflight:
                return self._shared_result(SharedActivityResponse('busy'), request, 'experience')
            response = self.product.application.set_shared_experience(request)
            return self._shared_result(response, request, 'experience')

    def shared_advance(self, payload):
        with self.lock:
            request = self._shared_request(payload, kind='advance')
            original = self.shared_requests.get(request.request_id)
            if original is not None and original != request:
                return self._shared_result(SharedActivityResponse('conflict'), request, 'advance')
            if original == request and self.shared_inflight == request.request_id:
                return self._shared_result(SharedActivityResponse('busy'), request, 'advance')
            response = self.product.application.query_shared_activity(request)
            if response.status != 'not-found':
                return self._shared_result(response, request, 'advance')
            if original == request and request.request_id in self.shared_results:
                return self._shared_result(self.shared_results[request.request_id], request, 'advance')
            if self.shared_inflight is not None or self.inflight:
                return self._shared_result(SharedActivityResponse('busy'), request, 'advance')
            self.snapshot()
            self.shared_requests[request.request_id] = request
            self.shared_inflight = request.request_id
            product = self.product
            def execute():
                try:
                    result = product.application.advance_shared_activity(request)
                except Exception:
                    result = SharedActivityResponse('failed-closed', problem_code='shared-operation-unverified')
                with self.lock:
                    self.shared_results[request.request_id] = result
                    self.shared_inflight = None
            Thread(target=execute, name='shared-manual-step', daemon=True).start()
            return self._shared_result(SharedActivityResponse('busy'), request, 'advance')

    def _manual_busy(self):
        return dict(ok=False, message='构图动作仍在处理，请先核实原结果；草稿保留。', state=self.snapshot())

    def send(self, payload):
        self._validate_message(payload)
        with self.lock:
            return self._manual_busy() if self.shared_inflight is not None else super().send(payload)

    def set_history(self, payload):
        with self.lock:
            return self._manual_busy() if self.shared_inflight is not None else super().set_history(payload)

    def boundary_apply(self, payload):
        with self.lock:
            return self._manual_busy() if self.shared_inflight is not None else super().boundary_apply(payload)

    def reload(self, payload):
        with self.lock:
            if self.shared_inflight is not None:
                return self._manual_busy()
            result = super().reload(payload)
            if result['ok']:
                self.shared_requests.clear()
                self.shared_results.clear()
            return result

    def message_scope(self, payload):
        with self.lock:
            result = super().message_scope(payload)
            shared = self._plain(self.product.application.query_shared_activity())
            if result['ok'] and shared['status'] == 'available':
                view = shared['view']
                result['message_scope'].update(shared_experience=view['visible_source'], activity_result=view['visible_result'])
            return result


def shared_activity_server(product, *, reopen, port=0, technical_variant='baseline'):
    adapter = SharedActivityChatAdapter(product, reopen=reopen)
    return create_server(None, port=port, adapter=adapter, page_name='shared_activity_chat.html',
        application_id=shared_activity_application_id(technical_variant),
        post_routes={'/send': adapter.send, '/operation': adapter.poll, '/request-result': adapter.lookup,
            '/context-boundary-query': adapter.boundary_query, '/context-boundary': adapter.boundary_apply,
            '/character-basis': adapter.character_basis, '/message-scope': adapter.message_scope,
            '/chat-archive': adapter.chat_archive, '/history': adapter.set_history, '/reload': adapter.reload,
            '/shared-activity': adapter.shared_state, '/shared-experience': adapter.shared_experience,
            '/shared-activity-preview': adapter.shared_preview, '/shared-activity-advance': adapter.shared_advance,
            '/shared-activity-request': adapter.shared_request_result})

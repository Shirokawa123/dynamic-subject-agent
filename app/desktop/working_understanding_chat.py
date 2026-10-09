"""S147 thin manual working-understanding UI; the Facade owns every effect."""
from threading import Thread
from uuid import UUID

from character_chat import create_server
from shared_activity_chat import SharedActivityChatAdapter
from dynamic_subject_agent.shared_activity import SharedActivityResponse
from dynamic_subject_agent.working_understanding import WorkingSourceQuote, WorkingUnderstandingRequest

APPLICATION_ID = 'working-understanding-chat-s147'


class WorkingUnderstandingChatAdapter(SharedActivityChatAdapter):
    def __init__(self, product, *, reopen):
        super().__init__(product, reopen=reopen)
        self.working_requests, self.working_results = {}, {}
        self.working_kind = None

    def snapshot(self):
        with self.lock:
            result = super().snapshot()
            if self.shared_inflight is not None or self.inflight:
                return dict(result, working_pending=self.working_kind is not None)
            working = self._plain(self.product.application.query_working_understanding())
            if working['status'] != 'available':
                working = dict(status=working['status'])
            result = dict(result, working_understanding=working, working_pending=False)
            if result['history']['status'] == 'available' and result['character']['status'] == 'active':
                self.last_snapshot = result
            return result

    @staticmethod
    def _uuid(value):
        return type(value) is str and str(UUID(value)) == value

    def _working_request(self, payload, kind):
        fields = {'request_id', 'expected_revision', 'sources', 'confirmed'}
        if (kind not in ('form', 'disable') or type(payload) is not dict or set(payload) != fields
            or not self._uuid(payload['request_id']) or type(payload['expected_revision']) is not int
            or payload['expected_revision'] < 0 or type(payload['confirmed']) is not bool
            or type(payload['sources']) is not list or len(payload['sources']) != (2 if kind == 'form' else 0)):
            raise ValueError('invalid-request')
        sources = []
        for source in payload['sources']:
            if (type(source) is not dict or set(source) != {'source_head_sequence', 'quote'}
                or type(source['source_head_sequence']) is not int or source['source_head_sequence'] < 1
                or type(source['quote']) is not str or not source['quote'].strip()
                or len(source['quote']) > 400 or '\x00' in source['quote']):
                raise ValueError('invalid-request')
            sources.append(WorkingSourceQuote(source['source_head_sequence'], source['quote']))
        if len(sources) == 2 and sources[0].source_head_sequence == sources[1].source_head_sequence:
            raise ValueError('invalid-request')
        return WorkingUnderstandingRequest(self.product.profile_id, self.product.timeline_id,
            payload['request_id'], payload['expected_revision'], tuple(sources), kind, payload['confirmed'])

    def working_state(self, payload):
        self._validate_empty(payload)
        return dict(ok=True, state=self.snapshot())

    def working_preview(self, payload):
        with self.lock:
            request = self._working_request(payload, 'form')
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False, shared_status='busy', message='原请求仍在处理，请先查读结果。', state=self.snapshot())
            value = self._plain(self.product.application.preview_working_understanding(request))
            material = value['view']['payload'] if value['status'] == 'previewed' else {}
            message = {
                'working-derived-source-unavailable': '这次依据依赖此前理解或它的方案；请先停用当前理解，再从新提交的两条原话重建。',
                'working-source-unavailable': '原话不在当前可用交流范围内，或历史参考已关闭；请核对设置并重新选取。',
                'working-revision-changed': '交流或活动已变化，请重新选取与查看。',
            }.get(value.get('problem_code'), '形成依据尚不能核实，请重新选取与查看；没有请求模型。')
            return dict(ok=value['status'] == 'previewed', shared_status=value['status'],
                working_preview={key: material.get(key) for key in ('scope', 'exchanges', 'activity_result')},
                message='' if value['status'] == 'previewed' else message,
                state=self.snapshot())

    def _working_result(self, response, request):
        status, kind = response.status, request.action
        ok = status in ('committed', 'replayed', 'no-op') and response.receipt is not None
        message = ('已停用当前理解；依赖它的内容不再参与后续选择和交流。' if kind == 'disable' else
            '已形成当前构图的暂定理解，可以查看出处或明确推进一次活动。') if ok else {
                'busy': '原动作仍在处理；可以写草稿，结束后再明确发送。',
                'not-found': '尚未找到原动作；这里只查读，没有重新执行。',
                'unknown': '原动作的交付尚不能确认；没有自动重试，原请求与草稿保留。',
                'conflict': '原动作与当前范围发生冲突；请重新查看来源与状态。',
                'cancelled': '没有确认形成理解；草稿与记录保持。',
                'unavailable': '当前原话或权限不可用于这个动作；没有形成新理解。',
            }.get(status, '本次动作未形成可提交结果；没有自动重试，原记录与草稿保留。')
        if status == 'no-op':
            message = '这两段原话不足以形成新理解；此前理解保持，可以重新选取原话。'
        return dict(ok=ok or status == 'busy', shared_status=status, shared_kind=kind,
            shared_request_id=request.request_id, shared_receipt=self._plain(response.receipt),
            shared_settled=status in ('committed', 'replayed', 'no-op', 'failed-closed', 'unavailable', 'conflict', 'cancelled'),
            shared_problem_code=response.problem_code, message=message, state=self.snapshot())

    def working_request_result(self, payload):
        if type(payload) is not dict or set(payload) != {'kind', 'request'} or payload['kind'] not in ('advance', 'form', 'disable'):
            raise ValueError('invalid-request')
        if payload['kind'] == 'advance':
            with self.lock:
                request = self._shared_request(payload['request'], kind='advance')
                original = self.shared_requests.get(request.request_id)
                if original is not None and original != request:
                    return self._shared_result(SharedActivityResponse('conflict'), request, 'advance')
                if self.shared_inflight is not None or self.inflight:
                    return self._shared_result(SharedActivityResponse('busy'), request, 'advance')
                return super().shared_request_result(payload)
        with self.lock:
            request = self._working_request(payload['request'], payload['kind'])
            original = self.working_requests.get(request.request_id)
            if original is not None and original != request:
                response = SharedActivityResponse('conflict')
            elif original == request and self.shared_inflight == request.request_id:
                response = SharedActivityResponse('busy')
            elif self.shared_inflight is not None or self.inflight:
                response = SharedActivityResponse('busy')
            else:
                response = self.product.application.query_working_understanding(request)
                if response.status == 'not-found' and original == request:
                    response = self.working_results.get(request.request_id, response)
            return self._working_result(response, request)

    def working_form(self, payload):
        with self.lock:
            request = self._working_request(payload, 'form')
            original = self.working_requests.get(request.request_id)
            if original is not None and original != request:
                return self._working_result(SharedActivityResponse('conflict'), request)
            if original == request and self.shared_inflight == request.request_id:
                return self._working_result(SharedActivityResponse('busy'), request)
            if self.shared_inflight is not None or self.inflight:
                return self._working_result(SharedActivityResponse('busy'), request)
            response = self.product.application.query_working_understanding(request)
            if response.status != 'not-found':
                return self._working_result(response, request)
            if original == request and request.request_id in self.working_results:
                return self._working_result(self.working_results[request.request_id], request)
            self.snapshot()
            self.working_requests[request.request_id] = request
            self.shared_inflight, self.working_kind = request.request_id, 'form'
            product = self.product
            def execute():
                try:
                    response = product.application.apply_working_understanding(request)
                except Exception:
                    response = SharedActivityResponse('failed-closed', problem_code='working-operation-unverified')
                with self.lock:
                    self.working_results[request.request_id] = response
                    self.shared_inflight = self.working_kind = None
            Thread(target=execute, name='working-manual-form', daemon=True).start()
            return self._working_result(SharedActivityResponse('busy'), request)

    def working_disable(self, payload):
        with self.lock:
            request = self._working_request(payload, 'disable')
            if self.shared_inflight is not None or self.inflight:
                return self._working_result(SharedActivityResponse('busy'), request)
            response = self.product.application.apply_working_understanding(request)
            return self._working_result(response, request)

    def shared_preview(self, payload):
        self._validate_empty(payload)
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False, shared_status='busy', message='原动作仍在处理，请先查读结果。', state=self.snapshot())
            value = self._plain(self.product.application.preview_working_activity('choice'))
            material = value['view']['payload'] if value['status'] == 'previewed' else {}
            return dict(ok=value['status'] == 'previewed', shared_status=value['status'],
                shared_preview={key: material.get(key) for key in ('current_activity', 'current_plan', 'working_understanding')},
                state=self.snapshot())

    def shared_advance(self, payload):
        with self.lock:
            request = self._shared_request(payload, kind='advance')
            original = self.shared_requests.get(request.request_id)
            if original is not None and original != request:
                return self._shared_result(SharedActivityResponse('conflict'), request, 'advance')
            if self.shared_inflight is not None or self.inflight:
                return self._shared_result(SharedActivityResponse('busy'), request, 'advance')
            response = self.product.application.query_shared_activity(request)
            if response.status != 'not-found':
                return self._shared_result(response, request, 'advance')
            if original == request and request.request_id in self.shared_results:
                return self._shared_result(self.shared_results[request.request_id], request, 'advance')
            self.snapshot()
            self.shared_requests[request.request_id] = request
            self.shared_inflight = request.request_id
            product = self.product
            def execute():
                try:
                    response = product.application.advance_working_activity(request)
                except Exception:
                    response = SharedActivityResponse('failed-closed', problem_code='working-activity-unverified')
                with self.lock:
                    self.shared_results[request.request_id] = response
                    self.shared_inflight = None
            Thread(target=execute, name='working-manual-activity', daemon=True).start()
            return self._shared_result(SharedActivityResponse('busy'), request, 'advance')

    def message_scope(self, payload):
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False, message_scope=dict(status='unavailable'), state=self.snapshot())
            result = super().message_scope(payload)
            if result['ok']:
                value = self._plain(self.product.application.preview_working_activity('reply', payload['text']))
                if value['status'] != 'previewed':
                    return dict(result, ok=False, message_scope=dict(status='failed-closed'))
                result['message_scope']['working_understanding'] = value['view']['payload']['evidence']['working_understanding']
            return result

    def reload(self, payload):
        with self.lock:
            result = super().reload(payload)
            if result['ok']:
                self.working_requests.clear(); self.working_results.clear()
            return result


def working_understanding_server(product, *, reopen, port=0):
    adapter = WorkingUnderstandingChatAdapter(product, reopen=reopen)
    return create_server(None, port=port, adapter=adapter, page_name='working_understanding_chat.html', application_id=APPLICATION_ID,
        post_routes={'/send': adapter.send, '/operation': adapter.poll, '/request-result': adapter.lookup,
            '/context-boundary-query': adapter.boundary_query, '/context-boundary': adapter.boundary_apply,
            '/character-basis': adapter.character_basis, '/message-scope': adapter.message_scope,
            '/chat-archive': adapter.chat_archive, '/history': adapter.set_history, '/reload': adapter.reload,
            '/working-understanding': adapter.working_state, '/working-understanding-preview': adapter.working_preview,
            '/working-understanding-form': adapter.working_form, '/working-understanding-disable': adapter.working_disable,
            '/working-understanding-request': adapter.working_request_result,
            '/working-activity-preview': adapter.shared_preview, '/working-activity-advance': adapter.shared_advance})

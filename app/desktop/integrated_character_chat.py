"""Single LOCAL preparation entry; business state is owned by the Facade."""
from hashlib import sha256

from character_chat import create_server
from living_activity_chat import LivingActivityChatAdapter
from dynamic_subject_agent.shared_activity import digest

APPLICATION_ID = 'integrated-character-local-s158'
LIVE_APPLICATION_ID = 'integrated-character-live-s158'
FOCUSED_APPLICATION_ID = 'integrated-character-focused-s158'
CONVERSATION_APPLICATION_ID = 'integrated-character-conversation-s158'
INTENT_APPLICATION_ID = 'integrated-character-intent-s158'


def integrated_live_application_id(technical_variant='baseline'):
    if technical_variant not in ('baseline', 'focused', 'conversation-text', 'intent-text'):
        raise ValueError('closed integrated entry variant required')
    return {'baseline': LIVE_APPLICATION_ID, 'focused': FOCUSED_APPLICATION_ID,
        'conversation-text': CONVERSATION_APPLICATION_ID, 'intent-text': INTENT_APPLICATION_ID}[technical_variant]


class IntegratedCharacterChatAdapter(LivingActivityChatAdapter):
    def message_scope(self, payload):
        if (type(payload) is not dict or set(payload) != {'text'}
            or type(payload['text']) is not str or not payload['text'].strip()
            or len(payload['text']) > 1000 or '\x00' in payload['text']):
            raise ValueError('invalid-request')
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False, message_scope=dict(status='unavailable'))
            response = self.product.application.preview_natural_feedback(payload['text'])
            if response.status != 'previewed':
                return dict(ok=False, message_scope=dict(status=response.status))
            data = response.view['payload']
            background = data['background']
            scope = dict(status='available', current_message=data['turn']['current_message'],
                history_enabled=data['turn']['history_enabled'],
                has_prior_committed_exchange=data['turn']['has_prior_committed_exchange'],
                character_core=background['character_core'], self_knowledge=background['self_knowledge'],
                personality_count=len(background['personality']), recent_dialogue=data['exchange'],
                shared_experience=data['evidence']['shared_experience'], current_plan=data['current_plan'],
                latest_share=data['evidence']['latest_share'], current_feedback=data['current_feedback'],
                projection_digest=digest(response.view),
                limitations=['明确指出要替换的文字时才修改；含糊指称先澄清，其他内容逐字保留。'])
            return dict(ok=True, message_scope=self._plain(scope),
                scope_key=sha256((self.product.profile_id + ':' + self.product.timeline_id).encode()).hexdigest())

    def shared_preview(self, payload):
        self._validate_empty(payload)
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False, shared_status='busy', state=self.snapshot())
            response = self.product.application.preview_living_activity('choice')
            data = response.view['payload'] if response.status == 'previewed' else {}
            return dict(ok=response.status == 'previewed', shared_status=response.status,
                shared_preview=self._plain({key: data.get(key) for key in
                    ('shared_experience', 'current_feedback', 'current_activity', 'current_plan')}),
                state=self.snapshot())


def integrated_character_server(product, *, reopen, port=0, allow_simulation=False, live=False,
                                technical_variant='baseline'):
    if type(live) is not bool:
        raise ValueError('explicit integrated entry mode required')
    application_id = integrated_live_application_id(technical_variant)
    if not live and technical_variant != 'baseline':
        raise ValueError('LOCAL preparation retains its original baseline')
    adapter = IntegratedCharacterChatAdapter(product, reopen=reopen, allow_simulation=allow_simulation)
    return create_server(None, port=port, adapter=adapter,
        page_name='integrated_character_live_chat.html' if live else 'integrated_character_chat.html',
        application_id=application_id if live else APPLICATION_ID,
        post_routes={'/send': adapter.send, '/operation': adapter.poll, '/request-result': adapter.lookup,
            '/context-boundary-query': adapter.boundary_query, '/context-boundary': adapter.boundary_apply,
            '/character-basis': adapter.character_basis, '/message-scope': adapter.message_scope,
            '/chat-archive': adapter.chat_archive, '/history': adapter.set_history, '/reload': adapter.reload,
            '/shared-activity': adapter.shared_state, '/shared-experience': adapter.shared_experience,
            '/shared-activity-preview': adapter.shared_preview, '/shared-activity-request': adapter.shared_request_result,
            '/living-controls-query': adapter.living_controls_query, '/living-controls': adapter.living_controls,
            '/living-presence': adapter.living_presence, '/living-heartbeat': adapter.living_heartbeat,
            '/living-share': adapter.living_share, '/living-simulation': adapter.living_simulation,
            '/living-request': adapter.living_request_result})

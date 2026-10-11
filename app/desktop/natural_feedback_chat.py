"""Manual feedback UI, actual Facade projections, no autonomous work."""
from hashlib import sha256
from character_chat import create_server
from shared_activity_chat import SharedActivityChatAdapter
from dynamic_subject_agent.shared_activity import digest

APPLICATION_ID='natural-feedback-chat-s155'


class NaturalFeedbackChatAdapter(SharedActivityChatAdapter):
    def message_scope(self,payload):
        if (type(payload) is not dict or set(payload)!={'text'} or type(payload['text']) is not str
            or not payload['text'].strip() or len(payload['text'])>1000 or '\x00' in payload['text']):
            raise ValueError('invalid-request')
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False,message_scope=dict(status='unavailable'))
            response=self.product.application.preview_natural_feedback(payload['text'])
            if response.status!='previewed':
                return dict(ok=False,message_scope=dict(status=response.status))
            data=response.view['payload'];background=data['background']
            activity=self._plain(self.product.application.query_shared_activity())
            if activity['status']!='available':return dict(ok=False,message_scope=dict(status='unavailable'))
            scope=dict(status='available',current_message=data['turn']['current_message'],
                history_enabled=data['turn']['history_enabled'],has_prior_committed_exchange=data['turn']['has_prior_committed_exchange'],
                character_core=background['character_core'],self_knowledge=background['self_knowledge'],
                personality_count=len(background['personality']),recent_dialogue=data['exchange'],
                shared_experience=data['evidence']['shared_experience'],activity_result=activity['view']['visible_result'],
                current_feedback=data['current_feedback'],projection_digest=digest(response.view),
                limitations=['当前自动修改覆盖明确引文替换；含糊指称先澄清，未确认的光线等不会擅改。'])
            return dict(ok=True,message_scope=self._plain(scope),scope_key=sha256((self.product.profile_id+':'+self.product.timeline_id).encode()).hexdigest())

    def shared_preview(self,payload):
        self._validate_empty(payload)
        with self.lock:
            if self.shared_inflight is not None or self.inflight:
                return dict(ok=False,shared_status='busy',state=self.snapshot())
            response=self.product.application.preview_shared_activity_step()
            data=response.view['payload'] if response.status=='previewed' else {}
            return dict(ok=response.status=='previewed',shared_status=response.status,
                shared_preview=self._plain({key:data.get(key) for key in ('shared_experience','current_feedback','current_activity','current_plan')}),state=self.snapshot())


def natural_feedback_server(product, *, reopen,port=0):
    a=NaturalFeedbackChatAdapter(product,reopen=reopen)
    return create_server(None,port=port,adapter=a,page_name='natural_feedback_chat.html',application_id=APPLICATION_ID,
        post_routes={'/send':a.send,'/operation':a.poll,'/request-result':a.lookup,'/context-boundary-query':a.boundary_query,
            '/context-boundary':a.boundary_apply,'/character-basis':a.character_basis,'/message-scope':a.message_scope,
            '/chat-archive':a.chat_archive,'/history':a.set_history,'/reload':a.reload,'/shared-activity':a.shared_state,
            '/shared-experience':a.shared_experience,'/shared-activity-preview':a.shared_preview,
            '/shared-activity-advance':a.shared_advance,'/shared-activity-request':a.shared_request_result})

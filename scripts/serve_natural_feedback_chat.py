"""S155 independent empty manual entry. Prepare is zero-model; serve needs approval."""
import argparse,json,os
from pathlib import Path
from uuid import UUID
from urllib.error import URLError
from serve_original_whole_chat import OriginalWholeChatEntry,DEFAULT_PACKAGE,history,ROOT
from serve_shared_activity_chat import default_entry_root as shared_root
from serve_original_context_chat import default_entry_root as context_root
from serve_living_activity_chat import default_entry_root as living_root,final_text_entry_root
from serve_living_action_contract_chat import default_entry_root as action_root
from serve_working_understanding_chat import default_entry_root as working_root,urlopen
from natural_feedback_chat import natural_feedback_server,APPLICATION_ID
from dynamic_subject_agent.local_product import LocalProductConfig,open_local_product,open_natural_feedback_product_live,validate_natural_feedback_entry
from dynamic_subject_agent.application import ApplicationQuery,ApplicationQueryKind
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.shared_activity import SHARED_TECHNICAL_VARIANTS
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW,open_natural_feedback_audit
from dynamic_subject_agent.natural_feedback_multispan import NaturalFeedbackMultispanDevelopmentGrant,MULTISPAN_DEVELOPMENT
from dynamic_subject_agent.frozen_attempt import canonical_json

ENTRY_VERSION='natural-feedback-entry-s155-1'
def default_entry_root():return ROOT/'.artifacts/s155/experience-entry'

class NaturalFeedbackChatEntry(OriginalWholeChatEntry):
    ENTRY_VERSION=ENTRY_VERSION
    default_entry_root=staticmethod(default_entry_root)
    def __init__(self,entry_root, *,live=True,package_path=DEFAULT_PACKAGE,transport=None,audit_path=None,observations=None):
        root=Path(entry_root).resolve();audit=None if audit_path is None else Path(audit_path).resolve()
        protected=[OriginalWholeChatEntry.default_entry_root(),context_root(),living_root(),final_text_entry_root(),action_root(),working_root(),
            *(shared_root(v) for v in SHARED_TECHNICAL_VARIANTS),*(ROOT/'.artifacts'/('s'+str(n)) for n in range(148,155))]
        protected=[p.resolve() for p in protected]
        if (type(live) is not bool or any(root.is_relative_to(p) or p.is_relative_to(root) for p in protected)
            or live and (root!=default_entry_root().resolve() or transport is not None or audit_path is not None)
            or not live and (transport is None or audit is None or root==default_entry_root().resolve()
                or any(root.is_relative_to(p) or p.is_relative_to(root) or audit.is_relative_to(p) or p.is_relative_to(audit) for p in (*protected,default_entry_root().resolve())))):
            raise ValueError('exact independent natural feedback entry required')
        self.root,self.product=root,None;self.transport,self.observations=transport,observations
        self.config=LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments',root/'state.json')
        self.audit_path=root/'provider-audit' if live else audit
        self.grant=NaturalFeedbackMultispanDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,MULTISPAN_DEVELOPMENT)
        fresh=not root.exists();content=self._review_package(Path(package_path).resolve()) if fresh else None
        try:
            if fresh:
                root.mkdir(parents=True,exist_ok=False);(root/'initialized').mkdir(exist_ok=False)
                with open_local_product(self.config,cognition=DormantDeepSeekCognition()) as author:
                    frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(content,APPROVED_BINDING['definition_basis'],True,True))
                    if frozen.status!='created':raise ValueError('new independent identity required')
                    self._fresh_identity_id=frozen.view.identity_id
                self.product=self._open()
                state=self.product.application.query_shared_activity()
                if history(self.product) or state.status!='available' or state.view['revision']!=0 or state.view['current_plan'] is not None:
                    raise ValueError('new entry must be empty and unstarted')
                value=dict(version=ENTRY_VERSION,technical_variant='multi-span',binding=dict(APPROVED_BINDING),profile_id=self.product.profile_id,timeline_id=self.product.timeline_id)
                with (root/'current.json').open('x',encoding='utf-8') as f:f.write(canonical_json(value));f.flush();os.fsync(f.fileno())
            value=self._read_pointer();self.identity=value['profile_id'],value['timeline_id']
            self._validate_current_identity()
            if self.product is None:self.product=self._open()
            if (self.product.profile_id,self.product.timeline_id)!=self.identity:raise ValueError('entry identity changed')
            self._history_state(self.product)
        except Exception:self.close();raise
    def _read_pointer(self):
        if not (self.root/'initialized').is_dir() or not self.config.state_path.is_file():raise ValueError('partial entry preserved; cannot recreate')
        value=json.loads((self.root/'current.json').read_text(encoding='utf-8'))
        if (set(value)!={'version','technical_variant','binding','profile_id','timeline_id'} or value['version']!=ENTRY_VERSION
            or value['technical_variant']!='multi-span' or value['binding']!=APPROVED_BINDING
            or any(type(value[k]) is not str or str(UUID(value[k]))!=value[k] for k in ('profile_id','timeline_id'))):raise ValueError('exact entry pointer required')
        return value
    def _validate_current_identity(self):validate_natural_feedback_entry(self.config,profile_id=self.identity[0],timeline_id=self.identity[1])
    @staticmethod
    def _history_state(product):
        response=product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,product.profile_id,product.timeline_id))
        if response.status.value=='available' and response.projection is not None:return 'available',response.projection.turns
        if response.status.value=='failed-closed':return 'failed-closed',None
        raise ValueError('entry history state unverified')
    def _open(self):
        return open_natural_feedback_product_live(self.config,identity_id=self.__dict__.pop('_fresh_identity_id',self.identity[0] if hasattr(self,'identity') else None),
            grant=self.grant,audit_path=self.audit_path,_transport=self.transport,observations=self.observations)
    def reopen(self):
        value=self._read_pointer()
        if (value['profile_id'],value['timeline_id'])!=self.identity:raise ValueError('entry identity witness changed')
        self._validate_current_identity();before=self._history_state(self.product);state=self.product.application.query_shared_activity()
        self.product.close();self.product=None;p=self._open()
        try:
            if self._history_state(p)!=before or p.application.query_shared_activity()!=state:raise ValueError('recovery changed canonical state')
        except Exception:p.close();raise
        self.product=p;return p

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--port',type=int,default=8796)
    args=parser.parse_args()
    if args.port!=8796:raise SystemExit('Only the reviewed independent port is accepted.')
    if not args.prepare:
        try:
            with urlopen('http://127.0.0.1:8796/health',timeout=4) as r:value=json.loads(r.read(1024))
        except URLError as error:
            if not isinstance(error.reason,ConnectionRefusedError):raise SystemExit('Port state unverified; no entry started.') from None
        except ConnectionRefusedError:pass
        else:
            if value!=dict(application=APPLICATION_ID):raise SystemExit('Unknown service; no entry opened.')
            return
    entry=NaturalFeedbackChatEntry(default_entry_root())
    try:
        if args.prepare:
            count=len(open_natural_feedback_audit(entry.audit_path,technical_variant='multi-span').snapshot())
            print(canonical_json(dict(status='prepared',application=APPLICATION_ID,audit_attempts=count,chat_turns=len(history(entry.product)),activity_revision=entry.product.application.query_shared_activity().view['activity_revision'],root=str(entry.root))),flush=True)
            return
        server=natural_feedback_server(entry.product,reopen=entry.reopen,port=8796)
        print('Natural feedback chat: http://127.0.0.1:8796',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
    finally:entry.close()

if __name__=='__main__':main()

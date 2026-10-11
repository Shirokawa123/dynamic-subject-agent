"""Owned experimental entry for the eligible choice mode; never serves a UI."""
import json,os
from pathlib import Path
from uuid import UUID
from serve_original_whole_chat import OriginalWholeChatEntry,DEFAULT_PACKAGE,ROOT
from serve_natural_feedback_chat import NaturalFeedbackChatEntry
from dynamic_subject_agent.local_product import LocalProductConfig,open_local_product,open_natural_feedback_product_live,validate_natural_feedback_entry
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.natural_feedback_choice_budget import NaturalFeedbackChoiceBudgetGrant,CHOICE_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
from dynamic_subject_agent.frozen_attempt import canonical_json

EXPERIMENT_PARENT=ROOT/'.artifacts/s157/scene-first'
VERSION='s157-selected-choice-experimental-entry-1'

class SelectedChoiceEntry(OriginalWholeChatEntry):
    def __init__(self,root, *, variant,transport,audit_path,package_path=DEFAULT_PACKAGE,observations=None):
        self.root=Path(root).resolve();self.product=None;self.variant=variant
        if self.root!=(EXPERIMENT_PARENT/'entry').resolve() or Path(audit_path).resolve()!=(EXPERIMENT_PARENT/'audit').resolve() or transport is None:
            raise ValueError('exact owned selected-candidate entry required')
        self.grant=NaturalFeedbackChoiceBudgetGrant(APPROVED_FEEDBACK_REVIEW,CHOICE_DEVELOPMENT,variant);self.grant.validate()
        self.transport,self.audit_path,self.observations=transport,Path(audit_path),observations
        self.config=LocalProductConfig(self.root/'DynamicSubjectAgent/m0/experiments',self.root/'state.json')
        fresh=not self.root.exists();content=self._review_package(Path(package_path).resolve()) if fresh else None
        try:
            if fresh:
                self.root.mkdir(parents=True,exist_ok=False);(self.root/'initialized').mkdir(exist_ok=False)
                with open_local_product(self.config,cognition=DormantDeepSeekCognition()) as author:
                    frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(content,APPROVED_BINDING['definition_basis'],True,True))
                    if frozen.status!='created':raise ValueError('independent candidate identity required')
                    self._fresh_id=frozen.view.identity_id
                self.product=self._open()
                state=self.product.application.query_shared_activity()
                if state.status!='available' or state.view['revision']!=0 or NaturalFeedbackChatEntry._history_state(self.product)!=('available',()):
                    raise ValueError('new candidate entry must be empty')
                value=dict(version=VERSION,variant=variant,binding=dict(APPROVED_BINDING),profile_id=self.product.profile_id,timeline_id=self.product.timeline_id)
                with (self.root/'current.json').open('x',encoding='utf-8') as f:f.write(canonical_json(value));f.flush();os.fsync(f.fileno())
            value=self._read_pointer();self.identity=value['profile_id'],value['timeline_id']
            validate_natural_feedback_entry(self.config,profile_id=self.identity[0],timeline_id=self.identity[1],technical_variant=variant)
            if self.product is None:self.product=self._open()
            if (self.product.profile_id,self.product.timeline_id)!=self.identity:raise ValueError('candidate entry identity changed')
        except Exception:self.close();raise

    def _read_pointer(self):
        if not (self.root/'initialized').is_dir() or not self.config.state_path.is_file():raise ValueError('partial candidate entry preserved')
        v=json.loads((self.root/'current.json').read_text(encoding='utf-8'))
        if (set(v)!={'version','variant','binding','profile_id','timeline_id'} or v['version']!=VERSION or v['variant']!=self.variant or v['binding']!=APPROVED_BINDING
            or any(type(v[k]) is not str or str(UUID(v[k]))!=v[k] for k in ('profile_id','timeline_id'))):raise ValueError('exact candidate pointer required')
        return v

    def _open(self):
        identity_id=self.__dict__.pop('_fresh_id',self.identity[0] if hasattr(self,'identity') else None)
        return open_natural_feedback_product_live(self.config,identity_id=identity_id,grant=self.grant,audit_path=self.audit_path,
            _transport=self.transport,observations=self.observations)

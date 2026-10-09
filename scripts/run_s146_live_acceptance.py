"""One approved S146 first scene; only the main agent executes --execute.

--self-check/--preflight create no product roots, transports or credentials.
The two form stages wait for one main-agent canonical semantic decision on
stdin. Stdout/checkpoints contain only closed metadata, counts and hashes.
Successful model text remains exclusively in the product canonical store.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sys
from threading import RLock
from time import perf_counter
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

from dynamic_subject_agent.deepseek import DeepSeekTransport
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind

REPO = Path(__file__).resolve().parents[1]
REVIEW_BASIS = 'e87c9db1f6f52409faee497ca05f0852362add519e461d48f50bee27d760977c'
SCENE_SHA = 'fbb87ebeec6a0dd0e8049d19bcf661fa5d4ac3064beaf7166f81170f6cc7c00a'
SCENE_PATH = REPO/'docs/experiments/s145/live-scene.json'
ROOT_RELATIVE = Path('DynamicSubjectAgent/working-understanding-development/s146/live-first-20261009-1')
REAL_LOCAL_APPDATA = Path('C:/Users/30252/AppData/Local')
PURPOSES = ('working-understanding-form', 'working-activity-choice', 'working-activity-reply')
MAX_REQUESTS = 15
SAFE_STATUSES = frozenset(('available', 'previewed', 'committed', 'replayed', 'terminal', 'pending',
    'no-op', 'unavailable', 'unknown', 'failed-closed', 'busy', 'conflict', 'cancelled', 'not-found'))


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {key:plain(item) for key,item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value.value if hasattr(value, 'value') else value


def digest(value):
    return sha256(canonical_json(plain(value)).encode('utf-8')).hexdigest()


def text_sha(text):
    return sha256(text.encode('utf-8')).hexdigest()


class AcceptanceStopped(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NormalEnd(AcceptanceStopped):
    """An observed bounded no-op/content decision, distinct from failure."""


def require(condition, code):
    if not condition:
        raise AcceptanceStopped(code)


def status_of(response):
    status = plain(getattr(response, 'status', None))
    return status if status in SAFE_STATUSES else 'unverified'


def safe_problem_code(value):
    from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
    codes=REVIEW_DIAGNOSTIC_CODES | {'working-understanding-insufficient','working-operation-unverified',
        'working-preview-unverified','working-state-unverified','working-operation-pending',
        'working-source-isolated-canonical-pending','working-source-permission-changed',
        'character-credential-unavailable','structured-choice-invalid','working-output-invalid',
        'expression-invalid','delivery-unverified','audit-failed',
        'original-whole-provider-failed','original-whole-history-changed'}
    return value if type(value) is str and value in codes else ('other' if value is not None else None)


def strict_json(text):
    def pairs(items):
        value = {}
        for key,item in items:
            if key in value:
                raise ValueError('duplicate-json-key')
            value[key] = item
        return value
    def invalid_number(_value):
        raise ValueError('non-json-number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_number)


def validate_preview(preview, purpose):
    from dynamic_subject_agent.working_understanding_remote_preview import working_remote_request_preview
    require(purpose in PURPOSES and type(preview) is dict and set(preview)=={'policy','payload'},
        'closed-working-preview-required')
    wire = working_remote_request_preview(ModelTask(ModelTaskKind(purpose), preview))
    body, payload = wire['body'], preview['payload']
    protocol = {key:value for key,value in body.items() if key!='messages'}
    expected = dict(model='deepseek-flash', max_tokens=4096, thinking={'type':'enabled'},
        reasoning_effort='high', stream=False)
    if purpose != PURPOSES[2]:
        expected['response_format'] = {'type':'json_object'}
    require(protocol==expected and wire['endpoint']=='https://api.deepseek.com/chat/completions'
        and wire['timeout_seconds']==30 and wire['automatic_retries']==0
        and wire['requests_per_manual_action']==1, 'approved-protocol-parameters-changed')
    require(body['messages'][0]['content']==preview['policy']
        and strict_json(body['messages'][1]['content'])==payload, 'wire-does-not-match-preview')
    if purpose!=PURPOSES[0]:
        evidence = payload['evidence'] if purpose==PURPOSES[2] else payload
        require(evidence['shared_experience'] is None, 'new-working-has-no-legacy-e1')
    return wire


def preflight():
    """Pure read/qualification checks, including real rather than virtual AppData."""
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.working_understanding_live import ApprovedWorkingUnderstandingGrant, working_live_contract
    review = json.loads((REPO/'docs/experiments/s145/review.json').read_text(encoding='utf-8'))
    unsigned = dict(review); unsigned.pop('review_basis')
    scene = json.loads(SCENE_PATH.read_text(encoding='utf-8'))
    require(review['review_basis']==digest(unsigned)==REVIEW_BASIS, 'approved-review-pin-changed')
    require(digest(scene)==SCENE_SHA==review['first_live_scene_sha256'], 'first-live-scene-pin-changed')
    require(review['existing_material_binding']==APPROVED_BINDING and sorted(PURPOSES)==review['new_purposes']
        and review['existing_shared_experience']=='always-null-no-legacy-E1-selection-capability', 'approved-material-or-purposes-changed')
    require(scene['maximum_first_requests']==MAX_REQUESTS==review['first_live_scene_maximum_requests']
        and scene['requests_per_stage']==1 and scene['automatic_retries']==0
        and scene['independent_fresh_identity'] is True and scene['existing_user_roots_touched'] is False
        and scene['simulated_time_used_to_claim_real_cross_day'] is False, 'bounded-first-scene-changed')
    for prefix in ('source', 'correction'):
        require(len(scene[prefix+'_messages'])==len(scene[prefix+'_quotes'])==2, 'exactly-two-source-pairs-required')
        for message,quote in zip(scene[prefix+'_messages'], scene[prefix+'_quotes']):
            require(type(message) is str and 0<len(message)<=1000 and type(quote) is str
                and 0<len(quote)<=400 and quote in message, 'fixed-source-boundary-changed')
    require(len(scene['gap_messages'])==3, 'fixed-gap-count-changed')
    grant = ApprovedWorkingUnderstandingGrant(REVIEW_BASIS, confirmed=True)
    grant.validate()
    contract = working_live_contract(APPROVED_BINDING)
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    require(local.is_absolute() and local.resolve()==REAL_LOCAL_APPDATA.resolve(), 'real-local-appdata-required')
    root = local/ROOT_RELATIVE
    require(root.resolve()==REAL_LOCAL_APPDATA/ROOT_RELATIVE and not root.exists() and not root.is_symlink(),
        'new-owned-first-root-required-existing-evidence-retained')
    return scene, root, digest(contract)


class SafeReport:
    def __init__(self, root, contract_sha):
        self.root, self.path = root, root/'metadata.json'
        self.lock, self.io_error_types = RLock(), []
        self.data = dict(version='s146-first-live-working-understanding-1', review_basis=REVIEW_BASIS,
            first_live_scene_sha256=SCENE_SHA, runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            live_contract_sha256=contract_sha, independent_root=str(root), status='preparing',
            synthetic_outputs=False, simulated_day=False, real_cross_day_verified=False,
            day_boundary_logic_verified=False, character_effect_verified=False,
            maximum_first_requests=MAX_REQUESTS, requests_per_stage=1, automatic_retries=0,
            raw_text_exported=False, reasoning_text_exported=False, service_started=False,
            direct_https_without_proxy=True, remote_calls=0, credential_read_attempts=0,
            remote_call_count_semantics='single-provider-transport-attempts-not-confirmed-delivery',
            stages=[], transport=[], audit=[], checks={}, semantic_reviews=[], first_failure=None,
            audit_count=0, person_content_assessment='main-canonical-review-required')

    def save(self):
        with self.lock:
            try:
                self.data['checkpoint_io_error_types'] = self.io_error_types[:]
                temporary = self.path.with_name('metadata.json.next')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                temporary.replace(self.path)
                return True
            except Exception as error:
                name = type(error).__name__
                if name not in self.io_error_types:
                    self.io_error_types.append(name)
                return False

    def checked_save(self, code):
        require(self.save() and not self.io_error_types, code)

    def begin(self, label, **metadata):
        row = dict(stage=label, status='started', error_type=None, **metadata)
        self.data['stages'].append(row)
        self.checked_save('checkpoint-before-stage-failed')
        return row

    def stop(self, error):
        normal = isinstance(error, NormalEnd)
        code = error.code if isinstance(error, AcceptanceStopped) else 'unexpected-runner-failure'
        stage = self.data['stages'][-1] if self.data['stages'] else None
        if stage and stage['status']=='started':
            stage.update(status='failed-or-unverified', error_type=type(error).__name__)
        stop = dict(stage=None if stage is None else stage['stage'], stop_code=code, error_type=type(error).__name__)
        if not normal and self.data['first_failure'] is None:
            self.data['first_failure'] = stop
        self.data.update(status='normal-bounded-end' if normal else 'stopped-on-first-failure-or-integrity',
            stopped_stage=stop['stage'], stop_code=code, error_type=stop['error_type'], runner_exit_code=0 if normal else 1)
        self.save()


def final_boundary(response, purpose, preview):
    """Inspect one response transiently; never retain final/reasoning strings."""
    from dynamic_subject_agent.deepseek import _ACCEPTED_RESPONSE_MODELS
    row = dict(http_status=response.status_code, response_body_bytes=len(response.body),
        response_body_sha256=sha256(response.body).hexdigest(), exact_output_contract=False,
        final_value_sha256=None, final_text_sha256=None, reply_sha256=None)
    try:
        envelope = strict_json(response.body.decode('utf-8'))
        choices, usage = envelope.get('choices'), envelope.get('usage')
        require(type(choices) is list and len(choices)==1 and type(choices[0]) is dict, 'response-choice-invalid')
        message = choices[0].get('message')
        require(type(message) is dict, 'response-message-invalid')
        content = message.get('content')
        row.update(model='deepseek-flash' if envelope.get('model')=='deepseek-flash' else 'other',
            assistant_role=message.get('role')=='assistant', finish_reason='stop' if choices[0].get('finish_reason')=='stop' else 'other',
            reasoning_chars=len(message['reasoning_content']) if type(message.get('reasoning_content')) is str else 0)
        row['usage'] = {key:count for key,count in (usage or {}).items()
            if key in ('prompt_tokens','completion_tokens','total_tokens') and type(count) is int and 0<=count<2**53}
        require(response.status_code==200 and len(response.body)<=65536 and envelope.get('model') in _ACCEPTED_RESPONSE_MODELS
            and message.get('role')=='assistant' and choices[0].get('finish_reason')=='stop'
            and 'delta' not in choices[0] and message.get('tool_calls') in (None,[])
            and message.get('refusal') in (None,'') and message.get('final') in (None,'')
            and (message.get('reasoning_content') is None or type(message.get('reasoning_content')) is str)
            and type(usage) is dict and type(usage.get('prompt_tokens')) is int and usage['prompt_tokens']>=0
            and type(usage.get('completion_tokens')) is int and 0<=usage['completion_tokens']<=4096
            and type(content) is str and bool(content.strip()), 'response-envelope-or-final-invalid')
        row['final_text_sha256'] = text_sha(content)
        if purpose==PURPOSES[2]:
            from dynamic_subject_agent.original_whole_chat import validate_whole_reply
            value = dict(reply_text=content, language='zh'); validate_whole_reply(value)
            row.update(reply_chars=len(content), reply_sha256=text_sha(content), wrapped_model_result_value_sha256=digest(value))
        else:
            value = strict_json(content)
            if purpose==PURPOSES[0]:
                from dynamic_subject_agent.working_understanding import validate_form
                validate_form(value, preview['payload']['activity_result'] is not None)
                row.update(formation_status=value['status'], statement_chars=len(value['statement']),
                    statement_sha256=text_sha(value['statement']), basis_refs=list(value['basis_refs']))
            else:
                from dynamic_subject_agent.first_life import validate_plan, LIFE_REASONS
                allowed_refs = {'W1'} if preview['payload']['working_understanding'] is not None else set()
                require(type(value) is dict and set(value)=={'action','plan','reason_code','basis_refs','decision_note'}
                    and value['action'] in preview['payload']['current_activity']['allowed_actions']
                    and value['reason_code'] in LIFE_REASONS and type(value['decision_note']) is str
                    and 0<len(value['decision_note'].strip())<=160 and '\x00' not in value['decision_note']
                    and type(value['basis_refs']) is list and all(type(x) is str for x in value['basis_refs'])
                    and len(value['basis_refs'])==len(set(value['basis_refs'])) and set(value['basis_refs'])<=allowed_refs,
                    'response-choice-output-invalid')
                if value['action'] in ('start','revise'):
                    validate_plan(value['plan'])
                else:
                    require(value['plan'] is None, 'response-noop-choice-has-plan')
                row.update(action=value['action'], plan_sha256=None if value['plan'] is None else digest(value['plan']),
                    basis_refs=list(value['basis_refs']), decision_note_sha256=digest(value['decision_note']))
        row.update(exact_output_contract=True, final_value_sha256=digest(value))
    except (Exception,):
        # Exception messages may contain response text; only a closed validity
        # flag escapes. The production Adapter independently adjudicates it.
        pass
    return row


def safe_observation(value):
    from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
    row = {}
    for key in ('task_kind','purpose'):
        if value.get(key) in PURPOSES: row[key]=value[key]
    if value.get('status') in ('complete','unavailable','unknown','failed-closed'): row['status']=value['status']
    for key in ('request_digest','wire_sha256'):
        if type(value.get(key)) is str and re.fullmatch('[0-9a-f]{64}', value[key]): row[key]=value[key]
    codes=REVIEW_DIAGNOSTIC_CODES | {'character-credential-unavailable','structured-choice-invalid',
        'working-output-invalid','expression-invalid','delivery-unverified','audit-failed'}
    if type(value.get('error_code')) is str and value['error_code'] in codes: row['error_code']=value['error_code']
    if 'model' in value: row['model']='deepseek-flash' if value['model']=='deepseek-flash' else 'other'
    if value.get('finish_reason') in ('stop','length','tool_calls','content_filter','aborted','other'): row['finish_reason']=value['finish_reason']
    if type(value.get('elapsed_seconds')) in (int,float) and math.isfinite(value['elapsed_seconds']): row['elapsed_seconds']=max(0.,value['elapsed_seconds'])
    if type(value.get('usage')) is dict:
        row['usage']={key:count for key,count in value['usage'].items() if key in
            ('prompt_tokens','completion_tokens','total_tokens','reasoning_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')
            and type(count) is int and 0<=count<2**53}
    return row


class ObservedTransport(DeepSeekTransport):
    def __init__(self, report):
        from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport, DeepSeekCredentialResolver
        from dynamic_subject_agent.local_product import _WindowsLabResolver
        class CountedResolver(DeepSeekCredentialResolver):
            def resolve(self, credential_ref):
                from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
                require((credential_ref.backend_id,credential_ref.key_id)==
                    (DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID),'unapproved-credential-slot')
                report.data['credential_read_attempts'] += 1
                report.checked_save('checkpoint-before-credential-read-failed')
                return _WindowsLabResolver().resolve(credential_ref)
        self.report = report
        self.delegate = DeepSeekUrlLibTransport(credential_resolver=CountedResolver(),
            _opener=build_opener(ProxyHandler({})).open)
        self.expected, self.active_stage, self.stage_calls, self.total_calls = None, None, 0, 0

    def arm(self, label, preview=None, purpose=None):
        self.active_stage, self.stage_calls, self.expected = label, 0, None
        if preview is not None:
            preview=deepcopy(preview)
            wire = validate_preview(preview,purpose)
            self.expected = dict(purpose=purpose, endpoint=wire['endpoint'], wire_sha256=wire['wire_sha256'],
                task_sha256=digest(preview), payload_sha256=digest(preview['payload']),
                policy_sha256=text_sha(preview['policy']), output_mode='text' if purpose==PURPOSES[2] else 'json',
                preview=preview)
        return None if self.expected is None else {key:value for key,value in self.expected.items() if key!='preview'}

    def disarm(self):
        self.expected = None

    def post_json(self, **kwargs):
        require(self.expected is not None and self.stage_calls==0 and self.total_calls<MAX_REQUESTS
            and not self.report.io_error_types, 'extra-or-unarmed-transport-request')
        require(kwargs['endpoint']==self.expected['endpoint'] and kwargs['timeout_seconds']==30
            and sha256(kwargs['body']).hexdigest()==self.expected['wire_sha256'], 'actual-http-wire-differs-from-preview')
        self.stage_calls+=1; self.total_calls+=1
        self.report.data['remote_calls']=self.total_calls
        row = dict(stage=self.active_stage, status='request-started', error_type=None,
            **{key:value for key,value in self.expected.items() if key!='preview'})
        self.report.data['transport'].append(row)
        self.report.checked_save('checkpoint-before-provider-failed')
        started=perf_counter()
        try:
            response=self.delegate.post_json(**kwargs)
            row.update(status='response-received',response_boundary=final_boundary(response,self.expected['purpose'],self.expected['preview']))
            return response
        except BaseException as error:
            row.update(status='transport-exception',error_type=type(error).__name__)
            raise
        finally:
            row['elapsed_seconds']=max(0.,perf_counter()-started)
            self.report.save()  # Never substitute an already received body.


def semantic_decision(line, statement_sha):
    """A single exact canonical review token; no retries or inferred approval."""
    if not line: raise NormalEnd('canonical-semantic-review-eof')
    try: value=strict_json(line)
    except Exception: raise AcceptanceStopped('canonical-semantic-review-token-invalid') from None
    require(type(value) is dict and set(value)=={'statement_sha256','decision'}
        and value['statement_sha256']==statement_sha and value['decision'] in ('continue','stop-out-of-scope'),
        'canonical-semantic-review-token-invalid')
    if value['decision']=='stop-out-of-scope': raise NormalEnd('canonical-working-understanding-out-of-scope')
    return value['decision']


class FirstRun:
    def __init__(self, root, scene, report):
        from dynamic_subject_agent.local_product import LocalProductConfig
        from dynamic_subject_agent.working_understanding_live import ApprovedWorkingUnderstandingGrant
        self.root,self.scene,self.report=root,scene,report
        self.config=LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments',root/'state.json')
        self.audit_path=root/'audit'; self.grant=ApprovedWorkingUnderstandingGrant(REVIEW_BASIS,confirmed=True)
        self.transport,self.observations,self.product=ObservedTransport(report),[],None

    def audit(self):
        from dynamic_subject_agent.working_understanding_live import open_working_understanding_audit
        audit=list(open_working_understanding_audit(self.audit_path).snapshot())
        require(len(audit)<=MAX_REQUESTS and all(row['purpose'] in PURPOSES for row in audit), 'audit-purpose-or-count-unverified')
        self.report.data.update(audit=audit,audit_count=len(audit))
        return audit

    def counts(self):
        return len(self.audit())

    def view(self):
        sent=self.transport.total_calls
        result=self.product.application.query_working_understanding()
        require(status_of(result)=='available' and type(result.view) is dict and sent==self.transport.total_calls,
            'canonical-working-view-unverified')
        return plain(result.view)

    def shared(self):
        sent=self.transport.total_calls
        result=self.product.application.query_shared_activity()
        require(status_of(result)=='available' and type(result.view) is dict and sent==self.transport.total_calls,
            'canonical-shared-decision-unverified')
        return plain(result.view)

    def history(self):
        from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
        sent=self.transport.total_calls
        result=self.product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            self.product.profile_id,self.product.timeline_id))
        require(status_of(result)=='available' and result.projection is not None and sent==self.transport.total_calls,
            'canonical-history-unverified')
        return plain(result.projection.turns)

    def fingerprint(self):
        return digest(dict(view=self.view(),shared=self.shared(),history=self.history()))

    def verify_support(self,preview,purpose,view):
        from dynamic_subject_agent.working_understanding import support_projection
        payload=preview['payload']
        evidence=payload['evidence'] if purpose==PURPOSES[2] else payload
        require(evidence['shared_experience'] is None
            and evidence['working_understanding']==support_projection(view['visible_understanding']),
            'preview-working-support-differs-from-current-canonical-closure')
        if purpose==PURPOSES[2]:
            result=view['visible_result']
            expected=None if result is None else dict(kind=result['kind'],plan=result['plan'])
            require(evidence['activity_result']==expected,'reply-result-differs-from-current-canonical-closure')
        else:
            require(payload['current_plan']==view['current_plan'],'choice-plan-differs-from-current-canonical-closure')

    def opening(self):
        from dynamic_subject_agent.local_product import open_working_understanding_product_live
        return open_working_understanding_product_live(self.config,grant=self.grant,audit_path=self.audit_path,
            identity_id=self.identity_id,_transport=self.transport,observations=self.observations)

    def create(self):
        from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
        from dynamic_subject_agent.application import ApplicationFacade
        from dynamic_subject_agent.local_product import open_local_product
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
        from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
        row=self.report.begin('create-independent-working-live',maximum_requests=0)
        self.transport.arm(row['stage'])
        package=REPO/'.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
        preview=ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(package,
            APPROVED_BINDING['definition_basis'],APPROVED_BINDING['runtime_asset_sha'],APPROVED_BINDING['persona_digest'],
            APPROVED_BINDING['subject_id'],APPROVED_BINDING['anchor_id']))
        require(preview.status=='previewed' and preview.review_basis==APPROVED_BINDING['review_basis'], 'approved-character-material-mismatch')
        with open_local_product(self.config,cognition=DormantDeepSeekCognition()) as author:
            frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
                package.read_text(encoding='utf-8'),APPROVED_BINDING['definition_basis'],True,True))
            require(frozen.status=='created','new-dormant-identity-required')
            self.identity_id=frozen.view.identity_id
        self.product=self.opening()
        view=self.view()
        require(not self.history() and view['current_plan'] is None and view['visible_understanding'] is None
            and view['visible_result'] is None and self.counts()==self.transport.total_calls==0,
            'fresh-live-state-or-zero-call-precondition-unverified')
        row.update(status='complete',audit_before=0,audit_after=0)
        self.report.checked_save('checkpoint-after-create-failed')

    def zero(self,label,action):
        before,sent=self.counts(),self.transport.total_calls
        row=self.report.begin(label,maximum_requests=0,audit_before=before)
        self.transport.arm(label)
        result=action()
        require(self.counts()==before and self.transport.total_calls==sent and not self.report.io_error_types,
            'zero-operation-produced-request-or-integrity-unknown')
        row.update(status='complete',audit_after=before,transport_count=0)
        self.report.checked_save('checkpoint-after-zero-operation-failed')
        return result

    def model_stage(self,label,purpose,preview,operation):
        before,sent,observed=self.counts(),self.transport.total_calls,len(self.observations)
        row=self.report.begin(label,purpose=purpose,maximum_requests=1,audit_before=before)
        row.update(**self.transport.arm(label,preview,purpose))
        self.report.checked_save('checkpoint-before-model-stage-failed')
        try:
            result=operation()
            row['status']=status_of(result)
            row['problem_code']=safe_problem_code(getattr(result,'problem_code',None))
            row['failure_code']=safe_problem_code(getattr(getattr(result,'projection',None),'failure_code',None))
        except BaseException as error:
            row.update(status='failed-or-unverified',error_type=type(error).__name__)
            raise
        finally:
            self.transport.disarm()
            row.update(transport_count=self.transport.total_calls-sent,
                observations=[safe_observation(value) for value in self.observations[observed:]])
            try: row['audit_after']=self.counts()
            except Exception as error:
                row.update(audit_after=None,audit_unverified=True,audit_error_type=type(error).__name__)
            self.report.save()
        require(not row.get('audit_unverified') and not self.report.io_error_types,'model-stage-audit-or-checkpoint-unverified')
        audit=self.audit()
        require(self.counts()-before<=1 and self.transport.total_calls-sent<=1,'single-stage-request-bound-exceeded')
        projection=getattr(result,'projection',None)
        require(row['status'] in ('terminal','committed','no-op') and not getattr(projection,'failure_code',None),
            'first-technical-failure-'+row['status'])
        require(self.counts()-before==self.transport.total_calls-sent==1,'stage-without-one-verified-request')
        raw=self.report.data['transport'][-1].get('response_boundary',{})
        require(raw.get('exact_output_contract') is True and audit[-1]['status']=='complete'
            and audit[-1]['purpose']==purpose and audit[-1]['request_digest']==digest(preview)
            and audit[-1]['output_digest']==raw.get('final_value_sha256'),'raw-http-audit-or-preview-mismatch')
        row.update(raw_http_matches_completed_audit=True,
            receipt_sha256=None if getattr(result,'receipt',None) is None else digest(result.receipt))
        self.report.checked_save('checkpoint-after-model-stage-failed')
        return result,row,raw

    def reply(self,label,text,*,disabled=False,expected_plan=None):
        from dynamic_subject_agent.timeline import SubjectCommand
        before=self.history()
        candidate=self.product.application.preview_working_activity('reply',text)
        require(status_of(candidate)=='previewed','reply-preview-'+status_of(candidate))
        preview=plain(candidate.view); payload=preview['payload']
        self.verify_support(preview,PURPOSES[2],self.view())
        require(payload['turn']['current_message']==text,'reply-current-message-differs')
        if disabled:
            require(payload['evidence']==dict(shared_experience=None,activity_result=None,working_understanding=None)
                and payload['exchange']==[],'disabled-preview-retains-old-chain')
        if expected_plan is not None:
            require(payload['evidence']['activity_result']['plan']==expected_plan,'reply-preview-differs-from-committed-result')
        def operation():
            result=self.product.application.submit(SubjectCommand.contribute_utterance(
                target_profile_id=self.product.profile_id,target_timeline_id=self.product.timeline_id,
                declared_intent='ask-collaborator-status',utterance=text,language='zh',provenance='project-original'),
                idempotency_key='s146-live-'+str(uuid4()))
            deadline=perf_counter()+150
            while status_of(result)=='pending' and perf_counter()<deadline:
                result=self.product.application.wait(result.operation_ref,timeout_seconds=30)
            return result
        _,row,raw=self.model_stage(label,PURPOSES[2],preview,operation)
        history=self.history()
        require(len(history)==len(before)+1 and history[-1]['user_text']==text,'canonical-complete-round-missing')
        canonical=dict(reply_text=history[-1]['assistant_text'],language='zh')
        require(text_sha(canonical['reply_text'])==raw['reply_sha256'] and digest(canonical)==raw['final_value_sha256'],
            'raw-final-reply-differs-from-canonical')
        row.update(raw_reply_equals_canonical=True,canonical_head_sequence=history[-1]['head_sequence'],
            canonical_reply_sha256=raw['reply_sha256'],reply_chars=raw['reply_chars'],disabled_whole_chain_filtered=disabled)
        self.report.checked_save('checkpoint-after-canonical-reply-failed')
        return history[-1]['head_sequence']

    def choice(self,label,*,initial=False):
        from dynamic_subject_agent.shared_activity import SharedActivityStepRequest
        before=self.view()
        candidate=self.product.application.preview_working_activity('choice')
        require(status_of(candidate)=='previewed','choice-preview-'+status_of(candidate))
        preview=plain(candidate.view)
        self.verify_support(preview,PURPOSES[1],before)
        if initial:
            require(before['current_plan'] is None and before['visible_understanding'] is None,
                'first-plan-is-not-independent-empty-baseline')
        request=SharedActivityStepRequest(self.product.profile_id,self.product.timeline_id,str(uuid4()),before['revision'])
        result,row,raw=self.model_stage(label,PURPOSES[1],preview,lambda:self.product.application.advance_working_activity(request))
        view,shared=self.view(),self.shared(); decision=shared['decision']
        canonical=dict(action=decision['action'],plan=shared['current_plan'] if decision['action'] in ('start','revise') else None,
            reason_code=decision['reason_code'],basis_refs=decision['basis_refs'],decision_note=decision['decision_note'])
        require(digest(canonical)==raw['final_value_sha256'],'raw-choice-differs-from-canonical')
        row.update(raw_choice_equals_canonical=True,action=canonical['action'],canonical_plan_sha256=digest(view['current_plan']),
            receipt_sha256=digest(result.receipt))
        self.report.checked_save('checkpoint-after-canonical-choice-failed')
        if canonical['action'] not in ('start','revise') or view['current_plan'] is None:
            raise NormalEnd('no-eligible-new-plan' if initial else 'no-actual-plan-change')
        if view['current_plan']==before['current_plan']:
            raise NormalEnd('no-actual-plan-change')
        require(view['visible_result']['plan']==view['current_plan'],'canonical-result-does-not-match-plan')
        if initial:
            require(view['visible_result']['source_dependencies']==[],'first-A1-plan-has-dependent-sources')
        if not initial:
            require(preview['payload']['working_understanding'] is not None,'later-choice-without-working-understanding')
        return request,view['current_plan']

    def form(self,label,sources,*,activity_plan=None):
        from dynamic_subject_agent.working_understanding import WorkingSourceQuote,WorkingUnderstandingRequest
        before=self.view()
        request=WorkingUnderstandingRequest(self.product.profile_id,self.product.timeline_id,str(uuid4()),before['revision'],
            tuple(WorkingSourceQuote(head,quote) for head,quote in sources),confirmed=True)
        candidate=self.product.application.preview_working_understanding(request)
        require(status_of(candidate)=='previewed','form-preview-'+status_of(candidate))
        preview=plain(candidate.view)
        expected_activity=None if activity_plan is None else dict(label='A1',kind='composition-text',plan=activity_plan)
        require(preview['payload']['exchanges']==[dict(label='U'+str(i+1),quote=quote) for i,(_,quote) in enumerate(sources)]
            and preview['payload']['activity_result']==expected_activity,'form-input-differs-from-selected-canonical-sources')
        result,row,raw=self.model_stage(label,PURPOSES[0],preview,lambda:self.product.application.apply_working_understanding(request))
        view=self.view()
        if raw['formation_status']=='insufficient':
            require(status_of(result)=='no-op' and getattr(result,'problem_code',None)=='working-understanding-insufficient'
                and view['formation_status']=='insufficient' and view['understanding']==before['understanding'],
                'insufficient-is-not-typed-noop-or-lost-prior-understanding')
            row['typed_insufficient_noop']=True
            self.report.checked_save('checkpoint-after-insufficient-noop-failed')
            raise NormalEnd('working-understanding-insufficient')
        require(status_of(result)=='committed' and view['formation_status']=='formed'
            and view['visible_understanding'] is not None,'formed-understanding-not-visible')
        understanding=view['visible_understanding']
        canonical=dict(status='formed',scope=understanding['scope'],statement=understanding['statement'],basis_refs=understanding['basis_refs'])
        require(digest(canonical)==raw['final_value_sha256']
            and [(x['source_head_sequence'],x['quote']) for x in understanding['sources']]==sources,
            'raw-form-or-committed-sources-differ')
        actual=understanding['activity_result']
        require((actual is None and activity_plan is None) or (actual is not None and actual['kind']=='composition-text'
            and actual['plan']==activity_plan),'committed-A1-differs-from-independent-plan')
        row.update(raw_form_equals_canonical=True,canonical_statement_sha256=text_sha(understanding['statement']),
            canonical_understanding_sha256=digest(understanding),canonical_head_sequence=plain(result.receipt)['head_sequence'])
        self.report.checked_save('checkpoint-after-canonical-form-failed')
        self.semantic_gate(label,understanding,row['canonical_head_sequence'])

    def semantic_gate(self,label,understanding,head):
        statement_sha=text_sha(understanding['statement'])
        gate=dict(stage=label,canonical_head_sequence=head,statement_sha256=statement_sha,
            understanding_sha256=digest(understanding),current_plan_sha256=digest(self.view()['current_plan']),status='awaiting')
        self.report.data['semantic_reviews'].append(gate)
        self.report.data['status']='awaiting-canonical-semantic-review'
        self.report.checked_save('checkpoint-before-semantic-review-failed')
        print(json.dumps({**gate,'status':'awaiting-canonical-semantic-review'},ensure_ascii=False),flush=True)
        try:
            decision=semantic_decision(sys.stdin.readline(512),statement_sha)
        except BaseException as error:
            gate.update(status='stopped',stop_code=error.code if isinstance(error,AcceptanceStopped) else 'semantic-review-input-failed')
            self.report.save(); raise
        gate.update(status='accepted',decision=decision)
        self.report.data['status']='running'
        self.report.checked_save('checkpoint-after-semantic-review-failed')

    def reopen(self):
        fingerprint=self.fingerprint()
        def action():
            self.product.close(); self.product=None
            self.product=self.opening()
            require(self.fingerprint()==fingerprint,'reopen-changed-canonical-business-state')
        self.zero('close-and-reopen-zero-model',action)

    def nonce(self,request):
        fingerprint=self.fingerprint()
        result=self.zero('same-nonce-read-zero-model',lambda:self.product.application.advance_working_activity(request))
        require(status_of(result)=='replayed' and self.fingerprint()==fingerprint,'same-nonce-changed-state-or-not-replayed')

    def disable(self):
        from dynamic_subject_agent.working_understanding import WorkingUnderstandingRequest
        request=WorkingUnderstandingRequest(self.product.profile_id,self.product.timeline_id,str(uuid4()),self.view()['revision'],action='disable',confirmed=True)
        result=self.zero('disable-understanding-zero-model',lambda:self.product.application.apply_working_understanding(request))
        require(status_of(result)=='committed','explicit-disable-not-committed')
        view=self.view()
        require(view['visible_understanding'] is None and view['current_plan'] is None and view['visible_result'] is None,
            'disabled-canonical-derived-chain-still-visible')

    def close(self):
        self.transport.disarm()
        if self.product is not None:
            self.product.close(); self.product=None


def execute_scene(run,scene):
    """The immutable single branch; exceptions/normal ends abort this sequence."""
    heads=[run.reply('source-reply-'+str(i+1),text) for i,text in enumerate(scene['source_messages'])]
    _,first_plan=run.choice('independent-choice-1',initial=True)
    run.form('form-from-two-quotes-and-actual-plan',list(zip(heads,scene['source_quotes'])),activity_plan=first_plan)
    for i,text in enumerate(scene['gap_messages']): run.reply('gap-reply-'+str(i+1),text)
    require(all(row['head_sequence'] not in heads for row in run.history()[-2:]),'selected-sources-still-in-recent-two-window')
    run.reopen()
    request,plan=run.choice('choice-using-valid-understanding')
    run.reply('result-reply',scene['result_question'],expected_plan=plan)
    run.nonce(request); run.disable()
    run.reply('disabled-reply',scene['result_question'],disabled=True)
    corrected=[run.reply('correction-reply-'+str(i+1),text) for i,text in enumerate(scene['correction_messages'])]
    run.form('rebuild-from-new-two-quotes',list(zip(corrected,scene['correction_quotes'])))
    _,corrected_plan=run.choice('corrected-choice')
    run.reply('corrected-result-reply',scene['result_question'],expected_plan=corrected_plan)


def self_check():
    """Pure boundary/control fixtures, with no product or credential construction."""
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
    marker='PRIVATE_FIXTURE_FINAL_AND_REASONING'
    reply=dict(model='deepseek-flash',usage=dict(prompt_tokens=1,completion_tokens=2),choices=[dict(
        finish_reason='stop',message=dict(role='assistant',content='合成完整短回复。',reasoning_content=marker))])
    raw=final_boundary(DeepSeekHttpResponse(200,json.dumps(reply).encode()),PURPOSES[2],{})
    require(raw['exact_output_contract'] and marker not in json.dumps(raw),'self-check-private-boundary-exported')
    statement_sha='1'*64
    require(semantic_decision(json.dumps(dict(statement_sha256=statement_sha,decision='continue')),statement_sha)=='continue',
        'self-check-semantic-continue-failed')
    rejected=0
    for line in ('',json.dumps(dict(statement_sha256='2'*64,decision='continue')),
        json.dumps(dict(statement_sha256=statement_sha,decision='unknown')),
        json.dumps(dict(statement_sha256=statement_sha,decision='stop-out-of-scope'))):
        try: semantic_decision(line,statement_sha)
        except AcceptanceStopped: rejected+=1
        else: raise AcceptanceStopped('self-check-semantic-gate-opened')
    return dict(status='self-check-passed',semantic_gate_rejections=rejected,private_text_exported=False,
        product_roots_created=0,product_opened=False,transport_created=False,remote_calls=0,credential_reads=0)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--self-check',action='store_true'); modes.add_argument('--preflight',action='store_true')
    modes.add_argument('--execute',action='store_true'); args=parser.parse_args(argv)
    report,run=None,None
    try:
        if args.self_check:
            print(json.dumps(self_check(),ensure_ascii=False),flush=True); return 0
        scene,root,contract_sha=preflight()
        if args.preflight:
            print(json.dumps(dict(status='preflight-passed',review_basis=REVIEW_BASIS,scene_sha256=SCENE_SHA,
                runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),maximum_first_requests=MAX_REQUESTS,
                product_roots_created=0,product_opened=False,transport_created=False,remote_calls=0,credential_reads=0)),flush=True)
            return 0
        root.mkdir(parents=True,exist_ok=False)
        report=SafeReport(root,contract_sha); report.checked_save('initial-checkpoint-failed')
        run=FirstRun(root,scene,report); run.create(); execute_scene(run,scene)
        require(run.counts()==run.transport.total_calls==MAX_REQUESTS,'complete-scene-request-count-unverified')
        report.data.update(status='complete-first-engineering-scene',runner_exit_code=0,
            main_canonical_form_semantic_reviews=2,real_reopen_verified=True)
        report.checked_save('final-complete-checkpoint-failed')
    except BaseException as error:
        if report is None:
            print(json.dumps(dict(status='preflight-stopped',error_type=type(error).__name__,
                stop_code=error.code if isinstance(error,AcceptanceStopped) else 'unexpected-preflight-failure',
                product_roots_created=0,remote_calls=0,credential_reads=0)),flush=True)
            return 1
        report.stop(error)
    finally:
        if run is not None:
            try: run.close()
            except BaseException as error:
                report.data['close_error_type']=type(error).__name__
                report.stop(AcceptanceStopped('final-product-close-unverified'))
            try:
                if run.audit_path.exists(): run.audit()
            except BaseException as error:
                report.data['final_audit_error_type']=type(error).__name__
                report.stop(AcceptanceStopped('final-audit-unverified'))
        if report is not None:
            if not report.save() or report.io_error_types:
                report.stop(AcceptanceStopped('final-checkpoint-unverified'))
            print(json.dumps({key:value for key,value in report.data.items() if key not in ('stages','transport')},
                ensure_ascii=False),flush=True)
    return 0 if report is None else report.data.get('runner_exit_code',1)


if __name__=='__main__':
    raise SystemExit(main())

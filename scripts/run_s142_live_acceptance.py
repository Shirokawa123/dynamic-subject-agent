"""One approved S142 first scene, at most five requests and zero retries.

Only hashes, bounded status/envelope/usage and counts reach the report.
Actual model text remains canonical; simulation is explicitly a trigger label.
Run --preflight for immutable pins and unused-resource guards without opening
an identity, audit, transport or credential backend. Main owns real execution.
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
from threading import RLock
from time import perf_counter
from uuid import uuid4

from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekUrlLibTransport
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from observe_whole_reply_boundaries import response_metadata

REPO = Path(__file__).resolve().parents[1]
REVIEW_BASIS = '153bc6e8bfe766a8cfc7a852b4ae295ea7acf8e2e20ea960d2ad7d7a91e08f06'
SCENARIO_SHA = '28d37c3ff2d3e4939de7cf7e3e6362aaa5a34d0a89fb1b87f3891cdc613f9315'
SCENE_PATH = REPO/'docs/experiments/s142/live-first-scene.json'
SCENE_SHA = '3786fe9d37c8d4346e80c81b2b60f0b3e1fefb3c4338c0e8c840261d37718a87'
OUTPUT = REPO/'docs/reports/2026-10-06-slice-142/live-first-metadata.json'
ROOT_RELATIVE = Path('DynamicSubjectAgent/living-activity-development/s142/live-first-20261006-1')
PURPOSES = ('living-activity-choice', 'living-activity-share', 'living-activity-reply')


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {key:plain(item) for key,item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value.value if hasattr(value, 'value') else value


def digest(value):
    return sha256(canonical_json(plain(value)).encode('utf-8')).hexdigest()


class AcceptanceStopped(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise AcceptanceStopped(code)


def validate_preview(preview, purpose):
    """Reject unreviewed fields before any credential or HTTPS transport."""
    fields = {PURPOSES[0]: {'background', 'shared_experience', 'current_activity', 'current_plan'},
        PURPOSES[1]: {'background', 'shared_experience', 'activity_result'},
        PURPOSES[2]: {'turn', 'background', 'exchange', 'evidence'}}
    require(type(preview) is dict and set(preview) == {'policy', 'payload'}
        and type(preview['policy']) is str and type(preview['payload']) is dict
        and set(preview['payload']) == fields[purpose], 'unreviewed-preview-fields')
    payload = preview['payload']; background = payload['background']
    require(type(background) is dict and set(background) == {'runtime_identity', 'character_core', 'self_knowledge',
        'personality', 'stage_description', 'encounter', 'disclosure'}
        and set(background['runtime_identity']) == {'subject_name', 'subject_identity', 'canon_start'}, 'unreviewed-background-fields')
    def plan(value):
        return value is None or type(value) is dict and set(value) == {'subject', 'composition', 'focus'} and all(
            type(value[key]) is str and 0 < len(value[key]) <= maximum
            for key,maximum in (('subject', 160), ('composition', 800), ('focus', 400)))
    if purpose == PURPOSES[0]:
        require(payload['shared_experience'] is None and plan(payload['current_plan'])
            and set(payload['current_activity']) == {'phase', 'allowed_actions'}, 'unreviewed-choice-material')
    elif purpose == PURPOSES[1]:
        require(payload['shared_experience'] is None and set(payload['activity_result']) == {'action', 'plan'}
            and payload['activity_result']['action'] in ('start', 'revise') and plan(payload['activity_result']['plan']), 'unreviewed-share-material')
    else:
        turn, exchange, evidence = payload['turn'], payload['exchange'], payload['evidence']
        require(set(turn) == {'current_message', 'history_enabled', 'has_prior_committed_exchange'}
            and type(turn['current_message']) is str and 0 < len(turn['current_message']) <= 1000
            and turn['history_enabled'] is True and type(exchange) is list and len(exchange) <= 2
            and all(set(row) == {'user_text', 'assistant_text'} and all(type(text) is str for text in row.values()) for row in exchange)
            and sum(len(row['user_text'])+len(row['assistant_text']) for row in exchange) <= 4000
            and set(evidence) == {'shared_experience', 'activity_result', 'latest_share'}
            and evidence['shared_experience'] is None and evidence['activity_result'] is not None
            and set(evidence['activity_result']) == {'kind', 'plan'} and plan(evidence['activity_result']['plan']), 'unreviewed-reply-material')
        share = evidence['latest_share']
        require(share is None or type(share) is dict and set(share) == {'text'}
            and type(share['text']) is str and 0 < len(share['text']) <= 400, 'unreviewed-share-followup-material')


def preflight():
    review = json.loads((REPO/'docs/experiments/s142/review.json').read_text(encoding='utf-8'))
    scenario = json.loads((REPO/'docs/experiments/s142/scenarios.json').read_text(encoding='utf-8'))
    scene = json.loads(SCENE_PATH.read_text(encoding='utf-8'))
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    require(review['review_basis'] == digest(review['review']) == REVIEW_BASIS, 'review-pin-changed')
    require(digest(scenario) == SCENARIO_SHA == review['review']['scenario_sha256'], 'approved-scenario-changed')
    require(digest(scene) == SCENE_SHA and scene['review_basis'] == REVIEW_BASIS, 'first-scene-pin-changed')
    require(scene['scene'] == scenario['real_first_scene'] == review['review']['real_first_scene'], 'first-scene-expands-approval')
    require(scene['followup_messages'] == scenario['followup_messages'], 'approved-messages-changed')
    require(scene['protocol'] == review['review']['protocol'] and scene['policy_sha256'] == review['review']['policy_sha256'], 'protocol-or-policy-changed')
    require(digest(APPROVED_BINDING) == scene['material_binding_sha256'] and APPROVED_BINDING == review['review']['material_binding'], 'approved-material-changed')
    require(scene['scene']['maximum_first_requests'] == 5 and scene['scene']['stage_request_limit'] == 1
        and scene['scene']['automatic_retries'] == 0 and scene['scene']['time_is_simulated'] is True, 'first-stage-bound-changed')
    require(all(type(text) is str and 0 < len(text) <= 1000 for text in scene['followup_messages'])
        and len(scene['followup_messages']) == 3, 'ordinary-message-bound-changed')
    local_app = Path(os.environ.get('LOCALAPPDATA', ''))
    require(local_app.is_absolute() and local_app.resolve() == Path('C:/Users/30252/AppData/Local').resolve(), 'real-local-appdata-required')
    root = local_app/ROOT_RELATIVE
    require(not root.exists() and not OUTPUT.exists() and not OUTPUT.with_name(OUTPUT.name+'.next').exists(), 'existing-first-resources-retained')
    require(OUTPUT.parent.is_dir(), 'report-directory-required')
    return scene, root


class SafeReport:
    def __init__(self, root, scene):
        self.lock, self.io_error_types = RLock(), []
        self.data = dict(version='s142-first-live-1', review_basis=REVIEW_BASIS,
            approved_scenario_sha256=SCENARIO_SHA, first_scene_sha256=SCENE_SHA,
            runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            independent_root=str(root), status='preparing', time_is_simulated=True,
            synthetic_outputs=False, maximum_first_requests=5, requests_per_stage=1,
            automatic_retries=0, raw_text_exported=False, reasoning_text_exported=False,
            stages=[], transport=[], checks={}, audit=[], audit_count=0)

    def save(self):
        with self.lock:
            try:
                self.data['checkpoint_io_error_types'] = self.io_error_types[:]
                temporary = OUTPUT.with_name(OUTPUT.name+'.next')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(OUTPUT)
                return True
            except Exception as error:
                name = type(error).__name__
                if name not in self.io_error_types:
                    self.io_error_types.append(name)
                return False

    def checked_save(self, code):
        require(self.save() and not self.io_error_types, code)

    def unverified(self, code):
        if self.data['status'] != 'stopped-for-unverified-or-integrity':
            self.data['last_known_status'] = self.data['status']
        self.data.update(status='stopped-for-unverified-or-integrity', closure_stop_code=code,
            runner_exit_code=1)

    def begin(self, label, **metadata):
        row = dict(stage=label, status='started', error_type=None, time_is_simulated=True, **metadata)
        with self.lock:
            self.data['stages'].append(row)
            self.checked_save('checkpoint-before-stage-failed')
        return row


def final_boundary(response, purpose):
    """Transiently parse final JSON; retain only schema flags, counts and hashes."""
    row = response_metadata(response)
    row.update(exact_task_schema=False, final_value_sha256=None, plan_sha256=None,
        reply_sha256=None, reply_chars=None, action=None, share=None)
    duplicates = []
    watched = {'choices', 'message', 'content', 'share', 'reply_text', 'language', 'action',
        'plan', 'subject', 'composition', 'focus', 'reason_code', 'basis_refs', 'decision_note'}
    def pairs(items):
        value = {}
        for key,item in items:
            if key in value and key in watched:
                duplicates.append(True)
            value[key] = item
        return value
    try:
        envelope = json.loads(response.body.decode('utf-8'), object_pairs_hook=pairs)
        content = envelope['choices'][0]['message']['content']
        value = json.loads(content, object_pairs_hook=pairs)
        row['duplicate_semantic_keys'] = row.get('duplicate_semantic_keys', False) or bool(duplicates)
        if type(value) is not dict:
            return row
        fields = {'living-activity-choice': {'action', 'plan', 'reason_code', 'basis_refs', 'decision_note'},
            'living-activity-share': {'share', 'reply_text', 'language'},
            'living-activity-reply': {'reply_text', 'language'}}[purpose]
        row['exact_task_schema'] = set(value) == fields and not row['duplicate_semantic_keys']
        row['final_value_sha256'] = digest(value)
        if purpose == 'living-activity-choice':
            row['action'] = value.get('action') if value.get('action') in ('start', 'revise', 'keep', 'rework', 'defer') else 'other'
            row['plan_sha256'] = None if value.get('plan') is None else digest(value['plan'])
        elif type(value.get('reply_text')) is str:
            row['reply_chars'] = len(value['reply_text'])
            row['reply_sha256'] = sha256(value['reply_text'].encode('utf-8')).hexdigest()
            row['share'] = value.get('share') if type(value.get('share')) is bool else None
        return row
    except (ValueError, UnicodeError, TypeError, KeyError, IndexError):
        return row


def safe_observation(value):
    """Treat Provider metadata as untrusted; retain closed fields only."""
    from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
    row = {}
    for key in ('task_kind', 'purpose'):
        if value.get(key) in PURPOSES:
            row[key] = value[key]
    if value.get('status') in ('complete', 'failed-closed', 'unavailable', 'unknown'):
        row['status'] = value['status']
    for key in ('request_digest', 'wire_sha256'):
        if type(value.get(key)) is str and re.fullmatch('[0-9a-f]{64}', value[key]):
            row[key] = value[key]
    codes = REVIEW_DIAGNOSTIC_CODES | {'character-credential-unavailable', 'structured-choice-invalid',
        'expression-invalid', 'delivery-unverified', 'audit-failed'}
    if type(value.get('error_code')) is str and value['error_code'] in codes:
        row['error_code'] = value['error_code']
    if 'model' in value:
        row['model'] = 'deepseek-flash' if value['model'] == 'deepseek-flash' else 'other'
    if value.get('finish_reason') in ('stop', 'length', 'tool_calls', 'content_filter',
        'insufficient_system_resource', 'aborted', 'other'):
        row['finish_reason'] = value['finish_reason']
    if type(value.get('elapsed_seconds')) in (float, int) and math.isfinite(value['elapsed_seconds']):
        row['elapsed_seconds'] = max(0.0, value['elapsed_seconds'])
    if type(value.get('usage')) is dict:
        row['usage'] = {key:count for key,count in value['usage'].items()
            if key in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens',
                'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens') and type(count) is int and 0 <= count < 2**53}
    return row


class ObservedTransport(DeepSeekTransport):
    """Never change approved bytes; reject additional or non-preview requests."""
    def __init__(self, report):
        from dynamic_subject_agent.local_product import _WindowsLabResolver
        self.delegate = DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        self.report, self.expected, self.active_stage = report, None, None
        self.stage_calls, self.total_calls, self.allowed = 0, 0, 0

    def arm(self, label, preview=None, purpose=None):
        from dynamic_subject_agent.living_activity_remote_preview import living_remote_request_preview
        self.active_stage, self.stage_calls = label, 0
        self.allowed = 0 if preview is None else 1
        self.expected = None
        if preview is not None:
            validate_preview(preview, purpose)
            task = ModelTask(ModelTaskKind(purpose), preview)
            wire = living_remote_request_preview(task)
            self.expected = dict(purpose=purpose, endpoint=wire['endpoint'], wire_sha256=wire['wire_sha256'],
                task_sha256=digest(preview), payload_sha256=digest(preview['payload']),
                policy_sha256=sha256(preview['policy'].encode('utf-8')).hexdigest())
        return deepcopy(self.expected)

    def post_json(self, **kwargs):
        require(self.expected is not None and self.allowed == 1 and self.stage_calls == 0
            and self.total_calls < 5 and not self.report.io_error_types, 'unapproved-extra-transport-request')
        require(kwargs['endpoint'] == self.expected['endpoint'] and kwargs['timeout_seconds'] == 30
            and sha256(kwargs['body']).hexdigest() == self.expected['wire_sha256'], 'actual-wire-differs-from-preview')
        self.stage_calls += 1
        self.total_calls += 1
        row = dict(stage=self.active_stage, status='request-started', error_type=None,
            **deepcopy(self.expected))
        self.report.data['transport'].append(row)
        self.report.checked_save('checkpoint-before-provider-failed')
        started = perf_counter()
        try:
            response = self.delegate.post_json(**kwargs)
            row.update(status='response-received', response_boundary=final_boundary(response, self.expected['purpose']))
            return response
        except BaseException as error:
            row.update(status='transport-exception', error_type=type(error).__name__)
            raise
        finally:
            row['elapsed_seconds'] = max(0.0, perf_counter()-started)
            self.report.save()  # Observability I/O cannot alter a received response.


class FirstRun:
    def __init__(self, root, scene, report):
        from dynamic_subject_agent.living_activity_live import ApprovedLivingActivityGrant
        from dynamic_subject_agent.local_product import LocalProductConfig
        self.root, self.scene, self.report = root, scene, report
        self.audit_path = root/'audit'
        self.config = LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments', root/'state.json')
        self.transport, self.observations = ObservedTransport(report), []
        self.grant = ApprovedLivingActivityGrant(review_basis=REVIEW_BASIS, confirmed=True)
        self.grant.validate()
        self.product = None

    def counts(self):
        from dynamic_subject_agent.living_activity_live import open_living_activity_audit
        return open_living_activity_audit(self.audit_path).counts()[1]

    def audit(self):
        from dynamic_subject_agent.living_activity_live import open_living_activity_audit
        value = list(open_living_activity_audit(self.audit_path).snapshot())
        self.report.data.update(audit=value, audit_count=len(value))
        require(len(value) <= 5, 'first-request-bound-exceeded')
        return value

    def view(self):
        response = self.product.application.query_living_activity()
        require(response.status == 'available' and type(response.view) is dict, 'canonical-living-view-unverified')
        return plain(response.view)

    def history(self):
        from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
        response = self.product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            self.product.profile_id, self.product.timeline_id))
        require(response.status.value == 'available' and response.projection is not None, 'canonical-history-unverified')
        return plain(response.projection.turns)

    def fingerprint(self):
        return digest(dict(living=self.view(), history=self.history(),
            context=self.product.application.query_whole_context_boundary()))

    def opening(self):
        from dynamic_subject_agent.local_product import open_living_activity_product_live
        return open_living_activity_product_live(self.config, identity_id=self.identity_id,
            grant=self.grant, audit_path=self.audit_path, _transport=self.transport, observations=self.observations)

    def create(self):
        from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
        from dynamic_subject_agent.application import ApplicationFacade
        from dynamic_subject_agent.local_product import open_local_product
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
        from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
        row = self.report.begin('create-fresh-independent-live', maximum_requests=0)
        self.transport.arm(row['stage'])
        package = REPO/'.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
        preview = ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(
            package, APPROVED_BINDING['definition_basis'], APPROVED_BINDING['runtime_asset_sha'],
            APPROVED_BINDING['persona_digest'], APPROVED_BINDING['subject_id'], APPROVED_BINDING['anchor_id']))
        require(preview.status == 'previewed' and preview.review_basis == APPROVED_BINDING['review_basis'], 'original-material-preview-mismatch')
        with open_local_product(self.config, cognition=DormantDeepSeekCognition()) as author:
            frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
                package.read_text(encoding='utf-8'), APPROVED_BINDING['definition_basis'], True, True))
            require(frozen.status == 'created', 'fresh-dormant-identity-required')
            self.identity_id = frozen.view.identity_id
        self.product = self.opening()
        state, history = self.view(), self.history()
        chat = self.product.application.reviewed_character_chat_status()
        require(chat.status == 'active' and chat.history_enabled is True and self.counts() == 0
            and self.transport.total_calls == 0 and not history and state['source'] is None
            and state['phase'] == 'unstarted' and state['current_plan'] is None
            and state['shares'] == [] and state['considered'] == []
            and state['permission']['paused'] is True and state['permission']['sharing_enabled'] is False
            and state['permission']['needs_attention'] is False and state['permission']['source_blocked'] is False,
            'fresh-start-preconditions-differ')
        row.update(status='complete', audit_before=0, audit_after=0)
        self.report.data['checks']['fresh-empty-no-e1-history-on-default-paused-shareoff'] = True
        self.audit(); self.report.checked_save('checkpoint-after-create-failed')

    def zero(self, label, action):
        before, sent = self.counts(), self.transport.total_calls
        row = self.report.begin(label, maximum_requests=0, audit_before=before)
        self.transport.arm(label)
        result = action()
        require(self.counts() == before and self.transport.total_calls == sent and not self.report.io_error_types,
            'zero-call-operation-generated-request')
        row.update(status='complete', audit_after=self.counts())
        self.audit(); self.report.checked_save('checkpoint-after-zero-operation-failed')
        return result

    def enable(self):
        from dynamic_subject_agent.living_activity import LivingControlRequest
        def operation():
            request = LivingControlRequest(self.product.profile_id, self.product.timeline_id, str(uuid4()),
                self.view()['permission']['revision'], paused=False, sharing_enabled=True, confirmed=True)
            result = self.product.application.set_living_controls(request)
            require(result.status == 'committed', 'explicit-controls-not-committed')
        self.zero('explicit-unpause-and-enable-sharing', operation)

    def model_stage(self, label, purpose, request_id, preview, operation):
        before, sent, observed = self.counts(), self.transport.total_calls, len(self.observations)
        row = self.report.begin(label, purpose=purpose, request_id=request_id,
            audit_before=before, maximum_requests=1, expected_task_sha256=digest(preview))
        expected = self.transport.arm(label, preview, purpose)
        row.update(expected_wire_sha256=expected['wire_sha256'], expected_payload_sha256=expected['payload_sha256'],
            policy_sha256=expected['policy_sha256'])
        self.report.checked_save('checkpoint-before-model-stage-failed')
        result = operation()
        row.update(status=getattr(getattr(result, 'status', None), 'value', getattr(result, 'status', 'unverified')),
            audit_after=self.counts(), transport_count=self.transport.total_calls-sent,
            observations=[safe_observation(value) for value in self.observations[observed:]])
        audit = self.audit()
        self.report.checked_save('checkpoint-after-model-stage-failed')
        require(self.counts()-before <= 1 and self.transport.total_calls-sent <= 1, 'single-stage-request-bound-exceeded')
        success = row['status'] in ('committed', 'terminal') and getattr(getattr(result, 'projection', None), 'failure_code', None) is None
        if not success:
            self.report.data.update(status='stopped-on-first-technical-failure', stopped_stage=label)
            self.report.checked_save('checkpoint-after-failure-failed')
            raise AcceptanceStopped('first-technical-failure')
        require(self.counts()-before == 1 and self.transport.total_calls-sent == 1 and len(audit) > before,
            'successful-stage-without-one-verified-request')
        request_row = self.report.data['transport'][-1]
        boundary = request_row.get('response_boundary', {})
        require(request_row['status'] == 'response-received' and boundary.get('http_status') == 200
            and boundary.get('envelope_json') is True and boundary.get('choices_count') == 1
            and boundary.get('assistant_role') is True and boundary.get('finish_reason') == 'stop'
            and boundary.get('exact_task_schema') is True and not boundary.get('duplicate_semantic_keys')
            and audit[-1]['status'] == 'complete' and audit[-1]['purpose'] == purpose
            and audit[-1]['request_digest'] == digest(preview)
            and audit[-1]['output_digest'] == boundary.get('final_value_sha256'), 'raw-final-audit-or-material-mismatch')
        row['raw_final_matches_completed_audit'] = True
        self.report.checked_save('checkpoint-after-raw-verification-failed')
        return result, row, boundary

    def activity(self):
        from dynamic_subject_agent.living_activity import LivingActionRequest
        candidate = self.product.application.preview_living_activity('choice')
        require(candidate.status == 'previewed', 'choice-preview-unavailable')
        preview = plain(candidate.view)
        require(preview['payload']['shared_experience'] is None and preview['payload']['current_plan'] is None,
            'first-choice-has-unapproved-prior-material')
        request = LivingActionRequest(self.product.profile_id, self.product.timeline_id, str(uuid4()), self.view()['revision'], 'simulation')
        result, row, raw = self.model_stage('labelled-simulated-opportunity', PURPOSES[0], request.request_id, preview,
            lambda:self.product.application.advance_living_activity(request))
        state = self.view(); actual = state['visible_result']
        require(actual is not None and actual['event']['kind'] == raw['action']
            and (None if actual['plan'] is None else digest(actual['plan'])) == raw['plan_sha256']
            and actual['event']['simulated'] is True, 'raw-choice-or-simulation-does-not-match-canonical')
        shared = self.product.application.query_shared_activity()
        require(shared.status == 'available' and type(shared.view) is dict, 'canonical-choice-decision-unverified')
        decision = plain(shared.view['decision'])
        canonical_value = dict(action=decision['action'], plan=actual['plan'], reason_code=decision['reason_code'],
            basis_refs=decision['basis_refs'], decision_note=decision['decision_note'])
        require(digest(canonical_value) == raw['final_value_sha256'], 'raw-full-choice-differs-from-canonical')
        row.update(action=raw['action'], plan_sha256=raw['plan_sha256'], simulated_event=True,
            canonical_actual_plan_matches_raw=True, canonical_choice_value_sha256=digest(canonical_value))
        self.report.checked_save('checkpoint-after-choice-failed')
        def replay():
            require(self.product.application.advance_living_activity(request).status == 'replayed'
                and self.product.application.query_living_activity(request).status == 'replayed', 'original-choice-nonce-not-replayed')
        self.zero('choice-nonce-replay-and-query', replay)
        if actual['event']['kind'] not in ('start', 'revise') or actual['plan'] is None:
            self.report.data.update(status='stopped-no-eligible-new-text-plan', first_choice_action=raw['action'])
            self.report.checked_save('checkpoint-after-no-eligible-stop-failed')
            return False
        self.actual_plan_sha256 = digest(actual['plan'])
        return True

    def share(self):
        from dynamic_subject_agent.living_activity import LivingActionRequest
        candidate = self.product.application.preview_living_activity('share')
        require(candidate.status == 'previewed', 'independent-share-preview-unavailable')
        preview = plain(candidate.view)
        require(preview['payload']['shared_experience'] is None
            and digest(preview['payload']['activity_result']['plan']) == self.actual_plan_sha256, 'share-has-wrong-actual-plan')
        before_history = self.history()
        request = LivingActionRequest(self.product.profile_id, self.product.timeline_id, str(uuid4()), self.view()['revision'], 'share')
        result, row, raw = self.model_stage('independent-share-consider', PURPOSES[1], request.request_id, preview,
            lambda:self.product.application.advance_living_activity(request))
        state = self.view()
        require(len(state['considered']) == 1 and state['considered'][0]['share'] is raw['share']
            and self.history() == before_history, 'canonical-share-decision-or-origin-differs')
        row.update(share=raw['share'], share_chars=raw['reply_chars'], assistant_origin_no_fake_user_turn=True)
        if raw['share']:
            require(len(state['shares']) == 1 and sha256(state['shares'][0]['text'].encode('utf-8')).hexdigest() == raw['reply_sha256'], 'raw-share-text-differs-from-canonical')
            self.share_text_sha256 = raw['reply_sha256']
            row['raw_share_equals_canonical'] = True
            canonical_value = dict(share=True, reply_text=state['shares'][0]['text'], language='zh')
        else:
            require(state['shares'] == [] and raw['reply_chars'] == 0, 'false-share-created-message')
            canonical_value = dict(share=False, reply_text='', language='zh')
        require(digest(canonical_value) == raw['final_value_sha256'], 'raw-full-share-decision-differs-from-canonical')
        row['canonical_share_value_sha256'] = digest(canonical_value)
        self.report.checked_save('checkpoint-after-share-failed')
        def replay():
            require(self.product.application.advance_living_activity(request).status == 'replayed'
                and self.product.application.query_living_activity(request).status == 'replayed', 'original-share-nonce-not-replayed')
        self.zero('share-nonce-replay-and-query', replay)
        def reopen():
            original = self.fingerprint()
            self.product.close(); self.product = self.opening()
            require(self.fingerprint() == original, 'reopen-changed-canonical-business-state')
        self.zero('share-restart', reopen)
        if raw['share'] is False:
            self.report.data.update(status='stopped-first-share-false')
            self.report.checked_save('checkpoint-after-false-stop-failed')
            return False
        require(raw['share'] is True, 'share-boolean-unverified')
        return True

    def reply(self, index, text):
        from dynamic_subject_agent.application import SubjectRequestLookupRequest
        from dynamic_subject_agent.timeline import SubjectCommand
        candidate = self.product.application.preview_living_activity('reply', text)
        require(candidate.status == 'previewed', 'ordinary-reply-preview-unavailable')
        preview = plain(candidate.view); payload = preview['payload']; evidence = payload['evidence']
        require(payload['turn']['current_message'] == text and evidence['shared_experience'] is None
            and digest(evidence['activity_result']['plan']) == self.actual_plan_sha256, 'reply-current-result-or-e1-differs')
        supplied = evidence['latest_share']
        require((supplied is not None and sha256(supplied['text'].encode('utf-8')).hexdigest() == self.share_text_sha256)
            if index < 2 else supplied is None, 'share-two-successful-round-window-differs')
        if index == 2:
            require(payload['exchange'] == [], 'third-actual-exchange-retains-s1-derived-complete-rounds')
        else:
            expected_exchange = [{key:turn[key] for key in ('user_text', 'assistant_text')} for turn in self.history()]
            require(payload['exchange'] == expected_exchange, 'first-two-exchange-differs-from-own-canonical-rounds')
        command = SubjectCommand.contribute_utterance(target_profile_id=self.product.profile_id,
            target_timeline_id=self.product.timeline_id, declared_intent='ask-collaborator-status',
            utterance=text, language='zh', provenance='project-original')
        key, previous_count = str(uuid4()), len(self.history())
        def send():
            response = self.product.application.submit(command, idempotency_key=key)
            deadline = perf_counter()+120
            while response.status.value == 'pending':
                require(perf_counter() < deadline, 'pending-delivery-unverified')
                self.report.data['stages'][-1]['status'] = 'pending'
                self.report.checked_save('pending-checkpoint-failed')
                response = self.product.application.wait(response.operation_ref, timeout_seconds=30)
            return response
        result, row, raw = self.model_stage('ordinary-followup-'+str(index+1), PURPOSES[2], key, preview, send)
        turns = self.history()
        require(len(turns) == previous_count+1 and turns[-1]['user_text'] == text
            and turns[-1]['head_sequence'] == result.projection.timeline_head_sequence
            and sha256(turns[-1]['assistant_text'].encode('utf-8')).hexdigest() == raw['reply_sha256'], 'raw-reply-not-exact-complete-canonical-round')
        row.update(reply_chars=raw['reply_chars'], reply_sha256=raw['reply_sha256'], raw_reply_equals_canonical=True,
            latest_share_sha256=None if supplied is None else self.share_text_sha256,
            exchange_complete_turn_count=len(payload['exchange']), exchange_sha256=digest(payload['exchange']),
            canonical_complete_round=True, third_complete_s1_history_filtered=index == 2)
        self.report.checked_save('checkpoint-after-reply-failed')
        def replay():
            replayed = self.product.application.submit(command, idempotency_key=key)
            looked = self.product.application.lookup_subject_request(SubjectRequestLookupRequest(command, key))
            require(replayed.status.value == 'terminal' and replayed.replayed is True
                and looked.query_status.value == 'found' and looked.operation is not None
                and looked.operation.status.value == 'terminal'
                and looked.operation.projection.timeline_head_sequence == result.projection.timeline_head_sequence,
                'original-reply-nonce-or-query-not-replayed')
        self.zero('reply-'+str(index+1)+'-nonce-replay-and-query', replay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    report, run = None, None
    try:
        scene, root = preflight()
        if args.preflight:
            print(json.dumps(dict(status='preflight-passed', review_basis=REVIEW_BASIS,
                approved_scenario_sha256=SCENARIO_SHA, first_scene_sha256=SCENE_SHA,
                maximum_first_requests=5, requests_per_stage=1, automatic_retries=0,
                identity_opened=False, transport_created=False, credential_reads=0, remote_calls=0,
                resource_exists=False, output_exists=False), ensure_ascii=False))
            return
        report = SafeReport(root, scene)
        report.checked_save('initial-checkpoint-failed')
        run = FirstRun(root, scene, report)
        run.create(); run.enable()
        if run.activity() and run.share():
            for index,text in enumerate(scene['followup_messages']):
                run.reply(index, text)
            report.data.update(status='first-scene-completed', first_plan_share_two_followups_third_filter=True)
        report.checked_save('checkpoint-after-first-scene-failed')
    except BaseException as error:
        if report is not None:
            row = report.data['stages'][-1] if report.data['stages'] else None
            if row is not None:
                row.update(error_type=type(error).__name__)
                if row['status'] in ('started', 'pending'):
                    row['status'] = 'failed-or-unverified'
            report.data.update(error_type=type(error).__name__, stop_code=error.code if type(error) is AcceptanceStopped else 'unexpected-runner-failure')
            report.data['runner_exit_code'] = 1
            if report.data['status'] not in ('stopped-on-first-technical-failure', 'stopped-first-share-false', 'stopped-no-eligible-new-text-plan'):
                report.data['status'] = 'stopped-for-unverified-or-integrity'
            report.save()
        else:
            print(json.dumps(dict(status='preflight-stopped', error_type=type(error).__name__,
                stop_code=error.code if type(error) is AcceptanceStopped else 'unexpected-preflight-failure',
                runner_exit_code=1, remote_calls=0, credential_reads=0), ensure_ascii=False))
        raise SystemExit(1) from None
    finally:
        if run is not None:
            try:
                run.audit()
            except Exception as error:
                report.data.update(audit_unverified=True, audit_error_type=type(error).__name__)
                report.unverified('final-audit-unverified')
            if run.product is not None:
                try:
                    before = run.counts(), run.transport.total_calls
                    run.transport.arm('final-permission-query')
                    controls = run.product.application.query_living_controls()
                    require(controls.status == 'available' and type(controls.view) is dict,
                        'final-permission-unverified')
                    report.data['final_permission'] = plain(controls.view)
                    require((run.counts(), run.transport.total_calls) == before, 'permission-query-generated-request')
                except Exception as error:
                    report.data.update(permission_unverified=True, permission_error_type=type(error).__name__)
                    report.unverified('final-permission-unverified')
                try:
                    run.product.close()
                except Exception as error:
                    report.data.update(close_unverified=True, close_error_type=type(error).__name__)
                    report.unverified('final-close-unverified')
        if report is not None:
            report.data.setdefault('runner_exit_code', 0)
            saved = report.save()
            if not saved or report.io_error_types:
                report.unverified('final-checkpoint-unverified')
                report.save()  # Best effort only; stdout still states unknown/nonzero.
            print(json.dumps({key:value for key,value in report.data.items() if key not in ('stages', 'transport', 'audit')}, ensure_ascii=False))
            if report.data['runner_exit_code'] != 0:
                raise SystemExit(1) from None


if __name__ == '__main__':
    main()

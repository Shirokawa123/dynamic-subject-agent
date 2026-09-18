"""Explicit task routing; ordinary chat keeps its existing projections."""
from dataclasses import replace
import json

from dynamic_subject_agent.runtime import CognitionEngine, ExpressionCandidate
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind
from dynamic_subject_agent.subject_tasks import TASK_INTENT, OPEN, SubjectTaskCommand, SubjectTaskProjection
from dynamic_subject_agent.text_artifacts import TEXT_EFFECT_INTENT, TextSaveApproval


class SubjectTaskCognition(CognitionEngine):
    supports_subject_tasks = True
    supports_text_effects = True
    def __init__(self, base: CognitionEngine, gateway: ModelGateway):
        self.base, self.gateway = base, gateway
        for name in ('adapter_version','provider_authority','experimental','test_only'):
            setattr(self, name, getattr(base,name))

    def preflight(self, *, context, command):
        if command.declared_intent in (TASK_INTENT,TEXT_EFFECT_INTENT):
            try:
                (SubjectTaskCommand if command.declared_intent==TASK_INTENT else TextSaveApproval).from_json(command.utterance)
            except (TypeError, ValueError):
                from dynamic_subject_agent.timeline import PreAdmissionRejected
                raise PreAdmissionRejected('invalid-subject-task', 'task command is invalid') from None
        else:
            self.base.preflight(context=context,command=command)

    def reserved_operation_id(self, **kwargs):
        return self.base.reserved_operation_id(**kwargs)

    def propose(self, *, plan, context, command, basis):
        if command.declared_intent not in (TASK_INTENT,TEXT_EFFECT_INTENT):
            return self.base.propose(plan=plan,context=context,command=command,basis=basis)
        if command.declared_intent==TEXT_EFFECT_INTENT:
            approval=TextSaveApproval.from_json(command.utterance)
            records=context.load_subject_tasks()
            preview=context.load_artifact_preview(approval.task_id,approval.revision)
            base=self._bounded_noop_proposal(context=context,basis=basis,experience_summary='处理逐次确认的本地文本保存。',
                expression_candidate=ExpressionCandidate('核对本地文本保存授权。','zh'))
            agency=replace(base.impact_envelope.agency,artifact_approval=approval,artifact_preview=preview,
                current_state=replace(base.impact_envelope.agency.current_state,tasks=records),admitted_command=command.utterance)
            return replace(base,impact_envelope=replace(base.impact_envelope,agency=agency))
        task = SubjectTaskCommand.from_json(command.utterance)
        proposal = None
        from dynamic_subject_agent.runtime import CognitionFailedClosed
        try:
            records = context.load_subject_tasks()
        except Exception:
            raise CognitionFailedClosed('agency', 'task-history-unavailable', 'task history could not be verified') from None
        old = next((r for r in records if r.task_id == task.task_id), None)
        valid = task.action == 'request' or (old is not None and old.revision == task.expected_revision and old.status in OPEN)
        if valid and task.action != 'cancel' and (task.action == 'revise' or sum(r.status in OPEN for r in records) < 5):
            try:
                proposal = self.gateway.execute(ModelTask(ModelTaskKind.SUBJECT_TASK_PROPOSAL,
                    SubjectTaskProjection.build(task.message,tuple(r for r in records if r.task_id != task.task_id)))).value
            except Exception:
                proposal = None
        base = self._bounded_noop_proposal(context=context,basis=basis,experience_summary='处理显式主体任务，状态以最终裁决为准。',
            expression_candidate=ExpressionCandidate('主体任务处理中。','zh'))
        agency = replace(base.impact_envelope.agency, task_command=task, task_proposal=proposal,
            current_state=replace(base.impact_envelope.agency.current_state,tasks=records),
            admitted_command=command.utterance)
        return replace(base,impact_envelope=replace(base.impact_envelope,agency=agency))

    def express(self, *, proposal, context, command, outcomes):
        if command.declared_intent not in (TASK_INTENT,TEXT_EFFECT_INTENT):
            return self.base.express(proposal=proposal,context=context,command=command,outcomes=outcomes)
        return ExpressionCandidate(json.loads(outcomes.agency.decision.reason)['reply'],'zh')

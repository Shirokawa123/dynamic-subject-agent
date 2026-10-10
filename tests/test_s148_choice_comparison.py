"""Actual prepared Interface projection; no live credentials or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s148_choice_comparison as trial
from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_working_understanding import state,request,step
from test_working_understanding_live import working_live_fixture,WorkingTransport,sources
from test_working_understanding_fidelity import faithful_fixture


def test_three_arms_share_actual_interface_initial_state_and_only_remove_early_information(faithful_fixture):
    opening,_,_,_=faithful_fixture
    transport=WorkingTransport();product=opening(transport)
    sources(product)
    advanced=product.application.advance_working_activity(step(product,'s148-independent-initial-plan'))
    assert advanced.status=='committed',advanced
    assert product.application.apply_working_understanding(request(product,'s148-source-supported-form')).status=='committed'
    full=trial.plain(product.application.preview_working_activity('choice').view)
    support=full['payload']['working_understanding']
    before=trial.plain(state(product));sent=len(transport.calls)
    bodies=[json.loads(trial.choice_wire(trial.choice_preview(full,support,arm),support)) for arm in ('N','Q','W')]
    assert all(body['messages'][0]==bodies[0]['messages'][0] for body in bodies)
    assert all({k:v for k,v in body.items() if k!='messages'}=={k:v for k,v in bodies[0].items() if k!='messages'} for body in bodies)
    payloads=[json.loads(body['messages'][1]['content']) for body in bodies]
    assert all({k:v for k,v in p.items() if k!='working_understanding'}=={k:v for k,v in payloads[0].items() if k!='working_understanding'} for p in payloads)
    assert payloads[0]['working_understanding'] is None
    assert payloads[1]['working_understanding']['statement'] is None
    assert payloads[1]['working_understanding']['support']==payloads[2]['working_understanding']['support']
    assert payloads[2]['working_understanding']==support
    assert trial.plain(state(product))==before and len(transport.calls)==sent
    # This source-only shape must still be rejected by the production surface.
    with pytest.raises(ValueError):
        trial.validate_working_request_payload(trial.ModelTask(trial.ModelTaskKind.WORKING_ACTIVITY_CHOICE,
            trial.choice_preview(full,support,'Q')))


def test_altered_support_and_extra_outbound_fields_cannot_use_comparison(faithful_fixture):
    opening,_,_,_=faithful_fixture
    product=opening(WorkingTransport());sources(product)
    assert product.application.apply_working_understanding(request(product,'s148-boundary-form')).status=='committed'
    full=trial.plain(product.application.preview_working_activity('choice').view)
    support=full['payload']['working_understanding']
    preview=trial.choice_preview(full,support,'Q')
    preview['payload']['working_understanding']['support']['exchanges'][0]['quote']='替换未提交原话'
    with pytest.raises(RuntimeError,match='exact-source'):
        trial.choice_wire(preview,support)
    preview=trial.choice_preview(full,support,'N');preview['payload']['internal_id']='private'
    with pytest.raises(ValueError,match='fields'):
        trial.choice_wire(preview,support)


def test_comparison_records_every_remaining_cell_as_not_run_after_first_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(trial,'ROOT',tmp_path/'owned')
    root=trial.ROOT;root.mkdir()
    manifest=dict(order=[a+'-'+b for a,b in trial.ORDER],requests={a+'-'+b:dict(preview={},full_support=None) for a,b in trial.ORDER},
        base=dict(payload=dict(current_plan={})),plan_sha256=trial.sha256((trial.REPO/'docs/experiments/s148/PLAN.md').read_bytes()).hexdigest())
    trial.save(root/'manifest.json',manifest)
    trial.save(root/'metadata.json',dict(status='prepared-awaiting-form-scope-review',manifest_sha256=trial.digest(manifest),calls=[],
        runner_sha256=trial.sha256(Path(trial.__file__).read_bytes()).hexdigest()))
    trial.save(root/'form-review.json',dict(manifest_sha256=trial.digest(manifest),eligible=dict(R=True,I=True,L=True,C=True)))
    def failed(self,task): raise trial.ModelGatewayFailure('transport-timeout')
    monkeypatch.setattr(trial.ComparisonAdapter,'invoke',failed)
    trial.compare()
    results=json.loads((root/'results.json').read_text(encoding='utf-8'))
    assert results['status']=='comparison-stopped'
    assert len(results['rows'])==12 and results['rows'][0]['status']=='failed'
    assert all(row['status']=='not-run' and row['reason']=='prior-first-technical-failure' for row in results['rows'][1:])
    with pytest.raises(RuntimeError,match='first-only'):
        trial.compare()

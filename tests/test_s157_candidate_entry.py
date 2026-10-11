from pathlib import Path
from uuid import uuid4
import json,sys
import pytest
from test_natural_feedback_chat_entry import natural_entry_setup,entry_setup
from test_original_whole_chat import approved,personality_fixture,model_fixture
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import s157_candidate_entry as entry_module
import run_s157_candidate_scene as scene

def test_selected_experimental_entry_is_empty_and_cannot_switch_mode_or_timeline(natural_entry_setup,monkeypatch,tmp_path):
    script,_,_,options,t=natural_entry_setup
    parent=tmp_path/'candidate-scene';monkeypatch.setattr(entry_module,'EXPERIMENT_PARENT',parent)
    monkeypatch.setattr(entry_module,'APPROVED_BINDING',script.APPROVED_BINDING)
    opts=dict(variant='choice-final',transport=t,audit_path=parent/'audit',package_path=options['package_path'])
    p=entry_module.SelectedChoiceEntry(parent/'entry',**opts);identity=p.identity
    assert p.product.application.query_shared_activity().view['revision']==0 and not t.calls
    p.close();p=entry_module.SelectedChoiceEntry(parent/'entry',**opts)
    assert p.identity==identity and not t.calls;p.close()
    pointer=parent/'entry/current.json';before=pointer.read_bytes()
    with pytest.raises(ValueError):entry_module.SelectedChoiceEntry(parent/'entry',**dict(opts,variant='choice-low'))
    assert pointer.read_bytes()==before
    v=json.loads(before);v['timeline_id']=str(uuid4());pointer.write_text(json.dumps(v),encoding='utf-8');changed=pointer.read_bytes()
    with pytest.raises(RuntimeError):entry_module.SelectedChoiceEntry(parent/'entry',**opts)
    assert pointer.read_bytes()==changed and not t.calls

def test_scene_missing_candidate_is_rejected_before_opening_or_creating_scene_root(monkeypatch,tmp_path):
    monkeypatch.setattr(scene,'ROOT',tmp_path/'never-created');opened=[]
    monkeypatch.setattr(scene,'opening',lambda *args:opened.append(True))
    def missing():raise RuntimeError('candidate-not-eligible')
    monkeypatch.setattr(scene,'eligible_variant',missing)
    with pytest.raises(RuntimeError):scene.main(['next'])
    assert not scene.ROOT.exists() and not opened

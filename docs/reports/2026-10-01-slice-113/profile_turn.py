"""Disposable offline diagnosis. Never connects to a network or reads a key."""
import sys,cProfile,pstats,json,time,os
from pathlib import Path
import run_s112_reply_comparison as runner
from dynamic_subject_agent.first_life_reply_live import open_approved_trial
from dynamic_subject_agent.local_product import open_first_life_reply_trial
from dynamic_subject_agent.model_gateway import ModelGateway
from test_s112_reply_comparison import FrozenTrialTransport
from concurrent.futures import ThreadPoolExecutor

def main(root):
 root=Path(root).resolve()
 approval=open_approved_trial(root, runner.SCENARIOS_PATH,confirmed=True,live=False)
 branch_id='plan-versus-completion-A';scenario,_=approval.branch(branch_id)
 branch=runner.prepare_branch(root/branch_id,approval.scenarios)
 def open(seed=None):
  return open_first_life_reply_trial(branch.config,definition_basis=branch.definition_basis,life_scope_digest=branch.life_scope_digest,approval=approval,branch_id=branch_id,seed_gateway=seed,_transport=FrozenTrialTransport() if seed is None else None)
 seed_adapter=runner.SeedAdapter(approval.scenarios,scenario)
 with open(ModelGateway(seed_adapter)) as product:
  runner.seed_branch(product, seed_adapter)
 # Profile both the actual submitting thread and any async continuation.
 original=ThreadPoolExecutor.submit; profiles=[]; measuring=[False]
 def profiled_submit(executor,fn,*args,**kwargs):
  if not measuring[0] or not executor._thread_name_prefix.startswith("m0-runtime-"): return original(executor,fn,*args,**kwargs)
  def target():
   p=cProfile.Profile();profiles.append(p)
   return p.runcall(fn,*args,**kwargs)
  return original(executor,target)
 ThreadPoolExecutor.submit=profiled_submit
 samples=[]
 with open() as product:
  measuring[0]=os.environ.get('S113_NO_PROFILE')!='1'
  for i,row in enumerate(scenario['turns'][:3],1):
   started=time.perf_counter()
   result=runner.send(product,row['user'],f's113-offline-profile-{i}')
   samples.append(dict(step=i,status=result.status,elapsed=time.perf_counter()-started))
   print(result.status, flush=True)
   assert result.status=='terminal', result
  measuring[0]=False
  saved=runner.read_history(product)
 with open() as product:
  assert runner.read_history(product)==saved
 stats=pstats.Stats(profiles[0]) if profiles else None
 if stats:
  for p in profiles[1:]:stats.add(p)
  stats.dump_stats(str(root/'profile.pstats'))
 (root/'samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
 print(json.dumps(samples))
 if stats:stats.strip_dirs().sort_stats('cumulative').print_stats(35)
if __name__=='__main__':main(sys.argv[1])

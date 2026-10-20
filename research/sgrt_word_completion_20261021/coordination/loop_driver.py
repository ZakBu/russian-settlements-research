#!/usr/bin/env python3
"""Execute declared repair stages, preserve attempts, and obey the independent Word gate.

This controls actual subprocess work. Live LLM delegation is performed by the root
agent using the collaboration API, never claimed to be launched by this script.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def run(schedule,execute=False):
 spec=json.loads(schedule.read_text());run_id=spec['run_id'];out=ROOT/'coordination/loops'/run_id;out.mkdir(parents=True,exist_ok=True)
 record={'run_id':run_id,'state':'RUNNING','stages':[],'schedule_sha256':sha(schedule),'agents_are_managed_by':'root collaboration tools; this process runs only declared subprocess stages'}
 env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
 for stage in spec.get('stages',[]):
  row={'id':stage['id'],'command':stage['command'],'repair_requirements':stage['requirements']}
  missing=[str(p) for p in map(Path,stage.get('required_inputs',[])) if not (p if p.is_absolute() else REPO/p).is_file()]
  if missing:row.update(state='WAITING_REAL_INPUT',missing_inputs=missing)
  elif not execute:row['state']='READY_NOT_EXECUTED'
  else:
   t=time.monotonic();log=out/(stage['id']+'.log')
   with log.open('wb') as f:p=subprocess.run(stage['command'],cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT)
   row.update(state='PRODUCED_REQUIRES_INDEPENDENT_REVIEW' if p.returncode==0 else 'RETURN_TO_REPAIR',exit_code=p.returncode,seconds=round(time.monotonic()-t,3),log=str(log.relative_to(ROOT)),log_sha256=sha(log))
  record['stages'].append(row);write(out/'iteration.json',record)
 gate=ROOT/'reviews/check_release_gate.py';log=out/'independent_word_gate.log'
 with log.open('wb') as f:p=subprocess.run([sys.executable,str(gate)],cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT)
 record['gate_exit_code']=p.returncode;record['gate_log_sha256']=sha(log)
 record['state']='ACCEPTED_ALL_WORD_REQUIREMENTS' if p.returncode==0 else 'RETURN_TO_REPAIR_LOOP'
 record['scientific_release_allowed']=p.returncode==0
 record['next_action']='Independent final delivery review' if p.returncode==0 else 'Use current_repair_queue.csv; obtain missing evidence, repair and recalculate, then request another independent review.'
 write(out/'iteration.json',record);print(json.dumps(record,ensure_ascii=False,indent=2))
 return 0 if record['scientific_release_allowed'] else 1
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--schedule',type=Path,required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args();raise SystemExit(run(a.schedule,a.execute))

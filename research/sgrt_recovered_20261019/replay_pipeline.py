"""Fresh-output replay of data, geography, raw municipal extraction and financial projection."""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, subprocess, sys, time
import pandas as pd
R=Path(__file__).resolve().parent;repo=R.parents[1];work=R.parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=work/'replays/recovered_20261019');ap.add_argument('--inputs',type=Path,default=work/'recovery_inputs');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
assert not (a.out/'data/panel.parquet').exists(),'Use a fresh replay output directory.'
checks=[];commands=[]
def run(name,argv):
    command=[sys.executable,*map(str,argv)];commands.append(command);print('RUN',name,flush=True)
    with (a.out/(name+'.log')).open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    print('DONE',name,flush=True)
def compare(label,original,replayed,keys):
    x=pd.read_parquet(original) if original.suffix=='.parquet' else pd.read_csv(original,float_precision='round_trip')
    y=pd.read_parquet(replayed) if replayed.suffix=='.parquet' else pd.read_csv(replayed,float_precision='round_trip')
    x=x.sort_values(keys).reset_index(drop=True);y=y.sort_values(keys).reset_index(drop=True)
    assert set(x.columns)==set(y.columns),(label,'column names')
    pd.testing.assert_frame_equal(x,y[x.columns],check_dtype=False,check_exact=False,rtol=0,atol=1e-9)
    checks.append({'table':label,'rows':len(x),'columns':len(x.columns),'passed':True,'rtol':0,'atol':1e-9})
    print('EQUAL',label,flush=True)
run('data',[R/'data/build_panel.py','--repo',repo,'--output',a.out/'data'])
compare('panel',R/'data/panel.parquet',a.out/'data/panel.parquet',['id'])
run('model',[R/'model/run_model.py','--panel',a.out/'data/panel.parquet','--out',a.out/'model','--skip-sensitivity'])
for n,key in [('nearest_membership',['id']),('centers',['id']),('zone_trajectories',['center_id']),('nested_aggregates',['aggregation_step','nested_unit']),('dynamic2021_membership',['id']),('fixed_dynamic_decomposition',['baseline_year','center_id'])]:
    compare(n,R/f'model/{n}.parquet',a.out/f'model/{n}.parquet',key)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    jobs=[pool.submit(run,'agriculture',[R/'agriculture/run.py','--source',a.inputs/'columnar/agriculture.parquet','--panel',a.out/'data/panel.parquet','--membership',a.out/'model/nearest_membership.parquet','--out',a.out/'agriculture']),pool.submit(run,'rfsd',[R/'rfsd/project_finances.py','--cache',a.inputs/'enrichment','--membership',a.out/'model/nearest_membership.parquet','--out',a.out/'rfsd'])]
    for job in jobs:job.result()
compare('crop main',R/'agriculture/zone_functional_main.csv',a.out/'agriculture/zone_functional_main.csv',['center_id'])
compare('municipal profiles',R/'agriculture/municipal_crop_profiles_2021.csv',a.out/'agriculture/municipal_crop_profiles_2021.csv',['oktmo'])
for n,keys in [('financial_observations',['center_id','year','max_distance_km','quality']),('sector_sensitivity',['center_id','year','max_distance_km','quality','okved_section']),('center_economic_witness',['center_id','year','max_distance_km','quality','okved_section'])]:
    compare(n,R/f'rfsd/primary2010/{n}.parquet',a.out/f'rfsd/{n}.parquet',keys)
receipt={'status':'PASS','commands':commands,'fresh_directory':str(a.out),'checks':checks,'passed':len(checks),'failed':0}
(a.out/'REPLAY.json').write_text(json.dumps(receipt,indent=2));(R/'REPLAY.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)

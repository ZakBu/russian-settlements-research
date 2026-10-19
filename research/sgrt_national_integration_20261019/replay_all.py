#!/usr/bin/env python3
"""Recompute nationwide derived tables in a fresh workspace from frozen inputs.

This replays the new national-integration wave. The older fifteen-year RFSD
calendar is a pinned input, not a claim to re-download/rebuild all 63M rows here.
Raw financial extracts 2016/2021 and selected physical POI are re-aggregated.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,tempfile,time
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--receipt',type=Path,default=ROOT/'REPLAY.json');ap.add_argument('--keep-temp',action='store_true');a=ap.parse_args()
 t=time.monotonic();tmp=Path(tempfile.mkdtemp(prefix='sgrt_national_replay_'));dst=tmp/ROOT.name;dst.mkdir();logs=ROOT/'replay_logs';logs.mkdir(exist_ok=True)
 receipt={'status':'RUNNING','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'temporary_base':str(tmp),'commands':[],'comparisons':[],'frozen_source_policy':'Original input trees are only read through symlinks; executable new builders and source selected-place fragments are copied. Frozen input SHA256 checked before/after; no OS read-only guarantee claimed.','scope':'New national integration; frozen 15-year RFSD calendar reused; raw financial extracts and physical POI re-aggregated.'}
 frozen={}
 # Copy executable builders only: no precomputed result can satisfy the replay.
 for p in ROOT.rglob('*.py'):
  if any(x.startswith('.') or x in {'__pycache__','replay_logs'} for x in p.relative_to(ROOT).parts):continue
  q=dst/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 for p in (ROOT/'places/selected').glob('*.parquet'):
  q=dst/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);frozen[str(p)]=sha(p)
 shutil.copy2(ROOT/'places/ACQUISITION.json',dst/'places/ACQUISITION.json')
 # Full frozen trees are linked for historical dependencies; mutation is never
 # part of these builders. Hash declared files, not unneeded binary caches.
 for name in ['anchor_research_20261019','functional_dynamics_20261019','restored']:(tmp/name).symlink_to((BASE/name).resolve(),target_is_directory=True)
 input_paths=set()
 for relative in ['economy/AUDIT.json','services/AUDIT.json','services/NAME_RELAXATION_AUDIT.json','agriculture/AUDIT.json','core/MASTER_AUDIT.json','core/EXTENDED_MASTER_AUDIT.json']:
  data=json.loads((ROOT/relative).read_text())
  for key in ['inputs','inputs_sha256']:
   v=data.get(key,{})
   if isinstance(v,dict):input_paths.update(v)
   elif isinstance(v,list):input_paths.update(x['path'] for x in v)
 # Auxiliary dependencies are explicit for portable packages.
 input_paths.update(['functional_dynamics_20261019/marketplaces/build_marketplaces.py','anchor_research_20261019/data/external_federal_axis.csv','restored/extracted/inputs/recovery_inputs/enrichment/world.geojson','anchor_research_20261019/model/documented_graph/service_edges_calculated.csv','functional_dynamics_20261019/model/results/canonical_documented_external_memberships.parquet','functional_dynamics_20261019/marketplaces/pickpoint_extracted_202102.csv'])
 for rel in sorted(input_paths):
  p=BASE/rel
  if p.is_file() and not p.is_relative_to(ROOT):frozen[str(p)]=sha(p)
 receipt['frozen_input_sha256_before']=frozen;dump(a.receipt,receipt)
 env=os.environ.copy();env.update({'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MPLCONFIGDIR':str(tmp/'matplotlib'),'PYTHONPYCACHEPREFIX':str(tmp/'pycache')})
 def run(label,rel,args=()):
  cmd=[sys.executable,str(dst/rel),*map(str,args)];start=time.monotonic();log=logs/(label+'.log')
  with log.open('w') as f:r=subprocess.run(cmd,cwd=tmp,env=env,stdout=f,stderr=subprocess.STDOUT)
  receipt['commands'].append({'label':label,'actual_command':cmd,'exit_code':r.returncode,'seconds':round(time.monotonic()-start,3),'log':str(log.relative_to(ROOT))});dump(a.receipt,receipt)
  if r.returncode:raise RuntimeError(label+' failed: '+str(log))
 try:
  run('01_economy','economy/build_economy_features.py',['--base',tmp,'--out',dst/'economy'])
  run('02_wb','services/build_wb_national.py')
  run('03_wb_geography_audit','services/audit_linkage_iterations.py')
  run('04_wb_name_relaxation','services/build_wb_name_relaxation.py')
  run('05_agriculture','agriculture/build_national_agriculture.py')
  run('06_agriculture_readback','agriculture/verify_national_agriculture.py')
  run('07_physical_places','places/build_places_features.py')
  run('08_master','core/build_feature_master.py',['--no-csv'])
  run('09_extended_master','core/build_extended_master.py')
  run('10_profiles','screening/support_point_screening.py',['--require-places'])
  run('11_pickpoint','services_pickpoint/build_pickpoint.py')
  run('12_documented_evidence','build_documented_evidence.py')
  tables=['economy/economy_features.parquet','services/wb_settlement_features.parquet','services/wb_objects_crosswalk.parquet','services/wb_name_relaxed_features.parquet','services/wb_type_relaxed_object_links.parquet','agriculture/point_municipal_agriculture.parquet','agriculture/municipal_crop_annual_profiles.parquet','places/places_objects_and_crosswalk.parquet','places/places_settlement_features.parquet','core/feature_master.parquet','core/feature_master_extended142572.parquet','screening/support_point_profiles.parquet','services_pickpoint/pickpoint_settlement_features.parquet','services_pickpoint/pickpoint_objects_crosswalk.parquet','documented_evidence/documented_settlement_features.parquet','documented_evidence/documented_external_relations.parquet']
  for rel in tables:
   expected=ROOT/rel;got=dst/rel;x=pq.read_table(expected).replace_schema_metadata(None);y=pq.read_table(got).replace_schema_metadata(None);equal=x.equals(y)
   receipt['comparisons'].append({'path':rel,'rows':len(x),'columns':len(x.column_names),'all_typed_cells_and_nulls_exact':equal,'expected_sha256':sha(expected),'replayed_sha256':sha(got)})
   if not equal:raise AssertionError('Typed all-cell replay mismatch: '+rel)
  receipt['frozen_input_sha256_after']={p:sha(p)for p in frozen};assert receipt['frozen_input_sha256_after']==frozen,'Frozen input changed'
  receipt['status']='PASS'
 except Exception as e:
  receipt['status']='FAIL';receipt['error']=str(e);raise
 finally:
  receipt['seconds']=round(time.monotonic()-t,3);receipt['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();receipt['executed_code_sha256']=sha(Path(__file__));dump(a.receipt,receipt)
  if receipt['status']=='PASS' and not a.keep_temp:shutil.rmtree(tmp)
 print(json.dumps({'status':receipt['status'],'commands':len(receipt['commands']),'tables':len(receipt['comparisons']),'seconds':receipt['seconds']}))
if __name__=='__main__':main()

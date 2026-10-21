#!/usr/bin/env python3
"""New immutable six-variant transport-bound configs; never rewrite original13.
Independent review must bind this exact graph, matrix and settlement snap,
directly or through its cryptographically reviewed routing receipt.
"""
from pathlib import Path
import argparse,json,hashlib,copy,datetime,shutil
H=Path(__file__).resolve().parent;REPO=next(p for p in H.parents if (p/'.git').exists())
VARIANTS=['baseline','narrow_general_health','broad_retail_plus_ATM','unknown_role_upper','P0_probability','inclusive_candidates']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.resolve().relative_to(REPO))
def dump(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
def run(a):
 source=a.source.resolve();net=a.network_directory.resolve();review=a.review.resolve();out=a.output.resolve();assert net.is_relative_to(REPO) and out.is_relative_to(REPO)
 assert not out.exists(),'Do not overwrite any config family'
 f=source/'cycle06_config_freeze_manifest.json';freeze=json.loads(f.read_text())
 for row in freeze['files']:assert sha(source/row['path'])==row['sha256'],row['path']
 matrix=net/'candidate_travel_times_manifest.json';snap=net/'settlement_road_snap.parquet';route=net/'routing_receipt.json';r=json.loads(route.read_text());j=json.loads(review.read_text());reviewtext=json.dumps(j,ensure_ascii=False)
 assert j.get('all_checks_passed') is True and j.get('n_failed',j.get('n_failed_checks',0))==0,'Independent graph/matrix admission required'
 assert not j.get('new_graph_matrix_acceptance_pending',False),'Finite semantic policy alone cannot admit matrix'
 matrixsha=sha(matrix);snapsha=sha(snap);graphsha=r['graph_sha256'];assert r['output_manifest_sha256']==matrixsha and str(r['source_snapshot_utc']).startswith('2021-01-01')
 direct=all(v in reviewtext for v in [matrixsha,snapsha,graphsha]);transitive=matrixsha in reviewtext and graphsha in reviewtext and sha(route) in reviewtext and snapsha in json.dumps(r)
 assert direct or transitive,'Unrelated or incomplete transport admission witness'
 if a.required_family=='transport_access_v2':assert 'access_v2' in str(net),'Requested actual access_v2 source family'
 out.mkdir(parents=True);shutil.copyfile(source/'cycle05_preregistration.json',out/'cycle05_preregistration.json');protocol=out/'transport_source_rebinding_protocol.json'
 provenance=[review,route,protocol]
 for name in ['artifact_manifest.json','graph_artifact_receipt.json','matrix_protocol.json','protocol.json']:
  if (net/name).exists():provenance.append(net/name)
 dump(protocol,dict(status='PREREGISTERED_TRANSPORT_SOURCE_REPAIR_ONLY_BEFORE_NEW_SIX_CI_PASSES',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),network_family=a.required_family,network_directory=rel(net),matrix_sha256=matrixsha,graph_sha256=graphsha,snap_sha256=snapsha,review=rel(review),review_sha256=sha(review),routing_receipt_sha256=sha(route),source_config_freeze_sha256=sha(f),six_original_scientific_scenarios_unchanged=True,old_memberships_or_outcomes_read=False,nonmass_additions_not_changed=True,code_sha256=sha(Path(__file__))))
 entries=[]
 for v in VARIANTS:
  original=source/('config_'+v+'_provisional.json');old=json.loads(original.read_text());new=copy.deepcopy(old);roads=[x for x in new['layers'] if x.get('prefix')=='road_'];assert len(roads)==1;roads[0]['path']=rel(snap)
  new.update(travel_manifest=rel(matrix),travel_edges=rel(matrix),network_source_snapshot_utc=r['source_snapshot_utc'],transport_reference_year=2021,target_run_id='sgrt_cycle06_'+a.required_family+'__'+v);new['provenance_sidecars']=list(dict.fromkeys(new.get('provenance_sidecars',[])+[rel(p) for p in provenance]))
  # After reversing the exact allowlist, the configuration must be byte-value identical.
  compare=copy.deepcopy(new)
  for k in ['travel_manifest','travel_edges','network_source_snapshot_utc','transport_reference_year','target_run_id','provenance_sidecars']:compare[k]=old[k]
  [x for x in compare['layers'] if x.get('prefix')=='road_'][0]['path']=[x for x in old['layers'] if x.get('prefix')=='road_'][0]['path'];assert compare==old,'Transport-only clone altered another setting'
  p=out/original.name;dump(p,new);entries.append(dict(variant=v,source=rel(original),source_sha256=sha(original),config=rel(p),configuration_sha256=sha(p)))
 dump(out/'binding_receipt.json',dict(status='SIX_PROVISIONAL_CONFIGS_BOUND_TO_INDEPENDENTLY_ADMITTED_TRANSPORT',entries=entries,transport_family=a.required_family,review_sha256=sha(review),matrix_sha256=matrixsha,graph_sha256=graphsha,snap_sha256=snapsha,scientific_parameters_unchanged=True,own_Mi_source_definitions_unchanged=True,model_outputs_read=False));files=list(out.iterdir());dump(out/'freeze_manifest.json',dict(files={p.name:sha(p) for p in files if p.is_file()}));print(out)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=H);p.add_argument('--network-directory',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--required-family',default='transport_access_v2');run(p.parse_args())

#!/usr/bin/env python3
"""Create a new bound final configuration after actual Ci and thematic review exist.
Never edit preregistered configs, frozen land/features, or prior memberships.
"""
from pathlib import Path
import argparse,json,hashlib,copy,datetime
import pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=ROOT.parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return str(p.resolve().relative_to(REPO))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(a):
 freeze=json.loads((H/'config_freeze_manifest.json').read_text());mismatch=[n for n,v in freeze['files'].items() if sha(H/n)!=v['sha256']]
 if mismatch:raise ValueError('Preregistered files changed: '+repr(mismatch))
 src=H/('config_'+a.variant+'_final.json');provisional=H/('config_'+a.variant+'_provisional.json');config=json.loads(src.read_text());pc=json.loads(provisional.read_text());original_pc=copy.deepcopy(pc)
 source_repair_proof=None
 if a.provisional_config:
  provisional=a.provisional_config.resolve();pc=json.loads(provisional.read_text());allowed={'travel_manifest','travel_edges','provenance_sidecars','layers'}
  diff={k for k in set(pc)|set(original_pc) if pc.get(k)!=original_pc.get(k)}
  if not diff<=allowed:raise ValueError('Clone changed preregistered scientific settings: '+repr(diff-allowed))
  extra=[v for v in pc.get('provenance_sidecars',[]) if v not in original_pc.get('provenance_sidecars',[])]
  if any(v not in pc.get('provenance_sidecars',[]) for v in original_pc.get('provenance_sidecars',[])) or any(not v.endswith(('/supplemental_routing_protocol.json','/supplemental_source_repair_protocol.json')) for v in extra):raise ValueError('Clone provenance contract failed')
  for v in extra:
   proof=json.loads((REPO/v).read_text())
   if v.endswith('/supplemental_source_repair_protocol.json'):source_repair_proof=proof
  if len(pc['layers'])!=len(original_pc['layers']):raise ValueError('Source clone added/removed source layers')
  for oldlayer,newlayer in zip(original_pc['layers'],pc['layers']):
   if oldlayer==newlayer:continue
   if not source_repair_proof or oldlayer.get('prefix') not in {'medical_','school_','services_'} or {k:v for k,v in oldlayer.items() if k!='path'}!={k:v for k,v in newlayer.items() if k!='path'}:raise ValueError('Undeclared source clone layer change')
   binding=next((v for v in source_repair_proof['family_bindings'] if v['prefix']==oldlayer['prefix']),None)
   if not binding or binding['old_path']!=oldlayer['path'] or binding['new_path']!=newlayer['path'] or binding['new_sha256']!=sha(REPO/newlayer['path']):raise ValueError('Source clone differs from frozen repair proof')
   olddata=pd.read_parquet(REPO/oldlayer['path'],columns=['id']+binding['strict_baseline_columns_identical']);newdata=pd.read_parquet(REPO/newlayer['path'],columns=['id']+binding['strict_baseline_columns_identical'])
   if not olddata.equals(newdata):raise ValueError('Actual strict source primary counts changed')
   for layer in config['layers']:
    if layer.get('prefix')==oldlayer['prefix']:layer['path']=newlayer['path']
  config['travel_manifest']=pc['travel_manifest'];config['travel_edges']=pc['travel_edges'];config['provenance_sidecars']+=extra
  if source_repair_proof:
   if not a.source_review:raise ValueError('Independent V4 source review required for final source-bound config')
   sr=a.source_review.resolve();review_text=sr.read_text();sj=json.loads(review_text)
   if str(sj.get('status','')).startswith(('COMPUTED_PENDING','PREPARED','FIX_REQUIRED','REJECT')) or sj.get('n_failed',sj.get('n_failed_checks',0))!=0:raise ValueError('Source repair independent review not passed')
   if source_repair_proof['new_source_freeze_manifest_sha256'] not in review_text and not all(v['new_sha256'] in review_text for v in source_repair_proof['family_bindings']):raise ValueError('Source review does not pin actual repaired feature bytes')
   config['provenance_sidecars'].append(rel(sr))

 ci_dir=(a.ci_directory or H/('provisional_'+a.variant)).resolve();receipt=ci_dir/'receipt.json';ci=ci_dir/'word_ci_center_features.parquet';r=json.loads(receipt.read_text())
 if r['variant']!=a.variant or r['input_bytes_changed'] or r['own_mass_refit'] or r['provisional_iterations']!=1:raise ValueError('Ci receipt variant/source/fixedMi contract failed')
 if r['input_sha256'].get(str(provisional.resolve()))!=sha(provisional):raise ValueError('Ci used a different provisional config')
 if r['selected_rural_volume_policy']!=config['settlement_role_policy']['rural_volume']:raise ValueError('Ci rural bound differs from final variant')
 x=pd.read_parquet(ci);mass=pd.read_parquet(ci_dir/'fixed_own_mass_components.parquet');z=x[['id','own_positive_mass']].merge(mass[['id','own_positive_mass']],on='id',validate='one_to_one',suffixes=('_Ci','_fixed'))
 if not z.own_positive_mass_Ci.equals(z.own_positive_mass_fixed):raise ValueError('Ci ownMi differs from independently saved fixed source mass')
 if x.word_centrality_observed2021_frame_0_1.isna().any() or not x.id.is_unique:raise ValueError('Missing/duplicate final candidateCi; do not invent fallback')
 fingerprint=hashlib.sha256(pd.util.hash_pandas_object(mass[['id','own_positive_mass']],index=False).to_numpy().tobytes()).hexdigest()
 if fingerprint!=r['own_mass_values_sha256']:raise ValueError('Saved provisional mass fingerprint mismatch')
 import sys
 sys.path.insert(0,str(ROOT/'model'));import run_word_model_cycle05 as current_model
 current_nodes,current_watched=current_model.load_nodes(pc);current_mass,current_components=current_model.build_mass(current_nodes,pc)
 comparecols=[v for v in mass if v=='id' or v=='own_positive_mass' or v.endswith(('_raw','_z')) or v=='n_observed_mass_blocks']
 if not current_mass[comparecols].equals(mass[comparecols]):raise ValueError('Actual current Mi components differ from the saved provisional components')
 thematic=next(REPO/l['path'] for l in config['layers'] if '/thematic2021/' in l['path']);review=a.thematic_review.resolve();reviewtext=review.read_text();reviewj=json.loads(reviewtext)
 if str(reviewj.get('status','')).startswith(('COMPUTED_PENDING','PREPARED','FIX_REQUIRED','REJECT')) or reviewj.get('n_failed',reviewj.get('n_failed_checks',0))!=0:raise ValueError('Thematic independent review not passed')
 if sha(thematic) not in reviewtext:raise ValueError('Thematic independent review does not pin the actual thematic bytes')
 if a.travel_manifest:
  config['travel_manifest']=rel(a.travel_manifest);config['travel_edges']=rel(a.travel_manifest)
 if a.external_anchors_receipt:
  ap=a.external_anchors_receipt.resolve();w=json.loads(ap.read_text());config['external_large_city_anchors']=[{**v,'source_receipt':rel(ap),'source_receipt_sha256':sha(ap)} for v in w['witnesses']];config['provenance_sidecars'].append(rel(ap))
 for l in config['layers']:
  if l.get('prefix')=='wordci_':l['path']=rel(ci)
  if '/thematic2021/' in l['path']:
   l['retain_evidence_suffix']=False
   l['retain_prefixes']+=['ethnicity_']
 # Recheck the actual source layers controlling fixed Mi, not a new generator assertion.
 current_changed=[]
 for l in pc['layers']:
  q=(REPO/l['path']).resolve();expected=r['input_sha256'].get(str(q))
  if expected is None or sha(q)!=expected:current_changed.append(str(q))
 if current_changed:raise ValueError('Provisional source features changed before final binding: '+repr(current_changed))
 config['rank_provisional_receipt']=rel(receipt);config['rank_index']['provisional_receipt_sha256']=sha(receipt);config['rank_index']['fixed_own_mass_values_sha256']=fingerprint;config['provenance_sidecars']=list(dict.fromkeys([rel(receipt) if p.endswith('/receipt.json') and '/provisional_' in p else p for p in config['provenance_sidecars']]+[rel(review),rel(H/'cycle05_preregistration.json'),rel(H/'config_freeze_manifest.json'),rel(Path(__file__))]))
 config['cycle05_final_binding']={'variant':a.variant,'new_Ci_sha256':sha(ci),'new_Ci_receipt_sha256':sha(receipt),'thematic_sha256':sha(thematic),'thematic_independent_review_sha256':sha(review),'no_previous_memberships_or_ranks_reused':True,'same_fixed_Mi_formula_for_provisional_and_final':True}
 out=(a.output or H/'bound_final'/('config_'+a.variant+'_final_bound.json')).resolve();out.parent.mkdir(parents=True,exist_ok=True)
 if out.exists():raise FileExistsError('Refusing to overwrite existing final bound config '+str(out))
 dump(out,config);binding=dict(status='FINAL_CONFIG_BOUND_TO_ACTUAL_NEW_CI_AND_REVIEWED_THEMATIC',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),variant=a.variant,eligible_centers=len(x),source_preregistered_final_config_sha256=sha(src),provisional_config_sha256=sha(provisional),new_Ci_sha256=sha(ci),fixed_Mi_values_sha256=fingerprint,thematic_review_sha256=sha(review),final_config_sha256=sha(out),final_config_path=rel(out),input_config17_snapshot_unchanged=True,code_sha256=sha(Path(__file__)))
 dump(out.with_suffix('.binding_receipt.json'),binding);print(json.dumps(binding,ensure_ascii=False,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--variant',choices=['baseline','narrow_general_health','broad_retail_plus_ATM','unknown_role_upper','P0_probability','inclusive_candidates'],default='baseline');p.add_argument('--ci-directory',type=Path);p.add_argument('--provisional-config',type=Path);p.add_argument('--thematic-review',type=Path,required=True);p.add_argument('--source-review',type=Path);p.add_argument('--travel-manifest',type=Path);p.add_argument('--external-anchors-receipt',type=Path);p.add_argument('--output',type=Path);run(p.parse_args())

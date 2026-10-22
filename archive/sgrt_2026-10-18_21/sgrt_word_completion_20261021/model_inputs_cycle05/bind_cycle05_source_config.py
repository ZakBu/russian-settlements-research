#!/usr/bin/env python3
"""Version source repair without rewriting preregistration, routing clones or prior runs."""
from pathlib import Path
import argparse,json,hashlib,shutil,datetime
import pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=ROOT.parents[1]
VARIANTS=['baseline','narrow_general_health','broad_retail_plus_ATM','unknown_role_upper','P0_probability','inclusive_candidates']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return str(p.resolve().relative_to(REPO))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def run(a):
 base=a.base_config_directory.resolve();new=a.medical_features.resolve();out=a.output_directory.resolve();orig=ROOT/'model_inputs_cycle05/relinked_v3/medical/settlement_features_full_axis.parquet';v3=pd.read_parquet(orig);v4=pd.read_parquet(new)
 if not v3.id.equals(v4.id) or not v4.id.is_unique:raise ValueError('Medical source repair changes axis IDs/order')
 strict=[c for c in v3 if c.startswith('medical_osm_baseline_') and c.endswith('_count')];different=[c for c in strict if not v3[c].equals(v4[c])]
 if different:raise ValueError('Source repair changes actual strict mass/provider input values: '+repr(different))
 bindings=[]
 for family,prefix in [('education','school_'),('commerce','services_'),('medical','medical_')]:
  op=H/'relinked_v3'/family/'settlement_features_full_axis.parquet';np=new.parents[1]/family/'settlement_features_full_axis.parquet';od=pd.read_parquet(op);nd=pd.read_parquet(np);cols=[c for c in od if '_baseline_' in c and c.endswith('_count')]
  if not od.id.equals(nd.id) or not all(od[c].equals(nd[c]) for c in cols):raise ValueError('Primary source counts orIDs changed in '+family)
  bindings.append(dict(family=family,prefix=prefix,old_path=rel(op),old_sha256=sha(op),new_path=rel(np),new_sha256=sha(np),strict_baseline_columns_identical=cols,strict_count_values_equal=len(od)*len(cols),all_feature_cells_equal=od.equals(nd)))
 if out.exists() and any(out.iterdir()):raise FileExistsError('Versioned source config directory is not empty')
 out.mkdir(parents=True,exist_ok=True);shutil.copyfile(H/'cycle05_preregistration.json',out/'cycle05_preregistration.json');protocol=out/'supplemental_source_repair_protocol.json';travel=a.travel_manifest.resolve() if a.travel_manifest else None
 record=dict(family_bindings=bindings,status='SOURCE_REPAIR_APPEND_STRICT_PRIMARY_MASS_COUNTS_IDENTICAL',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_preregistration_sha256=sha(H/'cycle05_preregistration.json'),old_medical_features=rel(orig),old_medical_features_sha256=sha(orig),new_medical_features=rel(new),new_medical_features_sha256=sha(new),new_source_freeze_manifest_sha256=sha(new.parents[1]/'source_freeze_manifest.json'),strict_baseline_columns_identical=strict,strict_baseline_rows=len(v3),strict_baseline_count_values_equal=len(v3)*len(strict),axis_IDs_order_unchanged=True,only_coordinate_candidate_provenance_repair_not_primary_count_change=True,scientific_design_change=False,new_primary_mass_fitting=False,no_membership_reuse=True,source_review_must_be_independently_accepted_before_final_binding=True,new_travel_manifest=rel(travel) if travel else None,new_travel_manifest_sha256=sha(travel) if travel else None,allowed_config_differences=['only_medical_layer_path','travel_manifest_or_travel_edges_if_new_complete360matrix','append_this_protocol_provenance'],code_sha256=sha(Path(__file__)));dump(protocol,record);clones=[]
 for variant in VARIANTS:
  p=base/('config_'+variant+'_provisional.json');c=json.loads(p.read_text())
  for binding in bindings:
   layers=[l for l in c['layers'] if l.get('prefix')==binding['prefix']]
   if len(layers)!=1 or layers[0]['path']!=binding['old_path']:raise ValueError('Unexpected original source binding '+binding['family'])
   layers[0]['path']=binding['new_path']
  if travel:c['travel_manifest']=rel(travel);c['travel_edges']=rel(travel)
  c['provenance_sidecars']=c.get('provenance_sidecars',[])+[rel(protocol)];q=out/p.name;dump(q,c);clones.append(dict(variant=variant,base=rel(p),base_sha256=sha(p),source_clone=rel(q),source_clone_sha256=sha(q)))
 dump(out/'source_binding_receipt.json',dict(status='NEW_SOURCE_BOUND_PROVISIONAL_CONFIGS_READY_PENDING_V4_SOURCE_REVIEW',protocol_sha256=sha(protocol),original17_and_routing_clones_unchanged=True,clones=clones));print(json.dumps(dict(status='SOURCEBOUND_READY',strict_columns=len(strict),strict_count_values_equal=record['strict_baseline_count_values_equal'],output_directory=rel(out)),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base-config-directory',type=Path,default=H/'routing_bound_v1');p.add_argument('--medical-features',type=Path,required=True);p.add_argument('--travel-manifest',type=Path);p.add_argument('--output-directory',type=Path,default=H/'source_bound_v4');run(p.parse_args())

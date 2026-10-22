"""Descriptive paired partition sensitivity, no retuning or CI claim."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
from sklearn.metrics import adjusted_rand_score
HERE=Path(__file__).resolve().parent;ENGINE=HERE.parent/'source477_adminall_v2'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
primary=ENGINE/'output_primary_v1';batch=ENGINE/'admitted_sensitivity_batch_receipt.json';receipt=json.loads(batch.read_text());watch={str(batch):sha(batch),str(Path(__file__)):sha(Path(__file__))};providers=set(pd.read_parquet(ENGINE/'source_provider_pool/active_provider_pool.parquet',columns=['id']).id);watch[str(ENGINE/'source_provider_pool/active_provider_pool.parquet')]=sha(ENGINE/'source_provider_pool/active_provider_pool.parquet');rows=[]
for run in receipt['completed']:
 out=ENGINE.parent.parent.parent/run['output'] if False else Path(run['output'])
 if not out.is_absolute():out=next(p for p in HERE.parents if (p/'model').is_dir() and (p/'transport').is_dir())/out
 bind=json.loads((out/'pre_execution_binding.json').read_text());caps=bind['protocol']['extent']['candidate_caps_minutes']+([180]if bind['scenario_parameters']['extended180']else[])
 manifest=out/'baseline_export_manifest.json';watch[str(manifest)]=sha(manifest)
 for item in json.loads(manifest.read_text())['files']:
  p=out/item['path'];assert sha(p)==item['sha256'];watch[str(p)]=item['sha256']
 for cap in caps:
  u=pd.read_parquet(out/f'cap_{cap:03}_raw_units.parquet');m=pd.read_parquet(out/f'cap_{cap:03}_raw_memberships.parquet')
  for partition in ['candidate_knee_or_fallback','supported_end_forest']:
   uu=u[u.partition_role.eq(partition)];mm=m[m.partition_role.eq(partition)].merge(uu[['unit_id','core_id']],on='unit_id',validate='many_to_one').sort_values('id');assert mm.id.is_unique
   territorial=uu.unit_role.eq('territorial_unit');record={'scenario':run['scenario'],'candidate_cap':cap,'partition_role':partition,'n_all_atoms':len(mm),'n_territorial_units':int(territorial.sum()),'n_protected_carry':int((~territorial).sum()),'largest_territorial_member_count':int(uu.loc[territorial,'n_members'].max()),'max_positive_envelope_minutes':float(uu.loc[territorial,'max_member_direct_minutes'].max()),'comparison_status':'NO_PRIMARY180CAP_EXTENDED_SCENARIO_ONLY','all_axis_ARI_to_primary':None,'active_provider_ARI_to_primary':None,'fraction_atoms_with_changed_focal':None,'fraction_atoms_in_different_exact_membership_unit':None,'bootstrap50_computed_for_sensitivity':False}
   if cap<=120:
    up=primary/f'cap_{cap:03}_raw_units.parquet';mp=primary/f'cap_{cap:03}_raw_memberships.parquet';watch[str(up)]=sha(up);watch[str(mp)]=sha(mp);bu=pd.read_parquet(up);bm=pd.read_parquet(mp);bu=bu[bu.partition_role.eq(partition)];bm=bm[bm.partition_role.eq(partition)].merge(bu[['unit_id','core_id']],on='unit_id',validate='many_to_one').sort_values('id')
    assert mm.id.reset_index(drop=True).equals(bm.id.reset_index(drop=True));a=mm.unit_id.to_numpy();b=bm.unit_id.to_numpy();active=mm.id.isin(providers).to_numpy();record.update(comparison_status='EXACT_SAME_SOURCE_ATOM_FRAME_PAIRED_OPERATIONAL_PARTITION',all_axis_ARI_to_primary=float(adjusted_rand_score(a,b)),active_provider_ARI_to_primary=float(adjusted_rand_score(a[active],b[active])),fraction_atoms_with_changed_focal=float(np.mean(mm.core_id.to_numpy()!=bm.core_id.to_numpy())),fraction_atoms_in_different_exact_membership_unit=float(np.mean(a!=b)))
   rows.append(record)
pd.DataFrame(rows).to_csv(HERE/'paired_partition_sensitivity.csv',index=False);assert all(sha(Path(p))==h for p,h in watch.items());r={'status':'ALL_SIX_ACTUAL_BASELINE_ONLY_SENSITIVITY_PARTITIONS_DESCRIBED_NO_RETUNING','n_partition_comparisons':len(rows),'sensitivity50_bootstrap_not_computed':True,'same_population_and_sourceMi_frame':True,'primary50_stability_is_separate':True,'source_pins':watch,'output_sha256':sha(HERE/'paired_partition_sensitivity.csv')};(HERE/'receipt.json').write_text(json.dumps(r,indent=2));print(pd.DataFrame(rows).query("partition_role=='supported_end_forest'")[['scenario','candidate_cap','n_territorial_units','all_axis_ARI_to_primary','active_provider_ARI_to_primary','fraction_atoms_with_changed_focal']].to_string(index=False))

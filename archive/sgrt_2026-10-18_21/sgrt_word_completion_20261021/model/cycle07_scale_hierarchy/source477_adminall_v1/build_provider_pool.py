"""Join admitted source eligibility to actual accepted directed routing maps.
No inferred service presence from routing, and no use of stale routable flags.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from matrix_query import sha
HERE=Path(__file__).resolve().parent
BASE=next(x for x in HERE.parents if (x/'transport').is_dir() and (x/'model').is_dir())

def main():
 protocol=json.loads((HERE/'PROTOCOL_v1.json').read_text())
 handoff_path=BASE/'model_inputs_cycle07/cycle07_source_mass_pool_admitted_handoff.json'
 handoff=json.loads(handoff_path.read_text())
 admission_path=BASE/handoff['independent_admission_path']
 if sha(admission_path)!=handoff['independent_admission_sha256']:raise ValueError('source admission bytes changed')
 admission=json.loads(admission_path.read_text())
 if admission.get('all_checks_passed') is not True:raise ValueError('source mass/pool not independently admitted')
 paths={k:BASE/handoff['paths'][k] for k in ['all173864_provider_eligibility','fixed_own_mass','effective_full_nodes']}
 for k,p in paths.items():
  if sha(p)!=handoff['sha256'][k]:raise ValueError('source handoff bytes changed: '+k)
 d=pd.read_parquet(paths['all173864_provider_eligibility'])
 mass=pd.read_parquet(paths['fixed_own_mass'],columns=['id','own_positive_mass'])
 check=d[['id','own_positive_mass']].merge(mass,on='id',validate='one_to_one',suffixes=('_pool','_mass'))
 if len(check)!=len(d) or not np.array_equal(check.own_positive_mass_pool,check.own_positive_mass_mass,equal_nan=True):raise ValueError('provider source mass identity mismatch')
 mp=BASE/protocol['matrix_manifest']
 if sha(mp)!=protocol['matrix_sha256']:raise ValueError('matrix manifest bytes changed')
 manifest=json.loads(mp.read_text());maps={}
 for key in ['origin_mapping','destination_mapping']:
  p=mp.parent/manifest[key]['path']
  if sha(p)!=manifest[key]['sha256']:raise ValueError('routing map bytes changed')
  maps[key]=pd.read_parquet(p)
  if maps[key].canonical_id.duplicated().any():raise ValueError('duplicate accepted canonical routing identity')
 d['accepted_routing_origin']=d.id.isin(maps['origin_mapping'].canonical_id)
 d['accepted_routing_destination']=d.id.isin(maps['destination_mapping'].canonical_id)
 d['active_provider']=d.eligible_source_provider.fillna(False)&d.accepted_routing_origin&d.accepted_routing_destination
 d['pool_status']=np.where(d.active_provider,'active_dated_provider',np.where(d.eligible_source_provider.fillna(False),'eligible_but_unrouted_unknown_field_coverage','outside_active_source_pool_not_service_absence'))
 active=d.loc[d.active_provider].sort_values('id').reset_index(drop=True)
 if active.id.duplicated().any() or (~np.isfinite(active.own_positive_mass)|active.own_positive_mass.le(0)).any():raise ValueError('invalid active fixed mass/identity')
 budgets=maps['destination_mapping'].set_index('canonical_id').loc[active.id,'routing_budget_minutes']
 if budgets.lt(180).any():raise ValueError('incomplete uniform180 provider field')
 out=HERE/'source_provider_pool';out.mkdir(exist_ok=True)
 if any(out.iterdir()):raise ValueError('provider pool output must be fresh')
 d.to_parquet(out/'all_source_provider_eligibility.parquet',index=False)
 active.to_parquet(out/'active_provider_pool.parquet',index=False)
 d.loc[d.eligible_source_provider.fillna(False)&~d.active_provider].to_parquet(out/'eligible_unrouted_source_providers.parquet',index=False)
 receipt=dict(status='SOURCE_ONLY_POOL_ROUTING_INTERSECTION_NOT_HIERARCHY_RESULT',code_sha256=sha(Path(__file__)),handoff_sha256=sha(handoff_path),source_admission_sha256=sha(admission_path),matrix_manifest_sha256=sha(mp),n_all=len(d),n_source_eligible=int(d.eligible_source_provider.sum()),n_active=len(active),n_eligible_unrouted=int((d.eligible_source_provider.fillna(False)&~d.active_provider).sum()),stale_routable_coordinate_flag_not_used=True,source_mass_identical=True,files={p.name:sha(p) for p in out.glob('*.parquet')})
 (out/'provider_pool_receipt.json').write_text(json.dumps(receipt,indent=2))
 print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()

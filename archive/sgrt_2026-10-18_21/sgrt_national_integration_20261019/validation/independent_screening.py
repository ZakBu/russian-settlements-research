#!/usr/bin/env python3
"""Rebuild nationwide function signatures from source layers, not author output."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent;O=H/'independent_sources/screening';O.mkdir(parents=True,exist_ok=True)
LEGAL={'retail47':'retail','food56':'food_service','education85':'education','health86':'healthcare','social8788':'social_care','repair95':'repair','personal96':'personal'}
PHYSICAL={'school':'education','preschool':'education','other_education':'education','hospital':'healthcare','healthcare':'healthcare','veterinary':'veterinary','pharmacy':'pharmacy','bank':'banking','atm':'banking','post_office':'postal_service','postal_collection_point':'postal_service','market':'retail','retail_store':'retail','food_service':'food_service'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 paths={'axis':B/'anchor_research_20261019/data/point_axis.parquet','economy':N/'economy/economy_features.parquet','wb':N/'services/wb_settlement_features.parquet','wb_relaxed':N/'services/wb_name_relaxed_features.parquet','screening':N/'screening/support_point_profiles.parquet'};pp=N/'places/places_settlement_features.parquet'
 if pp.exists():paths['places']=pp
 before={k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()};axis=pd.read_parquet(paths['axis']);ids=axis.id;e=pd.read_parquet(paths['economy']).set_index('id').reindex(ids);w=pd.read_parquet(paths['wb']).set_index('id').reindex(ids);s=pd.read_parquet(paths['screening']);checks=[]
 def ck(n,v,d=None):checks.append({'name':n,'pass':bool(v),'detail':d})
 ck('full_unique_axis',len(s)==142570 and s.id.is_unique and s.id.equals(ids));s=s.set_index('id').reindex(ids);q=pd.read_parquet(pp).set_index('id').reindex(ids) if pp.exists() else None
 functions=list(dict.fromkeys(list(LEGAL.values())+list(PHYSICAL.values())+['marketplace_pickup']));groups={key:{f:np.zeros(len(ids),bool) for f in functions} for key in ['legal_native','legal_conditional','physical_baseline','physical_conditional','wb_strict','wb_name_relaxed']}
 for key,prefix in [('legal_native','econ_native_2025_'),('legal_conditional','econ_alias_2025_')]:
  for g,f in LEGAL.items():groups[key][f]=e[prefix+g+'_legal_entities'].gt(0).to_numpy();ck(key+'_input_'+g,np.array_equal(e[prefix+g+'_legal_entities'],s[key+'_'+g+'_registered_entities']))
 groups['wb_strict']['marketplace_pickup']=w.wb_strict_focus_types_locations.gt(0).to_numpy();ck('wb_strict_input',np.array_equal(w.wb_strict_focus_types_locations,s.wb_strict_focus_published_locations))
 wr=pd.read_parquet(paths['wb_relaxed']).set_index('id').reindex(ids);groups['wb_name_relaxed']['marketplace_pickup']=wr.wb_name_relaxed_inclusive_focus_locations.gt(0).to_numpy();ck('wb_relaxed_focus_input',np.array_equal(wr.wb_name_relaxed_inclusive_focus_locations,s.wb_name_relaxed_inclusive_focus_locations));ck('wb_relaxed_focus_increment',np.array_equal(wr.wb_name_relaxed_inclusive_focus_locations-w.wb_strict_focus_types_locations,s.wb_name_relaxed_additional_focus_locations))
 if q is not None:
  for mode,key in [('baseline','physical_baseline'),('conditional','physical_conditional')]:
   for g,f in PHYSICAL.items():
    col=f'places_{mode}_{g}_count';groups[key][f] |= q[col].gt(0).to_numpy();ck(key+'_input_'+g,np.array_equal(q[col],s[key+'_'+g+'_source_places']))
 for f in functions:groups['physical_conditional'][f] |= groups['physical_baseline'][f]
 for key,components in [('baseline',['legal_native','physical_baseline','wb_strict']),('conditional',['legal_conditional','physical_conditional','wb_name_relaxed'])]:groups[key]={f:np.logical_or.reduce([groups[c][f] for c in components]) for f in functions}
 rows=[]
 for key,fg in groups.items():
  if key.startswith('physical_') and q is None:
   ck(key+'_missing_source_not_zero',s[key+'_function_diversity'].isna().all() and s[key+'_profile_category'].eq('observations_nodata').all());continue
  raw_count=np.zeros(len(ids),int)
  for f,positive in fg.items():ck(key+'_unmerged_mask_'+f,np.array_equal(positive,s[key+'_unmerged_function_'+f+'_witness'].to_numpy()));raw_count+=positive
  raw_category=np.array(['observed_none','single_observed_function','multiple_observed_functions'])[np.minimum(raw_count,2)];ck(key+'_unmerged_diversity',np.array_equal(raw_count,s[key+'_unmerged_function_diversity']));ck(key+'_unmerged_category',np.array_equal(raw_category,s[key+'_unmerged_profile_category']))
  primary={('trade_access' if f=='retail' else f):(fg[f]|fg['marketplace_pickup'] if f=='retail' else fg[f]) for f in functions if f!='marketplace_pickup'};count=np.zeros(len(ids),int)
  for f,positive in primary.items():ck(key+'_primary_mask_'+f,np.array_equal(positive,s[key+'_function_'+f+'_witness'].to_numpy()));count+=positive
  category=np.array(['observed_none','single_observed_function','multiple_observed_functions'])[np.minimum(count,2)];ck(key+'_diversity',np.array_equal(count,s[key+'_function_diversity']));ck(key+'_category',np.array_equal(category,s[key+'_profile_category']));signature=['|'.join(f for f in primary if primary[f][i]) for i in range(len(ids))];ck(key+'_signature',np.array_equal(signature,s[key+'_profile_signature']));rows.extend({'bundle':key,'category':c,'UIDs':int((category==c).sum())} for c in np.unique(category))
 # Distinct whole 7-function profiles across fifteen years; use tuple strings,
 # independently of the author's bit-coded state implementation.
 historical=[]
 for y in range(2011,2026):historical.append(e[[f'econ_native_{y}_{g}_legal_entities' for g in LEGAL]].gt(0).to_numpy())
 arrays=np.stack(historical,axis=1);presence=arrays.any(axis=2);switches=(arrays[:,1:,:]!=arrays[:,:-1,:]).any(axis=2).sum(axis=1);stable=(~(arrays!=arrays[:,:1,:]).any(axis=(1,2)))&presence.all(axis=1);distinct=np.array([len({tuple(t) for t in x}) for x in arrays]);ck('all_fifteen_years_presence',np.array_equal(presence.sum(axis=1),s.legal_2011_2025_witness_years));ck('all_profile_switches',np.array_equal(switches,s.legal_2011_2025_profile_switches));ck('all_presence_switches',np.array_equal((presence[:,1:]!=presence[:,:-1]).sum(axis=1),s.legal_2011_2025_presence_switches));ck('all_distinct_profiles',np.array_equal(distinct,s.legal_2011_2025_distinct_profiles_including_no_witness));ck('positive_profile_stable_all_years',np.array_equal(stable,s.legal_2011_2025_profile_stable_all_years))
 ck('no_external_centrality_claimed',not s.external_catchment_or_support_centrality_proven.any());ck('no_complete_function_census_claimed',not s.baseline_complete_physical_function_census.any());ck('zero_population_density_missing',s.loc[axis.population_2021.eq(0).to_numpy(),'functions_per_1000_population_descriptive'].isna().all());ck('no_infinite_density',not np.isinf(s.functions_per_1000_population_descriptive).any());ck('federal_pressure_not_measured',not s.external_federal_centre_influence_measured.any());ck('all_inputs_stable',all(sha(Path(v['path']))==v['sha256'] for v in before.values()))
 pd.DataFrame(rows).to_csv(O/'independent_profile_counts.csv',index=False);result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'inputs':before,'code_SHA256':sha(Path(__file__)),'places_loaded':q is not None,'stable_positive_legal_profiles':int(stable.sum()),'interpretation':'Functional evidence catalogue and descriptive trajectories; not demonstrated support centrality, institutional closure, actual flows or SGRT classification.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks; places_loaded=',q is not None,flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

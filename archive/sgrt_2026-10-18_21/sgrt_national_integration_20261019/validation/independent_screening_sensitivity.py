#!/usr/bin/env python3
"""Rebuild every branded-retail and coordinate-radius sensitivity from objects."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
from independent_screening import LEGAL,PHYSICAL
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent;O=H/'independent_sources/screening_sensitivity';O.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def category(v):return np.array(['observed_none','single_observed_function','multiple_observed_functions'])[np.minimum(v,2)]
def primary(a):return a.sum(axis=1)-(a[:,0]&a[:,-1])
def main():
 paths=[N/'economy/economy_features.parquet',N/'places/places_settlement_features.parquet',N/'places/places_objects_and_crosswalk.parquet',N/'services/wb_settlement_features.parquet',N/'services/wb_name_relaxed_features.parquet',N/'services/wb_objects_crosswalk.parquet',N/'screening/support_point_profiles.parquet'];before={str(p):sha(p) for p in paths};cols=['id']+[f'econ_{mode}_2025_{g}_legal_entities' for mode in ['native','alias'] for g in LEGAL];e=pd.read_parquet(paths[0],columns=cols);ids=e.id;functions=list(dict.fromkeys(list(LEGAL.values())+list(PHYSICAL.values())+['marketplace_pickup']));fidx={f:i for i,f in enumerate(functions)};n=len(ids);legal={mode:np.zeros((n,len(functions)),bool) for mode in ['native','alias']};physical={mode:np.zeros((n,len(functions)),bool) for mode in ['baseline','conditional']};checks=[]
 def ck(k,v):checks.append({'name':k,'pass':bool(v)})
 for mode,a in legal.items():
  for g,f in LEGAL.items():a[:,fidx[f]]|=e[f'econ_{mode}_2025_{g}_legal_entities'].gt(0).to_numpy()
 q=pd.read_parquet(paths[1]).set_index('id').reindex(ids)
 for mode,a in physical.items():
  for g,f in PHYSICAL.items():a[:,fidx[f]]|=q[f'places_{mode}_{g}_count'].gt(0).to_numpy()
 physical['conditional']|=physical['baseline'];wb=pd.read_parquet(paths[3],columns=['id','wb_strict_focus_types_locations']).set_index('id').reindex(ids);wr=pd.read_parquet(paths[4],columns=['id','wb_name_relaxed_inclusive_focus_locations']).set_index('id').reindex(ids);wbm={mode:np.zeros((n,len(functions)),bool) for mode in ['baseline','conditional']};wbm['baseline'][:,-1]=wb.wb_strict_focus_types_locations.gt(0);wbm['conditional'][:,-1]=wr.wb_name_relaxed_inclusive_focus_locations.gt(0)
 scols=[c for c in pq.ParquetFile(paths[6]).schema_arrow.names if c=='id' or 'retail_name_filtered_' in c or c.startswith(('coordinate_candidate_','native_plus_coordinate_candidate_'))];s=pd.read_parquet(paths[6],columns=scols).set_index('id').reindex(ids);pcols=['function_group','nearest_uid_unaccepted','nearest_distance_km','source_geography_scope','source_operating_status','baseline_uid','conditional_uid','source_category','name_signal_wildberries','name_signal_ozon','country_polygon_conflict'];po=pd.read_parquet(paths[2],columns=pcols);good=po.source_geography_scope.eq('axis_linkage_eligible')&po.nearest_uid_unaccepted.isin(ids)&~po.country_polygon_conflict.fillna(True)&~po.source_operating_status.isin(['permanently_closed','temporarily_closed']);po=po[good];named=po.function_group.eq('retail_store')&po.source_category.eq('shopping')&(po.name_signal_wildberries|po.name_signal_ozon);summary={'eligible_marketplace_name_shopping_POI':int(named.sum())}
 for mode,lmode in [('baseline','native'),('conditional','alias')]:
  uid=po.baseline_uid if mode=='baseline' else po.baseline_uid.fillna(po.conditional_uid);take=po.function_group.isin(['retail_store','market'])&~named&uid.isin(ids);keep=uid[take].value_counts().reindex(ids,fill_value=0).gt(0).to_numpy();a=physical[mode].copy();a[:,fidx['retail']]=keep;a |= legal[lmode]|wbm[mode];count=primary(a)
  for suffix,expected in [('function_diversity',count),('profile_category',category(count)),('unmerged_function_diversity',a.sum(axis=1)),('unmerged_profile_category',category(a.sum(axis=1)))]:ck(mode+'_retail_name_filtered_'+suffix,np.array_equal(expected,s[mode+'_retail_name_filtered_'+suffix]))
  summary[mode+'_primary_multiple']=int((count>=2).sum())
 objects=pd.read_parquet(paths[5],columns=['wb_candidate_uid','wb_nearest_axis_distance_km','wb_type_focus']);objects=objects[objects.wb_type_focus&objects.wb_candidate_uid.isin(ids)]
 for r in [.5,1,2,5]:
  tag=str(r).replace('.','p');a=np.zeros((n,len(functions)),bool);counts=objects.loc[objects.wb_nearest_axis_distance_km.le(r),'wb_candidate_uid'].value_counts().reindex(ids,fill_value=0);a[:,-1]=counts.gt(0);ck(f'radius_{r}_WB_all_UID_counts',np.array_equal(counts,s[f'coordinate_candidate_{tag}km_wb_focus_locations']))
  for g,f in PHYSICAL.items():
   count=po.loc[po.function_group.eq(g)&po.nearest_distance_km.le(r),'nearest_uid_unaccepted'].value_counts().reindex(ids,fill_value=0);a[:,fidx[f]] |= count.gt(0).to_numpy();ck(f'radius_{r}_{g}_all_UID_counts',np.array_equal(count,s[f'coordinate_candidate_{tag}km_{g}_places']))
  ck(f'radius_{r}_primary11_diversity',np.array_equal(primary(a),s[f'coordinate_candidate_{tag}km_function_diversity']));ck(f'radius_{r}_native_plus_primary11_diversity',np.array_equal(primary(a|legal['native']),s[f'native_plus_coordinate_candidate_{tag}km_function_diversity']))
 ck('all_inputs_stable',all(sha(Path(p))==v for p,v in before.items()));result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'summary':summary,'input_SHA256':before,'code_SHA256':sha(Path(__file__)),'meaning':'Exact reproducibility of declared construct/coordinate scenarios; these radii are geocoding sensitivity, not service catchments.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks',summary,flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

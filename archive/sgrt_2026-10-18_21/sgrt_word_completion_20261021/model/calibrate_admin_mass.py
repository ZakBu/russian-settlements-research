#!/usr/bin/env python3
"""Optional noncircular Word calibration on source-bound administrative rural population.

This trains administrative coverage, not observed functional trips. No provisional
largest-settlement mapping is allowed, and generated gravity catchments are forbidden.
"""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

def run(nodes_path,components_path,crosswalk_path,output,year=2021):
 output.mkdir(parents=True,exist_ok=True)
 nodes=pd.read_parquet(nodes_path);comp=pd.read_parquet(components_path);a=pd.read_parquet(crosswalk_path)
 required={'municipality_id','center_id','binding_status','binding_source','binding_year'}
 if not required<=set(a):raise ValueError('Source administrative map missing '+repr(required-set(a)))
 if not a.binding_status.eq('source_confirmed_administrative_center').all():raise ValueError('Only source-confirmed centers are eligible; no provisional maxima')
 if a.municipality_id.duplicated().any():raise ValueError('Ambiguous admin center per municipality')
 if a.binding_source.isna().any():raise ValueError('Missing administrative evidence')
 key='municipality_oktmo8_2021'
 if key not in nodes:raise ValueError('Municipal bridge absent')
 rural=~nodes.type.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 ordinary=nodes._population_axis_row.fillna(False)
 p=nodes.loc[ordinary&rural,[key,'id',f'population_{year}']].copy()
 total=p.groupby(key)[f'population_{year}'].sum(min_count=1);missing=p.groupby(key)[f'population_{year}'].apply(lambda x:int(x.isna().sum()))
 a['source_bound_rural_population']=a.municipality_id.map(total);a['n_unknown_population']=a.municipality_id.map(missing)
 # A rural administrative center is excluded from its own external rural proxy.
 own=nodes.set_index('id');center_rural=a.center_id.map(pd.Series(rural.to_numpy(),index=nodes.id)).fillna(False)
 own_p=a.center_id.map(own[f'population_{year}']);own_mo=a.center_id.map(own[key]);subtract=center_rural&own_mo.eq(a.municipality_id)&own_p.notna()
 a.loc[subtract,'source_bound_rural_population']-=own_p[subtract]
 a['own_rural_center_population_excluded']=subtract
 a=a[a.n_unknown_population.eq(0)&a.source_bound_rural_population.notna()].copy()
 comp=comp.rename(columns={'id':'center_id'});a=a.merge(comp,on='center_id',how='left',validate='many_to_one')
 a=a.merge(nodes[['id','region']].rename(columns={'id':'center_id'}),on='center_id',how='left',validate='many_to_one')
 features=[c for c in comp if c.startswith('block_') and c.endswith('_z') and comp[c].notna().sum()>0]
 if not features:raise ValueError('No intrinsic blocks')
 complete=a[features].notna().all(axis=1)&a.region.notna();s=a[complete].copy();s['target_log_administrative_rural_population']=np.log1p(s.source_bound_rural_population)
 if len(s)<30 or s.region.nunique()<5:raise ValueError('Too few complete independently mapped administrative units')
 predictions=np.full(len(s),np.nan);baseline=np.full(len(s),np.nan)
 folds=GroupKFold(min(5,s.region.nunique()))
 for train,test in folds.split(s,groups=s.region):
  m=make_pipeline(StandardScaler(),Ridge(alpha=1.));m.fit(s.iloc[train][features],s.iloc[train].target_log_administrative_rural_population);predictions[test]=m.predict(s.iloc[test][features]);baseline[test]=s.iloc[train].target_log_administrative_rural_population.mean()
 model=make_pipeline(StandardScaler(),Ridge(alpha=1.));model.fit(s[features],s.target_log_administrative_rural_population)
 valid=comp[features].notna().all(axis=1);result=comp[['center_id']].copy();result['administrative_proxy_calibrated_positive_mass']=np.nan;result.loc[valid,'administrative_proxy_calibrated_positive_mass']=np.exp(np.clip(model.predict(comp.loc[valid,features]),-20,30));result['evidence']='trained_administrative_coverage_not_observed_service_catchment';result.to_parquet(output/'calibrated_administrative_proxy_mass.parquet',index=False)
 s['out_of_region_prediction']=predictions;s['out_of_region_baseline']=baseline;s.to_parquet(output/'calibration_source_units_and_predictions.parquet',index=False)
 receipt={'status':'COMPUTED_ADMINISTRATIVE_PROXY_NOT_FUNCTIONALLY_VALIDATED','training_units':len(s),'regions':s.region.nunique(),'features':features,'coefficients_standardized':dict(zip(features,map(float,model[-1].coef_))),'spatial_heldout_rmse':float(np.sqrt(np.mean(np.square(predictions-s.target_log_administrative_rural_population)))),'mean_baseline_rmse':float(np.sqrt(np.mean(np.square(baseline-s.target_log_administrative_rural_population)))),'target_source':'independent_administrative_boundary_membership_not_model_catchment','population_reference_year':year,'known_time_limitation':'2021administrative dictionary; OSM source-confirmed mapping is exploratory, not legal proof','adopted_as_final_gravity_mass':False,'functional_validation_required':True}
 receipt['own_rural_center_excluded_from_target']=True
 receipt['input_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [nodes_path,components_path,crosswalk_path]}
 receipt['implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--nodes',type=Path,required=True);ap.add_argument('--components',type=Path,required=True);ap.add_argument('--admin-crosswalk',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--year',type=int,default=2021);a=ap.parse_args();run(a.nodes,a.components,a.admin_crosswalk,a.output,a.year)

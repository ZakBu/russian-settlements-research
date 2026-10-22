"""Cached per-source arrays for exactly the admitted context projection rules.
No new source mappings, thresholds or scope changes. Source population aggregation stays unchanged.
"""
import json
import numpy as np
import pandas as pd
from classify_complete import truth,number
class ContextCache:
 def __init__(self,n,contract):
  self.positions={ident:i for i,ident in enumerate(n.index)};self.w=pd.to_numeric(n.population_2021,errors='coerce').to_numpy(dtype=float,na_value=np.nan);self.wfinite=np.isfinite(self.w)&(self.w>=0);self.sourceunits={};self.fields={};self.positive=[];self.numeric=[]
  def units(cols):
   key=tuple(cols)
   if key not in self.sourceunits:
    frame=n[list(cols)];ok=frame.notna().all(axis=1).to_numpy();arr=np.full(len(n),-1,dtype=np.int64)
    if ok.any():arr[ok]=pd.MultiIndex.from_frame(frame.loc[ok]).factorize(sort=False)[0]
    self.sourceunits[key]=arr
   return self.sourceunits[key]
  def trutharray(column):return n[column].map(lambda x:truth(x) is True).to_numpy(dtype=bool)
  def field(column,kind):
   key=(column,kind)
   if key not in self.fields:
    values=n[column];nonmissing=values.notna().to_numpy();flag=trutharray(column) if kind=='boolean' else values.map(lambda x:number(x) is not None and number(x)>0).to_numpy(dtype=bool)
    self.fields[key]=(nonmissing,flag)
   return self.fields[key]
  for spec in contract.get('context_projection',[]):
   known=np.zeros(len(n),dtype=bool);positive=known.copy();columns=[]
   for col in spec['columns']:
    nonmissing,flag=field(col,spec['kind']);columns.append((col,nonmissing,flag));known|=nonmissing if spec['kind']=='boolean' else flag;positive|=flag
   if spec.get('observed_column'):known=trutharray(spec['observed_column']);positive &=known
   self.positive.append((spec,columns,known,positive,units(spec['independent_source_unit_columns'])))
  for spec in contract.get('context_numeric_projection',[]):
   values=pd.to_numeric(n[spec['value_column']],errors='coerce').to_numpy(dtype=float,na_value=np.nan);usable=np.isfinite(values)
   if spec.get('observed_column'):usable &=trutharray(spec['observed_column'])
   self.numeric.append((spec,values,usable,units(spec['independent_source_unit_columns'])))
 def apply(self,core_ids,rural_ids,raw_ids):
  scopes={name:np.fromiter((self.positions[x] for x in ids),dtype=np.int64,count=len(ids)) for name,ids in [('focal',core_ids),('rural_members',rural_ids),('all_members',raw_ids)]};row={}
  for spec,columns,known,positive,sourceunits in self.positive:
   take=scopes[spec['scope']];k=known[take];p=positive[take];weights=self.w[take];valid=~np.isnan(weights);den=float(weights[valid].sum()) if valid.any() else np.nan;prefix=spec['output_column']
   raw={col:{'n_field_nonmissing':int(nonmissing[take].sum()),'n_positive':int(flag[take].sum()),'n_missing':int((~nonmissing[take]).sum())} for col,nonmissing,flag in columns}
   row[prefix]=True if p.any() else pd.NA;row[prefix+'_actual_source_observed_flag']=True if k.any() else pd.NA;row[prefix+'_n_positive_members']=int(p.sum());row[prefix+'_n_source_observed_members']=int(k.sum());row[prefix+'_n_source_scope_members']=len(take);row[prefix+'_raw_source_field_controls_json']=json.dumps(raw,ensure_ascii=False)
   row[prefix+'_scope_known_population2021_denominator']=den;row[prefix+'_source_observed_population_coverage2021']=float(weights[k&valid].sum()/den) if den>0 else np.nan;row[prefix+'_positive_witness_population_share2021']=float(weights[p&valid].sum()/den) if den>0 else np.nan
   codes=sourceunits[take][k];row[prefix+'_n_distinct_observed_source_units']=int(len(np.unique(codes[codes>=0])));row[prefix+'_source_year']=spec['year'];row[prefix+'_source_grain']=spec['grain'];row[prefix+'_statistical_source_unit_independence_claimed']=False
  for spec,values,usable,sourceunits in self.numeric:
   take=scopes[spec['scope']];w=self.w[take];v=values[take];us=usable[take];fw=self.wfinite[take];ok=fw&us;den=float(w[fw].sum()) if fw.any() else np.nan;covered=float(w[ok].sum()) if ok.any() else np.nan;prefix=spec['output_prefix']
   row[prefix+'_weighted_mean']=float((v[ok]*w[ok]).sum()/covered) if covered>0 else np.nan;row[prefix+'_known_population2021_denominator']=den;row[prefix+'_source_observed_population_coverage2021']=float(covered/den) if den>0 and not np.isnan(covered) else 0. if den>0 else np.nan
   codes=sourceunits[take][us];row[prefix+'_n_distinct_observed_source_units']=int(len(np.unique(codes[codes>=0])));row[prefix+'_n_usable_NP_context_records']=int(us.sum());row[prefix+'_source_year']=spec['year'];row[prefix+'_source_grain']=spec['grain'];row[prefix+'_source_unit']=spec['unit'];row[prefix+'_statistical_source_unit_independence_claimed']=False;row[prefix+'_is_population_exposure_context_not_ownNP_productivity']=True
  return row

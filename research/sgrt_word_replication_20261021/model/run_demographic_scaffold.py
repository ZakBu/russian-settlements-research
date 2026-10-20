#!/usr/bin/env python3
"""Explicit demographic scaffold from Word; provisional municipal maxima, no centrality claim."""
from pathlib import Path
import os
import json
import numpy as np
import pandas as pd
from run_model import ROOT,OLD,MASTER,counts,mass,assign,hierarchy,aggregate,xyz

def run():
 out=Path(os.environ.get('SGRT_RESULT_DIR',str(ROOT/'results')))/'demographic_scaffold';out.mkdir(exist_ok=True)
 d=pd.read_parquet(MASTER);d['axis_kind']='ordinary';n=len(d)
 cp=counts(d);fm,_=mass(cp);base=(cp.gt(0).sum(axis=1)>=2)|(d.places_baseline_school_count>0)|(d.places_baseline_hospital_count>0)
 urban=d.settlement_type_2002.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 # One transparent potential fallback per current source municipality, never called its admin center.
 maxima=d.assign(idx=np.arange(n)).sort_values(['municipality_oktmo8_2021','population_2002','id'],ascending=[True,False,True]).drop_duplicates('municipality_oktmo8_2021').idx.to_numpy()
 provisional=np.zeros(n,bool);provisional[maxima]=True
 candidate=base.to_numpy()|urban.to_numpy()|provisional
 m=fm+np.log1p(d.population_2002.fillna(0).to_numpy(float))
 # Keep federal territory anchors separate and population aggregates outside ordinary sums.
 fed=pd.read_csv(OLD/'core/external_federal_features.csv');fed=fed.reindex(columns=d.columns);fed['axis_kind']='federal_territory_context'
 d=pd.concat([d,fed],ignore_index=True);m=np.r_[m,np.log1p(fed.population_2002.to_numpy(float))]
 candidate=np.r_[candidate,[True]*len(fed)];points=xyz(d.lat.to_numpy(),d.lon.to_numpy())
 r=assign(points,np.flatnonzero(candidate),m);levels,edges=hierarchy(points,np.flatnonzero(candidate),m,r['center'])
 mem=d[['id','name','region','axis_kind']].copy();mem['candidate_center']=candidate;mem['own_mass']=m
 mem['provisional_municipal_maximum']=np.r_[provisional,[False]*len(fed)];mem['candidate_supported_by_function_or_urban_status']=np.r_[base|urban,[True]*len(fed)]
 for level,idx in levels.items():mem[f'center_id_l{level}']=[d.id.iloc[i] if i>=0 else None for i in idx];mem[f'center_index_l{level}']=idx
 mem.iloc[:n].to_parquet(out/'memberships.parquet',index=False)
 edges['child_id']=d.id.to_numpy()[edges.child_index];edges['parent_id']=d.id.to_numpy()[edges.parent_index];edges.to_csv(out/'hierarchy.csv',index=False)
 systems,balances=aggregate(d,levels,m,out)
 low=systems[(systems.level==1)&systems.has_rural_periphery&systems.center_axis_kind.eq('ordinary')]
 receipt={'status':'COMPUTED_PROVISIONAL_DEMOGRAPHIC_SCAFFOLD','ordinary_candidate_centers':int(candidate[:n].sum()),'provisional_maxima_without_function_or_urban_support':int((provisional&~base.to_numpy()&~urban.to_numpy()).sum()),'ordinary_assigned':int((r['center'][:n]>=0).sum()),'levels':{str(l):int(systems.level.eq(l).sum()) for l in levels},'rural_systems_l1':len(low),'type_counts_l1_rural':{str(k):int(v) for k,v in low.demographic_type.value_counts().items()},'scope':'not actual functional catchments; explicit Word demographic scaffold on modern municipality proxy; largest settlement is not documented admin/function center','mass_uses_only_own_characteristics':True,'mass_fitted_to_catchments':False,'population_balances':balances}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':run()

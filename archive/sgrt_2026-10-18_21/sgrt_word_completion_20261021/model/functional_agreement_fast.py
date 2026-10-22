"""Vectorized cross-sector agreement; checked against full original outputs."""
import json
import numpy as np
import pandas as pd

def functional_agreement_fast(members,function_assignments):
 if function_assignments.empty:return pd.DataFrame(columns=['id','n_sector_leaders'])
 z=function_assignments.merge(members[['id','assigned_center_id']].rename(columns={'assigned_center_id':'integrated_center_id'}),on='id',validate='many_to_one')
 order=pd.Index(z.id.drop_duplicates(),name='id');functions=z.function_group.drop_duplicates().tolist()
 valid=z.assigned_center_id.notna();matches=z.assigned_center_id.eq(z.integrated_center_id)&valid
 counts=valid.groupby(z.id,sort=False,observed=True).sum().reindex(order).astype(int)
 unique=z.groupby('id',sort=False,observed=True).assigned_center_id.nunique(dropna=True).reindex(order).astype(int)
 agree=matches.groupby(z.id,sort=False,observed=True).sum().reindex(order)
 fraction=np.divide(agree.to_numpy(float),counts.to_numpy(float),out=np.full(len(order),np.nan),where=counts.to_numpy()>0)
 leaders=z.pivot(index='id',columns='function_group',values='assigned_center_id').reindex(index=order,columns=functions)
 values=leaders.astype(object).where(leaders.notna(),None).to_numpy()
 encoded=[json.dumps(dict(zip(functions,row)),ensure_ascii=False) for row in values]
 return pd.DataFrame({'id':order.to_numpy(),'n_assigned_sector_models':counts.to_numpy(),'n_sector_leaders':unique.to_numpy(),'sector_model_integrated_agreement_fraction':fraction,'different_sector_leaders_potential':unique.to_numpy()>=2,'sector_leaders_json':encoded,'actual_multicenter_flows_observed':False})

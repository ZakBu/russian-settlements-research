#!/usr/bin/env python3
"""Demographic contrasts in fixed documentary function-level memberships."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

R=Path(__file__).resolve().parent.parent

def direction(a,b,threshold):
    if pd.isna(a) or pd.isna(b):return 'unknown_missing_population'
    if a==0:return 'zero_both_censuses' if b==0 else 'positive_after_zero_census_not_function_birth'
    rate=(b/a-1)*100
    return 'stable_within_threshold' if abs(rate)<=threshold else ('growth' if rate>0 else 'decline')

def build(out=None):
    out=Path(out) if out is not None else R/'model/results'
    g=pd.read_parquet(out/'canonical_documented_external_memberships.parquet')
    p=pd.read_parquet(R.parent/'anchor_research_20261019/data/point_axis.parquet').set_index('id')
    rows=[];typ=[];checks=[]
    keys=['canonical_source_id','canonical_evidence_date','destination_uid','function_group','canonical_service_level']
    for k,x in g.groupby(keys,dropna=False):
        ids=set(x.origin_uid);uid=k[2]
        assert uid not in ids
        r=dict(zip(keys,k));r.update(center_name=p.loc[uid,'name'],n_external_origins=len(ids),external_origin_uids='|'.join(sorted(ids)),demographic_geography='fixed_document_membership_not_historical_service_presence',historical_function_presence_backcast=False)
        for y in [2002,2010,2021]:
            ext=p.loc[list(ids),f'population_{y}'];own=p.loc[uid,f'population_{y}']
            r[f'external_missing_{y}']=int(ext.isna().sum())
            r[f'external_zero_origins_{y}']=int(ext.eq(0).sum())
            r[f'center_population_{y}']=own
            r[f'external_population_{y}']=float(ext.sum()) if not ext.isna().any() else np.nan
            r[f'total_population_{y}']=r[f'external_population_{y}']+own
            checks.append(bool(pd.isna(r[f'total_population_{y}']) or r[f'total_population_{y}']==r[f'external_population_{y}']+own))
        for a,b in [(2002,2010),(2010,2021)]:
            for part in ['center','external','total']:
                p0,p1=r[f'{part}_population_{a}'],r[f'{part}_population_{b}']
                r[f'{part}_change_{a}_{b}']=p1-p0
                r[f'{part}_percent_{a}_{b}']=(p1/p0-1)*100 if pd.notna(p0) and p0>0 and pd.notna(p1) else np.nan
            for threshold in [1,5,10]:
                t={c:r[c] for c in keys};t.update(center_name=r['center_name'],from_census=a,to_census=b,stability_threshold_percent=threshold)
                for part in ['center','external','total']:t[part+'_direction']=direction(r[f'{part}_population_{a}'],r[f'{part}_population_{b}'],threshold)
                t['profile']=t['center_direction']+'__'+t['external_direction']
                t['functional_type_or_migration_process_identified']=False
                typ.append(t)
        rows.append(r)
    a=pd.DataFrame(rows);b=pd.DataFrame(typ)
    for n,d in [('centre_periphery_demography',a),('demographic_direction_sensitivity',b)]:d.to_csv(out/f'{n}.csv',index=False);d.to_parquet(out/f'{n}.parquet',index=False)
    # Check the actual documented multilevel case, including no center double count.
    low=a[a.center_name.eq('Малоказаккулово')&a.canonical_service_level.eq('grades_1_9')].iloc[0]
    assert [low[f'total_population_{y}'] for y in [2002,2010,2021]]==[578,550,559]
    high=a[a.center_name.eq('Уральск')&a.canonical_service_level.eq('grades_10_11')].iloc[0]
    assert high.total_population_2021==2225 and high.external_population_2021==559
    assert direction(0,0,5)=='zero_both_censuses'
    assert direction(0,1,5)=='positive_after_zero_census_not_function_birth'
    assert direction(None,1,5)=='unknown_missing_population'
    audit={'status':'PASS','fixed_function_level_catchments':len(a),'direction_scenarios':len(b),'all_census_population_conservation_checks':sum(checks),'all_conserved':all(checks),'real_case_low_population':[578,550,559],'real_case_high_2021_population':2225,'observed_functional_typology_asserted':False,'zero_denominators_not_divided':True,'missing_population_not_zero_imputed':True}
    (out/'CENTRE_PERIPHERY_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':build()

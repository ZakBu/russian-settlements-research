"""Independent readback of center-versus-external-origin demographic contrasts."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'model/results'
def main():
    p=pd.read_parquet(ROOT.parent/'anchor_research_20261019/data/point_axis.parquet').set_index('id')
    a=pd.read_parquet(R/'centre_periphery_demography.parquet')
    t=pd.read_parquet(R/'demographic_direction_sensitivity.parquet')
    g=pd.read_parquet(R/'canonical_documented_external_memberships.parquet')
    keys=['canonical_source_id','canonical_evidence_date','destination_uid','function_group','canonical_service_level']
    checks=[]
    def ck(k,v):checks.append({'check':k,'pass':bool(v)})
    def eq(x,y):return (pd.isna(x) and pd.isna(y)) or np.isclose(x,y,rtol=0,atol=1e-9)
    ck('28fixed_sets',len(a)==28)
    ck('168_direction_records',len(t)==168)
    for i,row in a.iterrows():
        selector=pd.Series(True,index=g.index)
        for k in keys:selector &= g[k].eq(row[k])
        ids=set(g.loc[selector,'origin_uid'])
        ck(f'{i}_origins_from_canonical_graph',ids==set(row.external_origin_uids.split('|')) and len(ids)==row.n_external_origins)
        ck(f'{i}_center_not_counted_twice',row.destination_uid not in ids)
        for y in [2002,2010,2021]:
            v=p.loc[sorted(ids),f'population_{y}']
            ext=v.sum() if not v.isna().any() else np.nan
            own=p.loc[row.destination_uid,f'population_{y}']
            ck(f'{i}_{y}_census_triplet',eq(row[f'external_population_{y}'],ext) and eq(row[f'center_population_{y}'],own) and eq(row[f'total_population_{y}'],ext+own))
            ck(f'{i}_{y}_zero_missing',row[f'external_missing_{y}']==v.isna().sum() and row[f'external_zero_origins_{y}']==v.eq(0).sum())
        tt=t.copy()
        for k in keys:tt=tt[tt[k].eq(row[k])]
        ck(f'{i}_2periods3thresholds',len(tt)==6 and set(tt.stability_threshold_percent)=={1,5,10})
        for _,rr in tt.iterrows():
            y0,y1=int(rr.from_census),int(rr.to_census)
            for part in ['center','external','total']:
                v0,v1=row[f'{part}_population_{y0}'],row[f'{part}_population_{y1}']
                if pd.isna(v0) or pd.isna(v1):d='unknown_missing_population'
                elif v0==0:d='zero_both_censuses' if v1==0 else 'positive_after_zero_census_not_function_birth'
                elif abs(100*(v1-v0)/v0)<=rr.stability_threshold_percent:d='stable_within_threshold'
                else:d='growth' if v1>v0 else 'decline'
                ck(f'{i}_{y0}_{rr.stability_threshold_percent}_{part}_direction',rr[part+'_direction']==d)
    ck('directions_not_functional_type',not t.functional_type_or_migration_process_identified.any())
    ck('not_historical_backcast',not a.historical_function_presence_backcast.any())
    out={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks_total':len(checks),'checks_passed':sum(x['pass'] for x in checks),'checks':checks,'scope':'fixed documentary center-versus-external-origin comparison; does not estimate a distance gradient or historical functional catchment','input_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in [R/'centre_periphery_demography.parquet',R/'demographic_direction_sensitivity.parquet',R/'canonical_documented_external_memberships.parquet']}}
    (Path(__file__).parent/'CENTER_CONTEXT_AUDIT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:out[k] for k in ['status','checks_total','checks_passed']}))
    assert out['status']=='PASS'
if __name__=='__main__':main()

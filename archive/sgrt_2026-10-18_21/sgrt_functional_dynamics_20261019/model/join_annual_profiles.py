#!/usr/bin/env python3
"""Attach any pinned-release annual legal witness panel to documented providers.

Usage: python join_annual_profiles.py --input economy/results/annual.parquet
Does not reconstruct historical physical sites, jobs or external service flows.
"""
from pathlib import Path
import argparse,json
import pandas as pd

R=Path(__file__).resolve().parent.parent

def join(path,out):
    d=pd.read_parquet(path)
    assert {'id','year','direct_consumer_function_diversity'}<=set(d.columns)
    keys=['id','year']+(['quality_mode'] if 'quality_mode' in d else [])
    assert not d.duplicated(keys).any()
    p=pd.read_parquet(R/'model/results/documented_provider_profiles.parquet',columns=['id','name','documented_external_function_groups','document_dates'])
    q=d[d.id.isin(p.id)].merge(p,on='id',how='left',suffixes=('','_documented_provider'),validate='many_to_one')
    q['historical_physical_function_change_identified']=False
    q['historical_external_catchment_reconstructed']=False
    q['geography_interpretation']='year_specific_registered_organizations_projected_to_frozen_settlement_axis_not_historical_boundaries'
    q=q.sort_values(keys)
    out.mkdir(parents=True,exist_ok=True)
    q.to_parquet(out/'documented_providers_annual_legal_witnesses.parquet',index=False);q.to_csv(out/'documented_providers_annual_legal_witnesses.csv',index=False)
    result={'input':str(path),'rows':len(q),'providers':q.id.nunique(),'years':sorted(q.year.unique().tolist()),'quality_modes':sorted(q.quality_mode.unique().tolist()) if 'quality_mode' in q else [],'same_release_required':True,'historical_sgrt_boundaries_claimed':False}
    (out/'ANNUAL_PROFILE_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--out',type=Path,default=R/'model/annual_results');a=ap.parse_args();join(a.input,a.out)

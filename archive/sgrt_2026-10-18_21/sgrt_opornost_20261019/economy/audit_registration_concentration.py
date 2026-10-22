#!/usr/bin/env python3
"""Diagnostic only: shared house-level geocodes may concentrate legal registration."""
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from build_coded_features import codes
from build_point_features import sha,dump

ap=argparse.ArgumentParser();ap.add_argument('--restored',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
a.out.mkdir(parents=True,exist_ok=True)
panelpath=a.restored/'research/sgrt_recovered_20261019/data/panel.parquet'
p=pq.read_table(panelpath,columns=['id','name','type','region','population_2021','oktmo_2021']).to_pandas()
lookup=pd.Series(p.id.to_numpy(),index=codes(p.oktmo_2021));assert lookup.index.is_unique
for year in [2021,2016]:
    source=a.restored/f'inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet'
    d=pq.read_table(source,columns=['inn','oktmo','lat','lon','geocoding_quality']).to_pandas()
    d=d[d.geocoding_quality.eq('house') & d.inn.notna() & d.lat.between(-90,90) & d.lon.between(-180,180)].copy()
    d['id']=codes(d.oktmo).map(lookup);d=d.dropna(subset=['id'])
    d['lat6']=d.lat.round(6);d['lon6']=d.lon.round(6)
    g=d.groupby(['id','lat6','lon6'],sort=False).size().rename('legal_entities_at_house_geocode').reset_index()
    total=g.groupby('id').legal_entities_at_house_geocode.sum().rename('exact_code_house_entities')
    count=g.groupby('id').size().rename('distinct_house_geocodes')
    top=g.sort_values('legal_entities_at_house_geocode',ascending=False,kind='stable').drop_duplicates('id').set_index('id')
    top=top.rename(columns={'legal_entities_at_house_geocode':'max_shared_house_geocode_entities','lat6':'max_shared_house_lat','lon6':'max_shared_house_lon'})
    out=p.drop(columns=['oktmo_2021']).merge(total,on='id',how='left').merge(count,on='id',how='left').merge(top,on='id',how='left')
    for c in ['exact_code_house_entities','distinct_house_geocodes','max_shared_house_geocode_entities']:out[c]=out[c].fillna(0).astype('int64')
    out['max_house_share_of_exact_code_house_entities']=out.max_shared_house_geocode_entities.div(out.exact_code_house_entities.replace(0,np.nan))
    out['year']=year;out['interpretation']='shared_geocoder_coordinate_not_proof_of_mass_registration_or_client_visits'
    target=a.out/f'house_geocode_concentration_{year}.parquet';out.to_parquet(target,index=False)
    out.nlargest(100,'max_shared_house_geocode_entities').to_csv(a.out/f'top100_{year}.csv',index=False)
    pd.testing.assert_frame_equal(out,pd.read_parquet(target))
    assert out.id.is_unique and len(out)==len(p)
    dump(a.out/f'audit_{year}.json',{'source_sha256':sha(source),'output_sha256':sha(target),'code_sha256':sha(Path(__file__)),
      'source_exact_house_entities':len(d),'aggregate_exact_house_entities':int(out.exact_code_house_entities.sum()),
      'np_observed_house_geocodes':int(out.exact_code_house_entities.gt(0).sum()),
      'max_entities_one_house_geocode':int(out.max_shared_house_geocode_entities.max()),
      'full_point_axis':True,'readback_pass':True,'aggregation_balance':len(d)==int(out.exact_code_house_entities.sum()),
      'no_decision_threshold_or_automatic_exclusion':True})
    print(year,len(d),int(out.exact_code_house_entities.gt(0).sum()),int(out.max_shared_house_geocode_entities.max()),flush=True)

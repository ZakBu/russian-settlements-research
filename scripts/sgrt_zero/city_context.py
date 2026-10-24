#!/usr/bin/env python3
"""Separate geographic context for three federal cities; census stays read-only."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import urllib.request

import pandas as pd

PREFIX='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'
CITIES=[
 {'qid':'Q649','revision':2558575480,'name':'Москва','suffix':'64748',
  'sha256':'0fdf6264222e06072184c43fa85a73fd62ab761d8e6c77a67c297901d85a97e3'},
 {'qid':'Q656','revision':2548934371,'name':'Санкт-Петербург','suffix':'126656',
  'sha256':'8d4ce7b52a313646c5b1e2b636ac6ba1542adcbbefb07aa89f40f955bb2d66d0'},
 {'qid':'Q7525','revision':2558752485,'name':'Севастополь','suffix':'121540',
  'sha256':'47e69c9cbebc3ccedfbc60f4d48b54e894b988892e730ce5e8f4a742c03e2aea'},
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquire(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for city in CITIES:
        path=directory/(city['qid']+'.json.gz')
        if path.exists():continue
        url=f"https://www.wikidata.org/wiki/Special:EntityData/{city['qid']}.json?revision={city['revision']}"
        req=urllib.request.Request(url,headers={'User-Agent':'SGRT-Research/1.0 (public geographic research)'})
        with urllib.request.urlopen(req,timeout=60) as response:raw=response.read()
        if hashlib.sha256(raw).hexdigest()!=city['sha256']:raise ValueError('Pinned city source changed: '+city['qid'])
        with gzip.open(path,'wb') as f:f.write(raw)


def read_context(directory):
    rows=[]
    for city in CITIES:
        path=Path(directory)/(city['qid']+'.json.gz')
        raw=gzip.open(path,'rb').read()
        if hashlib.sha256(raw).hexdigest()!=city['sha256']:raise ValueError('City source SHA differs: '+str(path))
        entity=json.loads(raw)['entities'][city['qid']]
        if entity['lastrevid']!=city['revision'] or entity['labels']['ru']['value']!=city['name']:
            raise ValueError('City source identity/revision differs')
        positions=[x['mainsnak']['datavalue']['value'] for x in entity['claims'].get('P625',[])
                   if x.get('rank')!='deprecated' and 'datavalue' in x['mainsnak']]
        if len(positions)!=1 or positions[0]['globe']!='http://www.wikidata.org/entity/Q2':
            raise ValueError('Ambiguous/non-Earth city coordinates')
        point=positions[0]
        rows.append(dict(source_record_id=PREFIX+city['suffix'],name=city['name'],
            lat=point['latitude'],lon=point['longitude'],source_id='WIKIDATA_CITY_CONTEXT_PINNED',
            source_qid=city['qid'],source_revision=city['revision'],source_sha256=city['sha256'],
            source_url=f"https://www.wikidata.org/wiki/Special:EntityData/{city['qid']}.json?revision={city['revision']}",
            coordinate_precision_degrees=point['precision'],
            location_precision='city_reference_point_not_facility_or_agglomeration_boundary',
            budget_population_credit=False,analysis_origin=True,
            population_role='external_context_nonadditive'))
    return pd.DataFrame(rows)


def enrich_reference(reference,contexts,population_types=None):
    out=reference.copy()
    if out.loc[out.source_record_id.notna(),'source_record_id'].duplicated().any():raise ValueError('Duplicate census IDs')
    if not contexts.source_record_id.is_unique:raise ValueError('Duplicate context city')
    if not contexts.source_record_id.isin(out.source_record_id).all():raise ValueError('Context city absent from reference')
    out['base_lat']=out.lat;out['base_lon']=out.lon
    out['base_population_role']=out.population_role
    out['analysis_origin']=out.ordinary_spatial_2021.fillna(False).astype(bool)
    out['budget_population_credit']=out.analysis_origin & out.credit_2021.fillna(False)
    out['context_coordinate_source_id']=pd.Series(None,index=out.index,dtype='object')
    out['context_coordinate_precision_degrees']=float('nan')
    for row in contexts.itertuples(index=False):
        mask=out.source_record_id.eq(row.source_record_id)
        out.loc[mask,['lat','lon']]=[row.lat,row.lon]
        out.loc[mask,'analysis_origin']=True
        out.loc[mask,'population_role']='external_context_nonadditive'
        out.loc[mask,'budget_population_credit']=False
        out.loc[mask,'context_coordinate_source_id']=row.source_id
        out.loc[mask,'context_coordinate_precision_degrees']=row.coordinate_precision_degrees
        for year in [2002,2010,2021]:out.loc[mask,f'credit_{year}']=False
    if population_types is not None:
        types=population_types[['source_record_id_2021','settlement_type_2021']].dropna(subset=['source_record_id_2021'])
        if types.source_record_id_2021.duplicated().any():raise ValueError('Duplicate type source ID')
        out['settlement_type_2021']=out.source_record_id.map(types.set_index('source_record_id_2021').settlement_type_2021)
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--population-wide',type=Path)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--download',action='store_true')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    before=digest(a.reference)
    if a.download:acquire(a.input)
    contexts=read_context(a.input)
    reference=pd.read_parquet(a.reference)
    types=pd.read_parquet(a.population_wide,columns=['source_record_id_2021','settlement_type_2021']) if a.population_wide else None
    enriched=enrich_reference(reference,contexts,types)
    a.output.mkdir(parents=True,exist_ok=True)
    contexts.to_parquet(a.output/'city_context_origins.parquet',index=False,compression='zstd')
    enriched.to_parquet(a.output/'analysis_reference.parquet',index=False,compression='zstd')
    contexts.to_csv(a.output/'city_context_origins.csv',index=False)
    ordinary=reference.ordinary_spatial_2021.fillna(False)
    assert enriched.loc[ordinary,'lat'].equals(reference.loc[ordinary,'lat'])
    assert enriched.loc[ordinary,'lon'].equals(reference.loc[ordinary,'lon'])
    assert digest(a.reference)==before
    summary={'ordinary_spatial_origins':int(ordinary.sum()),'added_context_origins':len(contexts),
        'analysis_origins':int(enriched.analysis_origin.sum()),'reference_regions':int(enriched.region.nunique()),
        'source_reference_sha256':before,'census_modified':False,'context_population_added_to_budget':False,
        'city_coordinates_are_not_facility_coordinates_or_boundaries':True,
        'sources':contexts.to_dict('records')}
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='sources'},ensure_ascii=False))


if __name__=='__main__':main()

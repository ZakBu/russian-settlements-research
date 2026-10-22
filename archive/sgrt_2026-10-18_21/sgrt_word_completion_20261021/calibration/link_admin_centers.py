#!/usr/bin/env python3
"""Resolve explicit source centers to census units; retain failed/ambiguous links."""
from pathlib import Path
import json
import re
import hashlib
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def distance(lat,lon,a,b):
    x,y=np.radians(lat),np.radians(lon);u,v=np.radians(a),np.radians(b)
    return 12742.0176*np.arcsin(np.sqrt(np.clip(np.sin((x-u)/2)**2+np.cos(x)*np.cos(u)*np.sin((y-v)/2)**2,0,1)))
def main():
    src=ROOT/'calibration/osm_explicit_admin_centers.parquet';d=pd.read_parquet(src)
    # Geofabrik uses oktmo:user in this extract; preserve the literal key, not a legal inference.
    d['oktmo_literal']=d.relation_tags_json.map(lambda s:json.loads(s).get('ref:oktmo') or json.loads(s).get('oktmo:user'))
    d['oktmo_source_key']=d.relation_tags_json.map(lambda s:'ref:oktmo' if 'ref:oktmo' in json.loads(s) else 'oktmo:user' if 'oktmo:user' in json.loads(s) else None)
    d['municipal_code8_literal']=d.oktmo_literal.map(lambda x:x if isinstance(x,str) and re.fullmatch(r'\d{8}',x) else None)
    axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet');axis['_name']=axis.name.map(norm)
    byname={k:g for k,g in axis[axis.lat.notna()&axis.lon.notna()].groupby('_name')}
    ids=[];distances=[];counts=[]
    for row in d.itertuples():
        c=byname.get(norm(row.center_name))
        if c is None or pd.isna(row.center_lat):ids.append(None);distances.append(None);counts.append(0);continue
        ds=distance(row.center_lat,row.center_lon,c.lat.to_numpy(),c.lon.to_numpy())
        ok=ds<=5;candidate=c.loc[ok]
        ids.append(candidate.id.iloc[0] if len(candidate)==1 else None)
        distances.append(float(ds[ok][0]) if len(candidate)==1 else None);counts.append(len(candidate))
    d['center_id']=ids;d['axis_link_distance_km']=distances;d['axis_candidate_count']=counts
    d['historical_boundary_equivalence_proven']=False
    d.to_parquet(ROOT/'calibration/osm_admin_centers_axis_linked.parquet',index=False)
    # Only municipal district/urban-okrug relations are eligible, never regional centers or village councils.
    e=d[d.admin_level.eq('6')&d.center_id.notna()&d.municipal_code8_literal.notna()].copy()
    native=set(axis.municipality_oktmo8_2021.dropna().astype(str));e=e[e.municipal_code8_literal.isin(native)]
    ambiguous=e.groupby('municipal_code8_literal').center_id.nunique();e=e[~e.municipal_code8_literal.isin(ambiguous[ambiguous>1].index)]
    e=e.drop_duplicates('municipal_code8_literal')
    out=e[['municipal_code8_literal','center_id','relation_id','relation_name','center_name','axis_link_distance_km','oktmo_source_key','historical_boundary_equivalence_proven']].rename(columns={'municipal_code8_literal':'municipality_id'})
    out['binding_status']='source_confirmed_administrative_center'
    out['binding_source']=out.relation_id.map(lambda n:f'https://www.openstreetmap.org/relation/{n}')
    out['binding_year']=2026
    out['binding_source_authority']='OSM explicit admin_centre member and literal code; not official legal boundary validation'
    out['not_eligible_for_historical_causal_validation']=True
    out.to_parquet(ROOT/'calibration/source_admin_crosswalk_exploratory.parquet',index=False)
    receipt={'source_rows':len(d),'explicit_code8_rows':int(d.municipal_code8_literal.notna().sum()),'axis_resolved':int(d.center_id.notna().sum()),'district_crosswalk_units':len(out),'independent_of_generated_gravity_zones':True,'not_legal_or_temporal_boundary_proof':True,'source_parquet_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'training_adopted_as_final_model':False}
    (ROOT/'calibration/admin_linkage_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()

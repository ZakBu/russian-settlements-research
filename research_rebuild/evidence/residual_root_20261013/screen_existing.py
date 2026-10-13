"""Generate missing-year candidates from admitted own points and native rows.

This file does not admit edges or alter source populations.
"""
from pathlib import Path
import argparse, hashlib, json, math, re, unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
def norm(v):
    if pd.isna(v): return ''
    return ' '.join(unicodedata.normalize('NFKC', str(v)).lower().replace('ё','е').split())
def name(v):
    v = norm(v)
    return re.sub(r'^(?:пос[её]лок|деревня|село|станция|ст\.|п\.|д\.|с\.)\s+', '', v)
def county(v):
    v = norm(v)
    v = re.sub(r'\b(?:муниципальный|городской|район|округ|го|г\.)\b', '', v)
    return ' '.join(v.split()).strip(' ,.-')
def dist(a,b):
    lat1,lon1,lat2,lon2=map(lambda x:math.radians(float(x)),[*a,*b]);h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088*2*math.asin(min(1,math.sqrt(h)))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--state-dir',required=True);args=ap.parse_args();s=Path(args.state_dir)
    paths=[s/'applied_state_observations.parquet',s/'applied_point_snapshot.parquet',ROOT/'research_rebuild/evidence/over500_lifecycle_integration_20261009/applied/integrated_credited_UID_roster.csv.gz',OUT/'initial_over500_residual.csv']
    a=pd.read_parquet(paths[0])
    # A snapshot is read only after its recovery receipt has been sealed.
    if not (s/'recovery_receipt.json').exists():
        paths[1]=ROOT/'publication/stage71/applied_point_snapshot.parquet'
    p=pd.read_parquet(paths[1],columns=['source_record_id','latitude','longitude','point_origin_file','point_origin_locator','point_origin_kind']).set_index('source_record_id')
    if paths[1].parent.name=='stage71':
        recipe=json.loads((ROOT/'research_rebuild/evidence/over500_root_20261009/fifteenth_recipe.json').read_text())
        for rel in recipe['point_rejections']:
            d=pd.read_csv(ROOT/rel,keep_default_na=False)
            p=p.drop(index=list(d.target_source_record_id),errors='raise')
        for rel in recipe['points']:
            d=pd.read_csv(ROOT/rel,keep_default_na=False).set_index('target_source_record_id')
            fields=['latitude','longitude','point_origin_file','point_origin_locator','point_origin_kind']
            p=p.drop(index=list(d.index),errors='ignore');p=pd.concat([p,d.reindex(columns=fields)])
        paths.extend(ROOT/x for x in recipe['point_rejections']+recipe['points'])
    t=pd.read_csv(paths[3],keep_default_na=False,low_memory=False)
    a['name_key']=a.settlement_name.map(name);a['county_key']=a.district_raw.map(county)
    yearsets={}
    for root,yr in zip(a.root,a.census_year):yearsets.setdefault(root,set()).add(int(yr))
    a['root_years']=a.root.map({k:','.join(map(str,sorted(v))) for k,v in yearsets.items()})
    wanted={(r['region_norm'],name(r['settlement_name'])) for r in t.to_dict('records')}
    relevant=[(r,n) in wanted for r,n in zip(a.region_norm,a.name_key)]
    byid=a.set_index('source_record_id');groups={k:v for k,v in a[a.is_additive_settlement_record.fillna(False)&pd.Series(relevant)].groupby(['region_norm','name_key'])}
    rows=[]
    for x in t.to_dict('records'):
        sid=x['source_record_id'];old=byid.loc[sid];g=groups.get((old.region_norm,old.name_key))
        if g is None:continue
        for z in g.to_dict('records'):
            tid=z['source_record_id'];yr=int(z['census_year'])
            if yr in map(int,old.root_years.split(',')):continue
            oldyears=set(map(int,old.root_years.split(',')));newyears=set(map(int,z['root_years'].split(',')))
            d=dist(tuple(p.loc[sid,['latitude','longitude']]),tuple(p.loc[tid,['latitude','longitude']])) if sid in p.index and tid in p.index else None
            n=int((g.census_year==yr).sum())
            rows.append(dict(from_source_record_id=sid,to_source_record_id=tid,region=old.region_norm,name=old.settlement_name,old_year=int(old.census_year),new_year=yr,old_population=old.population,new_population=z['population'],old_county=old.district_raw,new_county=z['district_raw'],same_normalized_county=bool(old.county_key and old.county_key==z['county_key']),old_type=old.settlement_type,new_type=z['settlement_type'],same_type=norm(old.settlement_type)==norm(z['settlement_type']),distance_km=d,old_root=old.root,new_root=z['root'],old_years=old.root_years,new_years=z['root_years'],no_component_year_overlap=not(oldyears&newyears),same_region_name_candidates_in_target_year=n,old_point_origin=p.loc[sid,'point_origin_file'] if sid in p.index else '',new_point_origin=p.loc[tid,'point_origin_file'] if tid in p.index else '',old_point_locator=p.loc[sid,'point_origin_locator'] if sid in p.index else '',new_point_locator=p.loc[tid,'point_origin_locator'] if tid in p.index else ''))
    f=pd.DataFrame(rows);f.to_csv(OUT/'missing_year_exact_name_candidates.csv',index=False)
    eligible=f[f.same_normalized_county & f.same_type & f.no_component_year_overlap & f.distance_km.notna() & f.distance_km.le(5)]
    eligible.to_csv(OUT/'county_point_stable_candidates.csv',index=False)
    (OUT/'screen_receipt.json').write_text(json.dumps({'candidate_only':True,'target_records':len(t),'candidate_pairs':len(f),'county_point_stable_candidate_pairs':len(eligible),'input_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2))
    print(f[['region','name','old_year','new_year','old_population','new_population','same_normalized_county','same_type','distance_km','no_component_year_overlap']].to_string(index=False));print('county candidates',len(eligible))
if __name__=='__main__':main()

"""Acquire an explicitly labelled third-party Ozon snapshot; never a verified official census."""
from pathlib import Path
import urllib.request, urllib.error, json, csv, hashlib, concurrent.futures, collections, math
P=Path(__file__).resolve().parent
T=json.loads((P/'ozon_nutrygo_tree.json').read_text()); SHA=T['sha']
INDEX=json.loads((P/'ozon_nutrygo_cities.json').read_text())
BASE=f'https://raw.githubusercontent.com/Pikhtachoo/nutrygo-pvz/{SHA}/'
D=P/'ozon_nutrygo_raw';D.mkdir(exist_ok=True)
FILES=sorted({r['file'] for r in INDEX['list']})
def fetch(name):
    dest=D/name
    try:
        if dest.exists(): b=dest.read_bytes()
        else:
            b=urllib.request.urlopen(BASE+name,timeout=30).read();json.loads(b);dest.write_bytes(b)
        return dict(file=name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),status='ok')
    except Exception as e:return dict(file=name,status='error',error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    manifest=list(pool.map(fetch,FILES))
(P/'ozon_nutrygo_shard_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
failed=[r for r in manifest if r['status']!='ok']
if failed:raise RuntimeError(f'{len(failed)} shard downloads failed; retained successful files')
rows=[];mismatches=[];schemas=collections.Counter()
cache={name:json.loads((D/name).read_text()) for name in FILES}
for city in INDEX['list']:
    file=city['file']; obj=cache[file]
    points=obj.get(city['city'],[]) if isinstance(obj,dict) else obj
    if len(points)!=city['count']:mismatches.append({'city':city['city'],'file':file,'expected':city['count'],'actual':len(points)})
    for point in points:
        schemas.update([','.join(sorted(point))]);rows.append(dict(source_city=city['city'],source_file=file,**point))
ids=collections.Counter(r.get('i') for r in rows)
unique={}
conflicts=[]
for r in rows:
    key=r.get('i')
    if key in unique and (unique[key].get('x'),unique[key].get('y'),unique[key].get('a'))!=(r.get('x'),r.get('y'),r.get('a')):conflicts.append(key)
    unique.setdefault(key,r)
valid=[];invalid=[]
for r in unique.values():
    y,x=r.get('y'),r.get('x')
    if isinstance(y,(int,float)) and isinstance(x,(int,float)) and math.isfinite(y) and math.isfinite(x) and -90<=y<=90 and -180<=x<=180:valid.append(r)
    else:invalid.append(r.get('i'))
fields=['source_city','source_file','i','a','y','x','p','h','k','r','n']
with (P/'ozon_nutrygo_points_third_party_20260806.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(unique.values())
normalized_fields=['objectid','address','lat','lon','city_label','raw_p','raw_k','source_shard','declared_snapshot','source_tree_sha','source_kind','point_type_source_inferred']
with (P/'ozon_nutrygo_normalized_20260806.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=normalized_fields);w.writeheader()
    for r in unique.values():
        w.writerow(dict(objectid=r.get('i'),address=r.get('a'),lat=r.get('y'),lon=r.get('x'),city_label=r['source_city'],raw_p=r.get('p'),raw_k=r.get('k'),source_shard=r['source_file'],declared_snapshot=INDEX.get('updated'),source_tree_sha=SHA,source_kind='third_party_source_declared_ozon_map',point_type_source_inferred='pickup_point' if r.get('p')==0 else 'parcel_locker' if r.get('p')==1 else 'unknown'))
regions=collections.Counter(r.get('a','').split(',')[0].strip() for r in valid)
summary=dict(source='https://github.com/Pikhtachoo/nutrygo-pvz',fixed_tree_sha=SHA,retrieved_on='2026-10-24',index_updated=INDEX.get('updated'),index_points=INDEX.get('points'),index_cities=INDEX.get('cities'),index_list_length=len(INDEX['list']),downloaded_shards=len(manifest),download_bytes=sum(r['bytes'] for r in manifest),sum_index_counts=sum(r['count'] for r in INDEX['list']),expanded_rows=len(rows),unique_ids=len(unique),duplicate_id_count=sum(n-1 for n in ids.values()),conflicting_ids=len(set(conflicts)),invalid_coordinates=len(invalid),valid_coordinates=len(valid),city_count_mismatches=mismatches,schemas=dict(schemas),type_p_counts=dict(collections.Counter(str(r.get('p')) for r in valid)),latitude_range=[min(r['y'] for r in valid),max(r['y'] for r in valid)],longitude_range=[min(r['x'] for r in valid),max(r['x'] for r in valid)],address_first_component_counts=regions.most_common(),coverage_status='third_party_near_national_candidate_not_verified_complete',provenance_status='README_self_reports_ozon_map; no_acquisition_code_or_independent_validation_found',license_status='no_license_file_or_metadata_found; do_not_republish_raw_data_as_openly_licensed',usable_as_confirmed_opening_history=False,coordinate_date_semantics='coordinates of a source-declared snapshot; index timestamp timezone unspecified; repository update is not point verification time')
(P/'ozon_nutrygo_validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ['address_first_component_counts','schemas','city_count_mismatches']},ensure_ascii=False,indent=2))
print('Address first components:',regions.most_common(15))
print('Count mismatches:',len(mismatches),'Schemas:',dict(schemas))

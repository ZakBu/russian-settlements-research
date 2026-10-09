from pathlib import Path
import json,gzip,hashlib,urllib.request,urllib.parse,datetime,pandas as pd
O=Path(__file__).parent
areas=[('Холмогорка',56.0547793,35.9378994),('Караваевской Фабрики',55.8614215,38.5837039),('Участка N 2',55.8614215,38.5837039),('Фирмы "Луч"',55.9538897,38.0747841),('Санатория "Звенигород"',55.7066553,36.8710329),('Санатория "Звенигород"',55.7083877,36.8805565)]
q='[out:json][timeout:20];('+''.join(f'nwr["place"~"village|hamlet|neighbourhood|suburb|locality"](around:700,{lat},{lon});way["landuse"="residential"](around:700,{lat},{lon});relation["landuse"="residential"](around:700,{lat},{lon});'for name,lat,lon in areas)+');out center tags;'
u='https://overpass-api.de/api/interpreter';entry={'url':u,'query':q,'normal_TLS':True,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'geographic_areas_are_candidates_only':areas}
try:
 with urllib.request.urlopen(urllib.request.Request(u,data=urllib.parse.urlencode({'data':q}).encode(),headers={'User-Agent':'RussianSettlementResearch/1.0 (bounded historical residential-source audit)'}),timeout=30)as r:raw=r.read();entry['status']=r.status
 f=O/'overpass_residential_compounds.json.gz';f.write_bytes(gzip.compress(raw,mtime=0));entry.update(source_file=str(f),source_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),raw_response_sha256=hashlib.sha256(raw).hexdigest());j=json.loads(raw);entry['feature_count']=len(j.get('elements',[]));rows=[]
 for e in j.get('elements',[]):rows.append(dict(provider='OSM_Overpass',feature_id=f'{e["type"]}/{e["id"]}',latitude=e.get('lat',e.get('center',{}).get('lat')),longitude=e.get('lon',e.get('center',{}).get('lon')),tags_json=json.dumps(e.get('tags',{}),ensure_ascii=False),own_name=e.get('tags',{}).get('name',''),feature_type=e.get('tags',{}).get('place',e.get('tags',{}).get('landuse','')),source_file=str(f),source_sha256=entry['source_sha256'],source_locator=f'elements type={e["type"]} id={e["id"]}',candidate_only=True,coordinate_admitted=False,identity_admitted=False,area_nearby_is_not_identity=True))
 pd.DataFrame(rows).to_csv(O/'overpass_residential_compound_candidates.csv',index=False);print('features',len(rows))
except Exception as e:entry['error']=str(e);print(type(e).__name__,str(e))
(O/'overpass_receipt.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2))

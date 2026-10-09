import zipfile,json,pathlib,pandas as pd
O=pathlib.Path(__file__).parent;p=pathlib.Path('/workspace/settlements-work/coordinate_first_20261008/sources/osm_geoapify_ru.zip');rows=[]
terms=['пореч','светлый','ткац','подольск','красный холм','шеметов','усадьб','кудинов','чапаев','поповка','луговая','пушкино','петровское']
with zipfile.ZipFile(p)as z:
 for m in z.namelist():
  if not m.endswith('ndjson'):continue
  with z.open(m)as f:
   for i,b in enumerate(f,1):
    o=json.loads(b);adr=o.get('address')or{};name=o.get('name','').lower().replace('ё','е');state=adr.get('state','')
    if state!='Московская область' or not any(t in name for t in terms):continue
    rows.append(dict(zip_member=m,line_1based=i,**o))
(O/'cached_osm_candidate_objects.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for o in rows:print(o['name'],o.get('osm_type'),o.get('osm_id'),o.get('location'),o.get('address'),o.get('tags'))
print('CANDIDATES',len(rows))

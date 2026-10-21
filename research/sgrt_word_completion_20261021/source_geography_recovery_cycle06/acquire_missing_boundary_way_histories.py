from pathlib import Path
import pandas as pd,json,requests,concurrent.futures,hashlib,xml.etree.ElementTree as ET,datetime
H=Path(__file__).resolve().parent;S=H/'sources';source=pd.read_parquet(H/'osm2021_inventory');a=pd.read_parquet(H/'all_exact_native11_osm2021_source_assertions.parquet');targets=set(a.loc[a.status.str.startswith('A2')&a.source_osm_type.eq('relation'),'source_osm_id']);ways=set(source.loc[source.osm_type.eq('way'),'osm_id']);missing=set()
for row in source[source.osm_type.eq('relation')&source.osm_id.isin(targets)].itertuples():missing.update(m['ref'] for m in json.loads(row.refs_or_members_json) if m['type']=='w' and m['ref'] not in ways)
def get(wid):
 u=f'https://api.openstreetmap.org/api/0.6/way/{wid}/history';r=requests.get(u,timeout=30);p=S/f'osm_way_{wid}_history.xml';p.write_bytes(r.content);out=dict(way_id=wid,url=u,status=r.status_code,file=str(p.relative_to(H)),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content),selected_snapshot_way=None)
 if r.status_code==200:
  root=ET.fromstring(r.content);versions=[w for w in root.findall('way') if w.attrib.get('timestamp','')<='2021-01-01T21:42:03Z'];w=max(versions,key=lambda w:int(w.attrib['version'])) if versions else None
  if w is not None:out['selected_snapshot_way']=dict(attributes=w.attrib,refs=[int(n.attrib['ref']) for n in w.findall('nd')],tags={n.attrib['k']:n.attrib['v'] for n in w.findall('tag')})
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:rows=list(pool.map(get,sorted(missing)))
(S/'missing_boundary_way_history_acquisition.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print([(r['way_id'],r['status'],len(r['selected_snapshot_way']['refs']) if r['selected_snapshot_way'] else None) for r in rows],flush=True)

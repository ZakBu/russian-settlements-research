from pathlib import Path
import json,gzip,hashlib,pandas as pd
O=Path(__file__).parent;p=O/'largest_hard_point_conflicts.csv';f=pd.read_csv(p).fillna('');want=set(f.loc[f.entity_source_path=='','wikidata_id']);found={}
paths=list(Path('/workspace/settlements-work/continuation_20261004').rglob('*.json'))+list(Path('/workspace/settlements-raw/data/raw/wikidata_entities_full').glob('batch*.json.gz'))+[p for d in ['wikidata_actual_full3_mass_reserve_20261007','wikidata_secondary_full3_expansion_20261007'] for p in Path('/workspace/settlements-work',d).glob('*.json.gz')]
for path in paths:
 if len(found)==len(want):break
 try:
  raw=path.read_bytes();a=json.loads(gzip.decompress(raw) if path.name.endswith('.gz') else raw)
 except Exception:continue
 if not isinstance(a,dict):continue
 es=a.get('entities',a.get('payload',{}).get('entities',{})) if 'claims' not in a else {a.get('id'):a}
 if not isinstance(es,dict):continue
 for q in want-found.keys():
  if q in es and isinstance(es[q],dict) and 'claims' in es[q]:found[q]=(es[q],str(path),hashlib.sha256(raw).hexdigest())
for i,r in f.iterrows():
 if r.wikidata_id in found:
  e,path,h=found[r.wikidata_id];f.at[i,'entity_source_path']=path;f.at[i,'entity_source_sha256']=h;f.at[i,'own_P625_claims_json']=json.dumps(e.get('claims',{}).get('P625',[]),ensure_ascii=False)
f.to_csv(p,index=False)
# Update only ancillary pins, publish application status last; accepted rows remain byte-identical.
rpath=O/'application_receipt.json';r=json.loads(rpath.read_text());rpath.unlink();m=json.loads((O/'source_manifest.json').read_text());m[str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
for e,path,h in found.values():m[path]=h
(O/'source_manifest.json').write_text(json.dumps(m,indent=2));r['source_API_requests']=20;r['application_API_requests']=0;r['hard_point_conflicts_held']=len(f);r['hard_point_conflict_own_entity_sources_pinned']=int((f.entity_source_path!='').sum());r['cached_census_reference_items_pinned']=17
for name in ('source_manifest.json','largest_hard_point_conflicts.csv'):r['outputs'][name]=hashlib.sha256((O/name).read_bytes()).hexdigest()
tmp=O/'application_receipt.tmp';tmp.write_text(json.dumps(r,indent=2,ensure_ascii=False));tmp.replace(rpath);print({'additional_conflict_sources':len(found),'source_missing_after_bounded_offline_scan':len(want)-len(found),'CSV_sha':r['outputs']['accepted_qualified_physical_observations.csv']})

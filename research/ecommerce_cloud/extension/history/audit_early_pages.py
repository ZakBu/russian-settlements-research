"""Audit downloaded early city pages without interpreting map shells as outlets."""
from pathlib import Path
import json,re,html,hashlib,base64,csv
ROOT=Path(__file__).resolve().parents[4];RAW=ROOT/'work/ecommerce_extension_history';OUT=Path(__file__).resolve().parent
j=json.loads((RAW/'early_cdx_09.body').read_bytes());cdx=[dict(zip(j[0],r))for r in j[1:]]
index={(x['timestamp'],x['original']):x for x in cdx};rows=[]
for f in sorted(RAW.glob('early_geo*.body')):
 receipt=json.loads(f.with_suffix('.request.json').read_text());text=f.read_text();states=[]
 for node_id,state in re.findall(r'id="(state-[^"]+)" data-state=\'(.*?)\'',text):
  if 'pickpointsMap'in node_id:states.append(json.loads(html.unescape(state)))
 m=re.search(r'/web/(\d{14})id_/(.*)',receipt['resolved_url']);capture=index.get((m[1],m[2]))
 assert capture is not None
 digest=base64.b32encode(hashlib.sha1(f.read_bytes()).digest()).decode();assert digest==capture['digest']
 rows.append({'source_body':str(f.relative_to(ROOT)),'capture_timestamp':m[1],'original_url':m[2],'cdx_sha1_verified':True,'sha256':receipt['sha256'],'map_states':len(states),'map_titles':' | '.join(x.get('title','')for x in states),'has_location':any('location'in x for x in states),'has_pvz':any('pvz'in x for x in states),'pvz_id':' | '.join(str(x.get('pvz',{}).get('id',''))for x in states),'evidence':'individual_existing_object'if any('pvz'in x for x in states)else 'city_map_shell_not_outlet_evidence'})
with (OUT/'early_page_audit.csv').open('w')as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
summary={'captures':len(cdx),'distinct_original_urls':len(set(x['original']for x in cdx)),'city_pages':sum(not re.search(r'/geo/[^/?]+/\d+/',x['original'])and not re.search(r'/geo/?(?:\?|$)',x['original'])for x in cdx),'object_pages':sum(bool(re.search(r'/geo/[^/?]+/\d+/',x['original']))for x in cdx),'root_pages':sum(bool(re.search(r'/geo/?(?:\?|$)',x['original']))for x in cdx),'downloaded_pages_sha1_verified':len(rows),'downloaded_city_shells':sum(not r['has_pvz']for r in rows),'new_national_object_panel_acquired':False}
(OUT/'early_page_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))

from pathlib import Path
import gzip,re,json,hashlib,collections
E=Path(__file__).resolve().parent;out=collections.defaultdict(list);domains=['nizhstat','mordovstat','tulastat','altstat','akstat','22.rosstat','71.rosstat','52.rosstat','13.rosstat'];files=list(Path('/workspace/settlements-raw/data/raw/wikipedia_articles').glob('*.json.gz'))
for p in files:
 try:t=gzip.open(p,'rt').read()
 except Exception:continue
 if not any(x in t for x in domains):continue
 for m in re.finditer(r'https?[^\s<>"{}]+',t):
  u=m.group(0).replace('\\/','/')
  if any(x in u for x in domains):out[u].append({'file':str(p),'context':t[max(0,m.start()-250):m.end()+350]})
rows=[{'url':u,'citation_occurrences':len(v),'first_witness':v[0]}for u,v in out.items()];(E/'cached_official_citation_URL_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps([{"url":x["url"],"occurrences":x["citation_occurrences"]}for x in rows],ensure_ascii=False,indent=2)[:22000]);print('URLCOUNT',len(rows))

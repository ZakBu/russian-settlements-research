from pathlib import Path
import json,gzip,re,pandas as pd,hashlib
O=Path(__file__).parent;r=pd.read_csv(O/'stage68_actual_remaining_primary.csv.gz');r=r[r.population.ge(500)];rows=[];seen=set()
for name in set(Path('/tmp/next69_cached_paths').read_text().splitlines()+Path('/tmp/next69_extra_cached_paths').read_text().splitlines()+['/workspace/russian-settlements-research/research_rebuild/evidence/cached_wikipedia_history_mass_20261008/cached_table_inventory.json']):
 p=Path(name)
 try:d=json.load(gzip.open(p,'rt')if p.suffix=='.gz'else p.open())
 except:continue
 if not isinstance(d,dict):continue
 z=d.get('query',{}).get('pages',{});z=z.values()if isinstance(z,dict)else z
 for page in z:
  title=page.get('title','');canon=title.split('(')[0].lower().strip().replace('ё','е');g=r[r.name_norm.eq(canon)]
  if g.empty:continue
  for rev in page.get('revisions',[]):
   text=rev.get('slots',{}).get('main',{}).get('content',rev.get('slots',{}).get('main',{}).get('*',rev.get('*','')))
   if not text or (title,rev.get('revid'))in seen:continue
   seen.add((title,rev.get('revid')));lines=[{'line':i,'text':t}for i,t in enumerate(text.splitlines(),1)if re.search(r'включ|присоедин|вош[её]л|упраздн|переимен',t,re.I)and re.search(r'20[012][0-9]',t)]
   if not lines:continue
   for a in g.to_dict('records'):rows.append({**a,'title':title,'sourcepath':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pageid':page.get('pageid'),'revision':rev.get('revid'),'coordinate':page.get('coordinates',[]),'eventlines':lines,'intro':text[:1800]})
(O/'actual68_cached_keyword_candidates.json.gz').write_bytes(gzip.compress(json.dumps(rows,ensure_ascii=False,default=str).encode()));print('hits',len(rows));print('\n'.join(f"{x['title']} {x['region_norm']} {x['census_year']} {x['population']} {x['eventlines'][:1]}"for x in rows))

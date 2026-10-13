from pathlib import Path
import pandas as pd,json,gzip,re,hashlib
O=Path(__file__).parent;R=pd.read_csv(O.parent/'assigned.csv');I=pd.read_csv('/dev/shm/over500-20261009/wiki_cached_title_index.csv.gz');norm=lambda s:re.sub(r'[^а-я0-9 ]',' ',str(s).lower().replace('ё','е')).strip();names={norm(x)for x in R.settlement_name};files=set()
for r in I.itertuples():
 n=norm(r.article_title.split('(')[0]);
 if n in names:files.add(r.cache_file)
# Include known qualified aliases and homonym pages.
extra=pd.read_csv('/dev/shm/over500-20261009/east_cached_index_subset.csv');files.update(extra.cache_file)
out=[]
for f in sorted(files):
 j=json.load(gzip.open(f));pgs=j.get('payload',j)['query']['pages'];pgs=pgs.values()if isinstance(pgs,dict)else pgs
 for p in pgs:
  n=norm(p['title'].split('(')[0]);
  if n in names or p['title']in set(extra.article_title):out.append(dict(source_path=f,source_sha256=hashlib.sha256(Path(f).read_bytes()).hexdigest(),page=p))
with gzip.open(O/'cached_own_pages.json.gz','wt')as f:json.dump(out,f,ensure_ascii=False)
print(len(out),len(files))

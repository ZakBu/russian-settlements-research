import urllib.request,urllib.parse,time,json,hashlib,concurrent.futures,re
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
BASE='https://rodnaya-vyatka.ru';ROOT=Path('/workspace/shared/vyatka1989_mass_extract');ROOT.mkdir(exist_ok=True)
def fetch(path):
 url=BASE+path; f=ROOT/(hashlib.sha256(url.encode()).hexdigest()+'.html')
 if not f.exists():
  raise RuntimeError('Network acquisition disabled: source terms review; use snapshot_cache.py')
  for attempt in range(4):
   try:
    time.sleep(.65);b=urllib.request.urlopen(url,timeout=90).read();f.write_bytes(b);break
   except Exception:
    if attempt==3:raise
    time.sleep(3*(attempt+1))
 b=f.read_bytes();return BeautifulSoup(b,'html.parser'),dict(url=url,raw_path=str(f),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def extract(d):
 path=f'/vpn1989-kirov/search?id_district={d}';queue=[path];seen=set();rows=[];receipts=[]
 while queue:
  p=queue.pop(0)
  if p in seen:continue
  seen.add(p);s,rc=fetch(p);receipts.append(rc)
  for a in s.select('.pager a'):
   q=a.get('href');
   if q and q not in seen and q not in queue:queue.append(q)
  for idx,tr in enumerate(s.select('#snmx_vpn1989-kirov_places_table > table > tbody > tr')):
   td=tr.find_all('td',recursive=False)
   if len(td)<14:
    note=tr.select_one('.snmx-comment')
    if note is not None and rows:
     rows[-1]['source_note_raw']=note.get_text(' ',strip=True);continue
    raise ValueError((p,idx,len(td)))
   v=[x.get_text(' ',strip=True) for x in td]; rid=v[0]
   def link(i):
    a=td[i].find('a');return BASE+a['href'] if a and a.get('href') else None
   row=dict(row_id=rid,name=v[3],type=v[2],district=v[4],selsovet=v[5],district_id=str(d),category=v[12],linked_place_url=link(1),district_url=link(4),selsovet_url=link(5),source_page_url=link(13),source_page_label=v[13],table_url=rc['url'],table_sha256=rc['sha256'],table_row_index=idx,raw_cells_json=json.dumps(v,ensure_ascii=False),object_level='locality',year=1989)
   for j,n in enumerate(['present_male','present_female','present_both','permanent_male','permanent_female','permanent_both'],6):
    row[n+'_raw']=v[j];z=v[j].replace(' ','').replace('\xa0','');row[n]=int(z) if z.isdigit() else None
   rows.append(row)
  print('page',d,len(receipts),len(rows),flush=True)
 return rows,receipts
if __name__=='__main__':
 rows=[];receipts=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for rr,rc in pool.map(extract,range(1,45)):
   rows+=rr;receipts+=rc
   pd.DataFrame(rows).to_parquet(ROOT/'facts_progress.parquet',index=False)
   (ROOT/'receipts_progress.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
 df=pd.DataFrame(rows);df.to_parquet(ROOT/'facts.parquet',index=False);df.to_csv(ROOT/'facts.csv',index=False)
 summary=dict(rows=len(df),unique_ids=df.row_id.nunique(),districts=df.district_id.nunique(),pages=len(receipts),bytes=sum(r['bytes'] for r in receipts),present_both_sum=int(df.present_both.sum()),permanent_both_sum=int(df.permanent_both.sum()),duplicates=int(df.row_id.duplicated().sum()),missing_present=int(df.present_both.isna().sum()),source_page_urls=df.source_page_url.nunique())
 (ROOT/'summary.json').write_text(json.dumps(summary,indent=2));(ROOT/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2));print(summary,flush=True)

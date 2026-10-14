"""Local-only forensic snapshot. Never requests the network."""
import json,hashlib
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
R=Path('/workspace/shared/vyatka1989_mass_extract');B='https://rodnaya-vyatka.ru';rows=[];receipts=[]
for d in range(1,45):
 for p in range(30):
  path=f'/vpn1989-kirov/search?id_district={d}' if p==0 else f'/vpn1989-kirov/search?page={p}&id_district={d}'
  u=B+path;f=R/(hashlib.sha256(u.encode()).hexdigest()+'.html')
  if not f.exists():continue
  b=f.read_bytes();h=hashlib.sha256(b).hexdigest();receipts.append(dict(url=u,raw_path=str(f),sha256=h,bytes=len(b)));s=BeautifulSoup(b,'html.parser');page_rows=[]
  for idx,tr in enumerate(s.select('#snmx_vpn1989-kirov_places_table > table > tbody > tr')):
   td=tr.find_all('td',recursive=False)
   if len(td)<14:
    note=tr.select_one('.snmx-comment')
    if note and page_rows:page_rows[-1]['source_note_raw']=page_rows[-1].get('source_note_raw','')+' '+note.get_text(' ',strip=True)
    else:raise ValueError((u,idx,str(tr)))
    continue
   v=[x.get_text(' ',strip=True) for x in td]
   def link(i):
    a=td[i].find('a');return B+a['href'] if a and a.get('href') else None
   r=dict(row_id=v[0],name=v[3],type=v[2],district=v[4],selsovet=v[5],district_id=str(d),category=v[12],linked_place_url=link(1),district_url=link(4),selsovet_url=link(5),source_page_url=link(13),source_page_label=v[13],table_url=u,table_sha256=h,table_row_index=idx,raw_cells_json=json.dumps(v,ensure_ascii=False),object_level='locality',year=1989,admission_status='not_admitted_terms_review')
   for j,n in enumerate(['present_male','present_female','present_both','permanent_male','permanent_female','permanent_both'],6):
    r[n+'_raw']=v[j];z=v[j].replace(' ','').replace('\xa0','');r[n]=int(z) if z.isdigit() else None
   page_rows.append(r)
  rows+=page_rows
D=pd.DataFrame(rows);D.to_parquet(R/'facts_partial_not_admitted.parquet',index=False);(R/'receipts_partial.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
S=dict(status='acquisition_stopped_terms_review',admission='not_admitted',rows=len(D),unique_ids=D.row_id.nunique(),districts_observed=D.district_id.nunique(),pages=len(receipts),bytes=sum(r['bytes'] for r in receipts),present_both_sum=int(D.present_both.sum()),permanent_both_sum=int(D.permanent_both.sum()),duplicate_ids=int(D.row_id.duplicated().sum()),source_page_urls=D.source_page_url.nunique(),note_rows=int(D.source_note_raw.notna().sum()),district_row_counts={str(k):int(v) for k,v in D.groupby('district_id').size().items()})
(R/'summary_partial.json').write_text(json.dumps(S,indent=2));print(json.dumps(S,indent=2))

#!/usr/bin/env python3
import csv,json,re,hashlib
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup
E=Path(__file__).resolve().parent
S=Path('/workspace/shared/rsfsr1979_urban_mass')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(name):
 s=BeautifulSoup((S/(name+'.html')).read_bytes().decode('cp1251'),'html.parser')
 return [(i,[' '.join(c.get_text(' ',strip=True).split()) for c in tr.find_all(['td','th'],recursive=False)]) for i,tr in enumerate(s.find_all('tr'),1)]
def write(name,data):
 if data:
  with (E/name).open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
region=admin=city='';out=[];headers=[]
for i,r in rows('rus79_reg2'):
 if len(r)!=4:continue
 label=r[0]
 if all(re.fullmatch(r'\d+',x) for x in r[1:]):
  match=re.match(r'^(г\.|пгт\b|рп\b|кп\b|дп\b)',label)
  scope='settlement' if match else 'city_subdivision_context'
  if match and match[0]=='г.':city=label
  t,m,f=map(int,r[1:])
  out.append(dict(source_record_id=f'1979:demoscope:rus79_reg2.php:html_tr:{i}',source_locator=f'HTML tr {i} (all document tr, direct child cells)',source_url='https://www.demoscope.ru/weekly/ssp/rus79_reg2.php',source_sha256=sha(S/'rus79_reg2.html'),source_citation='Всесоюзная перепись населения 1979. Таблица 1с. РГАЭ. Ф 1562. Оп. 336. Д. 5943-5951.',census_year=1979,population_basis='present',population_scope=scope,settlement_type_raw=match[0] if match else '',source_parsed_name=re.sub(r'\s*\(рц\)\s*$','',label[match.end():]).strip() if match else '',label_raw=label,region_label_raw=region,administrative_heading_raw=admin,parent_city_context_raw=city if not match else '',population_total=t,population_male=m,population_female=f,sex_balance_status='consistent' if t==m+f else 'conflict',unit='persons',source_fact_status='parsed_literal_source_native_observation',identity_status='source_native_unlinked',coordinate_admission_status='not_admitted',decision_status='candidate_not_accepted',overlap_policy='exclude_city_subdivision_rows_from_settlement_sum',zato_scope_policy='published_table_scope; closed_city_completeness_not_asserted; no_secondary_zato_addition_or_residual_allocation'))
 elif not any(r[1:]) and label:
  headers.append(dict(html_tr=i,label_raw=label))
  if label in ['С С С Р','Р С Ф С Р']:continue
  if label=='Ленинградский горсовет':region='г. Ленинград';admin=label;city='';continue
  if label.startswith('г. Москва и населенные пункты'):region='г. Москва';admin=label;city='';continue
  if re.search(r'область|АССР|автономный округ|автономная область| край',label) and not label.endswith('район'):
   region=label;admin=city=''
  elif re.search(r'район|горсовет|райсовет',label):admin=label;city=''
  else:region=label;admin=city=''
sett=[x for x in out if x['population_scope']=='settlement']
write('all_numeric_source_rows.csv',out);write('urban_settlements_1979.csv',sett)
(E/'source_headers.json').write_text(json.dumps(headers,ensure_ascii=False,indent=2))
controls=[]
for i,r in rows('rus79_reg1'):
 if len(r)==10 and r[0]=='Р С Ф С Р.':
  for offset,basis in [(1,'all'),(4,'urban'),(7,'rural')]:
   controls.append(dict(source_record_id=f'1979:demoscope:rus79_reg1.php:html_tr:{i}:{basis}',source_locator=f'HTML tr {i}, columns {offset+1}-{offset+3}',source_url='https://www.demoscope.ru/weekly/ssp/rus79_reg1.php',source_sha256=sha(S/'rus79_reg1.html'),population_basis='present',population_scope=basis,population_total=int(r[offset]),population_male=int(r[offset+1]),population_female=int(r[offset+2]),unit='persons'))
write('official_controls.csv',controls)
counts=Counter((x['region_label_raw'],x['label_raw']) for x in sett)
receipt=dict(settlement_rows=len(sett),settlement_population_sum=sum(x['population_total']for x in sett),type_profiles=[dict(type=k,rows=sum(x['settlement_type_raw']==k for x in sett),population_sum=sum(x['population_total']for x in sett if x['settlement_type_raw']==k))for k in sorted(set(x['settlement_type_raw'] for x in sett))],city_subdivision_rows=len(out)-len(sett),sex_balance_conflicts=[x['source_record_id']for x in out if x['sex_balance_status']=='conflict'],duplicate_region_label_groups=[dict(region=k[0],label=k[1],count=v)for k,v in counts.items()if v>1],nonprefix_non_district_labels=[x['label_raw']for x in out if x['population_scope']!='settlement' and not re.search('район|Часть города',x['label_raw'])],region_count=len(set(x['region_label_raw']for x in sett)),controls=controls,no_allocation=True,no_historical_identity_acceptance=True,permanent_population_extracted=False,assets={p.name:dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p),retrieval='2026-10-14 normal verified TLS curl HTTPS')for p in S.glob('*.html')},outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p))for p in E.glob('*.csv')})
control=next(x['population_total']for x in controls if x['population_scope']=='urban');receipt['settlement_sum_minus_official_urban_control']=receipt['settlement_population_sum']-control
(E/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items()if k not in ['assets','outputs','controls','duplicate_region_label_groups']},ensure_ascii=False,indent=2))

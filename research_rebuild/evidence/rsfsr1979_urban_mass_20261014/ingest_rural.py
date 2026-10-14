#!/usr/bin/env python3
import csv,json,re,hashlib
from pathlib import Path
from bs4 import BeautifulSoup
E=Path(__file__).resolve().parent;S=Path('/workspace/shared/rsfsr1979_urban_mass');p=S/'rus79_reg3.html'
b=p.read_bytes();sha=hashlib.sha256(b).hexdigest();s=BeautifulSoup(b.decode('cp1251'),'html.parser');out=[];headers=[];region=admin=''
for i,tr in enumerate(s.find_all('tr'),1):
 r=[' '.join(c.get_text(' ',strip=True).split()) for c in tr.find_all(['td','th'],recursive=False)]
 if len(r)!=4:continue
 label=r[0]
 parse_label=label.strip(' \"')
 if all(re.fullmatch(r'\d+',x) for x in r[1:]):
  typ=re.match(r'^(с\.|п\.|д\.|дп\b|ст-ца\b|станица\b|станция\b|поселок\b|хутор\b|сл\.|х\.|аул\b)',parse_label)
  t,m,f=map(int,r[1:]);out.append(dict(source_record_id=f'1979:demoscope:rus79_reg3.php:html_tr:{i}',source_locator=f'HTML tr {i} (all document tr, direct child cells)',source_url='https://www.demoscope.ru/weekly/ssp/rus79_reg3.php',source_sha256=sha,census_year=1979,population_basis='present',population_scope='settlement' if typ else 'unclassified_context',settlement_type_raw=typ[0] if typ else '',source_parsed_name=re.sub(r'\s*\(рц\)\s*$','',parse_label[typ.end():].rstrip(' .')).strip() if typ else '',label_raw=label,region_label_raw=region,administrative_heading_raw=admin,population_total=t,population_male=m,population_female=f,sex_balance_status='consistent' if t==m+f else 'conflict',unit='persons',source_fact_status='parsed_literal_source_native_observation',identity_status='source_native_unlinked',coordinate_admission_status='not_admitted',decision_status='candidate_not_accepted',coverage_scope='reg3 published rural table: administrative centres plus additional named settlements; not all rural settlements'))
 elif not any(r[1:]) and label:
  headers.append(dict(html_tr=i,label_raw=label))
  if label.rstrip(' .') in ['С С С Р','Р С Ф С Р']:continue
  if re.search(r'область|АССР|автономный округ|автономная область| край',label) and not label.endswith('район'):region=label.rstrip(' .');admin=''
  elif re.search(r'район|горсовет|райсовет',label):admin=label
  else:region=label.rstrip(' .');admin=''
def write(name,r):
 if r:
  with (E/name).open('w',newline='')as f:w=csv.DictWriter(f,list(r[0]));w.writeheader();w.writerows(r)
write('rural_centres_all_numeric_1979.csv',out);sett=[x for x in out if x['population_scope']=='settlement'];write('rural_centres_1979.csv',sett);(E/'rural_source_headers.json').write_text(json.dumps(headers,ensure_ascii=False,indent=2))
j=dict(source_sha256=sha,source_bytes=len(b),numeric_rows=len(out),settlement_rows=len(sett),settlement_population_sum=sum(x['population_total']for x in sett),unclassified=[x for x in out if x['population_scope']!='settlement'],sex_conflicts=[x['source_record_id']for x in out if x['sex_balance_status']=='conflict'],no_allocation=True,no_full_rural_coverage_claim=True,citation=s.get_text(' ',strip=True)[-1200:],outputs={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in E.glob('rural*.csv')});(E/'rural_receipt.json').write_text(json.dumps(j,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in j.items() if k not in ['citation','outputs']},ensure_ascii=False,indent=2))

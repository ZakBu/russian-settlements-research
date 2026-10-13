#!/usr/bin/env python3
import csv,json,hashlib,re
from pathlib import Path
from html.parser import HTMLParser
E=Path(__file__).resolve().parent
class Rows(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,t,a):
  if t=='tr':self.row=[]
  if t in ('td','th'):self.cell=[]
 def handle_data(self,d):
  if self.cell is not None:self.cell.append(d)
 def handle_endtag(self,t):
  if t in ('td','th') and self.cell is not None:
   if self.row is not None:self.row.append(' '.join(''.join(self.cell).split()))
   self.cell=None
  if t=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
m=next(x for x in json.loads((E/'initial_discovery.json').read_text()) if 'rus89_reg3' in x['url']);raw=Path(m['path']);raw=raw if raw.exists() else E/raw.name;b=raw.read_bytes();p=Rows();p.feed(b.decode('cp1251'))
region='';scope=[];out=[];headers=[]
for i,r in enumerate(p.rows,1):
 if len(r)!=4:continue
 if all(re.fullmatch(r'\d+',x) for x in r[1:]):
  if not re.match(r'^(с\.|п\.|ст\.|ст-ца|сл\.|д\.|аул|станица|село|пос)',r[0],re.I):raise ValueError(('Unrecognized settlement caption',r))
  t,male,female=map(int,r[1:]);assert t==male+female
  out.append(dict(source_record_id=f'1989:demoscope:rus89_reg3.php:html_tr:{i}',source_url=m['url'],source_sha256=hashlib.sha256(b).hexdigest(),source_locator=f'HTML tr {i}',census_year=1989,population_basis='present',population_scope='settlement',settlement_label_raw=r[0],region_label_raw=region,source_heading_path=' | '.join(scope),population_total=t,population_male=male,population_female=female,unit='persons',identity_status='source_native_unlinked'))
 elif not any(r[1:]) and r[0]:
  label=r[0];headers.append(dict(html_tr=i,label=label))
  if label=='Р С Ф С Р':scope=[label]
  elif label.endswith(' район'):scope=scope[:1]+[label]
  else:
   region=label
   if 'автономный' in label.lower():scope=scope[:3]+[label]
   else:scope=scope[:2]+[label]
with (E/'rural_district_centers_1989.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
(E/'source_headers.json').write_text(json.dumps(headers,ensure_ascii=False,indent=2))
receipt=dict(population_basis='present',source_citation='ТОМ 1. Часть 1. Таблица 3. Численность наличного населения',source_url=m['url'],source_sha256=hashlib.sha256(b).hexdigest(),source_bytes=len(b),rows=len(out),population_total=sum(x['population_total']for x in out),male=sum(x['population_male']for x in out),female=sum(x['population_female']for x in out),sex_balance_conflicts=0,duplicate_native_locators=len(out)-len({x['source_record_id']for x in out}),raw_label_region_duplicate_groups=[{'region':a,'label':c,'rows':n}for (a,c),n in __import__('collections').Counter((x['region_label_raw'],x['settlement_label_raw'])for x in out).items()if n>1],not_exhaustive_all_rural_settlements=True,no_aggregate_allocation=True,urban_territorial_population_context=108425580,rural_territorial_population_context=38974957)
receipt['urban_plus_this_rural_source_ceiling']=108425580+receipt['population_total'];receipt['gap_to_120million']=120000000-receipt['urban_plus_this_rural_source_ceiling'];receipt['output_sha256']=hashlib.sha256((E/'rural_district_centers_1989.csv').read_bytes()).hexdigest()
(E/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))

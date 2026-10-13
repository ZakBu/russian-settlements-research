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
from collections import Counter
b=(E/'rus89_reg2.html').read_bytes();sha=hashlib.sha256(b).hexdigest();p=Rows();p.feed(b.decode('cp1251'))
region='';macro='';district='';last_city='';out=[];headers=[]
for i,r in enumerate(p.rows,1):
 if len(r)!=4:continue
 label=r[0]
 if all(re.fullmatch(r'\d+',x) for x in r[1:]):
  t,m,f=map(int,r[1:]);typ=re.match(r'^(г\.|рп\b|кп\b|дп\b|пгт\b)',label)
  explicit_single_np=label=='Городское население -рп Сузун (рц)'
  if explicit_single_np:typ=re.search(r'рп\b',label)
  scope='settlement' if typ else ('city_district' if ' район' in label or label=='Промышленный райо' or label=='Городское население' else 'unclassified_context')
  if typ and typ[0]=='г.':last_city=label
  out.append(dict(source_record_id=f'1989:demoscope:rus89_reg2.php:html_tr:{i}',source_locator=f'HTML tr {i}',source_url='https://www.demoscope.ru/weekly/ssp/rus89_reg2.php',source_sha256=sha,census_year=1989,population_basis='present',population_scope=scope,settlement_type_raw=typ[0] if typ else '',source_parsed_name=re.sub(r'\s*\(рц\)\s*$','',re.sub(r'^(г\.|рп\b|кп\b|дп\b|пгт\b)\s*','',label if not explicit_single_np else 'рп Сузун (рц)')).strip()if typ else '',source_class_role='named_urban_settlement'if scope=='settlement'else 'city_subdivision_context',source_heading_path=' | '.join(x for x in ['Р С Ф С Р',macro,region,district]if x),label_raw=label,region_label_raw=region,macroregion_label_raw=macro,administrative_heading_raw=district,parent_city_context_raw=last_city if scope!='settlement' else '',population_total=t,population_male=m,population_female=f,sex_balance_status='consistent'if t==m+f else 'conflict',unit='persons',identity_status='source_native_unlinked',parser_rule='explicit_single_named_np_in_urban_caption'if explicit_single_np else 'literal_type_prefix_or_city_district',parent_child_overlap_status='city_subdivision_excluded_from_settlement_sum'if scope!='settlement'else 'named_settlement_no_automatic_scope_union'))
 elif not any(r[1:]) and label:
  headers.append(dict(html_tr=i,label_raw=label))
  if label=='Р С Ф С Р':continue
  if any(k in label for k in ['область','АССР','автономный округ','автономная область',' край']) and not label.endswith(' район'):
   region=label;district='';last_city=''
  elif label.endswith(' район') or label.endswith('горсовет') or label.endswith('райсовет'):
   if label.endswith(' район') and label in ['Северный район','Северо-Западный район','Центральный район','Волго-Вятский район','Центрально-Черноземный район','Поволжский район','Северо-Кавказский район','Уральский район','Западно-Сибирский район','Восточно-Сибирский район','Дальневосточный район']:macro=label;region='';district=''
   else:district=label;last_city=''
  else:region=label;district='';last_city=''
def write(name,rows):
 with (E/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(rows)
write('all_numeric_source_rows.csv',out);sett=[x for x in out if x['population_scope']=='settlement'];write('urban_settlements_1989.csv',sett);(E/'source_headers.json').write_text(json.dumps(headers,ensure_ascii=False,indent=2))
r=dict(source_sha256=sha,source_bytes=len(b),source_citation='Всесоюзная перепись населения 1989 года. Том 1, часть 1, таблица 3. Численность наличного населения',population_basis='present',all_numeric_rows=len(out),all_numeric_sum=sum(x['population_total']for x in out),scope_profiles=[dict(scope=k,rows=sum(x['population_scope']==k for x in out),population_sum=sum(x['population_total']for x in out if x['population_scope']==k))for k in sorted({x['population_scope']for x in out})],settlement_rows=len(sett),settlement_population_sum=sum(x['population_total']for x in sett),urban_territorial_control=108425580,settlement_sum_minus_control=sum(x['population_total']for x in sett)-108425580,sex_balance_conflicts=[x['source_record_id']for x in out if x['sex_balance_status']=='conflict'],unclassified_rows=[x for x in out if x['population_scope']=='unclassified_context'],moscow=[x for x in sett if x['label_raw']in ['г. Москва','г. Зеленоград']],no_allocation=True)
r['duplicate_region_label_groups']=[dict(region=a,label=c,rows=n)for(a,c),n in Counter((x['region_label_raw'],x['label_raw'])for x in sett).items()if n>1]
r['outputs']={n:dict(bytes=(E/n).stat().st_size,sha256=hashlib.sha256((E/n).read_bytes()).hexdigest())for n in ['all_numeric_source_rows.csv','urban_settlements_1989.csv']}
(E/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items()if k not in ['moscow','outputs','unclassified_rows']},ensure_ascii=False,indent=2));print('unclassified',r['unclassified_rows'])

from pathlib import Path
import re,json,hashlib,pandas as pd,pyarrow.parquet as pq
B=Path('/workspace/shared/rsfsr1989_rural_tyumen');O=Path(__file__).parent
s=(B/'tyumen2002_comparative.txt').read_text();meta=json.loads((B/'download.json').read_text());sha=hashlib.sha256((B/'tyumen2002_comparative.pdf').read_bytes()).hexdigest()
pat=re.compile(r'^\s*(.+?)\s+(\d+|[-хx…])\s+(\d+|[-хx…])\s+(\d+|[-хx…])\s+(\d+|[-хx…])\s+(\d+|[-хx…])\s+(\d+|[-хx…])\s*$')
np=re.compile(r'^(с|п|д)\.\s*(.+)$')
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е').replace('ѐ','е')).strip()
rows=[];unparsed=[];foot=[];started=False;region='тюменская';district='';admin='';city_context=False
for pdfpage,page in enumerate(s.split('\f'),1):
 if 'Численность населения по сельским населенным пунктам' in page and 'оба пола' in page:started=True
 if not started:continue
 if 'Численность населения регионов Уральского федерального округа' in page:break
 # Printed page may precede or follow the footer title.
 pm=re.search(r'^\s*(\d{1,2})\s+ИТОГИ',page,re.M) or re.search(r'ИТОГИ ВСЕРОССИЙСКОЙ ПЕРЕПИСИ НАСЕЛЕНИЯ – 2002\s+(\d{1,2})\s*$',page,re.M)
 printed=int(pm[1]) if pm else None
 for i,l in enumerate(page.splitlines(),1):
  if 'Ханты-Мансийский автономный округ' in l:region='ханты мансийский югра';district='';admin=''
  if 'Ямало-Ненецкий автономный округ' in l:region='ямало ненецкий';district='';admin=''
  if re.match(r'^\s*\d+\)\s*$',l) or re.match(r'^\s*В 1989',l):foot.append({'pdf_page':pdfpage,'printed_page':printed,'line':l.strip()})
  m=pat.match(l)
  if not m:
   if re.match(r'^\s*(с|п|д)\.',l):unparsed.append({'pdf_page':pdfpage,'line':l})
   continue
  raw=m[1].strip();vals=[int(x) if x.isdigit() else None for x in m.groups()[1:]]
  if raw.endswith(' район'):district=raw;admin='';continue
  if re.match(r'^г\.',raw):district=raw;admin='';continue
  if re.search(r'(с/а|п/а|АТО)',raw):admin=raw;continue
  n=np.match(raw)
  if not n:
   if raw.startswith('Разъезд №'):typ='разъезд';name=raw.replace('Разъезд №','').strip()
   elif raw=='Дом инвалидов':typ='';name=raw
   else:continue
  else:typ={'с':'село','п':'поселок','д':'деревня'}[n[1]];name=re.sub(r'\d+\)','',n[2]).strip()
  rows.append({'source_record_id':f'tyumen1989:pdf{pdfpage}:line{i}','census_year':1989,'region_norm':region,'district_raw':district,'administration_raw':admin,'settlement_name':name,'settlement_type':typ,'name_norm':norm(name),'type_norm':norm(typ),'population':vals[0],'male_1989':vals[1],'female_1989':vals[2],'population_2002':vals[3],'male_2002':vals[4],'female_2002':vals[5],'source_file':'tyumen2002_comparative.pdf','source_path':str(B/'tyumen2002_comparative.pdf'),'source_sha256':sha,'source_url':meta['retrieved_url'],'source_original_url':meta['source_url'],'source_locator':f'Printed p.{printed}; PDF p.{pdfpage}; line{i}','pdf_page':pdfpage,'printed_page':printed,'population_basis':'permanent','population_basis_evidence':'Publisher annotation p2 explicitly постоянного населения; 1989/2002 comparative table pp30–79','population_scope':'individual_rural_settlement_both_sexes','source_name_raw':raw,'source_line_raw':l.strip(),'population_value_quality':'reported_census_integer' if vals[0] is not None else 'no1989count','population_raw_1989':m[2],'male_raw_1989':m[3],'female_raw_1989':m[4],'population_raw_2002':m[5],'male_raw_2002':m[6],'female_raw_2002':m[7],'zero_symbol_1989':m[2]=='-','footnote_marker':bool(re.search(r'\d+\)',raw))})
d=pd.DataFrame(rows);d['sex_total_valid']=d.population.eq(d.male_1989+d.female_1989);d.to_csv(O/'tyumen1989_all_np_rows.csv',index=False);u=d[d.population.gt(0)&d.sex_total_valid&d.type_norm.ne('')].copy();u.to_csv(O/'tyumen1989_usable.csv',index=False);d[d.population.gt(0)&~d.sex_total_valid].to_csv(O/'tyumen1989_sex_total_failures.csv',index=False)
(O/'unparsed_np_lines.json').write_text(json.dumps(unparsed,ensure_ascii=False,indent=2));(O/'footnotes.json').write_text(json.dumps(foot,ensure_ascii=False,indent=2))
t=pq.read_table('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet',columns=['region_norm','settlement_name','name_norm','type_norm','district_raw','root']).to_pandas();t=t[t.region_norm.isin(u.region_norm.unique())].copy();t['district_norm']=t.district_raw.fillna('').map(norm);u['district_norm']=u.district_raw.map(norm)
exact=t.groupby(['region_norm','name_norm','type_norm','district_norm']).root.agg(lambda x:sorted(set(x))).to_dict();regional=t.groupby(['region_norm','name_norm','type_norm']).root.agg(lambda x:sorted(set(x))).to_dict();rs=[]
for r in u.to_dict('records'):
 k=(r['region_norm'],r['name_norm'],r['type_norm'],r['district_norm']);v=exact.get(k,[]);method='exact_name_type_district'
 if len(v)!=1:v=regional.get(k[:3],[]);method='exact_unique_name_type_in_region'
 r.update(candidate_root_count=len(v),candidate_root=v[0] if len(v)==1 else None,candidate_roots=json.dumps(v),candidate_method=method);rs.append(r)
a=pd.DataFrame(rs);a.to_csv(O/'tyumen1989_root_candidates.csv',index=False);q=a[a.candidate_root_count.eq(1)].copy();du=q.candidate_root.duplicated(False);q[~du].to_csv(O/'tyumen1989_unique_root_candidates.csv',index=False)
summary={'source_np_rows':len(d),'usable_np_rows':len(u),'usable_people':int(u.population.sum()),'source_positive_sex_failure_rows':int((d.population.gt(0)&~d.sex_total_valid).sum()),'unparsed_np_lines':len(unparsed),'unique_root_candidates':len(q[~du]),'candidate_people':int(q.loc[~du,'population'].sum()),'candidate_duplicate_root_rows':int(du.sum()),'per_region_source_usable':u.groupby('region_norm').population.agg(['size','sum']).to_dict('index'),'per_region_unique_candidates':q[~du].groupby('region_norm').population.agg(['size','sum']).to_dict('index'),'publication_year':2004,'publisher':'Тюменский областной комитет государственной статистики','title':'Итоги Всероссийской переписи населения–2002. ЧастьI. Численность населения Тюменской области','population_basis':'permanent_explicit','source_url':meta['source_url'],'retrieved_url':meta['retrieved_url'],'sha256':sha,'no_integration_modified':True}
(O/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))

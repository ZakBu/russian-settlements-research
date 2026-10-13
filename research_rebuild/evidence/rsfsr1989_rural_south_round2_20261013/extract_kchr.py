from pathlib import Path
import pandas as pd,pyarrow.parquet as pq,re,json,hashlib
B=Path('/workspace/shared/rsfsr1989_rural_south_round2');O=Path(__file__).parent
meta=next(x for x in json.loads((B/'northcaucasus_attempts.json').read_text()) if x['file']=='kchr2002_book1_2.pdf')
s=(B/'kchr2002_book1_2.txt').read_text();start=s.index('1.5. ЧИСЛЕННОСТЬ ПОСТОЯННОГО НАСЕЛЕНИЯ');s=s[start:s.index('1.6.',start)]
pat=re.compile(r'^\s*((?:аул|село|станица|хутор|пос[её]лок)\s+.+?)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)\s*$')
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е').replace('ѐ','е')).strip()
rows=[];district='';admin='';page=12
for i,l in enumerate(s.splitlines(),1):
 dm=re.search(r'\b[IVX]+\.\s+([А-ЯЁа-яё -]+ район)',l)
 if dm:district=dm[1];admin=''
 am=re.match(r'^\s*\d+\.?\s+([^0-9]+?\s(?:СМО|ГМО))',l)
 if am:admin=am[1]
 if re.fullmatch(r'\s*\d{2}\s*',l):page=int(l.strip())
 m=pat.match(l)
 if not m:continue
 vals=[int(x) if x.isdigit() else None for x in m.groups()[1:]]
 raw=m[1];typ,name=raw.split(' ',1);clean=re.sub(r'\d+\)','',name).strip()
 rows.append(dict(source_record_id=f'kchr1989:table1.5:line{i}',census_year=1989,region_norm='карачаево черкесская',district_raw=district,administration_raw=admin,settlement_name=clean,settlement_type=typ,name_norm=norm(clean),type_norm=norm(typ),population=vals[0],male_1989=vals[1],female_1989=vals[2],population_2002=vals[3],source_file='kchr2002_book1_2.pdf',source_path=str(B/'kchr2002_book1_2.pdf'),source_sha256=hashlib.sha256((B/'kchr2002_book1_2.pdf').read_bytes()).hexdigest(),source_url=meta['retrieval_url'],source_locator=f'Book1,Table1.5,printedpp12–20,blockline{i}',population_basis='permanent',population_basis_evidence='Table1.5 title and column heading explicitly say постоянное население по переписи на12.01.1989',source_name_raw=raw,population_scope='settlement_both_sexes',is_additive_settlement_record=vals[0] is not None,population_value_quality='reported_census_integer' if vals[0] is not None else 'no1989_ruralcount'))
d=pd.DataFrame(rows);d['sex_total_valid']=d.population.eq(d.male_1989+d.female_1989);d.to_csv(O/'kchr1989_all_np_rows.csv',index=False);u=d[d.population.gt(0)&d.sex_total_valid].copy();u.to_csv(O/'kchr1989_usable.csv',index=False)
# Candidate mapping retains same exact-name linkage methodology as first pass.
t=pq.read_table('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet',columns=['region_norm','settlement_name','name_norm','type_norm','district_raw','root']).to_pandas();t=t[t.region_norm.str.contains('карача',na=False)].copy();region_values=t.region_norm.unique().tolist();print('inputregions',region_values)
if len(region_values)==1:u['region_norm']=region_values[0]
u['district_norm']=u.district_raw.map(norm);t['district_norm']=t.district_raw.fillna('').map(norm)
exact=t.groupby(['region_norm','name_norm','type_norm','district_norm']).root.agg(lambda x:list(set(x))).to_dict();regional=t.groupby(['region_norm','name_norm','type_norm']).root.agg(lambda x:list(set(x))).to_dict()
rs=[]
for r in u.to_dict('records'):
 k=(r['region_norm'],r['name_norm'],r['type_norm'],r['district_norm']);v=exact.get(k,[]);method='exact_name_type_district'
 if len(v)!=1:v=regional.get(k[:3],[]);method='exact_unique_name_type_in_region'
 r['candidate_root_count']=len(v);r['candidate_root']=v[0] if len(v)==1 else None;r['candidate_roots']=json.dumps(v);r['candidate_method']=method;rs.append(r)
a=pd.DataFrame(rs);a.to_csv(O/'kchr1989_root_candidates.csv',index=False);unique=a[a.candidate_root_count.eq(1)].copy();dup=unique.candidate_root.duplicated(False);unique[~dup].to_csv(O/'kchr1989_unique_root_candidates.csv',index=False)
summary={'source_np_rows':len(d),'explicit1989rural_np_rows':len(u),'explicit1989rural_people':int(u.population.sum()),'reported_region_rural1989':213315,'population_sum_equals_source_region_total':int(u.population.sum())==213315,'sex_total_failures_explicit':int((d.population.notna()&~d.sex_total_valid).sum()),'unique_root_candidates':len(unique[~dup]),'candidate_people':int(unique.loc[~dup,'population'].sum()),'candidate_duplicate_root_rows':int(dup.sum()),'population_basis':'permanent_explicit','source_title':'Население Карачаево-Черкесской Республики. Статистический сборник по материалам Всероссийской переписи населения2002года. Книга1','publication_year':2005,'publisher':'Карачаево-Черкесскстат','source_url':meta['original_url'],'retrieval_url':meta['retrieval_url']}
(O/'kchr1989_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))

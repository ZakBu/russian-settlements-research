from pathlib import Path
import pandas as pd, json, hashlib, gzip, re, subprocess, importlib.util
O=Path(__file__).resolve().parent
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
P=O/'leningrad_2010_official_archived.pdf'
D=O/'parsed'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).casefold().replace('ё','е').replace('ѐ','е')).strip()
T={'г.':'город','г.п.':'пгт','дер.':'деревня','с.':'село','пос.':'поселок','п.ст.':'поселок','хут.':'хутор','корд.':'кордон','мест.':'местечко'}
def typ(x):return norm(x).replace('поселок','поселок')
s=pd.read_parquet(S);s=s[(s.census_year==2010)&(s.region_raw=='ленинградская')].copy()
def read(name):
 p=D/name
 return pd.read_csv(p if p.exists() else Path(str(p)+'.gz'))
v=read('leningrad_2010_explicit_locality_values_ge100.csv');u=read('leningrad_2010_named_localities_without_values.csv')
a=pd.concat([v,u],ignore_index=True)
v['key']=v.apply(lambda r:(T.get(r.type_raw,norm(r.type_raw)),norm(r.name_raw)),axis=1)
a['key']=a.apply(lambda r:(T.get(r.type_raw,norm(r.type_raw)),norm(r.name_raw)),axis=1)
s['key']=s.apply(lambda r:(typ(r.settlement_type),norm(r.settlement_name)),axis=1)
ac=a.key.value_counts();sc=s.key.value_counts()
raw=subprocess.check_output(['pdftotext','-layout',str(P),'-']).decode();pages=raw.split('\f')
rows=[]
for r in v.to_dict('records'):
 matches=s[s.key==r['key']]; page=pages[int(r['page'])-1]
 # Independent Poppler line verifies the explicit name and P/M/F sequence.
 nums=[str(int(r[k])) for k in ['population','men','women']]
 hits=[]
 pl=page.splitlines()
 for li,line in enumerate(pl):
  if norm(r['name_raw']) not in norm(line):continue
  ns=re.findall(r'\d+',line)
  if any(ns[j:j+3]==nums for j in range(len(ns)-2)):hits.append(line)
  elif not ns:
   for continuation in pl[li+1:li+4]:
    if re.findall(r'\d+',continuation)==nums:hits.append(line+' | '+continuation);break
 unique=int(ac[r['key']])==1 and len(matches)==1
 base={**r,'official_source_record_id':f"LEN2010:PETROSTAT:P{r['page']:03d}:L{r['line']:03d}",'official_source_sha256':sha(P),'official_source_locator':f"pdf_page={r['page']};pypdf_line={r['line']}",'official_all_roster_key_count':int(ac[r['key']]),'selected_key_count':len(matches),'independent_poppler_count_match':bool(hits),'independent_poppler_raw_line':hits[0] if hits else '', 'mapping_status':'unique_typed_region_key_pending_binding_scope_review' if unique else 'homonym_or_unmatched_hold','selection_applied':False}
 if unique:
  q=matches.iloc[0];base.update(old_source_record_id=q.source_record_id,old_population=q.population,old_quality=q.population_value_quality,old_source_file=q.source_file,old_source_sheet=q.source_sheet,old_source_row=q.source_row,old_district_raw=q.district_raw,official_minus_old_delta=int(r['population'])-int(q.population),old_population_preserved=True)
 rows.append(base)
q=pd.DataFrame(rows);q.to_csv(O/'explicit_primary_and_old_selected_mapping.csv.gz',index=False,compression='gzip')
unknown=u.copy();unknown['official_source_record_id']=unknown.apply(lambda r:f"LEN2010:PETROSTAT:P{r['page']:03d}:L{r['line']:03d}",axis=1);unknown.to_csv(O/'named_presence_only_unknown.csv.gz',index=False,compression='gzip')
protected=q[q.old_quality.fillna('').str.startswith('secondary_confidentiality')]
reviewed=q[q.old_quality.fillna('').isin(['reviewed_primary_reported_value','direct_official_city_value'])]
controls=read('leningrad_2010_group_controls.csv'); vals=v[v.settlement_group_source_label.isna()]
region_total=int(controls[controls.control_kind=='settlement_group_total'].population.sum()+vals.population.sum())
summary={'status':'source_supplement_and_mapping_candidates_no_selected_mutation','inputs':{str(S):sha(S),str(P):sha(P)},'source_pages':159,'explicit_rows':len(v),'explicit_population':int(v.population.sum()),'presence_only_rows_population_null':len(u),'source_disjoint_group_plus_ungrouped_population':region_total,'expected_official_region_population':1716868,'source_controls_match':region_total==1716868,'unallocated_population_for_presence_only':1716868-int(v.population.sum()),'independent_poppler_explicit_count_matches':int(q.independent_poppler_count_match.sum()),'unique_typed_region_binding_candidates':int((q.mapping_status=='unique_typed_region_key_pending_binding_scope_review').sum()),'protected_candidates':len(protected),'protected_old_sum':int(protected.old_population.sum()),'protected_primary_sum':int(protected.population.sum()),'protected_candidate_delta_unapplied':int(protected.official_minus_old_delta.sum()),'protected_abs_delta_le10':int((protected.official_minus_old_delta.abs()<=10).sum()),'protected_abs_delta_gt10':int((protected.official_minus_old_delta.abs()>10).sum()),'existing_primary_unique_candidates':len(reviewed),'existing_primary_population_mismatches':int((reviewed.official_minus_old_delta!=0).sum()),'no_gain_claim':True,'har_yaginsky':{'source_file':'/workspace/settlements-work/sources/r2-missing/arkhangelsk_2010_archived_original.html','source_sha256':'729fecf5845bd9f1e049c85b2659bfd077dfd2d2a01fecbc9d21cb83b7b9e486','physical_tr_one_based':4366,'selected_locator_zero_based':4365,'raw_label':'посёлок Харьягинский','raw_population_token':'-','interpretation':'NULL preserved; no exact count established'},'holds':'All mapping candidates require binding/scope review. Homonym count includes named under100 rows. No aggregate residual allocated. Source names absent from selected are not automatically omitted localities.'}
# Compact all parser outputs losslessly, preserving source manifest uncompressed hash pins.
for f in D.iterdir():
 if f.suffix in ['.csv','.txt']:
  with gzip.open(str(f)+'.gz','wb') as z:z.write(f.read_bytes())
  f.unlink()
summary['output_pins']={str(p.relative_to(O)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in O.rglob('*') if p.is_file() and p.name not in ['receipt.json']}
(O/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))

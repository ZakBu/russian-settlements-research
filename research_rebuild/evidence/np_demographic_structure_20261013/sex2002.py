#!/usr/bin/env python3
import argparse,hashlib,json,math,re
from pathlib import Path
import duckdb,xlrd,pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--integrated',default='/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');p.add_argument('--anchors',default='/workspace/scratch/tochno-np-attach-20261013/native_np_frozen_all_attributes.parquet');p.add_argument('--source',default='/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls');p.add_argument('--scratch',default='/workspace/scratch/np-demographic-structure-20261013');a=p.parse_args();S=Path(a.scratch);S.mkdir(parents=True,exist_ok=True)
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def norm(s):return re.sub(r'[^a-zа-я0-9]+',' ',s.casefold().replace('ё','е')).strip()
def count(v):
 try:
  n=float(v)
  return n if math.isfinite(n) and n>=0 and n==int(n) else None
 except (ValueError,TypeError):return None
c=duckdb.connect();data=c.execute("select * from read_parquet(?) where census_year=2002 and population_scope='settlement' and source_record_id like '2002:1_TOM_01_04.xls:0:%'",[a.integrated]).fetch_arrow_table().to_pylist();assert len({r['source_record_id'] for r in data})==len(data)
anchors=c.execute("select source_record_id,root from read_parquet(?) where tochno_frozen__object_level='Населенный пункт'",[a.anchors]).fetch_arrow_table().to_pylist();amap={}
for r in anchors:amap.setdefault(r['root'],[]).append(r['source_record_id'])
sheet=xlrd.open_workbook(a.source).sheet_by_index(0);digest=sha(a.source);claims=[];bindings=[];links=[]
marker=re.compile(r'^(?:[^-]+район\s*[-–—]\s*)?(?:Городское население\s*[-–—]\s*)?(?:г\.|пгт\.?|рп\.?|пос\.|п\.|с\.|д\.|ст-ца|ст\.|аул|х\.|сл\.)\s*(.+)$',re.I)
for r in data:
 excel_row=int(r['source_record_id'].rsplit(':',1)[1]);raw=sheet.row_values(excel_row-1);label=str(raw[0]).strip();m=marker.match(label);label_name=re.sub(r'\s*\(рц\)\s*$','',m.group(1)).strip() if m else ''
 ok=m is not None and norm(label_name)==norm(r['settlement_name']);total,male,female=[count(x) for x in raw[1:4]];ok=ok and ('район -' not in label.casefold() or total==r['population']);balance=total is not None and male is not None and female is not None and total==male+female
 linked=amap.get(r['root'],[]);status=('exact_native_uid_single_np_district_urban_caption_and_total' if re.match(r'[^-]+район\s*[-–—]',label,re.I) else 'exact_native_uid_literal_label') if ok else 'held_source_label_or_aggregate_scope';bindings.append(dict(source_record_id=r['source_record_id'],root=r['root'],source_row_1based=excel_row,source_label=label,integrated_label=r['settlement_name'],binding_status=status,source_total=total,integrated_population=r['population'],source_total_differs_from_integrated_population=total!=r['population'],sex_balance_verified=balance,anchor_count=len(linked)))
 if not ok:continue
 for source_field,index,value in [('male',2,male),('female',3,female)]:
  claims.append(dict(source_record_id=r['source_record_id'],root=r['root'],observation_year=2002,object_scope='NP',structure_kind='sex',source_field=source_field,source_value_raw=str(raw[index]),source_value_numeric=value,usable_value=value if balance else None,value_status='published_count' if balance else 'held_missing_or_sex_total_conflict',unit='Человек',source_dataset_version='VNP2002_official_tom1_table01-04',source_file=a.source,source_sha256=digest,source_sheet=sheet.name,source_row_1based=excel_row,source_column_0based=index,source_locator=f'{sheet.name}!row{excel_row}:col{index}',binding_rule=status,source_total=total,integrated_population=r['population'],source_total_differs_from_integrated_population=total!=r['population'],sex_balance_verified=balance,municipality_allocation=False,changes_existing_population=False,canonical_source_claim=True))
 for anchor in linked:links.append(dict(source_record_id=r['source_record_id'],root=r['root'],anchor_2021_source_record_id=anchor,observation_year=2002,values_are_2021=False,link_rule='existing_integrated_root_no_new_identity_inference'))
for name,rows in [('np_sex_2002_claims',claims),('np_sex_2002_bindings',bindings),('np_sex_2002_anchor_links',links)]:
 out=S/(name+'.parquet');pq.write_table(pa.Table.from_pylist(rows),out,compression='zstd')
assert all(not r['municipality_allocation'] and not r['changes_existing_population'] for r in claims);assert all(r['observation_year']==2002 for r in claims)
receipt=dict(native_source_candidates=len(data),matched_native_np_rows=len(claims)//2,source_label_holds=sum(r['binding_status'].startswith('held') for r in bindings),sex_claims=len(claims),usable_claims=sum(r['usable_value'] is not None for r in claims),linked_2021_anchor_count=len(set(r['anchor_2021_source_record_id'] for r in links)),sex_balance_conflicts=sum(not r['sex_balance_verified'] for r in bindings if not r['binding_status'].startswith('held')),source_total_differences=sum(r['source_total_differs_from_integrated_population'] for r in bindings),inputs={a.source:digest,a.integrated:sha(a.integrated),a.anchors:sha(a.anchors)},outputs={str(f):sha(f) for f in S.glob('np_sex_2002*.parquet')},no_population_replacement=True,source_population_covered=sum(r['source_total'] for r in bindings if not r['binding_status'].startswith('held')))
json.dump(receipt,open(E/'sex2002_receipt.json','w'),ensure_ascii=False,indent=2);print(receipt)

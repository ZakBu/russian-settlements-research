"""Check actual raw attribute equality, unique joins, and immutable census snapshot."""
from pathlib import Path
import hashlib,json,gzip,csv
import pandas as pd
import pyarrow as pa,pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent;OUT=Path('/workspace/scratch/tochno-np-attach-20261013')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(2**20),b''):h.update(x)
 return h.hexdigest()
r=json.loads((HERE/'receipt.json').read_text());final=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');assert sha(final)=='8be41d46b832310fc68bc48c715e71af87e5c525fc7e1c4d7264ce71931a623a'
d=pq.read_table(final,columns=['source_record_id','census_year','root','population','oktmo']).to_pandas();roots=d.set_index('source_record_id').root;n=pd.read_csv(OUT/'native_np_attribute_join.csv.gz');n['frozen_source_dataset_version']='v20251217';n['latest_source_dataset_version']='v20260925';n['context_source_dataset_version']='v20251217';n['latest_row_1based']=n.latest_row_1based.astype('Int64');n.to_csv(OUT/'native_np_attribute_join.csv.gz',index=False);assert len(n)==155414 and n.source_record_id.is_unique and n.frozen_row_1based.is_unique;assert n.latest_row_1based.is_unique;assert n.root.eq(n.source_record_id.map(roots)).all();assert n.attachment_status.str.startswith('verified_native_source_row').all()
checks=[]
for ver,src in [('frozen','/workspace/scratch/tochno-enrichment-20261013/raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'),('latest','/workspace/shared/tochno-20261013/allsettlements_v20260925/data_allsettlements_anon_156_v20260925.parquet')]:
 raw=pq.read_table(src)
 for kind in ['native_np','municipality']:
  t=pq.read_table(OUT/f'{kind}_{ver}_all_attributes.parquet')
  if kind=='native_np':
   meta=n.set_index('source_record_id').loc[t['source_record_id'].to_pylist()].reset_index();meta['source_dataset_version']='v20251217' if ver=='frozen' else 'v20260925'
   for c in meta.columns:
    arr=pa.array(meta[c],from_pandas=True);t=t.set_column(t.column_names.index(c),c,arr) if c in t.column_names else t.append_column(c,arr)
   pq.write_table(t,OUT/f'{kind}_{ver}_all_attributes.parquet',compression='zstd')
  if kind=='municipality':
   for c,value in [('source_dataset_version','v20251217' if ver=='frozen' else 'v20260925'),('source_census_year',2021),('administrative_effective_date_unknown',True)]:
    arr=pa.array([value]*t.num_rows);t=t.set_column(t.column_names.index(c),c,arr) if c in t.column_names else t.append_column(c,arr)
   pq.write_table(t,OUT/f'{kind}_{ver}_all_attributes.parquet',compression='zstd')
  prefix=f'tochno_{ver}__';cols=[prefix+c for c in raw.column_names];actual=t.select(cols).rename_columns(raw.column_names);ids=t[f'{ver}_row_1based'].to_pylist();expected=raw.take(pa.array([int(x)-1 for x in ids],type=pa.int64()));assert actual.equals(expected),f'raw source attribute mismatch {kind} {ver}'
  if kind=='native_np':assert t['root'].to_pylist()==[roots[x] for x in t['source_record_id'].to_pylist()]
  checks.append({'output':f'{kind}_{ver}_all_attributes.parquet','rows':t.num_rows,'raw_attributes':raw.num_columns,'every_raw_value_equal_to_source':True})
br=pd.read_csv(OUT/'native_np_municipality_bridge.csv.gz',dtype={'municipality_oktmo_raw':'string','municipality_oktmo_code8':'string'});assert not br.duplicated(['source_record_id','municipality_role']).any();assert len(br)==155414*3;assert br.root.eq(br.source_record_id.map(roots)).all();assert br.administrative_effective_date_unknown.all() and not br.historical_membership_asserted.any();codes=br.municipality_oktmo_code8.dropna();assert codes.str.fullmatch(r'\d{8}').all()
profile=br.merge(n[['source_record_id','native_source_object_level']],on='source_record_id',validate='many_to_one');profile['population']=profile.source_record_id.map(d.set_index('source_record_id').population);availability=profile.groupby(['native_source_object_level','municipality_role','context_status']).agg(records=('source_record_id','size'),population=('population','sum')).reset_index();availability.to_csv(HERE/'context_availability.csv',index=False);r['context_availability']=availability.to_dict('records')
used=set(br.municipality_frozen_row_1based.dropna().astype(int));mt=pq.read_table(OUT/'municipality_frozen_all_attributes.parquet',columns=['frozen_row_1based']);assert used==set(mt['frozen_row_1based'].to_pylist())
ctx=pd.read_csv(OUT/'all_years_reference2021_context.csv.gz');assert len(ctx)==465929 and ctx.source_record_id.is_unique;assert ctx.root.eq(ctx.source_record_id.map(roots)).all();assert not ctx.historical_membership_asserted.any();assert not ctx.loc[ctx.census_year.ne(2021),'attributes_are_native_to_record'].any()
audit=pd.read_csv(OUT/'native_name_validation.csv.gz');audit['attachment_status']=audit.source_record_id.map(n.set_index('source_record_id').attachment_status);audit.to_csv(OUT/'native_name_validation.csv.gz',index=False)
r['outputs']={f.name:{'path':str(f),'bytes':f.stat().st_size,'sha256':sha(f)} for f in OUT.iterdir() if f.is_file()};(HERE/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
result={'status':'passed','immutable_final_census_sha256':sha(final),'checks':checks,'native_join_unique':True,'context_join_unique':True,'context_rows':len(br),'all_years_context_rows':len(ctx),'administrative_effective_date_unknown':True,'earlier_nationality_not_relabelled_as_native':True};(HERE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))

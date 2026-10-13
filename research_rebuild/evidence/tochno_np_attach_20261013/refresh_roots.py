"""Refresh accepted-root context using final snapshot without recalculating source matches."""
import importlib.util,json,hashlib
from pathlib import Path
import pandas as pd
import collections,re
import pyarrow as pa,pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent;OUT=Path('/workspace/scratch/tochno-np-attach-20261013')
FINAL=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def dump(d,n):d.to_csv(OUT/(n+'.csv.gz'),index=False,compression={'method':'gzip','compresslevel':1,'mtime':0})
d=pq.read_table(FINAL,columns=['source_record_id','census_year','root','population','is_additive_settlement_record']).to_pandas();roots=d.set_index('source_record_id').root
n=pd.read_csv(OUT/'native_np_attribute_join.csv.gz');n['root']=n.source_record_id.map(roots)
sourcecols=['object_level','object_name','oktmo','region','mun_upper','mun_lower','population'];oldpath='/workspace/scratch/tochno-enrichment-20261013/raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet';newpath='/workspace/shared/tochno-20261013/allsettlements_v20260925/data_allsettlements_anon_156_v20260925.parquet';a=pq.read_table(oldpath,columns=sourcecols).to_pandas();b=pq.read_table(newpath,columns=sourcecols).to_pandas();version=pd.read_csv(OUT/'source_version_bridge.csv.gz')
def code_key(df):
 width=df.object_level.eq('Населенный пункт').map({True:11,False:8});raw=df.oktmo.fillna('');ok=(width.eq(11)&raw.str.fullmatch(r'\d{10,11}'))|(width.eq(8)&raw.str.fullmatch(r'\d{7,8}'))
 return pd.Series([v.zfill(int(w)) if good else None for v,w,good in zip(raw,width,ok)],index=df.index)
aa=a.assign(code_key=code_key(a),frozen_row_1based=a.index+1);bb=b.assign(code_key=code_key(b),latest_row_1based=b.index+1)
for frame in [aa,bb]:frame['unique_code']=~frame.duplicated(['object_level','code_key'],keep=False)&frame.code_key.notna()
kk=['object_level','code_key','region','object_name','population'];matches=aa[aa.unique_code].merge(bb[bb.unique_code],on=kk,suffixes=('_frozen','_latest'),validate='one_to_one')
lookup=matches.set_index('frozen_row_1based');mapped=version.frozen_row_1based.map(lookup.latest_row_1based);mask=version.latest_row_1based.isna()&mapped.notna();version.loc[mask,'latest_row_1based']=mapped[mask]
version.loc[mask,'source_version_rule']='unique_source_code_padding_region_objectname_population';changed=(lookup.mun_upper_frozen.fillna('')!=lookup.mun_upper_latest.fillna(''))|(lookup.mun_lower_frozen.fillna('')!=lookup.mun_lower_latest.fillna(''));version.loc[mask,'administrative_context_changed']=version.loc[mask,'frozen_row_1based'].map(changed).fillna(False)
version['source_version_rule']=version.source_version_rule.replace('unique_raw11digit_code_region_objectname_population','unique_np_code11_padding_region_objectname_population');dump(version,'source_version_bridge')
n=n.drop(columns=['latest_row_1based','version_match_status','source_version_rule','administrative_context_changed']).merge(version,on='frozen_row_1based',validate='one_to_one');n['attachment_status']='verified_native_source_row';n.loc[n.frozen_row_1based.isin([81591,81604]),'attachment_status']='verified_native_source_row_known_parser_artifact';n['source_dataset_version']='v20251217';n['source_census_year']=2021;n['administrative_effective_date_unknown']=True;dump(n,'native_np_attribute_join')
audit=pd.read_csv(OUT/'native_name_validation.csv.gz');audit['attachment_status']=audit.source_record_id.map(n.set_index('source_record_id').attachment_status);dump(audit,'native_name_validation')
br=pd.read_csv(OUT/'native_np_municipality_bridge.csv.gz',dtype={'municipality_oktmo_raw':'string'});br['root']=br.source_record_id.map(roots)
ar=list(a.itertuples(index=False));ri=collections.defaultdict(list)
for j,r in enumerate(a.itertuples()):
 if r.object_level=='Регион' and r.object_name==r.region:ri[r.region].append(j)
extra=[]
for r in n.itertuples():
 raw=ar[r.frozen_row_1based-1];hits=ri.get(raw.region,[]);role='region'
 if raw.object_level=='Город федерального значения':hits=[r.frozen_row_1based-1];role='federal_territory_context'
 status='exact_unique_source_context' if len(hits)==1 else ('ambiguous_source_context' if hits else 'no_exact_source_region');m=ar[hits[0]] if len(hits)==1 else None
 extra.append(dict(source_record_id=r.source_record_id,root=r.root,np_frozen_row_1based=r.frozen_row_1based,municipality_role=role,municipality_label_raw=raw.region,municipality_frozen_row_1based=hits[0]+1 if m is not None else None,municipality_oktmo_raw=m.oktmo if m is not None else None,municipality_object_level=m.object_level if m is not None else None,context_status=status,reference_year=2021,historical_membership_asserted=False,administrative_effective_date_unknown=True,source_census_year=2021,source_dataset_version='v20251217'))
# Recover upper/lower context for the four corrected native-label validations.
ui=collections.defaultdict(list);li=collections.defaultdict(list)
for j,r in enumerate(a.itertuples()):
 if r.object_level=='Муниципалитет верхнего уровня':ui[(r.region,r.object_name)].append(j)
 if r.object_level=='Муниципалитет нижнего уровня':li[(r.region,r.mun_upper,r.object_name)].append(j)
missing=n[~n.source_record_id.isin(br.source_record_id)]
for r in missing.itertuples():
 raw=ar[r.frozen_row_1based-1]
 for role,ix,k,label in [('upper',ui,(raw.region,raw.mun_upper),raw.mun_upper),('lower',li,(raw.region,raw.mun_upper,raw.mun_lower),raw.mun_lower)]:
  hits=ix.get(k,[]);m=ar[hits[0]] if len(hits)==1 else None;status='exact_unique_source_context' if len(hits)==1 else ('ambiguous_source_context' if hits else 'no_exact_source_municipality')
  extra.append(dict(source_record_id=r.source_record_id,root=r.root,np_frozen_row_1based=r.frozen_row_1based,municipality_role=role,municipality_label_raw=label,municipality_frozen_row_1based=hits[0]+1 if m is not None else None,municipality_oktmo_raw=m.oktmo if m is not None else None,municipality_object_level=m.object_level if m is not None else None,context_status=status,reference_year=2021,historical_membership_asserted=False,administrative_effective_date_unknown=True,source_census_year=2021,source_dataset_version='v20251217'))
br=pd.concat([br,pd.DataFrame(extra)],ignore_index=True);br=br.drop_duplicates(['source_record_id','municipality_role'],keep='last');br['municipality_oktmo_code8']=br.municipality_oktmo_raw.map(lambda v:str(v).zfill(8) if pd.notna(v) and re.fullmatch(r'\d{7,8}',str(v)) else None);dump(br,'native_np_municipality_bridge')
for file in ['native_np_frozen_all_attributes.parquet']:
 t=pq.read_table(OUT/file);ids=t['source_record_id'].to_pylist();meta=n.set_index('source_record_id').loc[ids].reset_index()
 for c in meta.columns:
  arr=pa.array(meta[c],from_pandas=True);t=t.set_column(t.column_names.index(c),c,arr) if c in t.column_names else t.append_column(c,arr)
 pq.write_table(t,OUT/file,compression='zstd')
valid=n[n.attachment_status.str.startswith('verified_native_source_row')];latest=valid[valid.latest_row_1based.notna()];newsource=pq.read_table(newpath);raw=newsource.take(pa.array((latest.latest_row_1based.astype(int)-1).tolist(),type=pa.int64())).rename_columns(['tochno_latest__'+c for c in newsource.column_names]);out=pa.Table.from_pandas(latest,preserve_index=False)
for col in raw.column_names:out=out.append_column(col,raw[col])
pq.write_table(out,OUT/'native_np_latest_all_attributes.parquet',compression='zstd')
counts=valid.groupby('root').size();u=valid[valid.root.map(counts).eq(1)]
ctx=d.merge(u[['root','source_record_id','frozen_row_1based','latest_row_1based']].rename(columns={'source_record_id':'reference_2021_source_record_id'}),on='root',how='left',validate='many_to_one');ctx['context_reference_year']=2021;ctx['attributes_are_native_to_record']=ctx.census_year.eq(2021);ctx['historical_membership_asserted']=False;ctx['administrative_effective_date_unknown']=True;ctx['source_dataset_version']='v20251217';ctx['source_census_year']=2021;ctx['context_status']=ctx.reference_2021_source_record_id.notna().map({True:'accepted_root_reference_2021',False:'no_unique_verified_2021_anchor'})
dump(ctx.drop(columns=['population','is_additive_settlement_record']),'all_years_reference2021_context')
receipt=json.loads((HERE/'receipt.json').read_text());receipt['original_root_snapshot_inputs']=receipt['inputs'];receipt['inputs'].pop('/workspace/scratch/residual-round2-20261013/final/integrated_spatial_temporal_records.parquet',None);receipt['inputs'][str(FINAL)]=sha(FINAL);receipt['root_context_refreshed_without_source_rematching']=True
coverage=[]
for y,g in ctx.groupby('census_year'):
 for kind,mask in [('all_records',pd.Series(True,index=g.index)),('reference2021_available',g.reference_2021_source_record_id.notna()),('latest_reference_available',g.latest_row_1based.notna())]:
  q=g[mask];coverage.append(dict(census_year=int(y),scope=kind,records=len(q),population=float(q.population.sum()),additive_records=int(q.is_additive_settlement_record.sum())))
receipt['verified_native_rows']=len(valid);receipt['held_name_rows']=0;receipt['known_native_parser_artifacts']=[81591,81604];receipt['coverage']=coverage;receipt['latest_attached_native_rows']=len(latest);receipt['source_version_rules']=version.source_version_rule.value_counts().to_dict();receipt['municipality_context_status']=br.groupby(['municipality_role','context_status']).size().reset_index(name='rows').to_dict('records');receipt['municipality_raw_code_lengths']=br.municipality_oktmo_raw.dropna().str.len().value_counts().to_dict()
# Profile denominators exclude the three federal-city aggregate source rows.
p=pd.read_csv(HERE/'attribute_availability.csv');old=pq.read_table('/workspace/scratch/tochno-enrichment-20261013/raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');new=pq.read_table('/workspace/shared/tochno-20261013/allsettlements_v20260925/data_allsettlements_anon_156_v20260925.parquet');import pyarrow.compute as pc
for v,t in [('frozen',old),('latest',new)]:
 q=valid[valid.native_source_object_level.eq('Населенный пункт')].copy();col='frozen_row_1based' if v=='frozen' else 'latest_row_1based';q=q[q[col].notna()];at=t.take(pa.array((q[col].astype(int)-1).tolist(),type=pa.int64()))
 for c in at.column_names:
  arr=at[c];idx=p.source_version.eq(v)&p.attribute.eq(c);p.loc[idx,'attached_np_rows']=at.num_rows;p.loc[idx,'null']=arr.null_count;p.loc[idx,'nonnull']=at.num_rows-arr.null_count
  if pa.types.is_integer(arr.type) or pa.types.is_floating(arr.type):
   p.loc[idx,'suppressed_minus9']=pc.sum(pc.cast(pc.equal(arr,-9),pa.int64())).as_py();p.loc[idx,'explicit_zero']=pc.sum(pc.cast(pc.equal(arr,0),pa.int64())).as_py()
  available=pc.is_valid(arr);observed=pc.and_(available,pc.fill_null(pc.not_equal(arr,-9),False)) if pa.types.is_integer(arr.type) or pa.types.is_floating(arr.type) else available
  p.loc[idx,'attached_np_reference_population']=pc.sum(at['population']).as_py();p.loc[idx,'nonnull_reference_population']=pc.sum(pc.filter(at['population'],available)).as_py();p.loc[idx,'unsuppressed_reference_population']=pc.sum(pc.filter(at['population'],observed)).as_py()
p.to_csv(HERE/'attribute_availability.csv',index=False)
# Add every accepted context source object, including region/federal rows, as raw secondary attrs.
used=sorted(set(br.municipality_frozen_row_1based.dropna().astype(int)));mm=version[version.frozen_row_1based.isin(used)].copy();mm['reference_year']=2021;mm['administrative_effective_date_unknown']=True
for vv,t,c,prefix,file in [('frozen',old,'frozen_row_1based','tochno_frozen__','municipality_frozen_all_attributes.parquet'),('latest',new,'latest_row_1based','tochno_latest__','municipality_latest_all_attributes.parquet')]:
 q=mm[mm[c].notna()];raw=t.take(pa.array((q[c].astype(int)-1).tolist(),type=pa.int64())).rename_columns([prefix+x for x in t.column_names]);out=pa.Table.from_pandas(q,preserve_index=False)
 for col in raw.column_names:out=out.append_column(col,raw[col])
 pq.write_table(out,OUT/file,compression='zstd')
receipt['outputs']={f.name:{'path':str(f),'bytes':f.stat().st_size,'sha256':sha(f)} for f in OUT.iterdir() if f.is_file()};(HERE/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(coverage,ensure_ascii=False))

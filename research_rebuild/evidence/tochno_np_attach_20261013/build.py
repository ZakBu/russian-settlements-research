"""Immutable source attributes and reference-2021 context; never edits census values."""
from pathlib import Path
import hashlib,json,re,unicodedata,collections
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent
OUT=Path('/workspace/scratch/tochno-np-attach-20261013');OUT.mkdir(exist_ok=True,parents=True)
INP=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
OLD=Path('/workspace/scratch/tochno-enrichment-20261013/raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
NEW=Path('/workspace/shared/tochno-20261013/allsettlements_v20260925/data_allsettlements_anon_156_v20260925.parquet')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def norm(v):return ' '.join(unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е').split())
def dump(d,n):d.to_csv(OUT/(n+'.csv.gz'),index=False,compression={'method':'gzip','compresslevel':1,'mtime':0})
def keys(d):
 cols=['object_level','oktmo','region','mun_upper','mun_lower','object_name','population']
 # Every string is the raw value; no speculative changed-name alias.
 return [tuple(None if pd.isna(v) else v for v in r) for r in d[cols].itertuples(index=False,name=None)]
def index_unique(ks):
 ix=collections.defaultdict(list)
 for i,k in enumerate(ks):ix[k].append(i)
 return ix
hashes={str(p):sha(p) for p in [INP,OLD,NEW]}
old=pq.read_table(OLD);new=pq.read_table(NEW)
cols=['object_level','object_name','oktmo','region','mun_upper','mun_lower','settlement','population']
a=old.select(cols).to_pandas();b=new.select(cols).to_pandas()
d=pq.read_table(INP,columns=['source_record_id','census_year','root','settlement_name','settlement_type','oktmo','population','is_additive_settlement_record','finite_ordinary_full3_all_ownpoints']).to_pandas()
n=d[d.census_year.eq(2021)].copy();n['frozen_row_1based']=n.source_record_id.str.extract(r'^2021:data_allsettlements_anon_156_v20251217\.parquet:parquet:(\d+)$')[0].astype(int)
assert n.source_record_id.is_unique and n.frozen_row_1based.is_unique
s=a.iloc[n.frozen_row_1based-1].reset_index(drop=True);n=n.reset_index(drop=True)
assert s.object_level.isin(['Населенный пункт','Город федерального значения']).all()
n['native_source_object_level']=s.object_level
assert n.population.eq(s.population).all() and n.oktmo.fillna('').eq(s.oktmo.fillna('')).all()
namechecks=[]
for x,y in zip(n.settlement_name,s.object_name):
 z=norm(x);raw=norm(y)
 pos=raw.rfind(z) if z else -1
 namechecks.append(pos>=0 and (pos==0 or not raw[pos-1].isalnum()) and (pos+len(z)==len(raw) or not raw[pos+len(z)].isalnum()))
n['name_validation']=namechecks
n['known_native_parser_artifact']=n.frozen_row_1based.isin([81591,81604])
assert s.loc[n.frozen_row_1based.eq(81591),'object_name'].iloc[0]=='дачный посёлок Кудряшовский'
assert s.loc[n.frozen_row_1based.eq(81604),'object_name'].iloc[0]=='дачный посёлок Мочище'
# Source-row provenance, population and code are exact. Name discrepancies are held.
n['attachment_status']=n.name_validation.map({True:'verified_native_source_row',False:'held_name_discrepancy'})
n.loc[n.known_native_parser_artifact,'attachment_status']='verified_native_source_row_known_parser_artifact'
dump(pd.concat([n[['source_record_id','settlement_name','settlement_type','attachment_status']],s[['object_name']]],axis=1),'native_name_validation')
oldks=keys(a);newks=keys(b);oi=index_unique(oldks);ni=index_unique(newks)
allmap=[]
for i,k in enumerate(oldks):
 hits=ni.get(k,[])
 status='exact_unique_raw_signature' if len(hits)==1 and len(oi[k])==1 else ('ambiguous_signature' if len(hits)>1 or len(oi[k])>1 else 'no_unchanged_signature')
 allmap.append((i+1,hits[0]+1 if status=='exact_unique_raw_signature' else None,status))
version=pd.DataFrame(allmap,columns=['frozen_row_1based','latest_row_1based','version_match_status'])
dump(version,'source_version_bridge')
# Second rule: changed parent labels cannot alone defeat identical unique NP identity.
codeold=collections.Counter(a.loc[a.object_level.eq('Населенный пункт'),'oktmo']);codenew=collections.Counter(b.loc[b.object_level.eq('Населенный пункт'),'oktmo'])
def relaxed_keys(df):
 return [(r.object_level,r.oktmo,r.region,r.object_name,r.population) for r in df.itertuples()]
rko=relaxed_keys(a);rkn=relaxed_keys(b);rix=index_unique(rkn)
version['source_version_rule']=version.version_match_status.map({'exact_unique_raw_signature':'exact_unique_full_raw_signature','ambiguous_signature':'held_ambiguous','no_unchanged_signature':'held_changed_or_missing'})
version['administrative_context_changed']=False
for i in version.index[version.latest_row_1based.isna()]:
 r=a.iloc[i];code=r.oktmo
 if r.object_level!='Населенный пункт' or not isinstance(code,str) or not re.fullmatch(r'\d{10,11}',code) or codeold[code]!=1 or codenew[code]!=1:continue
 hits=rix.get(rko[i],[])
 if len(hits)!=1:continue
 j=hits[0];version.loc[i,'latest_row_1based']=j+1;version.loc[i,'source_version_rule']='unique_raw_np_code_region_objectname_population';version.loc[i,'administrative_context_changed']=(r.mun_upper!=b.iloc[j].mun_upper or r.mun_lower!=b.iloc[j].mun_lower)
dump(version,'source_version_bridge')
n=n.merge(version,on='frozen_row_1based',validate='one_to_one');n.loc[~n.name_validation&~n.known_native_parser_artifact,'latest_row_1based']=None
n['reference_year']=2021
n['source_dataset_version']='v20251217'
n['source_census_year']=2021
n['administrative_effective_date_unknown']=True
joincols=['source_record_id','root','frozen_row_1based','latest_row_1based','attachment_status','version_match_status','source_version_rule','administrative_context_changed','reference_year','native_source_object_level','source_dataset_version','source_census_year','administrative_effective_date_unknown']
dump(n[joincols],'native_np_attribute_join')
valid=n[n.name_validation|n.known_native_parser_artifact].copy()
# Arrow keeps all raw source columns/types, including -9 suppression and nulls.
def wide(tbl,rows,prefix,meta,path):
 if path=='native_np_frozen_all_attributes.parquet' and (OUT/path).exists():return
 raw=tbl.take(pa.array(rows,type=pa.int64()));raw=raw.rename_columns([prefix+c for c in raw.column_names])
 out=pa.Table.from_pandas(meta,preserve_index=False)
 for c in raw.column_names:out=out.append_column(c,raw[c])
 pq.write_table(out,OUT/path,compression='zstd')
wide(old,(valid.frozen_row_1based-1).tolist(),'tochno_frozen__',valid[joincols],'native_np_frozen_all_attributes.parquet')
vnew=valid[valid.latest_row_1based.notna()].copy();wide(new,(vnew.latest_row_1based.astype(int)-1).tolist(),'tochno_latest__',vnew[joincols],'native_np_latest_all_attributes.parquet')
# Municipal levels are actual source levels, not an imposed five-level model.
mun=a[a.object_level.isin(['Муниципалитет верхнего уровня','Муниципалитет нижнего уровня'])].copy();mun['frozen_row_1based']=mun.index+1
upper=index_unique([ (r.region,r.object_name) for r in mun[mun.object_level.eq('Муниципалитет верхнего уровня')].itertuples() ])
# Store row ids explicitly rather than dataframe positional indices.
def municipal_index(level):
 ix=collections.defaultdict(list)
 for r in mun[mun.object_level.eq(level)].itertuples():
  k=(r.region,r.object_name) if level.endswith('верхнего уровня') else (r.region,r.mun_upper,r.object_name)
  ix[k].append(r.Index)
 return ix
ui=municipal_index('Муниципалитет верхнего уровня');li=municipal_index('Муниципалитет нижнего уровня')
bridge=[]
arows=list(a.itertuples(index=False))
for r in valid.itertuples():
 raw=arows[r.frozen_row_1based-1]
 for role,field,ix,k in [('upper','mun_upper',ui,(raw.region,raw.mun_upper)),('lower','mun_lower',li,(raw.region,raw.mun_upper,raw.mun_lower))]:
  label=getattr(raw,field);hits=[] if pd.isna(label) else ix.get(k,[])
  status='missing_source_context' if pd.isna(label) else ('exact_unique_source_context' if len(hits)==1 else ('ambiguous_source_context' if hits else 'no_exact_source_municipality'))
  m=arows[hits[0]] if len(hits)==1 else None
  bridge.append(dict(source_record_id=r.source_record_id,root=r.root,np_frozen_row_1based=r.frozen_row_1based,municipality_role=role,municipality_label_raw=label,municipality_frozen_row_1based=hits[0]+1 if m is not None else None,municipality_oktmo_raw=m.oktmo if m is not None else None,municipality_oktmo_code8=str(m.oktmo).zfill(8) if m is not None and re.fullmatch(r'\d{7,8}',str(m.oktmo)) else None,municipality_object_level=m.object_level if m is not None else None,context_status=status,reference_year=2021,historical_membership_asserted=False,administrative_effective_date_unknown=True,source_census_year=2021,source_dataset_version='v20251217'))
br=pd.DataFrame(bridge);dump(br,'native_np_municipality_bridge')
used=sorted(set(br.municipality_frozen_row_1based.dropna().astype(int)));mm=version[version.frozen_row_1based.isin(used)].copy();mm['reference_year']=2021
wide(old,(mm.frozen_row_1based-1).tolist(),'tochno_frozen__',mm,'municipality_frozen_all_attributes.parquet')
mmn=mm[mm.latest_row_1based.notna()].copy();wide(new,(mmn.latest_row_1based.astype(int)-1).tolist(),'tochno_latest__',mmn,'municipality_latest_all_attributes.parquet')
# Other years reference the unique native anchor in their already accepted root.
rootcounts=valid.groupby('root').size();unique=valid[valid.root.map(rootcounts).eq(1)]
ctx=d.merge(unique[['root','source_record_id','frozen_row_1based','latest_row_1based']].rename(columns={'source_record_id':'reference_2021_source_record_id'}),on='root',how='left',validate='many_to_one')
ctx['context_reference_year']=2021;ctx['historical_membership_asserted']=False;ctx['attributes_are_native_to_record']=ctx.census_year.eq(2021)
ctx['context_status']=ctx.reference_2021_source_record_id.notna().map({True:'accepted_root_reference_2021',False:'no_unique_verified_2021_anchor'})
dump(ctx[['source_record_id','census_year','root','reference_2021_source_record_id','frozen_row_1based','latest_row_1based','context_reference_year','attributes_are_native_to_record','historical_membership_asserted','context_status']],'all_years_reference2021_context')
# Actual availability of every raw attribute, by source level and among attached NPs.
profiles=[]
for label,tbl,ids in [('frozen',old,valid.loc[valid.native_source_object_level.eq('Населенный пункт'),'frozen_row_1based']-1),('latest',new,vnew.loc[vnew.native_source_object_level.eq('Населенный пункт'),'latest_row_1based'].astype(int)-1)]:
 at=tbl.take(pa.array(ids.tolist(),type=pa.int64()))
 for col in at.column_names:
  arr=at[col];supp=zero=None
  if pa.types.is_integer(arr.type) or pa.types.is_floating(arr.type):
   import pyarrow.compute as pc
   supp=pc.sum(pc.cast(pc.equal(arr,-9),pa.int64())).as_py();zero=pc.sum(pc.cast(pc.equal(arr,0),pa.int64())).as_py()
  import pyarrow.compute as pc
  available=pc.is_valid(arr)
  observed=pc.and_(available,pc.fill_null(pc.not_equal(arr,-9),False)) if supp is not None else available
  profiles.append(dict(source_version=label,attribute=col,attached_np_rows=at.num_rows,nonnull=at.num_rows-arr.null_count,null=arr.null_count,suppressed_minus9=supp,explicit_zero=zero,attached_np_reference_population=pc.sum(at['population']).as_py(),nonnull_reference_population=pc.sum(pc.filter(at['population'],available)).as_py(),unsuppressed_reference_population=pc.sum(pc.filter(at['population'],observed)).as_py()))
pd.DataFrame(profiles).to_csv(HERE/'attribute_availability.csv',index=False)
npold=a[a.object_level.eq('Населенный пункт')];missing=npold[~(npold.index+1).isin(n.frozen_row_1based)].copy();missing['frozen_row_1based']=missing.index+1;dump(missing,'source_np_not_in_integrated')
coverage=[]
for year,g in ctx.groupby('census_year'):
 for kind,mask in [('all_records',pd.Series(True,index=g.index)),('reference2021_available',g.reference_2021_source_record_id.notna()),('latest_reference_available',g.latest_row_1based.notna())]:
  q=g[mask];coverage.append(dict(census_year=int(year),scope=kind,records=len(q),population=float(q.population.sum()),additive_records=int(q.is_additive_settlement_record.sum())))
receipt=dict(inputs=hashes,source_rows={'frozen':old.num_rows,'latest':new.num_rows},attributes={'frozen':old.num_columns,'latest':new.num_columns},source_levels_frozen=a.object_level.value_counts().to_dict(),source_levels_latest=b.object_level.value_counts().to_dict(),native_2021_rows=len(n),native_actual_np_rows=int(n.native_source_object_level.eq('Населенный пункт').sum()),verified_native_rows=len(valid),held_name_rows=int((~n.name_validation&~n.known_native_parser_artifact).sum()),latest_attached_native_rows=len(vnew),source_np_total=len(npold),source_np_not_integrated=len(missing),source_np_not_integrated_population=int(missing.population.sum()),version_status=version.version_match_status.value_counts().to_dict(),source_version_rules=version.source_version_rule.value_counts().to_dict(),municipality_context_status=br.groupby(['municipality_role','context_status']).size().reset_index(name='rows').to_dict('records'),municipality_raw_code_lengths=br.municipality_oktmo_raw.dropna().str.len().value_counts().to_dict(),coverage=coverage,semantics={'nationality_reference_year':2021,'minus9':'suppressed, never zero','nationality_multiple_answers':'never sum categories','new_values_overwrite_census_or_coordinates':False,'historical_membership_asserted':False},outputs={})
for p in OUT.iterdir():
 if p.is_file():receipt['outputs'][p.name]={'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
(HERE/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ['native_2021_rows','verified_native_rows','held_name_rows','latest_attached_native_rows','source_np_not_integrated','version_status','coverage']},ensure_ascii=False))

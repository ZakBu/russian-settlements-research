"""Admit reviewed supplemental native observations without modifying selected data."""
from pathlib import Path
import hashlib,re
import pandas as pd
STANDARD_COLUMNS='source_record_id census_year settlement_name settlement_type name_norm type_norm region_norm district_raw population population_scope is_additive_settlement_record population_value_quality latitude longitude oktmo okato source_file source_path source_sha256 source_locator'.split()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def publication_key(sid,source_hash):
 m=re.fullmatch(r'(2002|2010|2021):(.+):([^:]+):(\d+)',str(sid));assert m,sid
 return int(m[1]),str(source_hash),m[3],int(m[4])
def append_reviewed_source_observations(state,observation_path,metadata_path,*,observation_sha256,metadata_sha256,accepted_metadata_statuses,expected_rows=100,expected_population=9856):
 """All validation precedes mutation; appended observations start as unpointed singletons."""
 op,mp=Path(observation_path),Path(metadata_path);assert sha(op)==observation_sha256 and sha(mp)==metadata_sha256
 rows=pd.read_csv(op,dtype=str,keep_default_na=False);meta=pd.read_csv(mp,dtype=str,keep_default_na=False)
 assert list(rows)==STANDARD_COLUMNS and len(rows)==expected_rows and rows.source_record_id.is_unique
 assert meta.source_record_id.is_unique and set(meta.source_record_id)==set(rows.source_record_id)
 meta=meta.set_index('source_record_id');assert meta.source_grade.eq('secondary_compilation_of_2002_census').all()
 assert meta.source_admission_status.isin(accepted_metadata_statuses).all()
 assert meta.independent_official_primary_locality_count_verified.eq('False').all()
 for flag in ['source_primary_grade','direct_official_primary_locality_value','primary_credit_from_source_alone','own_point_admitted','temporal_identity_admitted']:assert meta[flag].eq('False').all()
 assert not(set(rows.source_record_id)&set(state.obs.source_record_id))
 assert rows.census_year.eq('2002').all() and rows.is_additive_settlement_record.eq('True').all()
 assert rows.population_scope.eq('ordinary_settlement').all() and rows.population_value_quality.eq('verified_count_in_secondary_census_compilation').all()
 assert rows.latitude.eq('').all() and rows.longitude.eq('').all()
 rows.census_year=pd.to_numeric(rows.census_year).astype(int);rows.population=pd.to_numeric(rows.population)
 assert rows.population.ge(0).all() and rows.population.sum()==expected_population
 keys=set();baseline_hash_cache={}
 for native in state.obs[state.obs.census_year.eq(2002)].itertuples(index=False):
  h=native.source_sha256
  if pd.isna(h) or not str(h):
   q=Path(str(native.source_path)) if pd.notna(native.source_path) and str(native.source_path) else Path('/workspace/settlements-raw')/native.source_file
   if str(q) not in baseline_hash_cache:baseline_hash_cache[str(q)]=sha(q)
   h=baseline_hash_cache[str(q)]
  # Different source bytes cannot be the same publication row. Official-source namespaces
  # (e.g. ROSSTAT2002:T1:T4:...) have independent IDs and must retain their native syntax.
  if str(h) in set(rows.source_sha256):keys.add(publication_key(native.source_record_id,h))
 newkeys=[publication_key(sid,h) for sid,h in zip(rows.source_record_id,rows.source_sha256)]
 assert len(set(newkeys))==len(rows) and not(keys&set(newkeys)),'publication-row overlap'
 pins={}
 for sid,row in rows.set_index('source_record_id').iterrows():
  p=Path(row.source_path)
  if str(p) not in pins:pins[str(p)]=sha(p)
  assert pins[str(p)]==row.source_sha256
  k=publication_key(sid,row.source_sha256);assert k[2]==meta.loc[sid,'source_sheet'] and k[3]==int(meta.loc[sid,'source_row'])
 rows.is_additive_settlement_record=True
 for col in ['latitude','longitude']:rows[col]=float('nan')
 rows['root']=rows.source_record_id
 before=len(state.obs);oldpointkeys=set(state.point_rows);oldparents=dict(state.uf.parent)
 # Preserve admission grade and source metadata in a separate supplement; core schema stays stable.
 state.obs=pd.concat([state.obs,rows],ignore_index=True)
 for sid in rows.source_record_id:state.uf.parent[sid]=sid;state.years[sid]={2002}
 state.by_id=state.obs.set_index('source_record_id',drop=False)
 state.inputs.extend([op,mp]);state.supplemental_source_metadata=pd.concat([getattr(state,'supplemental_source_metadata',pd.DataFrame()),meta.reset_index()],ignore_index=True)
 assert len(state.obs)==before+expected_rows and state.obs.source_record_id.is_unique
 assert oldpointkeys==set(state.point_rows) and all(state.uf.parent[sid]==r for sid,r in oldparents.items())
 assert all(state.uf.find(sid)==sid and state.years[sid]=={2002} and sid not in state.point_rows for sid in rows.source_record_id)
 return {'status':'reviewed_secondary_source_observations_appended_as_unpointed_singletons','rows':len(rows),'source_population':int(rows.population.sum()),'source_IDs':rows.source_record_id.tolist(),'automatic_primary_credit':0,'original_selected_bytes_modified':False,'publication_row_overlap':0,'source_pins':pins}
def apply_reviewed_parent_grain(state,delta_path,*,delta_sha256,accepted_statuses,baseline_credited_IDs):
 """Retain raw parent544 count; classify source subtotal as nonadditive."""
 p=Path(delta_path);assert sha(p)==delta_sha256;d=pd.read_csv(p,dtype=str,keep_default_na=False);assert len(d)==1
 row=d.iloc[0];sid=row.source_record_id;child=row.bound_ordinary_child_source_record_id
 assert row.interpretation_status in accepted_statuses and row.source_count_changed=='False'
 native=state.by_id.loc[sid];assert int(native.census_year)==2002 and float(native.population)==float(row.population_original)==float(row.population_proposed)==544
 assert bool(native.is_additive_settlement_record) and row.is_additive_settlement_record_proposed=='False'
 assert native.source_file==row.source_file
 native_hash=native.source_sha256
 if pd.notna(native_hash) and str(native_hash):assert native_hash==row.source_hash
 native_path=native.source_path
 rawpath=Path(str(native_path)) if pd.notna(native_path) and str(native_path) else Path('/workspace/settlements-raw')/row.source_file
 assert sha(rawpath)==row.source_hash
 # Baseline selected provenance can be blank; evidence pointer stays in this interpretation layer.

 assert sid not in baseline_credited_IDs and sid not in state.point_rows and child not in state.point_rows
 assert state.uf.find(sid)==sid and state.years[sid]=={2002} and state.uf.find(child)==child and state.years[child]=={2002}
 index=state.obs.index[state.obs.source_record_id.eq(sid)];assert len(index)==1
 state.obs.loc[index,'is_additive_settlement_record']=False;state.obs.loc[index,'population_scope']=row.population_scope_proposed
 state.by_id=state.obs.set_index('source_record_id',drop=False);state.inputs.append(p)
 return {'status':'reviewed_source_parent_subtotal_nonadditive_interpretation','source_record_id':sid,'raw_population_retained':544,'additive_population_delta':-544,'primary_credit_delta':0,'UF_or_point_mutation':False,'interpretation_source_path':str(rawpath),'interpretation_source_sha256':row.source_hash,'baseline_source_provenance_fields_unchanged':True}

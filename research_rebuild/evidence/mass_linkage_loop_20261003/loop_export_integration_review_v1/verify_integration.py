#!/usr/bin/env python3
"""Data-only final export integration check against frozen R4 artifacts."""
from pathlib import Path
import csv,gzip,hashlib,json,math,re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pandas.testing import assert_frame_equal
import sys
sys.path.insert(0,'/workspace/russian-settlements-research')
from research_rebuild.mass_linkage.coverage import measure
C=Path('/workspace/settlements-work/continuation_20261003'); E=Path('/workspace/settlements-delivery/continuation-loop-20261003'); OUT=C/'loop_export_integration_review_v1'
MAN=E/'settlements_long.manifest.json'; TBL=E/'settlements_long.parquet'; CSV=E/'settlements_long.csv.gz'; COV=E/'coverage.json'
FROZEN={
 'census':C/'urban_primary_population_application_v1/selected_observations.parquet',
 'points':C/'accepted_geonames_graph_point_reuse_delta_v1/accepted_point_uses.parquet',
 'identity':C/'urban_primary_population_application_v1/accepted_identity_edges.parquet',
 'source_evidence':C/'urban_primary_source_context_annotations_v1/source_evidence.parquet',
 'legacy_quality':C/'urban_primary_coverage_inputs_v1/legacy_availability_projected_r4.parquet',
 'cumulative_bindings':C/'urban_primary_coverage_inputs_v1/cumulative_publication_bindings.parquet',
 'wiki':E/'wiki_literal_associations.parquet',
 'annual':E/'annual_official_observations.parquet',
 'source_manifest':E/'input_manifest.parquet',
}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def eq(a,b,what):
 try: assert_frame_equal(a.reset_index(drop=True),b.reset_index(drop=True),check_dtype=False,check_like=False)
 except Exception as e: raise AssertionError(what+': '+str(e)) from e
def str_eq(a,b):
 aa=pd.Series(a,dtype='object').where(pd.notna(a),'') if not isinstance(a,pd.Series) else a.astype('object').where(a.notna(),'')
 bb=pd.Series(b,dtype='object').where(pd.notna(b),'') if not isinstance(b,pd.Series) else b.astype('object').where(b.notna(),'')
 return aa.fillna('').astype(str).reset_index(drop=True).equals(bb.fillna('').astype(str).reset_index(drop=True))
def close_num(a,b):
 aa=pd.to_numeric(pd.Series(a),errors='coerce').to_numpy(dtype=float);bb=pd.to_numeric(pd.Series(b),errors='coerce').to_numpy(dtype=float)
 return bool(np.allclose(aa,bb,rtol=0,atol=1e-12,equal_nan=True))
def recurse_compare(a,b,path='root',tol=1e-12):
 if isinstance(a,dict) and isinstance(b,dict):
  if set(a)!=set(b):raise AssertionError(f'coverage keys mismatch at {path}: {set(a)^set(b)}')
  for k in a:recurse_compare(a[k],b[k],path+'.'+k,tol)
 elif isinstance(a,list) and isinstance(b,list):
  if len(a)!=len(b):raise AssertionError(f'coverage list length mismatch at {path}')
  for i,(x,y) in enumerate(zip(a,b)):recurse_compare(x,y,f'{path}[{i}]',tol)
 elif isinstance(a,(int,float)) and isinstance(b,(int,float)):
  if isinstance(a,int) and isinstance(b,int):
   if a!=b:raise AssertionError(f'coverage integer mismatch at {path}: {a} vs {b}')
  elif not math.isclose(float(a),float(b),rel_tol=0,abs_tol=tol):raise AssertionError(f'coverage float mismatch at {path}: {a} vs {b}')
 elif a!=b:raise AssertionError(f'coverage value mismatch at {path}: {a!r} vs {b!r}')
# Verify producer manifest output and frozen input checksums.
manifest=json.loads(MAN.read_text());pins={};expected_c_paths={}
for role,rec in manifest['inputs'].items():
 p=Path(rec['path']);actual=sha(p);pins['manifest_input:'+role]={'path':str(p),'expected':rec['sha256'],'actual':actual,'match':actual==rec['sha256']}
 role_map={'census':'census','coordinates':'points','identity':'identity','source_evidence':'source_evidence','wiki':'wiki','annual':'annual','source_manifest':'source_manifest'}
 if role in role_map:expected_c_paths[role]=actual==sha(FROZEN[role_map[role]])
for role,rec in manifest['outputs'].items():
 p=Path(rec['path']);actual=sha(p);pins['manifest_output:'+role]={'path':str(p),'expected':rec['sha256'],'actual':actual,'match':actual==rec['sha256']}
if not all(v['match'] for v in pins.values()):raise AssertionError('manifest input/output checksum mismatch')
for role in ['census','coordinates','identity','source_evidence','wiki','annual','source_manifest']:
 if not expected_c_paths.get(role,False):raise AssertionError('export input diverges from frozen artifact: '+role)
# Explicit receipt cross-checks for selected, points, graph and restricted evidence.
receipts={
 'selected':json.loads((C/'urban_primary_population_application_v1/acceptance_receipt.json').read_text()),
 'points':json.loads((C/'accepted_geonames_graph_point_reuse_delta_v1/acceptance_receipt.json').read_text()),
 'identity':json.loads((C/'accepted_shared_named_object_identity_delta_v1/acceptance_receipt.json').read_text()),
 'context':json.loads((C/'urban_primary_source_context_annotations_v1/receipt.json').read_text()),
 'coverage_inputs':json.loads((C/'urban_primary_coverage_inputs_v1/receipt.json').read_text()),
}
# Cross-check frozen values against their acceptance receipts and R4 projections.
sel_out=receipts['selected']['outputs']['selected_observations.parquet']['sha256']
if sel_out!=sha(FROZEN['census']):raise AssertionError('selected R4 differs from application receipt')
if receipts['points']['output']['sha256']!=sha(FROZEN['points']):raise AssertionError('R4 points differ from accepted point receipt')
if receipts['selected']['outputs']['accepted_identity_edges.parquet']['sha256']!=sha(FROZEN['identity']):raise AssertionError('R4 identity graph differs from primary application receipt')
if receipts['coverage_inputs']['outputs']['legacy_availability_projected_r4.parquet']!=sha(FROZEN['legacy_quality']):raise AssertionError('R4 legacy projection receipt pin mismatch')
if receipts['coverage_inputs']['outputs']['cumulative_publication_bindings.parquet']!=sha(FROZEN['cumulative_bindings']):raise AssertionError('cumulative publication bindings receipt pin mismatch')
if len(pd.read_parquet(FROZEN['annual']))!=516 or len(pd.read_parquet(FROZEN['wiki']))!=34004:raise AssertionError('annual/Wiki frozen export input counts differ')
# R4 frozen input sizes and accepted deltas.
assert pq.ParquetFile(FROZEN['census']).metadata.num_rows==465800
assert pq.ParquetFile(FROZEN['points']).metadata.num_rows==327430
assert pq.ParquetFile(FROZEN['identity']).metadata.num_rows==176568
assert pq.ParquetFile(FROZEN['cumulative_bindings']).metadata.num_rows==1344
# Output parquet counts, duplicate IDs, rows-by-type, coordinates and Wiki non-use.
q=pq.ParquetFile(TBL);n=q.metadata.num_rows;cols=q.schema_arrow.names
if n!=500320:raise AssertionError('export row count is not 500,320')
if len(set(cols))!=len(cols):raise AssertionError('duplicate export column names')
if any(re.search(r'(?:valid_from|valid_to|effective_start|effective_end)',c,re.I) for c in cols):raise AssertionError('export added legal OKTMO interval fields')
obs_ids=set();type_counts={};coord_counts={};assoc_counts={};wiki_coord_rows=0;duplicate_ids=0;census_parts=[];annual_parts=[];wiki_rows=0
corecols=['observation_id','record_type','source_record_id','observation_year','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population_value','population_value_quality','population_value_quality_original_tag','population_quality_limitation','displaced_source_record_id','publication_binding_basis','population_scope','source_path','source_sheet','source_row','source_native_id','source_sha256','source_hash_binding','source_locator','source_sha256_original_selected','oktmo_native_raw','oktmo_current_observed_2021','oktmo_observed_at_year','oktmo_identifier_observation_year','latitude','longitude','coordinate_quality','coordinate_provider_quality_raw','coordinate_admission_status','coordinate_source','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','coordinate_measurement_date_unknown','boundary_comparability_asserted','coordinate_uncertainty_flags_json','point_source_file','point_source_sha256','point_source_locator','point_source_kind','coordinate_provenance','coordinate_temporal_basis','direct_historical_coordinate_measurement','population_scope_comparability_asserted','coordinate_admission_rule','coordinate_source_date','coordinate_candidate_latitude','coordinate_candidate_longitude','entity_id','associated_census_entity_id','association_status','spatial_identity_status','population_raw','population_source_raw_line','source_association_status','historical_physical_identity_status']
for b in q.iter_batches(batch_size=10000,columns=corecols):
 d=b.to_pandas();
 if d.observation_id.isna().any():raise AssertionError('null observation_id')
 ids=d.observation_id.astype(str).tolist(); duplicate_ids+=len(ids)-len(set(ids));obs_ids.update(ids)
 for k,v in d.record_type.value_counts(dropna=False).items():type_counts[str(k)]=type_counts.get(str(k),0)+int(v)
 for k,v in d.association_status.value_counts(dropna=False).items():assoc_counts[str(k)]=assoc_counts.get(str(k),0)+int(v)
 lat=d.latitude.notna();lon=d.longitude.notna()
 if not lat.equals(lon):raise AssertionError('latitude/longitude nullness differs')
 for k,g in d.groupby('record_type',dropna=False):coord_counts[str(k)]=coord_counts.get(str(k),0)+int(g.latitude.notna().sum())
 w=d.record_type.eq('wiki_literal_series');wiki_rows+=int(w.sum())
 if d.loc[w,'latitude'].notna().any() or d.loc[w,'longitude'].notna().any():wiki_coord_rows+=int(d.loc[w,'latitude'].notna().sum()+d.loc[w,'longitude'].notna().sum())
 census=d[d.record_type.eq('census')]
 if len(census):census_parts.append(census)
 annual=d[d.record_type.eq('annual_official')]
 if len(annual):annual_parts.append(annual)
if duplicate_ids:raise AssertionError(f'{duplicate_ids} duplicate observation IDs')
if len(obs_ids)!=500320:raise AssertionError('unique observation count mismatch')
if type_counts!={'census':465800,'wiki_literal_series':34004,'annual_official':516}:raise AssertionError(f'unexpected record type counts {type_counts}')
if coord_counts!={'census':327430,'wiki_literal_series':0,'annual_official':495}:raise AssertionError(f'unexpected coordinate by record type {coord_counts}')
if assoc_counts.get('accepted_same_place_component')!=304502:raise AssertionError('census accepted identity-linked row count differs')
if manifest['summary']['census_linked_record_count']!=304502:raise AssertionError('manifest census-linked summary differs')
if wiki_coord_rows:raise AssertionError('Wiki literal series carry coordinates')
# Compare the full census layer's native fields to the immutable R4 selection using one indexed join.
census=pd.concat(census_parts,ignore_index=True);annual=pd.concat(annual_parts,ignore_index=True)
sel=pd.read_parquet(FROZEN['census'],columns=['source_record_id','census_year','source_file','source_path','source_sha256','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','population_value_quality','population_value_quality_original_tag','population_quality_limitation','displaced_source_record_id','publication_binding_basis','population_scope','source_sheet','source_row','source_native_id','source_locator','oktmo','settlement_id'])
if not sel.source_record_id.is_unique or not census.source_record_id.is_unique:raise AssertionError('selected/export census IDs not unique')
if set(sel.source_record_id)!=set(census.source_record_id):raise AssertionError('export census IDs differ from selected R4')
cs=census.set_index('source_record_id').loc[sel.source_record_id].reset_index(); sel=sel.reset_index(drop=True)
# Core source observations and raw OKTMO must be literal projections.
for outcol,incol in [('source_name_raw','source_name_raw'),('settlement_name','settlement_name'),('settlement_type','settlement_type'),('region_raw','region_raw'),('district_raw','district_raw'),('municipality_raw','municipality_raw'),('population_value','population'),('population_value_quality','population_value_quality'),('population_value_quality_original_tag','population_value_quality_original_tag'),('population_quality_limitation','population_quality_limitation'),('displaced_source_record_id','displaced_source_record_id'),('publication_binding_basis','publication_binding_basis'),('population_scope','population_scope'),('source_sheet','source_sheet'),('source_row','source_row'),('source_native_id','source_native_id'),('source_locator','source_locator'),('source_sha256_original_selected','source_sha256')]:
 a=cs[outcol];b=sel[incol]
 if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
  if not close_num(a,b):raise AssertionError('export value differs from selected field '+outcol)
 elif not str_eq(a,b):raise AssertionError('export value differs from selected field '+outcol)
# Source paths and hashes are resolved from the frozen, checksummed source manifest.
source_manifest=pd.read_parquet(FROZEN['source_manifest'],columns=['path','sha256'])
if not source_manifest.path.is_unique:raise AssertionError('source manifest paths are not unique')
manifest_hash=source_manifest.set_index('path').sha256
selected_path=sel.source_path.where(sel.source_path.notna() & sel.source_path.astype(str).ne(''),sel.source_file)
if not str_eq(cs.source_path,selected_path):raise AssertionError('export source paths do not match selected/path-manifest route')
manifest_path=cs.source_path.astype(str).str.replace('/workspace/settlements-raw/','',regex=False)
manifest_hash_expected=manifest_path.map(manifest_hash)
selected_projection=cs.source_hash_binding.eq('selected_source_projection')
manifest_bound=cs.source_hash_binding.eq('exact_path_in_frozen_input_manifest')
if not (selected_projection|manifest_bound).all():raise AssertionError('unexpected source hash binding class')
if not str_eq(cs.loc[manifest_bound,'source_sha256'],manifest_hash_expected.loc[manifest_bound]):raise AssertionError('manifest-backed source hash mismatch')
if not str_eq(cs.loc[selected_projection,'source_sha256'],sel.loc[selected_projection,'source_sha256']):raise AssertionError('selected-source-projection hash changed')
both=selected_projection & manifest_hash_expected.notna()
if not str_eq(cs.loc[both,'source_sha256'],manifest_hash_expected.loc[both]):raise AssertionError('selected source hash conflicts with manifest when both are available')
if not str_eq(cs.source_sha256_original_selected,sel.source_sha256):raise AssertionError('original selected source hash field changed')
is_2021=sel.census_year.eq(2021)
if not str_eq(cs.loc[is_2021,'oktmo_native_raw'],sel.loc[is_2021,'oktmo']):raise AssertionError('2021 native OKTMO was altered/padded')
if cs.loc[~is_2021,'oktmo_native_raw'].notna().any():raise AssertionError('non-2021 observations carry native OKTMO')
if not str_eq(cs.loc[is_2021,'oktmo_observed_at_year'],sel.loc[is_2021,'oktmo']):raise AssertionError('2021 observed OKTMO literal differs from selected raw value')
if not close_num(cs.loc[is_2021,'oktmo_identifier_observation_year'],pd.Series(2021,index=cs.index[is_2021]).where(sel.loc[is_2021,'oktmo'].notna())):raise AssertionError('2021 OKTMO observation-year indicator mismatch')
if cs.loc[~is_2021,'oktmo_identifier_observation_year'].notna().any() or cs.loc[~is_2021,'oktmo_observed_at_year'].notna().any():raise AssertionError('non-2021 observations carry a native-year OKTMO claim')
if not close_num(cs.observation_year,sel.census_year):raise AssertionError('census year differs')
# Check observed 2021 OKTMO snapshots remain literal strings where current source ID is available; do not treat as legal intervals.
legacy_r4=pd.read_parquet(C/'urban_primary_coverage_inputs_v1/legacy_availability_projected_r4.parquet',columns=['source_record_id','settlement_id'])
legacy_r4=legacy_r4.set_index('source_record_id').reindex(sel.source_record_id).reset_index(drop=True)
# Current codes are a literal 2021 snapshot keyed by the export's accepted entity
# components. Independently reconstruct exactly the builder's 2021 last-observation
# mapping rather than compare to historical projected settlement IDs.
edges=pd.read_parquet(FROZEN['identity'],columns=['from_source_record_id','to_source_record_id'])
parent={str(x):str(x) for x in sel.source_record_id}
def find(x):
 while parent[x]!=x:
  parent[x]=parent[parent[x]];x=parent[x]
 return x
for fr,to in edges.itertuples(index=False,name=None):
 a,b=find(str(fr)),find(str(to))
 if a!=b:parent[max(a,b)]=min(a,b)
entity={rid:'settlement:'+find(rid) for rid in parent}
latest={}
for rid,yr,code in zip(sel.source_record_id.astype(str),sel.census_year,sel.oktmo):
 if int(yr)==2021:latest[entity[rid]]=code
expected_current=sel.source_record_id.astype(str).map(lambda rid:latest.get(entity[rid]))
if not str_eq(cs.oktmo_current_observed_2021,expected_current):
 raise AssertionError('2021 current-code snapshot differs from exact selected 2021 entity mapping')
# The cumulative 564+780 binding projection must be literal and same-census scoped.
cumulative=pd.read_parquet(FROZEN['cumulative_bindings'])
if len(cumulative)!=1344 or cumulative.binding_scope.nunique()!=1 or not cumulative.binding_scope.iloc[0].startswith('same-census'):
 raise AssertionError('cumulative publication bindings are not exact same-census batch')
cumidx=cumulative.set_index('new_source_record_id')
if not set(cumidx.index).issubset(set(cs.source_record_id)):
 raise AssertionError('cumulative binding target missing from export')
bound=cs[cs.source_record_id.isin(cumidx.index)].set_index('source_record_id')
if len(bound)!=1344:raise AssertionError('export does not retain all 1,344 publication binding targets')
if not str_eq(bound.loc[cumidx.index,'displaced_source_record_id'],cumidx.old_source_record_id):
 raise AssertionError('cumulative old source IDs changed in exported binding rows')
if not close_num(bound.loc[cumidx.index,'population_value'],cumidx.primary_population):
 raise AssertionError('cumulative primary populations differ in export')
if bound.publication_binding_basis.isna().any():raise AssertionError('cumulative publication basis missing')
# Compare every Census coordinate to accepted point uses, retaining their exact origin and uncertainty.
point_cols=['target_source_record_id','target_year','latitude','longitude','coordinate_quality','coordinate_source','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','coordinate_admission_status','coordinate_measurement_date_unknown','boundary_comparability_asserted','coordinate_uncertainty_flags_json','coordinate_provenance','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_claim_artifact_file','point_claim_artifact_sha256','source_file','source_sha256','source_locator','coordinate_application_family','direct_historical_coordinate_measurement','population_scope_comparability_asserted','admission_rule','coordinate_source_date','provider_binding_status','provider_fias_binding_status']
pts=pd.read_parquet(FROZEN['points'],columns=point_cols)
if not pts.target_source_record_id.is_unique:raise AssertionError('frozen point targets are not unique')
coord=cs[cs.latitude.notna()].copy();
if len(coord)!=327430 or set(coord.source_record_id)!=set(pts.target_source_record_id):raise AssertionError('export census coordinate targets differ from frozen point uses')
pt=pts.set_index('target_source_record_id').loc[coord.source_record_id].reset_index(drop=True);coord=coord.reset_index(drop=True)
fallback=lambda primary,secondary,tertiary: primary.where(primary.notna() & primary.astype(str).ne(''),secondary.where(secondary.notna() & secondary.astype(str).ne(''),tertiary))
pt['expected_origin_file']=fallback(pt.point_origin_file,pt.point_claim_artifact_file,pt.source_file)
pt['expected_origin_sha256']=fallback(pt.point_origin_sha256,pt.point_claim_artifact_sha256,pt.source_sha256)
pt['expected_origin_locator']=fallback(pt.point_origin_locator,pt.source_locator,pt.source_locator)
field_map=[('latitude','latitude'),('longitude','longitude'),('coordinate_provider_quality_raw','coordinate_quality'),('coordinate_source','coordinate_source'),('coordinate_source_record_id','coordinate_source_record_id'),('coordinate_provider','coordinate_provider'),('coordinate_provider_id','coordinate_provider_id'),('coordinate_admission_status','coordinate_admission_status'),('coordinate_measurement_date_unknown','coordinate_measurement_date_unknown'),('boundary_comparability_asserted','boundary_comparability_asserted'),('coordinate_uncertainty_flags_json','coordinate_uncertainty_flags_json'),('coordinate_provenance','coordinate_provenance'),('point_source_file','expected_origin_file'),('point_source_sha256','expected_origin_sha256'),('point_source_locator','expected_origin_locator'),('point_source_kind','point_origin_kind')]
for outcol,incol in field_map:
 a=coord[outcol];b=pt[incol]
 if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
  if not close_num(a,b):raise AssertionError('coordinate source values differ: '+outcol)
 elif not str_eq(a,b):raise AssertionError('coordinate origin/uncertainty differs: '+outcol)
# Explicitly verify both GeoNames direct 2021 and historical reuse origin/uncertainty families.
gn_direct=pt.coordinate_application_family.eq('GN_current_2021_named_place_point')
gn_origin=pt.point_origin_kind.eq('geonames_ru_txt_named_place_point')
gn_historical=gn_origin & pt.target_year.lt(2021)
if int(gn_direct.sum())!=9044 or not gn_origin.any() or int(gn_historical.sum())<2000:raise AssertionError('GeoNames direct/historical export strata unexpectedly absent')
if pt.loc[gn_origin,'coordinate_uncertainty_flags_json'].isna().any():raise AssertionError('GeoNames point uncertainty JSON missing')
if coord.loc[gn_origin,'coordinate_uncertainty_flags_json'].isna().any():raise AssertionError('export dropped GeoNames point uncertainty JSON')
# Annual coordinates must be attached to the corresponding accepted 2021 census point.
if int(annual.latitude.notna().sum())!=495 or not annual.latitude.notna().equals(annual.longitude.notna()):raise AssertionError('annual coordinate count/nullness mismatch')
y2021=census[(census.observation_year==2021)&census.entity_id.notna()].copy()
if not y2021.entity_id.is_unique:raise AssertionError('2021 entity ids are not unique for annual association')
a_coord=annual[annual.latitude.notna()].copy()
if not a_coord.associated_census_entity_id.equals(a_coord.entity_id):raise AssertionError('annual point association does not name its target census entity')
carrier=y2021.set_index('entity_id').reindex(a_coord.associated_census_entity_id).reset_index(drop=True)
if carrier.latitude.isna().any():raise AssertionError('annual coordinate lacks a point-bearing 2021 census carrier')
for oc in ['latitude','longitude','coordinate_source','coordinate_source_record_id','coordinate_provider','point_source_file','point_source_sha256','point_source_locator','point_source_kind','coordinate_uncertainty_flags_json']:
 if not str_eq(a_coord[oc],carrier[oc]):
  if pd.api.types.is_numeric_dtype(a_coord[oc]) and pd.api.types.is_numeric_dtype(carrier[oc]):
   if not close_num(a_coord[oc],carrier[oc]):raise AssertionError('annual coordinate differs from accepted carrier: '+oc)
  else:raise AssertionError('annual coordinate origin differs from accepted carrier: '+oc)
# Exactly 780 source evidence target annotations; originals/untargeted rows remain byte-for-value.
ctx_receipt=receipts['context'];base_ev=C/'urban_primary_population_application_v1/source_evidence.parquet';ann_ev=FROZEN['source_evidence']
if sha(base_ev)!=ctx_receipt['inputs'][str(base_ev)] or sha(ann_ev)!=ctx_receipt['outputs']['source_evidence.parquet']:raise AssertionError('source evidence annotation receipt pin mismatch')
proposal_path=C/'urban_primary_application_proposal_adapter_v3/replacement_proposals.parquet'
proposal=pd.read_parquet(proposal_path,columns=['r2_source_record_id','replacement_source_record_id','primary_district_context_flag'])
proposal_sha=sha(proposal_path)
targets=set(proposal.replacement_source_record_id.astype(str));
if len(targets)!=780:raise AssertionError('context annotation target set not 780')
baseq=pq.ParquetFile(base_ev);annq=pq.ParquetFile(ann_ev);seen_targets=0
for ba,bb in zip(baseq.iter_batches(batch_size=8000,columns=['source_record_id','census_year','source_evidence_json']),annq.iter_batches(batch_size=8000,columns=['source_record_id','census_year','source_evidence_json'])):
 a=ba.to_pandas();b=bb.to_pandas()
 if not a.source_record_id.equals(b.source_record_id) or not a.census_year.equals(b.census_year):raise AssertionError('evidence IDs/years changed')
 for rid,ja,jb in zip(a.source_record_id.astype(str),a.source_evidence_json,b.source_evidence_json):
  old=json.loads(ja);new=json.loads(jb)
  if rid not in targets:
   if old!=new:raise AssertionError('untargeted source evidence JSON changed')
  else:
   seen_targets+=1
   if set(new)-set(old)!={'primary_district_context_flag','primary_district_historical_admin_identity_asserted','primary_district_context_annotation_proposals_sha256'}:raise AssertionError('target annotation keys changed beyond the three reviewed keys')
   if any(new[k]!=v for k,v in old.items()):raise AssertionError('original target evidence JSON value changed')
   if new['primary_district_context_flag']!='inherited_parsed_header_context_unverified' or new['primary_district_historical_admin_identity_asserted'] is not False:raise AssertionError('district-context annotation is not restrictive')
   if new['primary_district_context_annotation_proposals_sha256']!=proposal_sha:raise AssertionError('context annotation proposal pin differs')
if seen_targets!=780:raise AssertionError('source evidence target annotations not exact 780')
# Coverage axes recompute on frozen R4 artifacts with full national controls.
coverage_inputs={
 'selected':pd.read_parquet(FROZEN['census'],columns=['source_record_id','census_year','population','population_scope','population_value_quality','latitude','longitude','settlement_id']),
 'legacy':pd.read_parquet(C/'urban_primary_coverage_inputs_v1/legacy_availability_projected_r4.parquet'),
 'edges':pd.read_parquet(FROZEN['identity'],columns=['from_source_record_id','to_source_record_id','decision_status']),
 'points':pd.read_parquet(FROZEN['points'],columns=['target_source_record_id','latitude','longitude','coordinate_admission_status'])}
controls={2002:145166731,2010:142856536,2021:147182123}
calc=measure(coverage_inputs['selected'],coverage_inputs['legacy'],coverage_inputs['edges'],coverage_inputs['points'],controls)
actual_cov=json.loads(COV.read_text())

for key in calc: recurse_compare(calc[key],actual_cov[key],'coverage.'+key)
# Verify coverage builder input hashes against exact frozen R4 receipts/artifacts.
for key,path in [('selected',FROZEN['census']),('edges',FROZEN['identity']),('points',FROZEN['points']),('legacy_quality',C/'urban_primary_coverage_inputs_v1/legacy_availability_projected_r4.parquet')]:
 rec=actual_cov['inputs'][key]
 if rec['sha256']!=sha(path): raise AssertionError('coverage input pin differs for '+key)
# Check official current full-national controls and the known admitted-population shares.
if [x['official_control'] for x in calc['census_metrics']]!=[145166731,142856536,147182123]:raise AssertionError('full national census controls mismatch')
# CSV and Parquet row keys/type/order parity; stdlib CSV reader only.
pqkeys=pq.ParquetFile(TBL).iter_batches(batch_size=10000,columns=['observation_id','record_type','source_record_id'])
with gzip.open(CSV,'rt',encoding='utf-8',newline='') as f:
 reader=csv.DictReader(f);header=reader.fieldnames
 if header!=cols:raise AssertionError('CSV header/schema differs from Parquet')
 seen_csv=set();csv_n=0
 for batch in pqkeys:
  d=batch.to_pandas()
  for row in d.itertuples(index=False,name=None):
   rec=next(reader,None)
   if rec is None:raise AssertionError('CSV ended before Parquet')
   if (rec['observation_id'],rec['record_type'],rec['source_record_id'])!=tuple('' if pd.isna(v) else str(v) for v in row):raise AssertionError('CSV key/type sequence differs from Parquet')
   if rec['observation_id'] in seen_csv:raise AssertionError('duplicate CSV observation_id')
   seen_csv.add(rec['observation_id']);csv_n+=1
 if next(reader,None) is not None:raise AssertionError('CSV has rows beyond Parquet')
if csv_n!=500320:raise AssertionError('CSV row count mismatch')
# Annual point assignments use a coordinate row; wiki associations have none.
if int(manifest['summary']['coordinate_count'])!=327925 or int(manifest['summary']['coordinate_count_by_record_type']['census'])!=327430 or int(manifest['summary']['coordinate_count_by_record_type']['annual_official'])!=495 or int(manifest['summary']['wiki_rows_have_coordinates'])!=0:raise AssertionError('manifest coordinate totals unexpected')
# Existing reviews are pinned and their scopes remain those used by the export.
review_pins={
 'urban_application':sha(C/'urban_primary_population_application_review_v1/application_review.json'),
 'urban_context_addendum':sha(C/'urban_primary_source_context_annotations_v1/receipt.json'),
 'geonames_application':receipts['points']['review_sha256'],
 'identity_application':receipts['identity']['review_sha256'],
 'publication_binding':sha(C/'primary_urban_publication_binding_rule_review_v1/review_verdict.json')}
report={'verdict':'PASS_DATA_ONLY_EXPORT_INTEGRATION','manifest_path':str(MAN),'manifest_input_output_pins_match':True,'frozen_R4_inputs_match_manifest':expected_c_paths,'export_rows':500320,'unique_observation_ids':len(obs_ids),'record_type_counts':type_counts,'association_status_counts':assoc_counts,'coordinate_counts_by_record_type':coord_counts,'wiki_series_rows':wiki_rows,'wiki_series_coordinates':wiki_coord_rows,'census_rows_match_frozen_selected_core_and_native_oktmo':True,'oktmo_native_raw_literal_match':True,'current_oktmo_literal_2021_entity_mapping_matches_builder':True,'no_new_legal_OKTMO_interval_fields':True,'census_point_rows_exact_match_frozen_327430_uses':True,'canonical_point_origin_fields_match':True,'coordinate_uncertainty_json_matches_all_points':True,'GeoNames_direct_2021_rows':int(gn_direct.sum()),'GeoNames_canonical_origin_rows':int(gn_origin.sum()),'GeoNames_historical_reuse_rows':int(gn_historical.sum()),'source_evidence_target_annotations':seen_targets,'untargeted_source_evidence_rows_unchanged':465020,'selected_input_unchanged_R4':True,'coverage_axes_recomputed_against_full_national_controls':True,'coverage_2002_2010_2021_admitted_population_share':[x['axes']['coordinate_admitted']['official_control_population_fraction'] for x in calc['census_metrics']],'coverage_graph_counts':calc['identity_graph'],'csv_parquet_id_type_order_parity':True,'csv_rows':csv_n,'reused_review_pins':review_pins,'all_manifest_pins':pins}
(OUT/'integration_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
md=['# Final loop export integration review','',f"**Verdict: {report['verdict']}**",'',"The pinned export reconciles to the frozen R4 selected observations, identity graph, accepted point uses, restrictive source-evidence addendum, legacy-availability projection and cumulative publication bindings. It contains 500,320 unique observation IDs; the CSV-gzip and Parquet outputs have matching ordered IDs, record types and source IDs.",'',"The census layer has 465,800 exact selected records and 327,430 accepted points. The table carries 495 annual-record point associations and no coordinates on its 34,004 Wikipedia literal-series records. Census native OKTMO strings match the selected source values exactly; the export adds no validity-interval fields. The canonical point-origin fields and uncertainty JSON match all frozen point uses, including GeoNames 2021 points and historical continuity uses.",'',"Only the 780 primary-bound context records have the three restrictive metadata keys. Their original JSON values and all other evidence rows are unchanged; the district flag remains unverified and the identity assertion is false. Recomputed coverage axes match the export coverage using the full controls 145,166,731 (2002), 142,856,536 (2010) and 147,182,123 (2021). The coordinates/identity/publication conclusions are reused from their existing pinned reviews, not reevaluated here.",'',"Checksums, counts and coverage numerators are in `integration_review.json`. No export, source, code or admission artifact was modified."]
(OUT/'integration_review.md').write_text('\n'.join(md)+'\n')
print(json.dumps({k:v for k,v in report.items() if k=='verdict' or k in ['export_rows','record_type_counts','coordinate_counts_by_record_type','wiki_series_rows','wiki_series_coordinates','GeoNames_direct_2021_rows','GeoNames_canonical_origin_rows','GeoNames_historical_reuse_rows','coverage_2002_2010_2021_admitted_population_share','coverage_graph_counts','csv_parquet_id_type_order_parity']},ensure_ascii=False,indent=2))

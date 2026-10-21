#!/usr/bin/env python3
"""Independent literal-source and spatial audit; never imports the producer module."""
from pathlib import Path
import hashlib,json,re,datetime,sys,time
import numpy as np,pandas as pd,osmium
from sklearn.neighbors import BallTree
from shapely.geometry import Polygon,Point
from shapely import wkb
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[4];ROOT=REPO/'research/sgrt_word_completion_20261021';PRODUCER=ROOT/'typology2021_cycle05';RAW=Path('/workspace/scratch/sgrt_transport/russia-210101.osm.pbf');FILTERED=Path('/workspace/scratch/sgrt_validation/recreation2021_reference_complete.osm.pbf')
ACCEPT={'hotel','motel','hostel','guest_house','camp_site','caravan_site','chalet','apartment','resort'}
KEYS={'name','tourism','landuse','type','start_date','end_date','disused','abandoned','demolished'}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def pred(o):return o.tags.get('tourism') in ACCEPT or o.tags.get('landuse')=='allotments'
def kind(o):return 'node' if isinstance(o,osmium.osm.Node) else ('way' if isinstance(o,osmium.osm.Way) else 'relation')
checks=[]
def check(name,ok,**kw):checks.append(dict(check=name,passed=bool(ok),**kw))
paths=[PRODUCER/'extract_recreation2021.py',PRODUCER/'recreation2021_receipt.json',PRODUCER/'recreation_objects_2021.parquet',PRODUCER/'raw_relation_geometry_ledger.parquet',PRODUCER/'settlement_recreation_features_2021.parquet',ROOT/'axis/full_settlement_axis.parquet',FILTERED]
before={str(p):sha(p) for p in paths};receipt=json.loads((PRODUCER/'recreation2021_receipt.json').read_text())
if '--reuse-raw-ledger' in sys.argv:
 rawproof=json.loads((HERE/'raw_source_predicate_receipt.json').read_text());assert sha(HERE/'actual_raw2021_selected_predicate_ledger.parquet')==rawproof['selected_ledger_sha256'];assert sha(FILTERED)==rawproof['filtered_PBF_sha256']
 rawsha=rawproof['raw_PBF_sha256'];raw=pd.read_parquet(HERE/'actual_raw2021_selected_predicate_ledger.parquet');source_keys=set(zip(raw.osm_type,raw.osm_id));checks=rawproof['checks'].copy()
else:
 rawsha=sha(RAW);check('full_actual_historical_PBF_SHA_exact',rawsha==receipt['raw_source_sha256'])
 check('historical_reference_complete_PBF_SHA_exact',before[str(FILTERED)]==receipt['filtered_reference_complete_sha256'])
 rawrows=[]
 for o in osmium.FileProcessor(str(RAW)).with_filter(osmium.filter.KeyFilter('tourism','landuse')):
  if not pred(o):continue
  rawrows.append(dict(osm_type=kind(o),osm_id=o.id,osm_version=o.version,osm_last_edit=str(o.timestamp),selected_tags_json=json.dumps({k:v for k,v in dict(o.tags).items() if k in KEYS},ensure_ascii=False,sort_keys=True),node_lat=o.location.lat if isinstance(o,osmium.osm.Node) and o.location.valid() else np.nan,node_lon=o.location.lon if isinstance(o,osmium.osm.Node) and o.location.valid() else np.nan))
 raw=pd.DataFrame(rawrows);raw.to_parquet(HERE/'actual_raw2021_selected_predicate_ledger.parquet',index=False)
 filtered=[]
 for o in osmium.FileProcessor(str(FILTERED)).with_filter(osmium.filter.KeyFilter('tourism','landuse')):
  if pred(o):filtered.append((kind(o),o.id,o.version,str(o.timestamp),json.dumps({k:v for k,v in dict(o.tags).items() if k in KEYS},ensure_ascii=False,sort_keys=True)))
 source_keys=set(zip(raw.osm_type,raw.osm_id));filterkeys={(r[0],r[1]) for r in filtered}
 check('all132265_raw_predicate_records_retained_by_filtered_reference',len(raw)==132265 and source_keys==filterkeys)
 ridx=raw.set_index(['osm_type','osm_id']);check('filtered_literal_versions_timestamps_tags_exact_actual_full_raw',all((ridx.loc[(k,i),'osm_version'],ridx.loc[(k,i),'osm_last_edit'],ridx.loc[(k,i),'selected_tags_json'])==(v,ts,tags) for k,i,v,ts,tags in filtered))
 check('actual_raw_all_selected_edits_no_later_than_snapshot',pd.to_datetime(raw.osm_last_edit,utc=True).le(pd.Timestamp('2021-01-01T23:59:59Z')).all())
 rawproof=dict(status='ACTUAL_FULL_RAW_PREDICATE_AND_REFERENCE_COMPLETENESS_INDEPENDENTLY_VERIFIED',n_selected=len(raw),type_counts=raw.osm_type.value_counts().to_dict(),raw_PBF_sha256=rawsha,raw_PBF_bytes=RAW.stat().st_size,filtered_PBF_sha256=before[str(FILTERED)],selected_ledger_sha256=sha(HERE/'actual_raw2021_selected_predicate_ledger.parquet'),latest_selected_edit=str(pd.to_datetime(raw.osm_last_edit,utc=True).max()),checks=checks.copy())
 (HERE/'raw_source_predicate_receipt.json').write_text(json.dumps(rawproof,ensure_ascii=False,indent=2)+'\n')
 print('RAW_SOURCE_PROOF_COMPLETE',len(raw),'sourceSHA',rawsha,'reference_exact',all(c['passed'] for c in checks),flush=True)
objects=pd.read_parquet(PRODUCER/'recreation_objects_2021.parquet');relations=pd.read_parquet(PRODUCER/'raw_relation_geometry_ledger.parquet');features=pd.read_parquet(PRODUCER/'settlement_recreation_features_2021.parquet');axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet')
check('derived_site_keys_unique',not objects.duplicated(['osm_type','osm_id']).any())
check('all132232_geometry_records_are_actual_selected_raw_records',len(objects)==132232 and set(zip(objects.osm_type,objects.osm_id))<=source_keys)
missing=source_keys-set(zip(objects.osm_type,objects.osm_id));ledger_missing=set(('relation',int(v)) for v in relations.loc[~relations.geometry_assembled,'osm_id'])
check('exact33_unassembled_relations_account_for_all_source_geometry_omissions',len(missing)==33 and missing==ledger_missing)
meta=objects.merge(raw,on=['osm_type','osm_id'],validate='one_to_one',suffixes=('_model','_raw'))
check('every_geometry_version_and_timestamp_binds_raw_object',meta.osm_version_model.eq(meta.osm_version_raw).all() and meta.osm_last_edit_model.eq(meta.osm_last_edit_raw).all())
check('every_selected_tag_literal_matches_full_raw',all(json.loads(a)==json.loads(b) for a,b in zip(meta.tags_selected_json,meta.selected_tags_json)))
check('raw_node_coordinates_exact',np.allclose(meta.loc[meta.osm_type.eq('node'),'lat'],meta.loc[meta.osm_type.eq('node'),'node_lat'],rtol=0,atol=1e-10) and np.allclose(meta.loc[meta.osm_type.eq('node'),'lon'],meta.loc[meta.osm_type.eq('node'),'node_lon'],rtol=0,atol=1e-10))
check('source_group_and_inactive_flags_exact_raw_predicate',all((row.source_group==('allotments' if tags.get('landuse')=='allotments' else 'accommodation')) and row.inactive_source_asserted==any(tags.get(k) in ['yes','true','1'] for k in ['disused','abandoned','demolished']) for row,tags in zip(objects.itertuples(),map(json.loads,objects.tags_selected_json))))
# Validate geometry against a separately parsed reference-complete source, rather
# than testing representative_point against a saved representative_point copy.
lookup=objects.set_index(['osm_type','osm_id']);geo=[]
class Geom(osmium.SimpleHandler):
 def __init__(self):super().__init__();self.factory=osmium.geom.WKBFactory()
 def way(self,o):
  key=('way',o.id)
  if key not in lookup.index:return
  row=lookup.loc[key];coords=[(v.lon,v.lat) for v in o.nodes if v.location.valid()]
  if len(coords)==len(o.nodes) and len(coords)>=4 and coords[0]==coords[-1] and Polygon(coords).is_valid:
   ok=Polygon(coords).covers(Point(row.lon,row.lat)) and row.geometry_role=='interior_point_of_historical_closed_way'
  else:ok=bool(coords) and np.allclose([row.lon,row.lat],np.mean(coords,axis=0),rtol=0,atol=1e-10)
  geo.append(ok)
 def area(self,o):
  key=('relation',o.orig_id())
  if o.from_way() or key not in lookup.index:return
  row=lookup.loc[key]
  try:polygon=wkb.loads(self.factory.create_multipolygon(o),hex=True);geo.append(polygon.is_valid and polygon.covers(Point(row.lon,row.lat)))
  except Exception:geo.append(False)
g=Geom();g.apply_file(str(FILTERED),locations=True,idx='sparse_mem_array')
check('all107880_way_and_relation_geometries_covered_by_actual_source_geometry',len(geo)==int(objects.osm_type.ne('node').sum()) and all(geo),checked=len(geo))
accepted=axis[axis.lat.notna()&axis.lon.notna()&axis.population_2021.notna()&axis.is_additive_source_unit&~axis.axis_kind.fillna('').str.contains('territory',case=False)].copy()
tree=BallTree(np.radians(accepted[['lat','lon']].to_numpy()),metric='haversine');best,indices=tree.query(np.radians(objects[['lat','lon']].to_numpy()),k=1)
km=best[:,0]*6371.0088
check('all_nearestNP_distances_equal_independent_haversine_BallTree',np.allclose(km,objects.nearest_distance_km,rtol=1e-8,atol=1e-7),maximum_km_error=float(np.max(np.abs(km-objects.nearest_distance_km))))
matched=objects.nearest_axis_id.isin(set(accepted.id));check('all_nearestNP_ids_in_declared_2021_population_frame',matched.all())
# Independently verify that each assigned ID attains the exact minimum distance.
coords=accepted.set_index('id').reindex(objects.nearest_axis_id)[['lat','lon']].to_numpy();rads=np.radians(objects[['lat','lon']].to_numpy());cr=np.radians(coords);dlat=cr[:,0]-rads[:,0];dlon=cr[:,1]-rads[:,1];actual=12742.0176*np.arcsin(np.sqrt(np.clip(np.sin(dlat/2)**2+np.cos(cr[:,0])*np.cos(rads[:,0])*np.sin(dlon/2)**2,0,1)))
check('all_selected_nearestIDs_attain_independent_distance_minimum',np.allclose(actual,km,rtol=1e-8,atol=1e-7))
# Check each named equivalence class has exactly the 50m-neighbour graph components.
def norm(v):return re.sub('[^а-яa-z0-9]+',' ',str(v).lower().replace('ё','е')).strip()
obj=objects.copy();obj['_name']=obj.name.map(norm)
named=obj[obj.name.notna()&obj['_name'].ne('')];cluster_ok=True;graph_groups=0
for _,group in named.groupby(['source_group','nearest_axis_id','_name'],dropna=False):
 if len(group)<2:continue
 graph_groups+=1;bt=BallTree(np.radians(group[['lat','lon']].to_numpy()),metric='haversine');adj=bt.query_radius(np.radians(group[['lat','lon']].to_numpy()),r=.05/6371.0088);parent=list(range(len(group)))
 def find(v):
  while parent[v]!=v:parent[v]=parent[parent[v]];v=parent[v]
  return v
 for i,ns in enumerate(adj):
  for j in ns:
   x,y=find(i),find(int(j))
   if x!=y:parent[y]=x
 expected={};ids=group.site_id.tolist()
 for i in range(len(group)):expected.setdefault(find(i),[]).append(ids[i])
 mapping={v:min(members) for members in expected.values() for v in members}
 if not all(group.canonical_site_id.eq(group.site_id.map(mapping))):cluster_ok=False
check('same_name50m_dedup_exact_independent_haversine_neighbour_components',cluster_ok,multi_record_name_groups=graph_groups)
check('anonymous_sites_not_deduplicated',obj.loc[obj.name.isna()|obj['_name'].eq(''),'canonical_site_id'].eq(obj.loc[obj.name.isna()|obj['_name'].eq(''),'site_id']).all())
check('all_feature_axis_ids_exact_original_order',features.id.equals(axis.id))
valid=objects[objects.nearest_distance_km.le(3)&~objects.inactive_source_asserted]
for group,column,flag in [('accommodation','osm_accommodation_points_within3km','recreation_facility_evidence'),('allotments','osm_allotment_geometries_within3km','dacha_landuse_evidence')]:
 cells=valid[valid.source_group.eq(group)][['nearest_axis_id','canonical_site_id']].drop_duplicates();cnt=cells.groupby('nearest_axis_id').size();expected=features.id.map(cnt).fillna(0).astype(int)
 check(group+'_all_counts_from_actual_inrange_active_distinct_sites',features[column].eq(expected).all())
 check(group+'_positiveTRUE_missingUNKNOWN_never_absenceFALSE',features.loc[expected.gt(0),flag].eq(True).all() and features.loc[expected.eq(0),flag].isna().all())
check('all_snapshots20210101_and_positive_context_not_operation_census',objects.snapshot.eq('2021-01-01').all() and objects.context_not_verified_settlement_identity.eq(True).all() and features.recreation_absent_record_is_unknown.eq(True).all())
check('producer_files_and_filtered_reference_unchanged_during_review',before=={str(p):sha(p) for p in paths})
audit=dict(status='HISTORICAL_RECREATION_INDEPENDENTLY_VERIFIED' if all(c['passed'] for c in checks) else 'RETURN_TO_REPAIR_LOOP',n_checks=len(checks),n_failed=sum(not c['passed'] for c in checks),checks=checks,raw_objects=len(raw),geometry_objects=len(objects),unassembled_relations=len(missing),positive_accommodation_NP=int(features.recreation_facility_evidence.eq(True).sum()),positive_allotment_NP=int(features.dacha_landuse_evidence.eq(True).sum()),source_SHA256=before,raw_source_sha256=rawsha,reviewer_code_sha256=sha(Path(__file__)),physical_operation_verified=False,unknown_not_absence=True,source_year_date_limitations='Source immutablePBF20210101; nearestNP geographies may be later referencepoint; no physicalopening/closure causalclaim',raw_proof_file='raw_source_predicate_receipt.json')
(HERE/'recreation2021_independent_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in audit.items() if k not in ['checks','source_SHA256']},ensure_ascii=False,indent=2));print('FAILED',[c for c in checks if not c['passed']],flush=True)

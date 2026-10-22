#!/usr/bin/env python3
"""Mass POI-source preservation, geometry and every feature count audit.

An independent BallTree/haversine verifies geometry against the owner's
Cartesian KDTree; NumPy decodes original WKB. No author module imports.
Address linkage is separately checked against all same-name candidates.
"""
from pathlib import Path
import json,re,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
from sklearn.neighbors import BallTree
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent;O=H/'independent_sources/places';O.mkdir(parents=True,exist_ok=True);R=6371.0088
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(2**20),b''):h.update(x)
 return h.hexdigest()
def norm(s):
 if s is None:return ''
 s=re.sub(r'\([^)]*\)',' ',str(s).lower().replace('ё','е'));s=re.sub(r'^(?:город|село|деревня|поселок|посёлок|пгт|пос\.|п\.|с\.|д\.|г\.)\s*','',s);return re.sub(r'[^a-zа-я0-9]+',' ',s).strip()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,default=lambda v:v.tolist() if hasattr(v,'tolist') else v.item() if hasattr(v,'item') else str(v))
def wkbxy(blob):
 order='little' if blob[0]==1 else 'big';header=int.from_bytes(blob[1:5],order);assert header&255==1;start=9 if header&0x20000000 else 5;return np.frombuffer(blob,dtype=('<' if order=='little' else '>')+'f8',count=2,offset=start)
def distance(lat,lon,alat,alon):
 a,b=np.deg2rad(lat),np.deg2rad(alat);h=np.sin((a-b)/2)**2+np.cos(a)*np.cos(b)*np.sin(np.deg2rad(lon-alon)/2)**2;return 2*R*np.arctan2(np.sqrt(np.clip(h,0,1)),np.sqrt(np.clip(1-h,0,1)))
def main():
 files=sorted((N/'places/selected').glob('overture_ru_selected_*.parquet'));paths=files+[B/'anchor_research_20261019/data/point_axis.parquet',N/'places/places_objects_and_crosswalk.parquet',N/'places/places_settlement_features.parquet'];before={str(p):sha(p) for p in paths};axis=pd.read_parquet(paths[-3]);long=pd.read_parquet(paths[-2]);wide=pd.read_parquet(paths[-1]);checks=[];risks=[]
 gp=B/'anchor_research_20261019/model/documented_graph/service_edges_calculated.csv';before[str(gp)]=sha(gp);g=pd.read_csv(gp);quarantine=set(g.loc[g.geometry_status.eq('coordinate_conflict_quarantined'),'origin_uid'].dropna());ap=axis[~axis.id.isin(quarantine)&axis.lat.notna()&axis.lon.notna()].reset_index(drop=True)
 def ck(n,v,detail=None):checks.append({'name':n,'pass':bool(v),'detail':detail})
 ck('source_GERS_unique',long.source_place_id.is_unique and long.source_place_id.notna().all());ck('all_142570_UIDs',len(wide)==142570 and wide.id.is_unique and wide.id.equals(axis.id));wide=wide.set_index('id').reindex(axis.id);indexed=long.set_index('source_place_id');seen=[]
 for p in files:
  raw=pd.read_parquet(p);seen.extend(raw.id.tolist())
  if raw.empty:ck('empty_source_part_'+p.stem,pq.ParquetFile(p).metadata.num_rows==0);continue
  matched=indexed.reindex(raw.id);coords=np.array([wkbxy(x) for x in raw.geometry]);lon=coords[:,0];lat=coords[:,1]
  ck('source_ids_present_'+p.stem,matched.source_version.notna().all());ck('original_geometry_'+p.stem,np.array_equal(lon,matched.longitude.to_numpy()) and np.array_equal(lat,matched.latitude.to_numpy()));ck('original_version_'+p.stem,np.array_equal(raw.version.to_numpy(),matched.source_version.to_numpy()));ck('original_source_part_'+p.stem,matched.source_part.eq(p.name).all());ck('original_confidence_'+p.stem,np.allclose(raw.confidence,matched.source_confidence,equal_nan=True,rtol=0,atol=0))
  names=[(x or {}).get('primary') for x in raw.names];ck('original_primary_names_'+p.stem,pd.Series(names).fillna('').eq(matched.primary_name.reset_index(drop=True).fillna('')).all());statuses=[x if x else 'unknown' for x in raw.operating_status];ck('original_operating_status_'+p.stem,np.array_equal(statuses,matched.source_operating_status.to_numpy()))
  addresses=[[] if x is None else list(x) for x in raw.addresses];ck('original_all_addresses_'+p.stem,all(canonical(a)==canonical(json.loads(b)) for a,b in zip(addresses,matched.addresses_json)));ck('original_all_source_attributions_'+p.stem,all(canonical(a)==canonical(json.loads(b)) for a,b in zip(raw.sources,matched.sources_json)));ck('original_all_taxonomies_'+p.stem,all(canonical(a or {})==canonical(json.loads(b)) for a,b in zip(raw.taxonomy,matched.source_taxonomy_json)));ck('country_RU_attribute_'+p.stem,np.array_equal([any(a.get('country')=='RU' for a in x) for x in addresses],matched.source_country_ru.to_numpy()))
 ck('every_original_object_exactly_once',len(seen)==len(long) and len(set(seen))==len(seen) and set(seen)==set(long.source_place_id))
 tree=BallTree(np.deg2rad(ap[['lat','lon']].to_numpy()),metric='haversine');rad,near=tree.query(np.deg2rad(long[['latitude','longitude']].to_numpy()),k=2);km=rad[:,0]*R;ck('every_nearest_distance',np.allclose(km,long.nearest_distance_km,rtol=0,atol=1e-8));lookup=ap.set_index('id');ref=lookup.loc[long.nearest_uid_unaccepted];claimed=distance(long.latitude.to_numpy(),long.longitude.to_numpy(),ref.lat.to_numpy(),ref.lon.to_numpy());ck('every_nearest_UID_geometrically_valid',np.allclose(km,claimed,rtol=0,atol=1e-8));ck('baseline_conditional_candidate_disjoint',long[['baseline_uid','conditional_uid','nearest_candidate_uid']].notna().sum(axis=1).le(1).all());ck('external_geography_not_reassigned',long.loc[long.source_geography_scope.ne('axis_linkage_eligible'),['baseline_uid','conditional_uid','nearest_candidate_uid']].isna().all().all());ck('quarantined_geometry_never_used',not long[['baseline_uid','conditional_uid','nearest_candidate_uid','nearest_uid_unaccepted']].isin(quarantine).any().any())
 # Reconstruct exact-address candidates independently from published raw address
 # payload retained in long. This checks all same-name possibilities, not only kNN.
 names={}
 for i,n in enumerate(ap.name.map(norm)):names.setdefault(n,[]).append(i)
 alat=ap.lat.to_numpy();alon=ap.lon.to_numpy();uids=ap.id.to_numpy();base_expected=[];conditional_expected=[];cand_expected=[]
 for row in long.itertuples(index=False):
  addresses=json.loads(row.addresses_json);localities={norm(a.get('locality')) for a in addresses if a.get('locality')};localities.discard('');typed=set()
  for a in addresses:
   for hit in re.finditer(r'(?:^|[,;])\s*(?:город|село|деревня|пос[её]лок|пгт|г\.|с\.|д\.|п\.)\s*([^,;]+)',a.get('freeform') or '',re.I):typed.add(norm(hit.group(1)))
  def candidates(tokens):
   ix=sorted({i for token in tokens for i in names.get(token,[])})
   if not ix:return []
   dd=distance(row.latitude,row.longitude,alat[ix],alon[ix]);return [(i,dd[k]) for k,i in enumerate(ix) if dd[k]<=10]
  exact=candidates(localities);extra=candidates(typed);base=None;conditional=None
  if len(exact)==1 and exact[0][1]<=5 and not row.country_polygon_conflict:base=uids[exact[0][0]]
  elif len(exact)==1:conditional=uids[exact[0][0]]
  elif not exact and len(extra)==1 and extra[0][1]<=5 and not row.country_polygon_conflict:conditional=uids[extra[0][0]]
  candidate=row.nearest_uid_unaccepted if base is None and conditional is None and row.nearest_distance_km<=10 and not row.country_polygon_conflict else None
  if row.source_geography_scope!='axis_linkage_eligible':base=conditional=candidate=None
  base_expected.append(base);conditional_expected.append(conditional);cand_expected.append(candidate)
 for label,expected in [('baseline_uid',base_expected),('conditional_uid',conditional_expected),('nearest_candidate_uid',cand_expected)]:
  ck('all_address_identity_rules_'+label,pd.Series(expected).fillna('').eq(long[label].fillna('')).all())
 # Recompute every mode's all-source, requested, family, signal, and status counts.
 for mode,key in [('baseline','baseline_uid'),('conditional','conditional_uid'),('nearest_candidate','nearest_candidate_uid')]:
  linked=long[long[key].notna()];not_closed=linked[~linked.source_operating_status.isin(['permanently_closed','temporarily_closed'])];requested_all=linked[~linked.function_group.isin(['unknown_999','outside_requested_functions'])];requested=requested_all[~requested_all.source_operating_status.isin(['permanently_closed','temporarily_closed'])]
  prefix=f'places_{mode}_'
  for c in [x for x in wide if x.startswith(prefix) and (x.endswith('_count') or x.endswith('_diversity'))]:
   suffix=c[len(prefix):]
   if suffix=='all_categories_count':expected=linked.groupby(key).size()
   elif suffix=='requested_function_count':expected=requested.groupby(key).size()
   elif suffix=='requested_function_diversity':expected=requested.groupby(key).function_group.nunique()
   elif suffix.startswith('name_signal_'):expected=not_closed.loc[not_closed[suffix[:-6]]].groupby(key).size()
   elif suffix.startswith('operating_'):expected=requested_all.loc[requested_all.source_operating_status.eq(suffix[len('operating_'):-6])].groupby(key).size()
   else:expected=not_closed.loc[not_closed.function_group.eq(suffix[:-6])].groupby(key).size()
   ck('every_settlement_'+c,np.array_equal(expected.reindex(axis.id,fill_value=0).to_numpy(),wide[c].to_numpy()))
 ck('no_actual_flow_claimed',not long.external_service_catchment_observed.any());ck('no_operation_verification_claimed',not long.physical_operation_independently_verified.any());ck('no_complete_census_claimed',not wide.places_source_is_complete_facility_census.any());ck('no_true_absence_claimed',not wide.places_true_function_absence_established.any());ck('all_source_inputs_stable',all(sha(Path(p))==v for p,v in before.items()))
 summary={'source_objects':len(long),'source_parts':len(files),'baseline_objects':int(long.baseline_uid.notna().sum()),'conditional_only_objects':int(long.conditional_uid.notna().sum()),'nearest_candidate_objects':int(long.nearest_candidate_uid.notna().sum()),'external_geography_objects':int(long.source_geography_scope.ne('axis_linkage_eligible').sum()),'nearest_first_second_ties':int(np.isclose(rad[:,0],rad[:,1],rtol=0,atol=1e-12).sum())};result={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,'summary':summary,'input_SHA256':before,'code_SHA256':sha(Path(__file__)),'scope':'Full source/geometry/address-rule/feature-count audit. Source taxonomy semantic mapping and country polygon selection are not independently verified as real-world institution/sovereignty evidence. No travel-flow or actual operation validation.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks',summary,flush=True);assert all(c['pass'] for c in checks)
if __name__=='__main__':main()

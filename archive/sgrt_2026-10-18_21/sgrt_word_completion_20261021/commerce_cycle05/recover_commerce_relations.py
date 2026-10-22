#!/usr/bin/env python3
"""Recover omitted historical commerce and administration relations, with conservative service_site deduplication.

This produces a new source version. Model assignments are not read. An object is
an OSM observation, never evidence that all services in a settlement is known.
"""
from pathlib import Path
import sys,json,hashlib,re,datetime
import numpy as np,pandas as pd,osmium
from shapely import wkb
from shapely.geometry import Point
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
sys.path.insert(0,str(BASE/'education'))
from build_school_features import link,xyz,dist,norm
sys.path.insert(0,str(BASE/'calibration'))
from build_services_2021 import selected,group as service_group
PBF=Path('/workspace/scratch/sgrt_validation/services2021_reference_complete.osm.pbf')
OLD=BASE/'calibration/services_2021_objects.parquet';AXIS=BASE/'axis/full_settlement_axis.parquet'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as s:
  for b in iter(lambda:s.read(2**20),b''):h.update(b)
 return h.hexdigest()
def numeric(v):
 return float(v) if v is not None and re.fullmatch(r'\d+(\.\d+)?',str(v).strip()) and float(v)>=0 else np.nan
class Extract(osmium.SimpleHandler):
 def __init__(self):
  super().__init__();self.raw={};self.geometry={};self.failures={};self.factory=osmium.geom.WKBFactory()
 def relation(self,r):
  tags=dict(r.tags)
  if selected(tags):
   self.raw[r.id]={'osm_id':r.id,'osm_type':'relation','name':tags.get('name'),'amenity':tags.get('amenity'),'healthcare':tags.get('healthcare'),'tags_json':json.dumps(tags,ensure_ascii=False),'member_refs_json':json.dumps([{'type':m.type,'ref':m.ref,'role':m.role}for m in r.members]),'source_last_edit':str(r.timestamp),'source_version':r.version}
 def area(self,a):
  if a.from_way() or not selected(dict(a.tags)):return
  try:
   g=wkb.loads(self.factory.create_multipolygon(a),hex=True)
   if g.is_empty or not g.is_valid:raise ValueError('invalid_or_empty_polygon')
   self.geometry[a.orig_id()]=g
  except Exception as e:self.failures[a.orig_id()]=str(e)
def main():
 before={str(p):sha(p)for p in [PBF,OLD,AXIS]}
 assert before[str(PBF)]=='138db8dea69edec00b2eee1b53f8ab41b9b79c66a0476da6a04c429ed2a3fa14'
 h=Extract();h.apply_file(str(PBF),locations=True,idx='sparse_mem_array')
 rows=[];unresolved=[]
 for rid,r in h.raw.items():
  g=h.geometry.get(rid)
  if g is None:unresolved.append(dict(r,geometry_status=h.failures.get(rid,'no_assembled_polygon')));continue
  pt=g.representative_point();rows.append(dict(r,lon=pt.x,lat=pt.y,geometry_role='interior_representative_point_of_valid_relation_polygon',geometry_status='assembled_valid_polygon',polygon_wkb=g.wkb))
 d=pd.DataFrame(rows);d['site_id']='osm:relation:'+d.osm_id.astype(str);d['service_group']=d.tags_json.map(lambda t:service_group(json.loads(t)));d['source_snapshot']='2021-01-01';d['source']='OpenStreetMap via Geofabrik Russia historical snapshot';d['source_license']='ODbL-1.0'
 axis=pd.read_parquet(AXIS);d=link(d,axis)
 old=pd.read_parquet(OLD);old['recovery_status']='previous_node_way_assertion';old['count_eligible']=True
 old['source_version_cycle05']='frozen_old_assertion_retained'
 d['canonical_site_id']=d.site_id;d['possible_duplicate_of']=None;d['recovery_status']='new_relation_no_same_group_service_site_overlap';d['count_eligible']=True;d['duplicate_evidence_json']='[]'
 trees={}
 for group,g in old.groupby('service_group'):
  trees[group]=(g,cKDTree(xyz(g.lat.to_numpy(),g.lon.to_numpy())))
 for idx,r in d.iterrows():
  oldg,tree=trees[r.service_group];poly=h.geometry[r.osm_id];pt=xyz([r.lat],[r.lon])[0]
  # Search envelope covers the complete polygon, plus50m. This avoids missing
  # a distant building inside large university grounds.
  minx,miny,maxx,maxy=poly.bounds
  envelope=oldg[oldg.lon.between(minx-.001,maxx+.001)&oldg.lat.between(miny-.001,maxy+.001)]
  within=tree.query_ball_point(pt,2*np.sin(.05/12742.0176))
  near=oldg.iloc[within];candidates=pd.concat([envelope,near]).drop_duplicates('site_id')
  namesame=[];overlap=[]
  member_ids={(v['type'],v['ref'])for v in json.loads(r.member_refs_json)}
  for _,q in candidates.iterrows():
   contained=poly.covers(Point(q.lon,q.lat));distance=float(dist(np.linalg.norm(pt-xyz([q.lat],[q.lon])[0])));member=(q.osm_type[0],int(q.osm_id))in member_ids
   same_name=pd.notna(r['name'])and pd.notna(q['name']) and bool(norm(r['name'])) and norm(r['name'])==norm(q['name'])
   ev={'site_id':q.site_id,'canonical_site_id':q.canonical_site_id,'name':q['name'],'inside_relation':contained,'distance_km':distance,'shared_member':member,'same_normalized_name':same_name}
   if contained or distance<=.05 or member:overlap.append(ev)
   if same_name and (contained or distance<=.05 or member):namesame.append(ev)
  if namesame:
   canonical=sorted({v['canonical_site_id']for v in namesame})
   if len(canonical)==1:
    d.at[idx,'canonical_site_id']=canonical[0];d.at[idx,'possible_duplicate_of']=canonical[0];d.at[idx,'recovery_status']='same_named_existing_service_site_duplicate';d.at[idx,'duplicate_evidence_json']=json.dumps(namesame,ensure_ascii=False)
   else:
    d.at[idx,'count_eligible']=False;d.at[idx,'recovery_status']='ambiguous_multiple_same_named_existing_service_sitees';d.at[idx,'duplicate_evidence_json']=json.dumps(namesame,ensure_ascii=False)
  elif overlap:
   d.at[idx,'count_eligible']=False;d.at[idx,'recovery_status']='possible_existing_service_site_overlap_not_counted_additionally';d.at[idx,'duplicate_evidence_json']=json.dumps(overlap,ensure_ascii=False)
  # Duplicate observations cannot assign the existing service_site to two localities.
  if d.at[idx,'recovery_status']=='same_named_existing_service_site_duplicate':
   q=old[old.canonical_site_id.eq(d.at[idx,'canonical_site_id'])];accepted=set(q.baseline_uid.dropna())|set(q.candidate_uid.dropna());incoming=r.baseline_uid if pd.notna(r.baseline_uid)else r.candidate_uid
   if pd.notna(incoming) and accepted and incoming not in accepted:
    d.at[idx,'count_eligible']=False;d.at[idx,'recovery_status']='duplicate_service_site_locality_link_conflict_not_counted'
 # Apply the same duplicate guard among newly recovered relations themselves.
 # Parent grounds and separately tagged building relations must not add two
 # service_site witnesses. Ambiguous nested children remain raw but uncounted.
 from shapely.strtree import STRtree
 polys=[h.geometry[rid]for rid in d.osm_id];spatial=STRtree(polys)
 handled=set()
 for i,p in enumerate(polys):
  for j in spatial.query(p,predicate='intersects'):
   j=int(j)
   if i==j or (min(i,j),max(i,j))in handled:continue
   handled.add((min(i,j),max(i,j)));a,b=d.iloc[i],d.iloc[j]
   if a.service_group!=b.service_group:continue
   overlap=p.intersection(polys[j]).area/max(min(p.area,polys[j].area),1e-20)
   if overlap<.95:continue
   # Prefer already anchored original service_sitees, then larger service_site grounds.
   anchor_a=a.recovery_status=='same_named_existing_service_site_duplicate';anchor_b=b.recovery_status=='same_named_existing_service_site_duplicate'
   if anchor_a!=anchor_b:keep,drop=(i,j)if anchor_a else(j,i)
   else:keep,drop=(i,j)if p.area>=polys[j].area else(j,i)
   k,q=d.iloc[keep],d.iloc[drop]
   if not bool(q.count_eligible):continue
   if k.canonical_site_id==q.canonical_site_id:continue
   ev={'site_id':k.site_id,'canonical_site_id':k.canonical_site_id,'nested_polygon_fraction':overlap,'source':'recovered_relation_peer','same_normalized_name':pd.notna(k['name'])and pd.notna(q['name'])and norm(k['name'])==norm(q['name'])}
   previous=json.loads(d.at[drop,'duplicate_evidence_json']);d.at[drop,'duplicate_evidence_json']=json.dumps(previous+[ev],ensure_ascii=False)
   same_locality=(pd.isna(k.baseline_uid)or pd.isna(q.baseline_uid)or k.baseline_uid==q.baseline_uid)
   if ev['same_normalized_name'] and same_locality:
    d.at[drop,'canonical_site_id']=d.at[keep,'canonical_site_id'];d.at[drop,'possible_duplicate_of']=d.at[keep,'canonical_site_id'];d.at[drop,'recovery_status']='same_named_recovered_relation_service_site_duplicate'
   else:
    d.at[drop,'count_eligible']=False;d.at[drop,'recovery_status']='nested_recovered_relation_service_site_ambiguous_not_counted_additionally'
 # Resolve alias chains after relation-peer deduplication.
 aliases=dict(zip(d.site_id,d.canonical_site_id))
 for idx,r in d.iterrows():
  canon=r.canonical_site_id;seen=set()
  while canon in aliases and aliases[canon]!=canon and canon not in seen:
   seen.add(canon);canon=aliases[canon]
  d.at[idx,'canonical_site_id']=canon
 # An alias into an unaccepted recovered service_site cannot revive it as a new count.
 eligibility=dict(zip(d.site_id,d.count_eligible))
 for idx,r in d.iterrows():
  if r.canonical_site_id in eligibility and not eligibility[r.canonical_site_id]:
   d.at[idx,'count_eligible']=False
   if r.recovery_status=='same_named_recovered_relation_service_site_duplicate':d.at[idx,'recovery_status']='alias_of_ambiguous_recovered_service_site_not_counted'
 d['source_version_cycle05']='omitted_relation_recovered_from_same_historical_pbf'
 # Explicit negative shop tags are not positive retail witnesses. Keepallraw,
 # exclude countingonlyif noindependentbank/post/market/governmentpurpose.
 negative_shop={'no','vacant','closed','disused','abandoned','demolished'}
 def negative_shop_row(row):
  tags=json.loads(row.tags_json);return row.service_group=='other_retail' and tags.get('shop') in negative_shop
 old_negative=old.apply(negative_shop_row,axis=1);new_negative=d.apply(negative_shop_row,axis=1)
 old.loc[old_negative,'count_eligible']=False;old.loc[old_negative,'recovery_status']='explicit_negative_shop_tag_not_positive_retail_witness'
 d.loc[new_negative,'count_eligible']=False;d.loc[new_negative,'recovery_status']='explicit_negative_shop_tag_not_positive_retail_witness'
 old_eligible=dict(zip(old.site_id,old.count_eligible))
 for idx,r in d.iterrows():
  if r.canonical_site_id in old_eligible and not old_eligible[r.canonical_site_id]:
   d.at[idx,'count_eligible']=False;d.at[idx,'recovery_status']='alias_into_explicit_negative_shop_tag_conflict_not_counted'
 # Retain all raw relation assertions, including assembly failures, in separate ledger.
 allraw=pd.DataFrame(list(h.raw.values()));allraw['geometry_assembled']=allraw.osm_id.isin(h.geometry);allraw['service_group']=allraw.tags_json.map(lambda t:service_group(json.loads(t)));allraw.to_parquet(HERE/'relation_source_ledger.parquet',index=False)
 pd.DataFrame(unresolved).to_parquet(HERE/'relation_unresolved_geometry.parquet',index=False)
 d.to_parquet(HERE/'service_relations_2021.parquet',index=False)
 allobj=pd.concat([old,d.drop(columns=['polygon_wkb'])],ignore_index=True,sort=False)
 # Explicit identity has precedence over a spatial candidate for the same
 # physical canonical site and SAME settlement. This makes counts additive.
 strict_pairs=set(zip(allobj.loc[allobj.count_eligible&allobj.baseline_uid.notna(),'baseline_uid'],allobj.loc[allobj.count_eligible&allobj.baseline_uid.notna(),'canonical_site_id']))
 allobj['count_baseline_eligible']=allobj.count_eligible&allobj.baseline_uid.notna()
 allobj['count_candidate_additional_eligible']=[bool(ok)and pd.notna(uid)and(uid,canon)not in strict_pairs for ok,uid,canon in zip(allobj.count_eligible,allobj.candidate_uid,allobj.canonical_site_id)]
 allobj['new_source_repair_uses_model_assignments']=False
 allobj.to_parquet(HERE/'services_2021_objects_repaired.parquet',index=False)
 features=axis[['id']].copy();groups=sorted(old.service_group.unique())
 for g in groups:
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   z=allobj[allobj.service_group.eq(g)&allobj[key].notna()&allobj[f'count_{mode}_eligible']].drop_duplicates([key,'canonical_site_id'])
   features[f'services_osm2021_{g}_{mode}_count']=features.id.map(z.groupby(key).size()).fillna(0).astype('int32')
  total=features[f'services_osm2021_{g}_baseline_count']+features[f'services_osm2021_{g}_candidate_additional_count'];features[f'services_osm2021_{g}_observed_presence']=pd.array(np.where(total.gt(0),True,None),dtype='boolean')
 features['service_absence_means_unknown']=True;features['service_source_scope']='2021-01-01 historical node/way/relation assertions; no census completeness, source absence is unknown function';features['service_cycle05_source_version']='historical_relation_geometry_recovery_conservative_same_service_site_dedup'
 features.to_parquet(HERE/'services_2021_settlement_features.parquet',index=False)
 old_features=pd.read_parquet(BASE/'calibration/services_2021_settlement_features.parquet');assert np.array_equal(features.id,old_features.id)
 counts=[c for c in old_features if c.startswith('services_osm2021_') and c.endswith('_count')];assert set(counts)=={f'services_osm2021_{g}_{mode}_count'for g in groups for mode in ['baseline','candidate_additional']}
 changes=features[['id']].copy()
 for col in counts:changes[col+'_delta']=features[col]-old_features[col]
 changes['any_count_changed']=changes.drop(columns='id').ne(0).any(axis=1);changes.to_parquet(HERE/'feature_count_changes.parquet',index=False)
 summary=[]
 for g in groups:
  z=allobj[allobj.service_group.eq(g)];rel=d[d.service_group.eq(g)];zok=z[z.count_eligible];bcol=f'services_osm2021_{g}_baseline_count';ccol=f'services_osm2021_{g}_candidate_additional_count';oldunion=old_features[bcol]+old_features[ccol];newunion=features[bcol]+features[ccol]
  summary.append({'service_group':g,'old_raw_node_way_assertions':int(old.service_group.eq(g).sum()),'selected_raw_relation_assertions':int(allraw.service_group.eq(g).sum()),'assembled_relation_assertions':int(rel.shape[0]),'accepted_relations_with_new_canonical_site':int((rel.count_eligible&rel.canonical_site_id.eq(rel.site_id)).sum()),'relation_same_named_duplicate':int(rel.recovery_status.isin(['same_named_existing_service_site_duplicate','same_named_recovered_relation_service_site_duplicate']).sum()),'relation_overlap_or_ambiguous_excluded_from_added_counts':int((~rel.count_eligible).sum()),'new_baseline_positive_settlements':int(features[bcol].gt(0).sum()),'old_baseline_positive_settlements':int(old_features[bcol].gt(0).sum()),'new_union_positive_settlements':int(newunion.gt(0).sum()),'old_union_positive_settlements':int(oldunion.gt(0).sum()),'baseline_site_witnesses_delta':int(features[bcol].sum()-old_features[bcol].sum()),'candidate_additional_witnesses_delta':int(features[ccol].sum()-old_features[ccol].sum()),'new_union_positive_np_ids':int((newunion.gt(0)&oldunion.eq(0)).sum()),'count_eligible_raw_assertions':len(zok)})
 pd.DataFrame(summary).to_csv(HERE/'service_group_inventory.csv',index=False)
 strata=axis[['id','region','type','population_2021','lat','lon']].merge(features,on='id',validate='one_to_one');strata['located_axis']=strata.lat.notna()&strata.lon.notna();strata['population_size']=pd.cut(strata.population_2021,[-1,0,99,499,1999,9999,np.inf],labels=['zero','1-99','100-499','500-1999','2000-9999','10000+']).astype('object').fillna('unknown');strata['rural_urban_proxy']=np.where(strata.type.isin(['город','пгт','посёлок городского типа','рабочий посёлок']),'urban','rural_or_other')
 for dimension in ['population_size','region','rural_urban_proxy']:
  rows=[]
  for value,z in strata.groupby(dimension,dropna=False):
   for g in groups:
    b=z[f'services_osm2021_{g}_baseline_count'];c=z[f'services_osm2021_{g}_candidate_additional_count'];rows.append({'stratum':value,'service_group':g,'axis_denominator':len(z),'located_axis':int(z.located_axis.sum()),'baseline_positive_settlements':int(b.gt(0).sum()),'baseline_site_witnesses':int(b.sum()),'candidate_additional_site_witnesses':int(c.sum()),'union_positive_settlements':int((b+c).gt(0).sum()),'unknown_actual_service_settlements':int((b+c).eq(0).sum())})
  pd.DataFrame(rows).to_csv(HERE/f'coverage_by_{dimension}.csv',index=False)
 before_all=json.loads((HERE/'protocol.json').read_text())['source_sha256'];after_all={p:sha(Path(p))for p in before_all};assert before_all==after_all
 assert len(allobj)==len(old)+len(d) and allobj.site_id.is_unique and features.id.is_unique and len(features)==len(axis)
 assert len(h.raw)==len(d)+len(unresolved)
 for g in groups:
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   expected=allobj[allobj.service_group.eq(g)&allobj[key].notna()&allobj[f'count_{mode}_eligible']].drop_duplicates([key,'canonical_site_id']).shape[0];assert features[f'services_osm2021_{g}_{mode}_count'].sum()==expected
 assert not ((allobj.count_candidate_additional_eligible)&pd.Series([(u,c)in strict_pairs for u,c in zip(allobj.candidate_uid,allobj.canonical_site_id)])).any()
 receipt={'status':'ACTUALLY_RECOVERED_DATED_COMMERCE_RELATIONS_PENDING_INDEPENDENT_REVIEW','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_snapshot':'2021-01-01T21:42:03Z','source_url':'https://download.geofabrik.de/russia-210101.osm.pbf','parent_full_pbf_sha256':'1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe','input_sha256':before_all,'inputs_unchanged':True,'code_sha256':sha(Path(__file__)),'new_source_model_agreement_metrics_read':False,'model_assignments_used_for_source_filter_or_identity':False,'author_previous_role_read_frozen_baseline_model':True,'raw_selected_relations':len(h.raw),'assembled_valid_geometry_relations':len(d),'unresolved_relation_geometry':len(unresolved),'relation_statuses':d.recovery_status.value_counts().to_dict(),'assembled_relations_with_new_accepted_canonical_site':int((d.count_eligible&d.site_id.eq(d.canonical_site_id)).sum()),'old_explicit_negative_shop_tags_excluded_from_counts':int(old_negative.sum()),'new_explicit_negative_shop_tags_excluded_from_counts':int(new_negative.sum()),'explicit_negative_tag_rule':'shop=no/vacant/closed/disused/abandoned/demolished withnoindependentbank/post/market/governmentpurposeisnotpositiveother_retailwitness; rawassertions retained','old_raw_assertions_retained':len(old),'all_raw_assertions':len(allobj),'axis_rows':len(features),'axis_ids_with_count_change':int(changes.any_count_changed.sum()),'source_grain':'OSMphysicalserviceobservations,notbusinessregistry/legalentities/observedflows','identity_rule':'exactsameoriginaleducation.link baseline literalunique5km; spatialcandidate<=2.5km separated, explicitconflictguard; nofederalcitydonation','counting_rule':'samegroupuniquecanonicalsitewithinsettlement; strictidentitytakesprecedenceoverspatialcandidate; unresolved/overlapnotadditionalwitness','recovered_relation_point_method':'representative_pointinsidevalidassembledpolygon','same_date_new_geometry_not_opening_event':True,'no_physical_absence_claim':True,'no_capacity_or_actual_users_claim':True,'source_validity_limit':'OSMcoverageandfunctiontruth remainincomplete; noobservedcommuting/attractionclaim','summary':summary,'output_files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in sorted(HERE.glob('*.parquet'))}|{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in sorted(HERE.glob('*.csv'))}}
 (HERE/'relation_recovery_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items()if k not in ['input_sha256','summary','output_files']},ensure_ascii=False,indent=2),flush=True);print(pd.DataFrame(summary).to_string(index=False),flush=True)
if __name__=='__main__':main()

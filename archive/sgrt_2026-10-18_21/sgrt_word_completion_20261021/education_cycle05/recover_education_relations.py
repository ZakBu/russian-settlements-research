#!/usr/bin/env python3
"""Recover omitted historical education relations, with conservative campus deduplication.

This produces a new source version. Model assignments are not read. An object is
an OSM observation, never evidence that all education in a settlement is known.
"""
from pathlib import Path
import sys,json,hashlib,re,datetime
import numpy as np,pandas as pd,osmium
from shapely import wkb
from shapely.geometry import Point
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
sys.path.insert(0,str(BASE/'education'))
from build_school_features import link,school_group,xyz,dist,norm
PBF=Path('/workspace/scratch/medical_mass/history2021/medical_reference_complete.osm.pbf')
OLD=BASE/'education/education_objects_2021.parquet';AXIS=BASE/'axis/full_settlement_axis.parquet'
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
  if tags.get('amenity') in ['school','kindergarten','college','university']:
   self.raw[r.id]={'osm_id':r.id,'osm_type':'relation','name':tags.get('name'),'amenity':tags.get('amenity'),'healthcare':tags.get('healthcare'),'tags_json':json.dumps(tags,ensure_ascii=False),'member_refs_json':json.dumps([{'type':m.type,'ref':m.ref,'role':m.role}for m in r.members]),'source_last_edit':str(r.timestamp),'source_version':r.version}
 def area(self,a):
  if a.from_way() or a.tags.get('amenity') not in ['school','kindergarten','college','university']:return
  try:
   g=wkb.loads(self.factory.create_multipolygon(a),hex=True)
   if g.is_empty or not g.is_valid:raise ValueError('invalid_or_empty_polygon')
   self.geometry[a.orig_id()]=g
  except Exception as e:self.failures[a.orig_id()]=str(e)
def main():
 before={str(p):sha(p)for p in [PBF,OLD,AXIS]}
 assert before[str(PBF)]=='255bbe391bcee6d774476818ca0148a8aa83cbac06cadf0b2c9adc555b267352'
 h=Extract();h.apply_file(str(PBF),locations=True,idx='sparse_mem_array')
 rows=[];unresolved=[]
 for rid,r in h.raw.items():
  g=h.geometry.get(rid)
  if g is None:unresolved.append(dict(r,geometry_status=h.failures.get(rid,'no_assembled_polygon')));continue
  pt=g.representative_point();rows.append(dict(r,lon=pt.x,lat=pt.y,geometry_role='interior_representative_point_of_valid_relation_polygon',geometry_status='assembled_valid_polygon',polygon_wkb=g.wkb))
 d=pd.DataFrame(rows);d['site_id']='osm:relation:'+d.osm_id.astype(str);d['education_group']=d.apply(school_group,axis=1);d['source_snapshot']='2021-01-01';d['source']='OpenStreetMap via Geofabrik Russia historical snapshot';d['source_license']='ODbL-1.0'
 axis=pd.read_parquet(AXIS);d=link(d,axis)
 old=pd.read_parquet(OLD);old['recovery_status']='previous_node_way_assertion';old['count_eligible']=True
 old['source_version_cycle05']='frozen_old_assertion_retained'
 d['canonical_site_id']=d.site_id;d['possible_duplicate_of']=None;d['recovery_status']='new_relation_no_same_group_campus_overlap';d['count_eligible']=True;d['duplicate_evidence_json']='[]'
 trees={}
 for group,g in old.groupby('education_group'):
  trees[group]=(g,cKDTree(xyz(g.lat.to_numpy(),g.lon.to_numpy())))
 for idx,r in d.iterrows():
  oldg,tree=trees[r.education_group];poly=h.geometry[r.osm_id];pt=xyz([r.lat],[r.lon])[0]
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
   same_name=pd.notna(r['name'])and pd.notna(q['name']) and norm(r['name'])==norm(q['name'])
   ev={'site_id':q.site_id,'canonical_site_id':q.canonical_site_id,'name':q['name'],'inside_relation':contained,'distance_km':distance,'shared_member':member,'same_normalized_name':same_name}
   if contained or distance<=.05 or member:overlap.append(ev)
   if same_name and (contained or distance<=.05 or member):namesame.append(ev)
  if namesame:
   canonical=sorted({v['canonical_site_id']for v in namesame})
   if len(canonical)==1:
    d.at[idx,'canonical_site_id']=canonical[0];d.at[idx,'possible_duplicate_of']=canonical[0];d.at[idx,'recovery_status']='same_named_existing_campus_duplicate';d.at[idx,'duplicate_evidence_json']=json.dumps(namesame,ensure_ascii=False)
   else:
    d.at[idx,'count_eligible']=False;d.at[idx,'recovery_status']='ambiguous_multiple_same_named_existing_campuses';d.at[idx,'duplicate_evidence_json']=json.dumps(namesame,ensure_ascii=False)
  elif overlap:
   d.at[idx,'count_eligible']=False;d.at[idx,'recovery_status']='possible_existing_campus_overlap_not_counted_additionally';d.at[idx,'duplicate_evidence_json']=json.dumps(overlap,ensure_ascii=False)
  # Duplicate observations cannot assign the existing campus to two localities.
  if d.at[idx,'recovery_status']=='same_named_existing_campus_duplicate':
   q=old[old.canonical_site_id.eq(d.at[idx,'canonical_site_id'])];accepted=set(q.baseline_uid.dropna())|set(q.candidate_uid.dropna());incoming=r.baseline_uid if pd.notna(r.baseline_uid)else r.candidate_uid
   if pd.notna(incoming) and accepted and incoming not in accepted:
    d.at[idx,'count_eligible']=False;d.at[idx,'recovery_status']='duplicate_campus_locality_link_conflict_not_counted'
 # Apply the same duplicate guard among newly recovered relations themselves.
 # Parent grounds and separately tagged building relations must not add two
 # campus witnesses. Ambiguous nested children remain raw but uncounted.
 from shapely.strtree import STRtree
 polys=[h.geometry[rid]for rid in d.osm_id];spatial=STRtree(polys)
 handled=set()
 for i,p in enumerate(polys):
  for j in spatial.query(p,predicate='intersects'):
   j=int(j)
   if i==j or (min(i,j),max(i,j))in handled:continue
   handled.add((min(i,j),max(i,j)));a,b=d.iloc[i],d.iloc[j]
   if a.education_group!=b.education_group:continue
   overlap=p.intersection(polys[j]).area/max(min(p.area,polys[j].area),1e-20)
   if overlap<.95:continue
   # Prefer already anchored original campuses, then larger campus grounds.
   anchor_a=a.recovery_status=='same_named_existing_campus_duplicate';anchor_b=b.recovery_status=='same_named_existing_campus_duplicate'
   if anchor_a!=anchor_b:keep,drop=(i,j)if anchor_a else(j,i)
   else:keep,drop=(i,j)if p.area>=polys[j].area else(j,i)
   k,q=d.iloc[keep],d.iloc[drop]
   if not bool(q.count_eligible):continue
   if k.canonical_site_id==q.canonical_site_id:continue
   ev={'site_id':k.site_id,'canonical_site_id':k.canonical_site_id,'nested_polygon_fraction':overlap,'source':'recovered_relation_peer','same_normalized_name':pd.notna(k['name'])and pd.notna(q['name'])and norm(k['name'])==norm(q['name'])}
   previous=json.loads(d.at[drop,'duplicate_evidence_json']);d.at[drop,'duplicate_evidence_json']=json.dumps(previous+[ev],ensure_ascii=False)
   same_locality=(pd.isna(k.baseline_uid)or pd.isna(q.baseline_uid)or k.baseline_uid==q.baseline_uid)
   if ev['same_normalized_name'] and same_locality:
    d.at[drop,'canonical_site_id']=d.at[keep,'canonical_site_id'];d.at[drop,'possible_duplicate_of']=d.at[keep,'canonical_site_id'];d.at[drop,'recovery_status']='same_named_recovered_relation_campus_duplicate'
   else:
    d.at[drop,'count_eligible']=False;d.at[drop,'recovery_status']='nested_recovered_relation_campus_ambiguous_not_counted_additionally'
 # Resolve alias chains after relation-peer deduplication.
 aliases=dict(zip(d.site_id,d.canonical_site_id))
 for idx,r in d.iterrows():
  canon=r.canonical_site_id;seen=set()
  while canon in aliases and aliases[canon]!=canon and canon not in seen:
   seen.add(canon);canon=aliases[canon]
  d.at[idx,'canonical_site_id']=canon
 # An alias into an unaccepted recovered campus cannot revive it as a new count.
 eligibility=dict(zip(d.site_id,d.count_eligible))
 for idx,r in d.iterrows():
  if r.canonical_site_id in eligibility and not eligibility[r.canonical_site_id]:
   d.at[idx,'count_eligible']=False
   if r.recovery_status=='same_named_recovered_relation_campus_duplicate':d.at[idx,'recovery_status']='alias_of_ambiguous_recovered_campus_not_counted'
 d['source_version_cycle05']='omitted_relation_recovered_from_same_historical_pbf'
 # Retain all raw relation assertions, including assembly failures, in separate ledger.
 allraw=pd.DataFrame(list(h.raw.values()));allraw['geometry_assembled']=allraw.osm_id.isin(h.geometry);allraw.to_parquet(HERE/'relation_source_ledger.parquet',index=False)
 pd.DataFrame(unresolved).to_parquet(HERE/'relation_unresolved_geometry.parquet',index=False)
 d.to_parquet(HERE/'education_relations_2021.parquet',index=False)
 allobj=pd.concat([old,d.drop(columns=['polygon_wkb'])],ignore_index=True,sort=False)
 def levels(row):
  t=json.loads(row.tags_json);raw=t.get('isced:level');explicit=[]
  if raw:
   explicit=[int(v)for v in re.findall(r'(?<!\d)[0-8](?!\d)',raw)]
  primary=t.get('education_level:primary')=='yes';secondary=t.get('education_level:secondary')=='yes';name_signal=None
  if row.education_group=='school':
   name=norm(row['name']if pd.notna(row['name'])else'')
   for pattern,level in [(r'средняя|\bсош\b|гимназия|лицей',3),(r'основная|\bоош\b',2),(r'начальная|\bнош\b',1)]:
    if re.search(pattern,name):name_signal=level;break
  return pd.Series({'source_isced_levels_json':json.dumps(sorted(set(explicit))),'explicit_programme_primary':primary,'explicit_programme_secondary':secondary,'source_general_max_isced':max([v for v in explicit if v in [1,2,3]],default=None),'name_school_level_signal_unverified':name_signal,'capacity_explicit_nonnegative_numeric':numeric(t.get('capacity')),'students_explicit_nonnegative_numeric':numeric(t.get('students')),'programme_tag_evidence':bool(explicit)or primary or secondary})
 allobj=pd.concat([allobj,allobj.apply(levels,axis=1)],axis=1)
 # Exact locality evidence takes priority over a spatial candidate for the
 # samecanonicalcampus and settlement; candidate_additional must be additive.
 strict_pairs=set(zip(allobj.loc[allobj.count_eligible&allobj.baseline_uid.notna(),'baseline_uid'],allobj.loc[allobj.count_eligible&allobj.baseline_uid.notna(),'canonical_site_id']))
 allobj['count_baseline_eligible']=allobj.count_eligible&allobj.baseline_uid.notna()
 allobj['count_candidate_additional_eligible']=[bool(ok)and pd.notna(uid)and(uid,canon)not in strict_pairs for ok,uid,canon in zip(allobj.count_eligible,allobj.candidate_uid,allobj.canonical_site_id)]
 allobj.to_parquet(HERE/'education_objects_2021_repaired.parquet',index=False)
 # Schema-compatible replacement for the10 old count columns. Unknown actual
 # presence/capacity is nullable, never a false zero for unobserved functions.
 features=axis[['id']].copy();groups=['school','preschool','college','university','specialized_non_general_school']
 for g in groups:
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   z=allobj[allobj.education_group.eq(g)&allobj[key].notna()&allobj[f'count_{mode}_eligible']].drop_duplicates([key,'canonical_site_id'])
   features[f'education_osm2021_{g}_{mode}_count']=features.id.map(z.groupby(key).size()).fillna(0).astype('int32')
  col=f'education_osm2021_{g}_observed_presence';counts=features[f'education_osm2021_{g}_baseline_count']+features[f'education_osm2021_{g}_candidate_additional_count'];features[col]=pd.array(np.where(counts.gt(0),True,None),dtype='boolean')
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   z=allobj[allobj.education_group.eq(g)&allobj[key].notna()&allobj[f'count_{mode}_eligible']]
   # Partialcapacity is only the maximum observed source assertion percampus;
   # duplicate assertions must not inflate capacity totals.
   cap=z.groupby([key,'canonical_site_id']).capacity_explicit_nonnegative_numeric.max().dropna()
   features[f'education_osm2021_{g}_{mode}_capacity_observed_campuses']=features.id.map(cap.groupby(level=0).size()).fillna(0).astype('int32')
   features[f'education_osm2021_{g}_{mode}_partial_capacity_sum']=features.id.map(cap.groupby(level=0).sum(min_count=1))
 features['education_history_comparison_scope']='2021 mapped node/way/relation assertions; absence and snapshot change are not physical absence/closure; no census completeness'
 features['education_cycle05_source_version']='historical_relation_recovery_conservative_campus_dedup'
 features.to_parquet(HERE/'settlement_features_2021_full_axis.parquet',index=False)
 summary=[];old_features=pd.read_parquet(BASE/'education/settlement_features_2021_full_axis.parquet')
 for g in groups:
  z=allobj[allobj.education_group.eq(g)];rel=d[d.education_group.eq(g)];zok=z[z.count_eligible];strict=zok.baseline_uid.dropna();cand=zok.candidate_uid.dropna()
  summary.append({'education_group':g,'old_raw_node_way_assertions':int(old.education_group.eq(g).sum()),'recovered_raw_relation_assertions':int(rel.shape[0]),'relation_campus_duplicate':int(rel.recovery_status.isin(['same_named_existing_campus_duplicate','same_named_recovered_relation_campus_duplicate']).sum()),'relation_overlap_or_ambiguous_excluded_from_added_counts':int((~rel.count_eligible).sum()),'count_eligible_raw_assertions':len(zok),'baseline_settlements':strict.nunique(),'spatial_candidate_settlements':cand.nunique(),'union_settlements':pd.concat([strict,cand]).nunique(),'source_capacity_numeric_assertions':int(z.capacity_explicit_nonnegative_numeric.notna().sum()),'explicit_programme_tag_assertions':int(z.programme_tag_evidence.sum()),'old_baseline_settlements':int(old_features[f'education_osm2021_{g}_baseline_count'].gt(0).sum()),'old_union_settlements':int((old_features[f'education_osm2021_{g}_baseline_count']+old_features[f'education_osm2021_{g}_candidate_additional_count']).gt(0).sum())})
 pd.DataFrame(summary).to_csv(HERE/'education_level_inventory.csv',index=False)
 strata=axis[['id','region','type','population_2021','is_additive_source_unit','geography_status']].merge(features,on='id',validate='one_to_one');strata['has_accepted_coordinate']=strata.id.map(axis.set_index('id').lat.notna()&axis.set_index('id').lon.notna());strata['population_size']=pd.cut(strata.population_2021,[-1,0,99,499,1999,9999,np.inf],labels=['zero','1-99','100-499','500-1999','2000-9999','10000+']).astype('object').fillna('unknown');strata['rural_urban_proxy']=np.where(strata.type.isin(['город','пгт']),'urban','rural_or_other')
 for dimension in ['population_size','region','rural_urban_proxy']:
  output=[]
  for value,s in strata.groupby(dimension,dropna=False):
   for g in groups:
    b=s[f'education_osm2021_{g}_baseline_count'];c=s[f'education_osm2021_{g}_candidate_additional_count'];output.append({'stratum':value,'education_group':g,'axis_denominator':len(s),'located_axis':int(s.has_accepted_coordinate.sum()),'baseline_positive_settlements':int(b.gt(0).sum()),'baseline_site_witnesses':int(b.sum()),'candidate_site_witnesses':int(c.sum()),'union_positive_settlements':int((b+c).gt(0).sum()),'unknown_actual_function_settlements':int((b+c).eq(0).sum())})
  pd.DataFrame(output).to_csv(HERE/f'coverage_by_{dimension}.csv',index=False)
 after={str(p):sha(p)for p in [PBF,OLD,AXIS]};assert before==after
 assert allobj.site_id.is_unique and len(features)==173527 and features.id.is_unique
 assert len(h.raw)==len(d)+len(unresolved)
 for g in groups:
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   expected=allobj[allobj.education_group.eq(g)&allobj[key].notna()&allobj[f'count_{mode}_eligible']].drop_duplicates([key,'canonical_site_id']).shape[0]
   assert features[f'education_osm2021_{g}_{mode}_count'].sum()==expected
 receipt={'status':'ACTUALLY_RECOVERED_DATED_SOURCE_RELATIONS_PENDING_INDEPENDENT_REVIEW','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'author_has_read_model_assignments':False,'source_snapshot':'2021-01-01','source_url':'https://download.geofabrik.de/russia-210101.osm.pbf','inputs_sha256':before,'code_sha256':sha(Path(__file__)),'capacity_units':'Generic OSMcapacity unless explicitly provided bysource; partial numbers are not certified student seats','inputs_unchanged':before==after,'raw_education_relations':len(h.raw),'assembled_valid_geometry_relations':len(d),'unresolved_relation_geometry':len(unresolved),'relation_statuses':d.recovery_status.value_counts().to_dict(),'all_raw_assertions':len(allobj),'axis_rows':len(features),'coverage':summary,'no_physical_absence_claim':True,'no_opening_closure_claim':True,'capacity_is_partial_witness_not_total':True,'relation_point_method':'Representative point in valid assembledOSMrelationpolygon; notobservedschoolentrance','dedup_rule':'Samegroup exactnormalizednonemptyname andpolygoncontainment/<=50m/sharedmember aliasesexistingcampus; recoveredpeer>=95%polygoncontainment guardsnestedcampusduplicates; otheroverlap notadded tocounts; originalassertionsretained','external_limit':'Relation assembliesstillincomplete; schoolidentities/programmes/capacities notnationalcensus','output_files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in sorted(HERE.glob('*.parquet'))}|{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in sorted(HERE.glob('*.csv'))}}
 (HERE/'relation_recovery_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items()if k not in ['coverage','output_files','inputs_sha256']},ensure_ascii=False,indent=2));print(pd.DataFrame(summary).to_string(index=False))
if __name__=='__main__':main()

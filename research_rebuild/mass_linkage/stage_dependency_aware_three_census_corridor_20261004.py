#!/usr/bin/env python3
"""Stage candidate-only 2010 corridor bridges with explicit point dependency.

This rule requires exact unique typed source rows for all three censuses, the
already accepted 2002↔2021 component, and literal 2009/2011 classifier lineage.
Where a current component point was carried through that accepted path, it is
recorded as dependent corroboration, never described as an independent point.
"""
from __future__ import annotations
import hashlib,json,math,re,unicodedata
from collections import defaultdict,Counter
from pathlib import Path
import duckdb
import pandas as pd
from build_long_table import ACCEPTED_COORDINATE_STATUSES,ACCEPTED_EDGE_STATUSES,ACCEPTED_PROJECTION_STATUSES

W=Path('/workspace'); C=W/'settlements-work/continuation_20261004'; F=W/'settlements-delivery/continuation-consolidated-20261003'
OUT=C/'R4/dependency_aware_three_census_corridor_v1'
SELECTED=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'
EDGES=C/'accepted_mass_extensions/accepted_identity_edges.parquet'; POINTS=C/'accepted_mass_extensions/accepted_point_uses.parquet'
RES=C/'accepted_mass_extensions/joint_residual.parquet'
PRIOR=C/'R4/stable_type_corridor_mass/review_freeze_v2/all_candidate_dispositions.csv'
DISTRICT=C/'R4/district_context_semantic_audit/scoped_context_resolved_candidate_row_ids.csv'
PHYSICAL={'деревня','село','поселок','посёлок','город','пгт','станица','хутор','аул','кишлак','слобода','арбан','выселок','починок','местечко','разъезд','станция'}
BAD_SCOPE={'region','municipality','federal_city','federal_city_region','federal_territory','territorial_aggregate','federal_city_aggregate'}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def norm(x):
 if x is None or pd.isna(x):return ''
 return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(x)).casefold().replace('ё','е')).strip()
def digits(x):return re.sub(r'\D','',str(x or ''))
def event_asserted(s):
 try:x=json.loads(s or '{}')
 except Exception:return False
 v=x.get('legacy_verified_successor_settlement_id')
 return v is not None and str(v).strip() not in ('','0','None','nan')
def dist(a,b):
 lat1,lon1=a;lat2,lon2=b
 R=6371.0088
 p1,p2=math.radians(lat1),math.radians(lat2)
 dlat=math.radians(lat2-lat1);dlon=math.radians(lon2-lon1)
 z=math.sin(dlat/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
 return 2*R*math.asin(math.sqrt(z))

class UF:
 def __init__(self,frame,points):
  self.p={str(x):str(x) for x in frame.source_record_id}
  self.years={str(x):{} for x in frame.source_record_id}
  self.member={str(x):[str(x)] for x in frame.source_record_id}
  self.pointids=set(str(x) for x in points.target_source_record_id)
  self.idrow=frame.set_index(frame.source_record_id.astype(str),drop=False)
  for r in frame.itertuples(index=False):
   sid=str(r.source_record_id);y=int(r.census_year);v=self.years[sid].setdefault(y,[0,0,0,0]);pop=0 if pd.isna(r.population) else int(r.population)
   v[0]+=1;v[1]+=pop
   if sid in self.pointids:v[2]+=1;v[3]+=pop
 def find(self,x):
  x=str(x);p=self.p[x]
  if p!=x:self.p[x]=self.find(p)
  return self.p[x]
 def metrics(self,root):
  out={y:{'full_rows':0,'full_population':0,'joint_rows':0,'joint_population':0} for y in (2002,2010,2021)}
  z=self.years[self.find(root)]
  if all(y in z for y in (2002,2010,2021)):
   for y in z:
    a=z[y];out[y]={'full_rows':a[0],'full_population':a[1],'joint_rows':a[2],'joint_population':a[3]}
  return out
 def union(self,a,b):
  ra,rb=self.find(a),self.find(b)
  if ra==rb:return 'same_component'
  if set(self.years[ra])&set(self.years[rb]):return 'year_collision'
  lo,hi=sorted((ra,rb));self.p[hi]=lo
  for y,v in self.years[hi].items():
   if y in self.years[lo]:
    x=self.years[lo][y];self.years[lo][y]=[x[i]+v[i] for i in range(4)]
   else:self.years[lo][y]=v
  self.member[lo].extend(self.member[hi]);self.member[hi]=[];self.years[hi]={}
  return 'merged'
 def add_point(self,sid):
  sid=str(sid);self.pointids.add(sid);root=self.find(sid);r=self.idrow.loc[sid];y=int(r.census_year);p=0 if pd.isna(r.population) else int(r.population)
  self.years[root][y][2]+=1;self.years[root][y][3]+=p

def coverage(uf):
 out={y:{'full_rows':0,'full_population':0,'joint_rows':0,'joint_population':0} for y in (2002,2010,2021)}
 for r in list(uf.years):
  if uf.find(r)==r:
   m=uf.metrics(r)
   for y in out:
    for k in out[y]:out[y][k]+=m[y][k]
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=True);c=duckdb.connect()
 sel=c.execute("select source_record_id,census_year::int census_year,settlement_name,settlement_type,region_raw,region_norm,district_raw,population,population_scope,is_additive_settlement_record,source_sha256,source_path,source_sheet,source_row,source_locator,source_native_id,okato,oktmo from read_parquet(?) where census_year in (2002,2010,2021)",[str(SELECTED)]).df()
 sel.source_record_id=sel.source_record_id.astype(str);by=sel.set_index('source_record_id',drop=False)
 # Canonical accepted ledgers and status sets are checked in full. Nullable old
 # flags are not consulted for the baseline.
 ed=c.execute('select * from read_parquet(?)',[str(EDGES)]).df();pt=c.execute('select * from read_parquet(?)',[str(POINTS)]).df()
 if ed.decision_status.isna().any() or not set(ed.decision_status.astype(str))<=ACCEPTED_EDGE_STATUSES:raise RuntimeError('bad canonical identity status')
 if ed.selection_projection_status.isna().any() or not set(ed.selection_projection_status.astype(str))<=ACCEPTED_PROJECTION_STATUSES:raise RuntimeError('bad canonical projection status')
 if pt.coordinate_admission_status.isna().any() or not set(pt.coordinate_admission_status.astype(str))<=ACCEPTED_COORDINATE_STATUSES:raise RuntimeError('bad canonical coordinate status')
 uf=UF(sel,pt);all_year={}
 for r in sel.itertuples(index=False):
  all_year.setdefault((int(r.census_year),norm(r.settlement_name),norm(r.region_norm)),[]).append(str(r.source_record_id))
 for r in ed.itertuples(index=False):
  a,b=str(r.from_source_record_id),str(r.to_source_record_id)
  if a in uf.p and b in uf.p:uf.union(a,b)
 base=coverage(uf)
 expected={2002:(105536,116990219),2010:(105514,114527509),2021:(105542,115269151)}
 for y,pair in expected.items():
  if (base[y]['joint_rows'],base[y]['joint_population'])!=pair:raise RuntimeError(f'baseline mismatch {y}: {base[y]}')
 # Attach source evidence only for the candidate endpoints by exact source ID.
 ev=c.execute('select source_record_id,source_evidence_json from read_parquet(?)',[str(EVID)]).df()
 evid=dict(zip(ev.source_record_id.astype(str),ev.source_evidence_json.fillna('{}').astype(str)))
 # Validated raw classifier/GeoKLADR evidence from frozen stable corridor v2.
 v2=pd.read_csv(PRIOR,low_memory=False)
 v2=v2[(v2.from_year.eq(2010))&(v2.to_year.eq(2021))].copy()
 audit=pd.read_csv(DISTRICT,low_memory=False)
 resolved=set(audit.loc[audit.scoped_context_hold_resolved_candidate_only.eq(True),'from_source_record_id'].astype(str))
 residual=set(c.execute('select source_record_id from read_parquet(?) where census_year=2010',[str(RES)]).df().source_record_id.astype(str))
 candidates=[];holds=[]
 # Current point witnesses are taken from the existing 2002/2021 component.
 points_by_id=defaultdict(list)
 for p in pt.itertuples(index=False):
  points_by_id[str(p.target_source_record_id)].append(p)
 for q in v2.itertuples(index=False):
  oldid,curid=str(q.from_source_record_id),str(q.to_source_record_id)
  if oldid not in residual or oldid not in by.index or curid not in by.index:continue
  # Keep only unique all-type source keys at each publication year.
  old=by.loc[oldid];cur=by.loc[curid];key=(norm(old.settlement_name),norm(old.region_norm));year2002=all_year.get((2002,*key),[]);year2010=all_year.get((2010,*key),[]);year2021=all_year.get((2021,*key),[])
  if len(year2002)!=1 or len(year2010)!=1 or len(year2021)!=1:continue
  id02=year2002[0]
  a=by.loc[id02]
  why=[]
  types=[norm(a.settlement_type),norm(old.settlement_type),norm(cur.settlement_type)]
  if len(set(types))!=1 or types[0] not in PHYSICAL:why.append('three_census_types_not_same_physical_settlement_type')
  if not all(bool(x) for x in [a.is_additive_settlement_record,old.is_additive_settlement_record,cur.is_additive_settlement_record]):why.append('one_or_more_source_rows_not_explicitly_additive')
  if any(norm(x) in BAD_SCOPE for x in [a.population_scope,old.population_scope,cur.population_scope]):why.append('nonphysical_aggregate_population_scope')
  if int(q.historical_name_type_region_match_count or 0)!=1:why.append('historical_classifier_key_not_unique')
  if norm(q.historical_classifier_name_parsed)!=norm(old.settlement_name) or norm(q.historical_named_object_name_parsed_2009)!=norm(old.settlement_name):why.append('classifier_parsed_name_mismatch')
  if norm(q.historical_classifier_type_raw)!=norm(old.settlement_type) and norm(q.historical_geokladr_type_raw)!=norm(old.settlement_type):why.append('historical_classifier_type_mismatch')
  if digits(old.okato) and str(q.source_old_okato_matches_historic_classifier).casefold()=='false':why.append('2010_native_OKATO_conflicts_with_historical_classifier')
  if event_asserted(evid.get(oldid,'{}')) or event_asserted(evid.get(curid,'{}')) or event_asserted(evid.get(id02,'{}')):why.append('explicit_successor_event')
  districts=[norm(a.district_raw),norm(old.district_raw),norm(cur.district_raw)]
  known=[x for x in districts if x]
  district_rel='unknown_or_blank' if len(known)<3 else ('exact_normalized_agreement' if len(set(known))==1 else 'varies')
  context_reviewed=(oldid in resolved)
  if len(known)==3 and len(set(known))>1 and not context_reviewed:why.append('three_source_named_district_context_unresolved')
  # Existing 2002↔2021 component is the source of current-point context. Its
  # point origin and graph dependency are retained explicitly.
  r02,rc,ro=uf.find(id02),uf.find(curid),uf.find(oldid)
  if r02!=rc:why.append('2002_and_2021_not_already_same_accepted_component')
  if ro==rc:why.append('2010_already_same_accepted_component')
  elif set(uf.years[ro])&set(uf.years[rc]):why.append('accepted_graph_year_collision')
  compset=uf.member[r02]
  carriers=[]
  for sid in compset:
   for p in points_by_id.get(sid,[]):
    if not pd.isna(p.latitude) and not pd.isna(p.longitude):carriers.append(p)
  if not carriers:why.append('no_accepted_point_in_existing_2002_2021_component')
  rawpt=(float(q.historical_geokladr_raw_latitude),float(q.historical_geokladr_raw_longitude))
  distances=[dist(rawpt,(float(p.latitude),float(p.longitude))) for p in carriers]
  if distances and min(distances)>5:why.append('historical_2011_point_over_5km_from_existing_component_carriers')
  nearest=min(carriers,key=lambda p:dist(rawpt,(float(p.latitude),float(p.longitude))) if carriers else float('inf')) if carriers else None
  dependency='same_raw_historical_geokladr_origin_already_in_component' if nearest and str(getattr(nearest,'coordinate_source_sha256',''))==str(q.historical_geokladr_dbf_sha256) else 'existing_accepted_component_point_comparison_not_an_independent_identity_witness'
  row={'from_source_record_id':oldid,'from_year':2010,'to_source_record_id':curid,'to_year':2021,'relation':'same_place_candidate','candidate_status':'hold' if why else 'candidate_for_independent_review','candidate_only':not bool(why),'hold_reasons_json':json.dumps(sorted(set(why)),ensure_ascii=False),
       'source_2002_record_id':id02,'source_2002_file':a.source_path,'source_2002_sha256':a.source_sha256,'source_2002_locator':a.source_locator,'source_2002_type_raw':a.settlement_type,'source_2002_name_raw':a.settlement_name,'source_2002_region_raw':a.region_raw,'source_2002_district_raw':a.district_raw,
       'source_2010_file':old.source_path,'source_2010_sha256':old.source_sha256,'source_2010_locator':old.source_locator,'source_2010_native_id_opaque':old.source_native_id,'source_2010_type_raw':old.settlement_type,'source_2010_name_raw':old.settlement_name,'source_2010_region_raw':old.region_raw,'source_2010_district_raw':old.district_raw,'source_2010_population':old.population,'source_2010_okato_raw':old.okato,'source_2010_oktmo_raw':old.oktmo,
       'source_2021_file':cur.source_path,'source_2021_sha256':cur.source_sha256,'source_2021_locator':cur.source_locator,'source_2021_native_id_opaque':cur.source_native_id,'source_2021_type_raw':cur.settlement_type,'source_2021_name_raw':cur.settlement_name,'source_2021_region_raw':cur.region_raw,'source_2021_district_raw':cur.district_raw,'source_2021_population':cur.population,'source_2021_okato_raw':cur.okato,'source_2021_oktmo_raw':cur.oktmo,
       'canonical_name_key':key[0],'canonical_region_key':key[1],'all_type_year_unique_2002_2010_2021':True,'three_source_district_relation':district_rel,'district_semantic_audit_candidate_only':context_reviewed,
       'historical_classifier_sql_sha256':q.historical_classifier_sql_sha256,'historical_classifier_sql_line':q.historical_classifier_sql_line_1based,'historical_classifier_name_raw':q.historical_classifier_name_raw,'historical_classifier_name_parsed':q.historical_classifier_name_parsed,'historical_classifier_type_raw':q.historical_classifier_type_raw,'historical_classifier_okato2009_raw':q.historical_classifier_okato2009_raw,
       'historical_geokladr_dbf_sha256':q.historical_geokladr_dbf_sha256,'historical_geokladr_record':q.historical_geokladr_row_1based,'historical_geokladr_byte_offset':q.historical_geokladr_byte_offset_0based,'historical_geokladr_okato2011_raw':q.historical_geokladr_okato2011_raw,'historical_geokladr_name_raw':q.historical_geokladr_name_raw,'historical_geokladr_type_raw':q.historical_geokladr_type_raw,'historical_geokladr_lat':rawpt[0],'historical_geokladr_lon':rawpt[1],
       'existing_2002_2021_component_id':r02,'existing_component_point_witness_source_id':getattr(nearest,'target_source_record_id',None),'existing_component_point_source':getattr(nearest,'coordinate_source',None),'existing_component_point_file':getattr(nearest,'coordinate_source_file',None),'existing_component_point_sha256':getattr(nearest,'coordinate_source_sha256',None),'existing_component_point_locator':getattr(nearest,'coordinate_source_locator',None),'historical_to_existing_component_point_distance_km':None if not distances else min(distances),'existing_point_dependency_class':dependency,
       'old_source_evidence_json':evid.get(oldid,'{}'),'modern_source_evidence_json':evid.get(curid,'{}'),'2002_source_evidence_json':evid.get(id02,'{}'),
       'observed_status_event_json':'','point_use_candidate_only':(oldid not in uf.pointids and not bool(why)),
       'point_use_already_accepted':oldid in uf.pointids,'identity_admission':False,'point_admission':False}
  if row['candidate_only']:
   row['observed_status_event_json']=json.dumps({'event_type':'stable_type_same_place_candidate','type_2002':a.settlement_type,'type_2010':old.settlement_type,'type_2021':cur.settlement_type,'effective_date':'not claimed'},ensure_ascii=False)
   candidates.append(row)
  else:holds.append(row)

 # Deterministic union simulation of the candidate identity edges and the
 # matching 2011 point use on 2010. No point source/admission is changed.
 cand=sorted(candidates,key=lambda r:(-int(r['source_2010_population'] or 0),r['from_source_record_id']))
 sim=UF(sel,pt)
 for r in ed.itertuples(index=False):
  if str(r.from_source_record_id) in sim.p and str(r.to_source_record_id) in sim.p:sim.union(r.from_source_record_id,r.to_source_record_id)
 before=coverage(sim); accepted=[];dropped=[]
 for r in cand:
  status=sim.union(r['from_source_record_id'],r['to_source_record_id'])
  if status!='merged':r['simulation_union_result']=status;dropped.append(r);continue
  if r['point_use_candidate_only']:
   sim.add_point(r['from_source_record_id']);r['simulation_union_result']='merged_and_new_historical_point_staged'
  else:
   r['simulation_union_result']='merged_identity_existing_point_preserved'
  accepted.append(r)
 after=coverage(sim)
 pd.DataFrame(candidates+holds+dropped).to_csv(OUT/'all_candidate_dispositions.csv',index=False)
 pd.DataFrame(accepted).to_csv(OUT/'staged_identity_candidates.csv',index=False)
 point_candidates=[r for r in accepted if r['point_use_candidate_only']]
 pd.DataFrame(point_candidates).to_csv(OUT/'staged_point_use_candidates.csv',index=False)
 pd.DataFrame(holds+dropped).to_csv(OUT/'disjoint_holds.csv',index=False)
 summary={'status':'candidate_only_not_applied','rule':'Three whole-source-year unique exact normalized locality name/region/type observations (2002, 2010, 2021), source additivity/nonaggregate gates, 2009/2011 literal classifier typed physical object, existing accepted 2002↔2021 same-place component and point carrier; stage 2010↔2021 same_place. Stage a historical 2011 point-use candidate only when the 2010 endpoint has no already accepted point. Existing point dependency is exposed and not claimed independent. District mismatch passes only when exact row is covered by the semantic audit; otherwise known three-source differences hold.','source_pins':{str(p):sha(p) for p in [SELECTED,EVID,EDGES,POINTS,RES,PRIOR,DISTRICT]},'accepted_status_counts':{'edges':len(ed),'points':len(pt),'three_census_source_rows':len(sel)},'baseline_joint':before,'conditional_joint':after,'joint_population_gain_by_year':{str(y):after[y]['joint_population']-before[y]['joint_population'] for y in (2002,2010,2021)},'inventory':{'historical_2010_endpoint_rows_considered':len(v2),'candidate_pairs_pre_simulation':len(candidates),'graph_safe_pairs_after_simulation':len(accepted),'new_point_use_candidates_after_simulation':len(point_candidates),'identity_candidates_with_existing_point_preserved':sum(bool(x['point_use_already_accepted']) for x in accepted),'holds_or_redundant':len(holds)+len(dropped),'accepted_2002_2021_component_point_dependency_same_geokladr_origin':sum('same_raw_historical' in str(x['existing_point_dependency_class']) for x in accepted)},'hold_reason_marginals':dict(Counter(x for r in holds+dropped for x in json.loads(r['hold_reasons_json']))),'limitations':['All edges and point uses remain candidates.','Existing accepted points are never duplicated; where present, they remain attached to the source row.','No historical population is changed; no exact census date or population-boundary equivalence is claimed.','The current accepted point may derive from the same 2011 GeoKLADR source lineage; dependency is explicit and is not independent spatial corroboration.','District audit removes only the recorded scoped context hold and is not an identity admission.']}
 for f in sorted(OUT.iterdir()):
  if f.is_file() and f.name!='receipt.json':summary.setdefault('outputs_sha256',{})[f.name]=sha(f)
 (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str)+'\n')
 print(json.dumps({'inventory':summary['inventory'],'joint_population_gain_by_year':summary['joint_population_gain_by_year']},indent=2))

if __name__=='__main__':main()

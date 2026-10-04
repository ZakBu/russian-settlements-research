#!/usr/bin/env python3
"""Stage review-only rural/PGT type-change links with literal source witnesses.

The frozen primary temporal cohort is excluded. Candidate support combines a
literal OKATO 2009 / named typed GeoKLADR 2011 lineage and its raw physical
point with an independently-originated direct accepted 2021 point. It records
only observed status differences between census dates, not legal dates or
population/boundary comparability.
"""
from __future__ import annotations
import hashlib,json,math,re,sys
from collections import defaultdict,Counter
from pathlib import Path
import pandas as pd

ROOT=Path('/workspace/settlements-work')
OUT=ROOT/'continuation_20261004/R4/type_change_mass_v2'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
SOURCE_EVIDENCE=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
EDGES=ROOT/'continuation_20261004/accepted_mass_extensions/accepted_identity_edges.parquet'
POINTS=ROOT/'continuation_20261004/accepted_mass_extensions/accepted_point_uses.parquet'
COVERAGE=ROOT/'continuation_20261004/accepted_mass_extensions/coverage.json'
RAW_SQL=ROOT/'sources/raw_okato_2009_verification_v1/raw_classifier.parquet'
HIST_NAMED=ROOT/'coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet'
BLOCKED=ROOT/'continuation_20261003/blocked_point_reuse_targets_v1.json'
WD_RECEIPT=ROOT/'continuation_20261004/independent_review/wikidata_review_receipt_final.json'
PRIMARY_FREEZE=ROOT/'continuation_20261004/root/R4/temporal_mass/primary_comparison_extension/review_freeze_v3/staged_identity_edges.csv'
YEARS=(2002,2010,2021)
BAD_GRAINS={'federal_city_region','federal_territory','municipality','region','territorial_aggregate','federal_city','federal_city_aggregate'}
STATUS_SCOPE={'город','пгт','поселок','село','деревня','хутор','станица','аул','кишлак','слобода','арбан','выселок','починок','местечко'}

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def norm(v):
 if v is None or pd.isna(v):return ''
 return ' '.join(re.sub(r'\s+',' ',str(v).replace('ё','е').casefold()).split())
def blank(v):return v is None or pd.isna(v) or str(v).strip()==''
def truth(v):return not blank(v) and str(v).casefold() in {'true','1','t','yes'}
def false(v):return v is False or (not blank(v) and str(v).casefold() in {'false','0','f','no'})
def j(v):
 if isinstance(v,dict):return v
 if blank(v):return {}
 try:return json.loads(v)
 except Exception:return {}
def compact(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),sort_keys=True,default=str)
def code(v):return '' if blank(v) else re.sub(r'\.0$','',str(v).strip())
def classifier_type(v):
 s=norm(v)
 return {'деревня':'деревня','село':'село','поселок сельского типа':'поселок','поселок':'поселок','поселок городского типа':'пгт','пгт':'пгт','город':'город','станица':'станица','хутор':'хутор','станция':'станция','разъезд':'разъезд','слобода':'слобода'}.get(s,'')
def hav(a,b):
 p1,p2=map(math.radians,(a[0],b[0]));dp=p2-p1;dl=math.radians(b[1]-a[1]);z=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.asin(math.sqrt(z))

class DSU:
 def __init__(self,ids,years):
  self.ids=ids;self.ix={v:i for i,v in enumerate(ids)};self.p=list(range(len(ids)));self.rank=[0]*len(ids);self.mask=[1<<{2002:0,2010:1,2021:2}[int(y)] for y in years]
 def find(self,i):
  p=self.p[i]
  while p!=self.p[p]:p=self.p[p]
  while i!=p:q=self.p[i];self.p[i]=p;i=q
  return p
 def root(self,s):return self.find(self.ix[s])
 def union(self,a,b,check=False):
  x=self.find(self.ix[a]);y=self.find(self.ix[b])
  if x==y:return 'already_connected'
  if check and self.mask[x]&self.mask[y]:return 'same_year_component_collision'
  if self.rank[x]<self.rank[y]:x,y=y,x
  self.p[y]=x;self.mask[x]|=self.mask[y]
  if self.rank[x]==self.rank[y]:self.rank[x]+=1
  return 'merged'

def main():
 if (OUT/'freeze_manifest.json').exists():raise SystemExit(f'refusing to overwrite frozen review bundle: {OUT}')
 OUT.mkdir(parents=True,exist_ok=True)
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 from build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES,ACCEPTED_PROJECTION_STATUSES
 cols=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','region_norm','district_raw','municipality_raw','population','population_scope','is_additive_settlement_record','source_sha256','source_locator','okato','oktmo','latitude','longitude','coordinate_source']
 s=pd.read_parquet(SELECTED,columns=cols);s=s[s.census_year.isin(YEARS)].copy();s['source_record_id']=s.source_record_id.astype(str);s['census_year']=s.census_year.astype(int)
 s['name_key']=s.settlement_name.map(norm);s['region_key']=s.region_norm.map(norm);s['type_key']=s.settlement_type.map(norm);s['okato_key']=s.okato.map(code)
 ev=pd.read_parquet(SOURCE_EVIDENCE,columns=['source_record_id','census_year','source_evidence_json']);ev.source_record_id=ev.source_record_id.astype(str)
 s=s.merge(ev,on=['source_record_id','census_year'],how='left',validate='one_to_one')
 # Literal exact-name uniqueness across all selected locality types in the whole region/year.
 counts=s.groupby(['census_year','name_key','region_key'],dropna=False).source_record_id.nunique().to_dict()
 groups=defaultdict(lambda:defaultdict(list))
 for x in s.itertuples(index=False):
  if x.name_key and x.region_key:groups[(x.name_key,x.region_key)][int(x.census_year)].append(x)
 primary=pd.read_csv(PRIMARY_FREEZE,dtype=str).fillna('');primary_keys=set()
 primary_ids=set(primary.from_source_record_id.astype(str))|set(primary.to_source_record_id.astype(str))
 for v in primary.supporting_key:
  d=j(v);k=(norm(d.get('name_norm')),norm(d.get('region_norm')))
  if all(k):primary_keys.add(k)
 blocked=set(json.loads(BLOCKED.read_text())['blocked_target_source_record_ids'])
 receipt=json.loads(WD_RECEIPT.read_text())['decision'];hard=set(receipt['hard_geo_point_choice_hold_ids'][:3]);hard.update(receipt.get('four_frozen_known_holds_not_in_candidate_pool',[]));hard|=blocked
 # Raw 2009 classifier; only rows that match name/code/type literally count.
 sql=pd.read_parquet(RAW_SQL,columns=['historical_okato','name_raw','name','status','is_settlement_raw','source_line_1based','source_sha256','source_snapshot_version'])
 sql['c']=sql.historical_okato.map(code);sql_by=defaultdict(list)
 for q in sql.itertuples(index=False):
  if q.c:sql_by[q.c].append(q)
 # Enriched named GeoKLADR rows retain source DBF locator and both raw source pins.
 h=pd.read_parquet(HIST_NAMED,columns=['historical_okato_2011_raw','historical_okato_2009_raw','name','status','historical_point_modern_region','source_line_1based','record_number_1based','record_byte_offset_0based','source_sha256_2009','source_sha256_2011','is_deleted','is_settlement_raw','latitude_from_lat','longitude_from_long'])
 h['c09']=h.historical_okato_2009_raw.map(code);h['c11']=h.historical_okato_2011_raw.map(code);h['name_key']=h.name.map(norm);h['region_key']=h.historical_point_modern_region.map(norm)
 h=h[(~h.is_deleted.fillna(False)) & h.is_settlement_raw.astype(str).str.casefold().eq('t')].copy()
 h=h[pd.to_numeric(h.latitude_from_lat,errors='coerce').between(-90,90)&pd.to_numeric(h.longitude_from_long,errors='coerce').between(-180,180)].copy()
 h_by=defaultdict(list)
 for q in h.itertuples(index=False):
  for c in {q.c09,q.c11}:
   if c:h_by[c].append(q)
 # Actual direct accepted 2021 points only; propagated carriers are excluded.
 p=pd.read_parquet(POINTS,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','inference_modern_point_use_target_source_record_id','inference_identity_path_decision_ids_json','point_origin_kind','point_origin_file','point_origin_sha256','point_origin_locator','source_okato_raw','admission_rule','coordinate_application_family'])
 if p.coordinate_admission_status.isna().any() or not p.coordinate_admission_status.astype(str).isin(ACCEPTED_COORDINATE_STATUSES).all():raise RuntimeError('canonical coordinate ledger contains status outside build_long_table accepted set')
 point_status_counts=p.coordinate_admission_status.value_counts().to_dict()
 p.target_source_record_id=p.target_source_record_id.astype(str)
 all_point_targets=set(p.target_source_record_id)
 p=p[p.target_year.eq(2021)].copy()
 p=p[p.inference_modern_point_use_target_source_record_id.isna() & p.inference_identity_path_decision_ids_json.isna()].copy()
 p=p[~p.point_origin_kind.astype(str).str.startswith('retrospective_')].copy();p=p[pd.to_numeric(p.latitude,errors='coerce').between(-90,90)&pd.to_numeric(p.longitude,errors='coerce').between(-180,180)].copy()
 direct=defaultdict(list)
 for q in p.itertuples(index=False):
  direct[q.target_source_record_id].append({'lat':float(q.latitude),'lon':float(q.longitude),'kind':q.point_origin_kind,'file':q.point_origin_file,'sha256':q.point_origin_sha256,'locator':q.point_origin_locator,'okato':q.source_okato_raw,'rule':q.admission_rule,'family':q.coordinate_application_family,'origin_key':compact([q.point_origin_kind,q.point_origin_file,q.point_origin_sha256,q.point_origin_locator])})
 # Build accepted graph once; staged edges are simulated after the immutable base.
 ids=s.source_record_id.tolist();years=s.census_year.tolist();idset=set(ids)
 graph=pd.read_parquet(EDGES,columns=['from_source_record_id','to_source_record_id','decision_status','selection_projection_status','relation'])
 if graph.decision_status.isna().any() or not graph.decision_status.astype(str).isin(ACCEPTED_EDGE_STATUSES).all():raise RuntimeError('canonical identity ledger contains status outside build_long_table accepted set')
 if graph.selection_projection_status.isna().any() or not graph.selection_projection_status.astype(str).isin(ACCEPTED_PROJECTION_STATUSES).all():raise RuntimeError('canonical identity ledger has invalid projection status')
 if not graph.relation.eq('same_place').all():raise RuntimeError('canonical identity ledger contains non-same_place relation')
 accepted=[]
 for q in graph.itertuples(index=False):
  a,b=str(q.from_source_record_id),str(q.to_source_record_id)
  if a not in idset or b not in idset:raise RuntimeError('canonical accepted identity endpoint missing from selected census')
  accepted.append((a,b))
 if len(accepted)!=len(graph):raise RuntimeError('did not load every canonical accepted identity edge')
 dsu=DSU(ids,years)
 for a,b in accepted:dsu.union(a,b)
 base_points=all_point_targets
 def coverage(u):
  full=set()
  for ix,sid in enumerate(ids):
   r=u.find(ix)
   if u.mask[r]==7:full.add(r)
  fr=jr=fp=jp=0
  for x in s.itertuples(index=False):
   r=u.root(x.source_record_id)
   if r in full:fr+=1;fp+=0 if pd.isna(x.population) else int(x.population)
   if r in full and x.source_record_id in base_points:jr+=1;jp+=0 if pd.isna(x.population) else int(x.population)
  return {'full_chain_rows':fr,'full_chain_population':fp,'joint_full_rows':jr,'joint_full_population':jp}
 baseline=coverage(dsu)
 coverage_receipt=json.loads(COVERAGE.read_text())
 expected_full={'full_chain_rows':sum(int(x['axes']['full_census_chain']['rows']) for x in coverage_receipt['census_metrics']),'full_chain_population':sum(int(x['axes']['full_census_chain']['known_population']) for x in coverage_receipt['census_metrics'])}
 expected_joint={'joint_full_rows':sum(int(x['axes']['joint_admitted_coordinate_and_full_chain']['rows']) for x in coverage_receipt['census_metrics']),'joint_full_population':sum(int(x['axes']['joint_admitted_coordinate_and_full_chain']['known_population']) for x in coverage_receipt['census_metrics'])}
 if {k:baseline[k] for k in expected_full}!=expected_full or {k:baseline[k] for k in expected_joint}!=expected_joint:
  raise RuntimeError(f'base DSU coverage does not match accepted coverage.json: actual={baseline}; expected={expected_full|expected_joint}')
 # Only create pair records for groups with exactly one source observation per endpoint year.
 # Ambiguous whole-region exact-name cohorts are retained as one grouped hold per cohort.
 rows=[];ambiguous=[];seen_target=set()
 for (name,region),by in sorted(groups.items()):
  years_present=sorted(y for y in by if y in YEARS)
  if len(years_present)<2:continue
  changed=[(ya,yb) for ix,ya in enumerate(years_present) for yb in years_present[ix+1:] if len(by[ya])==len(by[yb])==1 and by[ya][0].type_key!=by[yb][0].type_key]
  if not changed:continue
  if (name,region) in primary_keys or any(x.source_record_id in primary_ids for y in years_present for x in by[y]):continue
  dup={y:len(by[y]) for y in years_present if len(by[y])>1}
  if dup:
   endpoints=[{'year':y,'source_record_id':x.source_record_id,'type_raw':x.settlement_type,'population':x.population,'source_file':x.source_file,'source_locator':x.source_locator} for y in years_present for x in by[y]]
   ambiguous.append({'name_norm_exact':name,'region_norm_exact':region,'years_present':years_present,'rows_per_year':compact({y:len(by[y]) for y in years_present}),'ambiguous_years_json':compact(dup),'endpoint_competitors_json':compact(endpoints),'hold_reason':'exact_name_homonym_across_locality_types_or_source_rows_in_whole_region_year','candidate_only':False,'identity_admission':False})
   continue
  for ya,yb in changed:
   a,b=by[ya][0],by[yb][0]
   # Limit to comparisons that finish in the contemporary 2021 source frame.
   if yb!=2021:continue
   ae=j(a.source_evidence_json);be=j(b.source_evidence_json)
   why=[]
   if a.type_key not in STATUS_SCOPE or b.type_key not in STATUS_SCOPE:why.append('outside_rural_PGT_and_related_named_settlement_status_scope')
   for x,e,label in [(a,ae,'from'),(b,be,'to')]:
    if not truth(x.is_additive_settlement_record) or not truth(e.get('is_additive_settlement_record')) or not false(e.get('is_federal_aggregate')) or truth(e.get('source_evidence_federal_aggregate_endpoint')) or norm(x.population_scope) in BAD_GRAINS:why.append(label+'_source_not_verified_additive_nonfederal_physical_NP')
    if x.source_record_id in hard:why.append(label+'_target_quarantine_or_WD_point_hold')
    if e.get('legacy_verified_successor_settlement_id') or truth(e.get('legacy_same_year_collision')):why.append(label+'_actual_successor_or_collision_evidence')
   if (name,region) in primary_keys:why.append('overlaps_frozen_primary_temporal_cohort')
   oldcode=code(a.okato);newcode=code(b.okato)
   # Exact historical source code must reproduce a literal typed classifier row and
   # a named physical 2011 GeoKLADR object with the same code/name/region.
   sources=[]
   for c in sorted({oldcode,newcode}-{''}):
    sqlrows=[q for q in sql_by.get(c,[]) if norm(q.name)==name and str(q.is_settlement_raw).casefold()=='t']
    hrows=[q for q in h_by.get(c,[]) if q.name_key==name and q.region_key==region and not q.is_deleted]
    for q in sqlrows:
     for z in hrows:
      if norm(q.status)==norm(z.status):
       sources.append({'matched_code':c,'sql_name_raw':q.name_raw,'sql_type_raw':q.status,'sql_line_1based':q.source_line_1based,'sql_source_sha256':q.source_sha256,'sql_snapshot':q.source_snapshot_version,'geokladr_name_raw':z.name,'geokladr_type_raw':z.status,'geokladr_region_norm':z.historical_point_modern_region,'geokladr_row_number_1based':z.record_number_1based,'geokladr_byte_offset_0based':z.record_byte_offset_0based,'geokladr_sql_line_1based':z.source_line_1based,'geokladr_2009_sha256':z.source_sha256_2009,'geokladr_2011_sha256':z.source_sha256_2011,'geokladr_raw_lat':float(z.latitude_from_lat),'geokladr_raw_lon':float(z.longitude_from_long),'source_object_type_matches_from_or_to':norm(z.status) in {a.type_key,b.type_key}})
   if not sources:why.append('no_exact_name_type_code_raw_2009_2011_named_physical_lineage')
   typed=[src for src in sources if classifier_type(src['sql_type_raw']) in {a.type_key,b.type_key} and classifier_type(src['geokladr_type_raw']) in {a.type_key,b.type_key}]
   if sources and not typed:why.append('raw_official_type_does_not_match_either_census_endpoint_status')
   modern=direct.get(b.source_record_id,[])
   if not modern:why.append('no_direct_accepted_2021_physical_point')
   # Compare each raw historical physical row with each independent 2021 direct point.
   witnesses=[];dist=[]
   for src in typed:
    for pt in modern:
     same=bool(src['geokladr_2011_sha256'] and src['geokladr_2011_sha256']==pt['sha256'] and src['geokladr_row_number_1based'] and str(src['geokladr_row_number_1based']) in str(pt['locator']))
     d=hav((src['geokladr_raw_lat'],src['geokladr_raw_lon']),(pt['lat'],pt['lon']))
     witnesses.append({'historical_raw':src,'modern_direct_accepted_point':pt,'distance_km':d,'same_raw_origin_excluded':same})
     if not same:dist.append(d)
   if sources and modern and not dist:why.append('historical_and_modern_witnesses_not_independent')
   if dist and min(dist)>5:why.append('historical_raw_vs_modern_direct_points_disagree_over_5km')
   if dist and max(dist)>5:why.append('alternative_raw_or_modern_points_span_over_5km')
   if not (truth(a.is_additive_settlement_record) and truth(b.is_additive_settlement_record)):pass
   # Graph union safety against overlapping census-year components.
   ra,rb=dsu.root(a.source_record_id),dsu.root(b.source_record_id)
   gs='already_connected' if ra==rb else ('same_year_component_collision' if dsu.mask[ra]&dsu.mask[rb] else 'safe_component_merge')
   if gs=='already_connected':why.append('already_connected_in_accepted_mass_graph')
   if gs=='same_year_component_collision':why.append('graph_merge_would_duplicate_census_year')
   rec={'edge_id':'TC-'+hashlib.sha256((a.source_record_id+'|'+b.source_record_id).encode()).hexdigest()[:18],'relation':'same_place','from_source_record_id':a.source_record_id,'from_year':ya,'to_source_record_id':b.source_record_id,'to_year':yb,'name_norm_exact':name,'from_name_raw':a.source_name_raw,'to_name_raw':b.source_name_raw,'from_type_raw':a.settlement_type,'to_type_raw':b.settlement_type,'observed_type_change_between_census_dates':True,'observed_type_change_interval':f'{ya}–{yb}; exact legal change date unknown','legal_type_change_date_claimed':False,'boundary_or_population_comparability_claimed':False,'from_region_raw':a.region_raw,'to_region_raw':b.region_raw,'expected_region_norm':region,'from_okato_raw':a.okato,'to_okato_raw':b.okato,'from_oktmo_raw':a.oktmo,'to_oktmo_raw':b.oktmo,'from_population':a.population,'to_population':b.population,'from_population_scope':a.population_scope,'to_population_scope':b.population_scope,'from_source_file':a.source_file,'from_source_sha256':a.source_sha256,'from_source_locator':a.source_locator,'from_source_native_id':a.source_native_id,'to_source_file':b.source_file,'to_source_sha256':b.source_sha256,'to_source_locator':b.source_locator,'to_source_native_id':b.source_native_id,'from_source_evidence_json':a.source_evidence_json,'to_source_evidence_json':b.source_evidence_json,'whole_region_all_type_name_unique_from':counts.get((ya,name,region))==1,'whole_region_all_type_name_unique_to':counts.get((yb,name,region))==1,'source_OKATO_2009_GeoKLADR_2011_lineage_json':compact(sources),'raw_official_type_matches_either_endpoint_status':bool(typed),'raw_historical_vs_direct_modern_point_witnesses_json':compact(witnesses),'independent_point_pair_count':len(dist),'min_point_distance_km':min(dist) if dist else None,'max_point_distance_km':max(dist) if dist else None,'accepted_graph_status_before_simulation':gs,'legacy_identity_flags_json':compact({'from':ae.get('legacy_identity_reasons'),'to':be.get('legacy_identity_reasons'),'retained_as_warnings':True}),'rule_status':'candidate_for_independent_review' if not why else 'hold_or_already_connected','hold_reasons_json':compact(why),'candidate_only':not why,'identity_admission':False}
   rows.append(rec)
 # Simulate only staged edges over an untouched reconstructed accepted graph.
 staged=[x for x in rows if x['candidate_only']]
 sim=DSU(ids,years)
 for a,b in accepted:sim.union(a,b)
 applied=[]
 for x in sorted(staged,key=lambda z:(z['from_year'],z['name_norm_exact'],z['from_source_record_id'],z['to_source_record_id'])):
  r=sim.union(x['from_source_record_id'],x['to_source_record_id'],True);x['simulation_union_result']=r
  if r=='merged':applied.append(x)
  elif r=='already_connected':
   x['candidate_only']=False;x['rule_status']='redundant_after_deterministic_candidate_union';x['hold_reasons_json']=compact(['already_connected_by_earlier_staged_candidate_edge'])
 after=coverage(sim)
 # Review sample: all candidates when small, then highest-pop holds and seeded risk strata.
 f=pd.DataFrame(rows);amb=pd.DataFrame(ambiguous)
 if f.empty:f=pd.DataFrame(columns=['edge_id','candidate_only','rule_status','hold_reasons_json','from_population','to_population'])
 f['pair_pop']=pd.to_numeric(f.from_population,errors='coerce').fillna(0)+pd.to_numeric(f.to_population,errors='coerce').fillna(0)
 picks=f.sort_values(['pair_pop','edge_id'],ascending=[False,True]).head(30)
 chosen=set(picks.edge_id.tolist())
 for status,q in [('candidate_for_independent_review',35),('hold_or_already_connected',35)]:
  sub=f[(f.rule_status==status)&~f.edge_id.isin(chosen)].sort_values('edge_id')
  if len(sub)>q:sub=sub.sample(q,random_state=20261004)
  chosen.update(sub.edge_id.tolist())
 sample=f[f.edge_id.isin(chosen)].sort_values(['pair_pop','edge_id'],ascending=[False,True]).head(100).copy()
 f=f.drop(columns=['pair_pop']);sample=sample.drop(columns=['pair_pop'])
 amb.to_csv(OUT/'whole_region_homonym_holds.csv',index=False,encoding='utf-8')
 f.to_csv(OUT/'observed_type_change_event_pairs.csv',index=False,encoding='utf-8')
 f[f.candidate_only].to_csv(OUT/'staged_status_change_edges.csv',index=False,encoding='utf-8')
 f[~f.candidate_only].to_csv(OUT/'type_change_holds.csv',index=False,encoding='utf-8')
 f[f.rule_status.eq('redundant_after_deterministic_candidate_union')].to_csv(OUT/'simulation_redundant_edges.csv',index=False,encoding='utf-8')
 sample.to_csv(OUT/'fixed_100_type_change_review_sample.csv',index=False,encoding='utf-8')
 reason_counts=Counter()
 for x in f.hold_reasons_json:
  for reason in j(x):reason_counts[reason]+=1
 outs=['whole_region_homonym_holds.csv','observed_type_change_event_pairs.csv','staged_status_change_edges.csv','type_change_holds.csv','simulation_redundant_edges.csv','fixed_100_type_change_review_sample.csv']
 summ={'status':'candidate_only_no_admissions','scope':'Rural/PGT status changes outside frozen primary temporal comparison cohort; 2002/2010 endpoints to 2021 only','rule':'Exact normalized name+region unique across all selected locality types in each endpoint census year; additive nonfederal source rows; exact native OKATO 2009 + named typed physical GeoKLADR 2011 raw code/name/type/region lineage; raw 2011 point and direct accepted 2021 point independently sourced and all compared alternatives within 5 km; event/collision/quarantine and graph-year-collision holds apply.','interpretation':'Only status labels observed at census dates are recorded. Legal change date, boundary continuity, and population comparability remain unknown. Legacy transition/similarity flags retained as warnings unless an actual event/collision gate fires.','canonical_ledger_policy':'All graph rows are included using build_long_table.ACCEPTED_EDGE_STATUSES and accepted projection statuses; optional candidate_only/admission_allowed projection booleans are ignored. All point uses are included for baseline joint coverage using build_long_table.ACCEPTED_COORDINATE_STATUSES; only direct noninferred 2021 point uses may witness the new route. Base coverage is asserted against accepted_mass_extensions/coverage.json per year.','canonical_ledger_status_counts':{'accepted_identity_edges':graph.decision_status.value_counts().to_dict(),'accepted_point_uses':point_status_counts},'primary_temporal_exclusion':{'frozen_file':str(PRIMARY_FREEZE),'sha256':sha(PRIMARY_FREEZE),'excluded_edge_rows':len(primary),'excluded_endpoint_ids':len(primary_ids),'excluded_name_region_keys':len(primary_keys)},'hard_holds':{'union_count':len(hard),'blocked31_file_sha256':sha(BLOCKED),'wikidata_receipt_sha256':sha(WD_RECEIPT)},'events':{'unique_unambiguous_changed_endpoint_pairs':len(f),'candidate_edges':int(f.candidate_only.sum()),'hold_or_already_connected_edges':int((~f.candidate_only).sum()),'whole_region_homonym_cohorts':len(amb),'homonym_competitor_rows':int(pd.to_numeric(amb.get('endpoint_competitors_json',pd.Series(dtype=str)).str.len(),errors='coerce').fillna(0).gt(0).sum()) if len(amb) else 0,'candidate_endpoint_population_sum_diagnostic_only':int(pd.to_numeric(f.loc[f.candidate_only,'from_population'],errors='coerce').fillna(0).sum()+pd.to_numeric(f.loc[f.candidate_only,'to_population'],errors='coerce').fillna(0).sum())},'hold_reason_counts':dict(reason_counts),'accepted_graph_simulation':{'base_accepted_graph_edges':len(accepted),'baseline':baseline,'baseline_matches_coverage_receipt':True,'after_deterministic_candidate_union':after,'simulated_merges':len(applied),'full_chain_population_increment':after['full_chain_population']-baseline['full_chain_population'],'joint_full_population_increment':after['joint_full_population']-baseline['joint_full_population'],'base_graph_untouched':True},'review_sample':{'rows':len(sample),'design':'top-population candidate/hold cases and seeded risk-status fill; descriptive only','labels':sample.rule_status.value_counts().to_dict()},'input_sha256':{str(q):sha(q) for q in [SELECTED,SOURCE_EVIDENCE,EDGES,POINTS,COVERAGE,RAW_SQL,HIST_NAMED,BLOCKED,WD_RECEIPT,PRIMARY_FREEZE]},'direct_2021_point_target_count':len(direct),'selected_rows_by_year':s.census_year.value_counts().sort_index().to_dict(),'outputs':{n:{'sha256':sha(OUT/n),'bytes':(OUT/n).stat().st_size} for n in outs}}
 (OUT/'summary.json').write_text(json.dumps(summ,ensure_ascii=False,indent=2,default=str)+'\n')
 print(json.dumps({'candidate_edges':summ['events']['candidate_edges'],'held_pairs':summ['events']['hold_or_already_connected_edges'],'homonym_groups':len(amb),'base':baseline,'after':after,'outputs':summ['outputs']},ensure_ascii=False,indent=2,default=str))

if __name__=='__main__':main()

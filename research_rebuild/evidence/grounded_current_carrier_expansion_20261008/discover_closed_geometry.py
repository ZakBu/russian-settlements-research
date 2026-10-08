from pathlib import Path
import sys,json,re,collections,math
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;APP=R/'research_rebuild/evidence/main_axis_residual_application63_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');P=APP/'applied_point_snapshot.parquet';C=APP/'applied_component_snapshot.csv.gz';F=APP/'applied_remaining_primary.csv.gz';V=R/'research_rebuild/evidence/main_axis_residual_registry_20261008/competitors/all_selected_native_competitors.parquet';con=duckdb.connect();f=con.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,is_additive_settlement_record,latitude,longitude,okato,oktmo,source_file,source_locator from read_parquet(?)',[str(S)]).fetchdf();ef=con.execute('select source_record_id,effective_region_norm from read_parquet(?)',[str(V)]).fetchdf().set_index('source_record_id').effective_region_norm.to_dict();f['region_norm']=f.source_record_id.map(ef);pts=con.execute('select target_source_record_id as source_record_id,latitude,longitude,coordinate_admission_status,coordinate_source_record_id,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,point_ledger_path from read_parquet(?)',[str(P)]).fetchdf().fillna('').set_index('source_record_id').to_dict('index');con.close();cs=pd.read_csv(C,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');f['root']=f.source_record_id.map(lambda x:cs[x]['root']);rd=f.set_index('source_record_id').to_dict('index');members=f.groupby('root').source_record_id.agg(list).to_dict();ys={r:{int(rd[i]['census_year']) for i in ids} for r,ids in members.items()};uf=UnionFind(members);remaining=set(pd.read_csv(F,usecols=['source_record_id']).source_record_id);newcur=set();currentroot={r:next((i for i in ids if int(rd[i]['census_year'])==2021),'') for r,ids in members.items()};bad=set(json.loads((R/'research_rebuild/evidence/temporal_residual_mass_20261008/state_snapshot_receipt.json').read_text())['conflicting_point_targets'])
EXTRA=O/'accepted_current_point_delta.csv.gz'
ex=pd.read_csv(EXTRA,dtype=str,keep_default_na=False)
for z in ex.to_dict('records'):
 sid=z['target_source_record_id'];assert int(rd[sid]['census_year'])==2021 and z['coordinate_admission_status']=='reviewed_extension_rule_accepted'
 assert sid not in pts
 pts[sid]={**z,'source_record_id':sid}
newcur.update(ex.target_source_record_id)
LIVE=R/'research_rebuild/evidence/current_live_named_residual_sources_20261008/accepted_point_use_delta.csv.gz'
for z in pd.read_csv(LIVE,dtype=str,keep_default_na=False).to_dict('records'):
 sid=z['target_source_record_id'];assert int(rd[sid]['census_year'])==2021 and z['coordinate_admission_status']=='reviewed_extension_rule_accepted'
 if sid not in pts:pts[sid]={**z,'source_record_id':sid};newcur.add(sid)

def nm(v):
 x=normalize(v);x=re.sub(r'^(?:поселок|село|деревня|хутор|пгт|рп|п\.|с\.|д\.)\s+','',x);x=re.sub(r'\s+(?:п\.|с\.|д\.|пгт|рп)$','',x);x=re.sub(r'\bим\.\s*','имени ',x);x=re.sub(r'^(?:свх\.?|совхоз)\s+','совхоза ',x)
 x=re.sub(r'ж\.?\s*[д/]\.?\s*','железнодорожная ',x);x=re.sub(r'\bжелезнодорожн(?:ая|ой|ого)\b','железнодорожная',x)
 x=re.sub(r'^(?:при\s+)?(?:железнодорожная\s+)?(?:станция|станции|разъезд|разъезда|ст\.)\s+','',x);x=re.sub(r'\s+(?:железнодорожная\s+)?станция$','',x)
 x=re.sub(r'[^а-яa-z0-9]+',' ',x)
 ordinal={'первый':'1','первая':'1','первое':'1','второй':'2','вторая':'2','второе':'2','третий':'3','третья':'3','третье':'3','четвертый':'4','четвертая':'4','четвертое':'4','пятый':'5','пятая':'5','пятое':'5','шестой':'6','шестая':'6','седьмой':'7','седьмая':'7','восьмой':'8','восьмая':'8','девятый':'9','девятая':'9','десятый':'10','десятая':'10'}
 words=x.split();words=[ordinal.get(w,w) for w in words];words=[re.sub(r'^(\d+)(?:я|й|е|ая|ое|ый|ой)$',r'\1',w) for w in words];words=[w for i,w in enumerate(words) if not (w in ['я','й','е','ая','ое','ый','ой'] and i and words[i-1].isdigit())];words=[w for w in words if w not in ['номер','n','no']]
 if words and words[0].isdigit() and not any(w.isdigit() for w in words[1:]):words=words[1:]+words[:1]
 return ' '.join(words)
def ty(v):
 x=normalize(v);return {'поселок городского типа':'пгт','рабочий поселок':'пгт','рп':'пгт','посёлок':'поселок'}.get(x,x)
physical={'город','пгт','село','деревня','поселок','хутор','станица','аул','слобода','станция','разъезд','железнодорожный объект','железнодорожная станция','железнодорожный разъезд','аал','арбан','починок','заимка','кордон','участок','местечко'}
def compatible(a,b):return a==b or (a in physical and b in physical)
def coord(sid):return (float(pts[sid]['latitude']),float(pts[sid]['longitude']))
G=R/'research_rebuild/evidence/temporal_after_new_current_points_20261008/resolved_candidate_geometry.parquet';gc=duckdb.connect().execute('select * from read_parquet(?)',[str(G)]).fetchdf().set_index('source_record_id').to_dict('index')
for sid,z in pts.items():
 if int(rd[sid]['census_year']) in [2002,2010] and sid not in gc:gc[sid]={'latitude':z['latitude'],'longitude':z['longitude'],'provider':'canonical_stage62_accepted_ownpoint','source_file':z['point_origin_file'],'source_locator':z['point_origin_locator'],'source_kind':z['point_origin_kind'],'coordinate_ref':z['point_ledger_path']}
def candidatecoord(sid):
 z=gc.get(sid);return (float(z['latitude']),float(z['longitude'])) if z is not None and 41<=float(z['latitude'])<=82 and 19<=float(z['longitude'])<=180 else None
def county(sid):
 z=rd[sid];v=county_key(z['district_raw'])
 if not v:
  cur=currentroot.get(z['root']);v=county_key(rd[cur]['district_raw']) if cur else ''
 return v
native=collections.defaultdict(list);current=collections.defaultdict(list);occupied=collections.defaultdict(set);aliases={r:{nm(rd[i]['settlement_name']) for i in ids} for r,ids in members.items()}
for sid,z in rd.items():
 if not z['is_additive_settlement_record']:continue
 native[(int(z['census_year']),z['region_norm'],nm(z['settlement_name']))].append(sid)
 if sid in pts:occupied[(int(z['census_year']),coord(sid))].add(sid)
 if int(z['census_year'])==2021:
  for name in aliases[z['root']]:current[(z['region_norm'],name)].append(sid)
reviewed=set()
for q in [O/'continuity_candidate_identity_pairs.csv.gz',O/'context_candidate_identity_pairs.csv.gz']:
 if q.exists():
  rr=pd.read_csv(q,dtype=str,keep_default_na=False)
  if len(rr):reviewed.update(tuple(sorted((x.from_source_record_id,x.to_source_record_id))) for x in rr.itertuples())
event=set(pd.read_csv(R/'research_rebuild/evidence/remaining_large_lifecycle_residual_20261008/accepted_direct_event_native_credit_union.csv',usecols=['source_record_id']).source_record_id);pins={str(q):sha(q) for q in [S,P,C,F,V,G,R/'research_rebuild/evidence/temporal_after_new_current_points_20261008/candidate_geometry_resolver_receipt.json',EXTRA,APP/'application_receipt.json']}
for n in ['direct_inclusion_transformation_path_native_credit_union.csv','formation_path_native_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv']:
 q=R/'research_rebuild/evidence/working_full_chain_20261007'/n
 if q.exists():pins[str(q)]=sha(q);event.update(pd.read_csv(q,usecols=['source_record_id']).source_record_id)
pins[str(EXTRA)]=sha(EXTRA)
pins[str(LIVE)]=sha(LIVE)
pins[str(LIVE.parent/'final_handoff_receipt.json')]=sha(LIVE.parent/'final_handoff_receipt.json')
pins[str(O/'current_admission_receipt.json')]=sha(O/'current_admission_receipt.json')
counts=collections.Counter();candidates=[];holds=[];rivals=[];seen=set();allnative_geom_occupancy=collections.defaultdict(set)
for sid,z in rd.items():
 g=candidatecoord(sid)
 if g is not None and z['is_additive_settlement_record']:allnative_geom_occupancy[(int(z['census_year']),g)].add(sid)
old=sorted([sid for sid in remaining if int(rd[sid]['census_year']) in [2002,2010]],key=lambda sid:-(float(rd[sid]['population']) if pd.notna(rd[sid]['population']) else 0))
for phase in ['new_independently_source_admitted_current_carriers','all_remaining_grounded_current_carriers_same_rule']:
 for sid in old:
  a=rd[sid];g=candidatecoord(sid)
  if g is None:counts[phase+': no valid imported candidate geometry']+=1;continue
  if sid in bad:counts['active accepted old point conflict']+=1;continue
  near=[];potential=[];name=nm(a['settlement_name']);ac=county(sid)
  for cur in current[(a['region_norm'],name)]:
   z=rd[cur]
   if not compatible(ty(a['settlement_type']),ty(z['settlement_type'])):continue
   if cur in pts and distance_km(g,coord(cur))<=5:near.append(cur)
   elif cur not in pts and (not ac or not county(cur) or ac==county(cur)):potential.append(cur)
  if len(near)!=1 or potential:counts[phase+': current physical candidate not uniquely sourcebound']+=1;continue
  bid=near[0]
  if phase=='new_independently_source_admitted_current_carriers' and bid not in newcur:continue
  if phase!='new_independently_source_admitted_current_carriers' and bid in newcur:continue
  pair=tuple(sorted([sid,bid]))
  if pair in reviewed or pair in seen:continue
  seen.add(pair);z=rd[bid];ar,br=uf.find(a['root']),uf.find(z['root'])
  if ar==br:counts['already accepted same component']+=1;continue
  if ys[ar]&ys[br]:counts['native repeated-year component']+=1;continue
  ids=list(dict.fromkeys(members[ar]+members[br]));reasons=[];ownpoint=coord(bid);distance=distance_km(g,ownpoint)
  if any(x in bad for x in ids):reasons.append('active accepted point conflict in component')
  if any(x in event for x in ids):reasons.append('known nonordinary lifecycle or territorial scope')
  if any(pd.isna(rd[x]['population']) for x in ids):reasons.append('protected unknown native population')
  if any(x in pts and distance_km(coord(x),ownpoint)>5 for x in ids):reasons.append('actual accepted ownpoint contradicts current anchor')
  if any(x not in pts and occupied[(int(rd[x]['census_year']),ownpoint)] for x in ids):reasons.append('explicit retrospective point would collide with same-year admitted ownpoint')
  if any(x in pts and len(occupied[(int(rd[x]['census_year']),coord(x))])>1 for x in ids):reasons.append('actual accepted ownpoint shared by other same-year native record')
  for x in ids:
   if int(rd[x]['census_year'])==2021:continue
   row=rd[x];xg=candidatecoord(x);xp=coord(x) if x in pts else xg
   if x not in pts and xg is not None and len(allnative_geom_occupancy[(int(row['census_year']),xg)])>1:reasons.append('imported candidate coordinate is shared by distinct same-year native records')
   if xp is None:
    # A second old member already joined natively may rely on the independently positive carrier/native path; do not create an extra imported-geometry claim.
    xp=ownpoint
   nearold=[];unplaced=[]
   for rival in native[(int(row['census_year']),row['region_norm'],nm(row['settlement_name']))]:
    rr=rd[rival]
    if not compatible(ty(row['settlement_type']),ty(rr['settlement_type'])):continue
    rp=coord(rival) if rival in pts else candidatecoord(rival)
    if rival==x or (rp is not None and distance_km(rp,ownpoint)<=5):nearold.append(rival)
    elif rp is None and (not county(x) or not county(rival) or county(x)==county(rival)):unplaced.append(rival)
    rivals.append({'target_source_record_id':x,'rival_source_record_id':rival,'year':int(row['census_year']),'rival_name':rr['settlement_name'],'rival_type':rr['settlement_type'],'rival_printed_county':rr['district_raw'],'rival_county_context':county(rival),'rival_geometry_kind':'accepted_ownpoint' if rival in pts else ('imported_candidate_only' if rp else 'no_geometry'),'rival_distance_to_grounded_current_km':distance_km(rp,ownpoint) if rp else '', 'competing_near_or_unplaced':rival in nearold or rival in unplaced})
   if nearold!=[x] or unplaced:reasons.append('actual same-year physical or unplaced sourcecounty namesake remains unresolved')
   ca=str(row['okato'] or '').removesuffix('.0');cb=str(z['okato'] or '').removesuffix('.0')
   if ca not in ['', 'None','nan'] and cb not in ['', 'None','nan'] and ca!=cb and ca+'000'!=cb and cb+'000'!=ca:reasons.append('actual native own OKATO contradiction without dated recoding proof')
  out={'from_source_record_id':sid,'to_source_record_id':bid,'from_year':int(a['census_year']),'to_year':2021,'name':a['settlement_name'],'region':a['region_norm'],'from_type':a['settlement_type'],'to_type':z['settlement_type'],'from_county':a['district_raw'],'to_county':z['district_raw'],'from_population':a['population'],'to_population':z['population'],'distance_km':distance,'imported_old_candidate_latitude':g[0],'imported_old_candidate_longitude':g[1],'grounded_current_latitude':ownpoint[0],'grounded_current_longitude':ownpoint[1],'current_anchor_is_new_current_point':bid in newcur,'discovery_phase':phase,'component_source_ids_json':json.dumps(ids,ensure_ascii=False),'old_component_years':','.join(map(str,sorted(ys[ar]))),'other_component_years':','.join(map(str,sorted(ys[br]))),'old_geometry_status':'actual independent named-NP source candidate disambiguation only; not admitted or measured historic coordinates','candidate_geometry_provider':gc[sid]['provider'],'candidate_geometry_source_file':gc[sid]['source_file'],'candidate_geometry_source_locator':gc[sid]['source_locator'],'candidate_geometry_source_kind':gc[sid]['source_kind'],'candidate_geometry_coordinate_ref':gc[sid]['coordinate_ref']}
  if reasons:out['held_reason']='; '.join(sorted(set(reasons)));holds.append(out);counts.update(set(reasons));continue
  candidates.append(out);ny=ys[ar]|ys[br];uf.union(ar,br);nr=uf.find(ar);ys[nr]=ny;members[nr]=ids;counts[phase+': candidate source-positive imported-geometry route']+=1
keep={i for z in candidates for i in json.loads(z['component_source_ids_json'])};rivals=[x for x in rivals if x['target_source_record_id'] in keep]
for name,rows in [('geometry_candidate_identity_pairs.csv.gz',candidates),('geometry_held_identity_pairs.csv.gz',holds),('geometry_all_native_namesake_competitors.csv.gz',rivals)]:pd.DataFrame(rows).drop_duplicates().to_csv(O/name,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':63,'no_State_load':True,'candidate_generation_implies_admission':False,'candidate_geometry_never_historic_measurement_claim':True,'new_current_anchors_candidates':sum(x['current_anchor_is_new_current_point'] for x in candidates),'all_remaining_grounded_anchors_candidates':sum(not x['current_anchor_is_new_current_point'] for x in candidates),'candidate_pairs':len(candidates),'held_pairs':len(holds),'outcomes':dict(counts),'reviewed_prior_pairs_skipped':len(reviewed),'input_pins':pins,'output_pins':{q.name:sha(q) for q in O.glob('geometry*.csv.gz')}};(O/'geometry_candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))

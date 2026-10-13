from pathlib import Path
import sys,json,re,collections,math
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;APP=R/'research_rebuild/evidence/primary_residual_mass_application_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');P=APP/'applied_point_snapshot.parquet';C=APP/'applied_component_snapshot.csv.gz';F=APP/'applied_remaining_primary.csv.gz';V=R/'research_rebuild/evidence/main_axis_residual_registry_20261008/competitors/all_selected_native_competitors.parquet';con=duckdb.connect();f=con.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,is_additive_settlement_record,latitude,longitude,okato,oktmo,source_file,source_locator from read_parquet(?)',[str(S)]).fetchdf();ef=con.execute('select source_record_id,effective_region_norm from read_parquet(?)',[str(V)]).fetchdf().set_index('source_record_id').effective_region_norm.to_dict();f['region_norm']=f.source_record_id.map(ef);pts=con.execute('select source_record_id,latitude,longitude,coordinate_admission_status,coordinate_source_record_id,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,point_ledger_path from read_parquet(?)',[str(P)]).fetchdf().fillna('').set_index('source_record_id').to_dict('index');con.close();cs=pd.read_csv(C,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');f['root']=f.source_record_id.map(lambda x:cs[x]['root']);rd=f.set_index('source_record_id').to_dict('index');members=f.groupby('root').source_record_id.agg(list).to_dict();ys={r:{int(rd[i]['census_year']) for i in ids} for r,ids in members.items()};uf=UnionFind(members);remaining=set(pd.read_csv(F,usecols=['source_record_id']).source_record_id);newp=pd.read_csv(APP/'accepted_point_use_delta.csv.gz',dtype=str,keep_default_na=False);newcur={i for i in newp.target_source_record_id if int(rd[i]['census_year'])==2021};assert len(newcur)==1047;currentroot={r:next((i for i in ids if int(rd[i]['census_year'])==2021),'') for r,ids in members.items()};bad=set(json.loads((R/'research_rebuild/evidence/temporal_residual_mass_20261008/state_snapshot_receipt.json').read_text())['conflicting_point_targets'])
EXTRA=R/'research_rebuild/evidence/current_positive_residual_point_sources_20261008/accepted_point_use_delta.csv.gz'
ex=pd.read_csv(EXTRA,dtype=str,keep_default_na=False)
for z in ex.to_dict('records'):
 sid=z['target_source_record_id'];assert int(rd[sid]['census_year'])==2021 and z['coordinate_admission_status']=='reviewed_extension_rule_accepted'
 if sid not in pts:pts[sid]={**z,'source_record_id':sid}
newcur.update(ex.target_source_record_id)
EXTRA604=R/'research_rebuild/evidence/current_remaining_cached_named_sources_20261008/accepted_point_use_delta.csv.gz'
ex604=pd.read_csv(EXTRA604,dtype=str,keep_default_na=False)
for z in ex604.to_dict('records'):
 sid=z['target_source_record_id'];assert int(rd[sid]['census_year'])==2021 and z['coordinate_admission_status']=='reviewed_extension_rule_accepted'
 if sid in pts:assert (float(pts[sid]['latitude']),float(pts[sid]['longitude']))==(float(z['latitude']),float(z['longitude']))
 else:pts[sid]={**z,'source_record_id':sid}
newcur.update(ex604.target_source_record_id)

def nm(v):
 x=normalize(v);x=re.sub(r'^(?:поселок|село|деревня|хутор|пгт|рп|п\.|с\.|д\.)\s+','',x);x=re.sub(r'\s+(?:п\.|с\.|д\.|пгт|рп)$','',x);x=re.sub(r'\bим\.\s*','имени ',x);x=re.sub(r'^(?:свх\.?|совхоз)\s+','совхоза ',x);return ' '.join(re.sub(r'["«»]','',x).split())
def ty(v):
 x=normalize(v);return {'поселок городского типа':'пгт','рабочий поселок':'пгт','рп':'пгт','посёлок':'поселок'}.get(x,x)
physical={'пгт','село','деревня','поселок','хутор','станица','аул','слобода'}
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
event=set(pd.read_csv(R/'research_rebuild/evidence/remaining_large_lifecycle_residual_20261008/accepted_direct_event_native_credit_union.csv',usecols=['source_record_id']).source_record_id);pins={str(q):sha(q) for q in [S,P,C,F,V,G,R/'research_rebuild/evidence/temporal_after_new_current_points_20261008/candidate_geometry_resolver_receipt.json',APP/'accepted_point_use_delta.csv.gz',APP/'application_receipt.json']}
for n in ['direct_inclusion_transformation_path_native_credit_union.csv','formation_path_native_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv']:
 q=R/'research_rebuild/evidence/working_full_chain_20261007'/n
 if q.exists():pins[str(q)]=sha(q);event.update(pd.read_csv(q,usecols=['source_record_id']).source_record_id)
pins[str(EXTRA)]=sha(EXTRA)
pins[str(EXTRA604)]=sha(EXTRA604)

# Diagnose the exact 7,966 route failures against the same grounded carrier set that generated Stage63 candidates.
out=[];gate=collections.Counter();rawcoded=duckdb.connect().execute('select * from read_parquet(?)',[str(Path('/workspace/settlements-work/grounded_current_carrier_expansion_20261008/source_positive_coded_current_candidates.parquet'))]).fetchdf().set_index('target_source_record_id').to_dict('index')
for sid in remaining:
 a=rd[sid]
 if int(a['census_year']) not in [2002,2010]:continue
 g=candidatecoord(sid)
 if g is None:continue
 name=nm(a['settlement_name']);ac=county(sid);near=[];potential=[];allcur=[]
 for cur in current[(a['region_norm'],name)]:
  z=rd[cur]
  if not compatible(ty(a['settlement_type']),ty(z['settlement_type'])):continue
  cp=coord(cur) if cur in pts else None;d=distance_km(g,cp) if cp else None
  q={'source_record_id':cur,'name':z['settlement_name'],'type':z['settlement_type'],'county':z['district_raw'],'has_accepted_current_ownpoint':cur in pts,'candidate_geometry_distance_to_accepted_current_km':d,'raw_exactcoded_level6_positive':cur in rawcoded,'raw_point_equals_accepted_point':bool(cur in rawcoded and cp and abs(float(rawcoded[cur]['latitude'])-cp[0])<1e-7 and abs(float(rawcoded[cur]['longitude'])-cp[1])<1e-7)}
  allcur.append(q)
  if cp and d<=5:near.append(cur)
  elif cp is None and (not ac or not county(cur) or ac==county(cur)):potential.append(cur)
 if len(near)==1 and not potential:continue
 if len(near)>1:why='multiple actual accepted current physical namesakes within5km'
 elif len(near)==1 and potential:why='one accepted nearby carrier plus unplaced samecounty current namesake'
 elif potential:why='no accepted nearby carrier; current samecounty named NP lacks accepted ownpoint'
 elif allcur:why='literal compatible current counterparts exist but all accepted ownpoints >5km from old candidate'
 else:why='no literal compatible current counterpart under existing alias/type rules'
 gate[why]+=1;out.append({'source_record_id':sid,'year':int(a['census_year']),'name':a['settlement_name'],'type':a['settlement_type'],'region':a['region_norm'],'county':a['district_raw'],'native_population':a['population'],'route_gate_reason':why,'old_candidate_geometry_provider':gc[sid]['provider'],'old_candidate_source_locator':gc[sid]['source_locator'],'actual_current_counterparts_json':json.dumps(allcur,ensure_ascii=False,default=str),'near_accepted_current_count':len(near),'unplaced_samecounty_current_count':len(potential)})
assert len(out)==7966,len(out)
pd.DataFrame(out).to_csv(O/'exact_7966_current_grounding_gate_diagnostics.csv.gz',index=False,compression={'method':'gzip','mtime':0});receipt={'baseline_carriers':'actual62 accepted + independently admitted133+604 Stage63 current packets; reproduces exact prior7966 routes','candidate_routes':len(out),'not_accepted_or_applied_gains':True,'gate_counts':dict(gate),'native_population_by_gate_and_year':pd.DataFrame(out).groupby(['route_gate_reason','year']).native_population.sum().to_dict() if False else [{'gate':k[0],'year':int(k[1]),'native_population':int(v)} for k,v in pd.DataFrame(out).groupby(['route_gate_reason','year']).native_population.sum().items()],'top50_native_population_routes':sorted(out,key=lambda z:-(float(z['native_population']) if pd.notna(z['native_population']) else 0))[:50],'input_pins':pins,'output_pins':{str(O/'exact_7966_current_grounding_gate_diagnostics.csv.gz'):sha(O/'exact_7966_current_grounding_gate_diagnostics.csv.gz')}};(O/'current_grounding_gate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,default=str)+'\n');print(json.dumps({'gate_counts':dict(gate),'native_population_by_gate_and_year':receipt['native_population_by_gate_and_year']},ensure_ascii=False))

from pathlib import Path
import pandas as pd,duckdb,ast,collections,json,re,unicodedata,sys,time,resource
START=time.monotonic();O=Path(__file__).parent;PACK=O.parent;E=PACK.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize,distance_km
RULE=E/'current_cached_ownarticle_residual_expansion_20261008/review_articles.py';t=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
B=E/'main_axis_residual_application65_20261008';S=B/'applied_state_observations.parquet';C=B/'applied_component_snapshot.csv.gz';P=B/'applied_point_snapshot.parquet';F=PACK/'actual65_current_remaining.csv.gz';N=PACK/'accepted_point_use_delta.csv.gz';RES=E/'temporal_published_code_alias_mass_20261008/candidate_identity_pairs.csv.gz'
reserved=pd.read_csv(RES,dtype=str,keep_default_na=False);reserved=set(reserved.from_source_record_id)|set(reserved.to_source_record_id);pending=pd.read_csv(N,dtype=str,keep_default_na=False).rename(columns={'target_source_record_id':'source_record_id'});f=pd.read_csv(F,dtype=str,keep_default_na=False);f=f[f.component_years.eq('2021') & (f.has_own_point.eq('True')|f.source_record_id.isin(pending.source_record_id)) & ~f.source_record_id.isin(reserved)].sort_values('population',key=lambda a:pd.to_numeric(a,errors='coerce'),ascending=False)
keys={(namekey(z['settlement_name']),regionkey(z['region_norm']),county(z['district_raw'])) for z in f.to_dict('records')};allname=collections.defaultdict(list);c=duckdb.connect();c.execute("SET memory_limit='256MB'");cur=c.execute('select * from read_parquet(?) where population_scope in (\'settlement\',\'settlement_aggregate\') and district_raw is not null',[str(S)]);cols=[x[0] for x in cur.description];scanned=0
while True:
 batch=cur.fetchmany(5000)
 if not batch:break
 for tup in batch:
  z=dict(zip(cols,tup));scanned+=1
  if not z['district_raw'] or not z['settlement_name']:continue
  key=(namekey(z['settlement_name']),regionkey(z['region_norm']),county(z['district_raw']))
  if key in keys:allname[(int(z['census_year']),key)].append(z)
print('streamed',scanned,'relevant native observations',sum(map(len,allname.values())),flush=True)
rough=[]
for z in f.to_dict('records'):
 key=(namekey(z['settlement_name']),regionkey(z['region_norm']),county(z['district_raw']));curr=allname.get((2021,key),[])
 if len(curr)!=1:continue
 for yr in [2002,2010]:
  old=allname.get((yr,key),[])
  if len(old)==1 and old[0]['source_record_id'] not in reserved and old[0]['root']!=z['root']:rough.append((z,curr[0],old[0],key))
rootsneeded={x['root'] for z,v,q,k in rough for x in [z,q]};rt=pd.DataFrame({'root':list(rootsneeded)});c.register('wanted_roots',rt);members=c.execute('select s.source_record_id,s.root,s.census_year from read_parquet(?) s join wanted_roots using(root)',[str(S)]).fetchdf();years=collections.defaultdict(set);ms=collections.defaultdict(list)
for z in members.to_dict('records'):years[z['root']].add(int(z['census_year']));ms[z['root']].append(z['source_record_id'])
c.register('wanted_members',members[['source_record_id','root']]);pt=c.execute('select p.source_record_id,p.latitude,p.longitude,p.coordinate_source_record_id,p.point_origin_file,p.point_origin_sha256,p.point_origin_locator,p.point_origin_kind,p.coordinate_admission_status,w.root from read_parquet(?) p join wanted_members w using(source_record_id)',[str(P)]).fetchdf();c.close();pr={z['source_record_id']:z for z in pt.to_dict('records')};rootpoints=collections.defaultdict(list)
for z in pending.to_dict('records'):
 if z['source_record_id'] in set(members.source_record_id):z['root']=members.set_index('source_record_id').root[z['source_record_id']];pr[z['source_record_id']]=z
for z in pr.values():rootpoints[z['root']].append(z)
out=[];holds=[]
for z,v,q,key in rough:
 sid=z['source_record_id'];oid=q['source_record_id'];a=z['root'];b=q['root'];reason=[]
 if sid not in pr:continue
 if typekey(z['settlement_type'])!=typekey(q['settlement_type']):reason.append('source_physical_type_mismatch')
 if years[a]&years[b]:reason.append('component_sameyear_overlap_independent_identity_not_established')
 xy=(float(pr[sid]['latitude']),float(pr[sid]['longitude']));far=[]
 for p in rootpoints[b]:
  d=distance_km(xy,(float(p['latitude']),float(p['longitude'])))
  if d>5:far.append({'source_record_id':p['source_record_id'],'distance_km':d,'coordinate_source_record_id':p.get('coordinate_source_record_id')})
 if far:reason.append('historic_component_point_over5km_positive_conflict_no_supersession')
 row={'current_source_record_id':sid,'historic_source_record_id':oid,'historic_census_year':q['census_year'],'current_population2021':z['population'],'historic_population':q['population'],'current_settlement_name':z['settlement_name'],'current_settlement_type':z['settlement_type'],'source_region':z['region_norm'],'current_native_district':z['district_raw'],'historic_native_district':q['district_raw'],'exact_normalized_name_region_county_key_json':json.dumps(key,ensure_ascii=False),'current_alltype_native_namesakes':1,'historic_alltype_native_namesakes':1,'current_root':a,'historic_root':b,'current_component_years':','.join(map(str,sorted(years[a]))),'historic_component_years':','.join(map(str,sorted(years[b]))),'current_component_members_json':json.dumps(ms[a],ensure_ascii=False),'historic_component_members_json':json.dumps(ms[b],ensure_ascii=False),'historic_native_observation_json':json.dumps(q,ensure_ascii=False,default=str),'current_native_observation_json':json.dumps(v,ensure_ascii=False,default=str),'current_independently_admitted_or_planned_ownpoint_json':json.dumps(pr[sid],ensure_ascii=False,default=str),'historic_component_conflict_witnesses_json':json.dumps(far,ensure_ascii=False),'proposed_identity_rule':'independently published same normalized literal settlement name/type/region and explicit actual source county; unique alltype native county-name in each year; no sameyear component overlap or historic point>5km; positive current named geography supports physical identity, finite population not identity evidence','status':'SOURCE_COUNTY_COUNTERPART_PROPOSAL_NOT_ADMITTED','hold_reasons':';'.join(reason),'historical_coordinate_use_asserted':False,'population_comparability_asserted':False,'historical_raw_workbook_literal_reopened':False}
 (holds if reason else out).append(row)
for fn,rows in [('source_bound_exact_county_history_counterpart_proposals',out),('source_county_history_proposal_holds',holds)]:pd.DataFrame(rows).to_csv(O/(fn+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
u={z['current_source_record_id']:z for z in out};r={'actual_baseline':65,'current_singleton_with_ownpoint_targets':len(f),'source_bound_counterpart_proposals':len(out),'unique_current_native_UIDs':len(u),'unique_current_known_population2021':sum(float(z['current_population2021']) for z in u.values() if z['current_population2021']),'historic_year_counts':dict(collections.Counter(z['historic_census_year'] for z in out)),'proposal_holds':len(holds),'identity_edges_or_retrospective_points_admitted':0,'finite_current_population_used_as_identity_evidence':False,'NULL_population_imputed_as_zero':False,'actual_State_loads':0,'other_temporal_owncode_route_reserved_endpoints_excluded':len(reserved),'historical_raw_workbooks_reopened':0,'scope':'native source-bound observation proposals only; source workbook literal validation and identity admission still required','seconds':time.monotonic()-START,'peak_RSS_MB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'input_pins':{str(p):sha(p) for p in [S,C,P,F,N,RES,RULE,O/'propose_exact_source_county.py']}};(O/'history_proposal_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'},ensure_ascii=False))

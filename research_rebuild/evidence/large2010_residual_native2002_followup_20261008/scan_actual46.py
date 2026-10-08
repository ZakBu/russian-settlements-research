import sys,json,collections,importlib.util,re
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
s=load(46);sp=importlib.util.spec_from_file_location('f',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
members=collections.defaultdict(list)
for sid,y in s.obs[['source_record_id','census_year']].itertuples(index=False,name=None):members[s.uf.find(sid)].append(sid)
oldidx={k:g for k,g in s.obs[s.obs.census_year.eq(2002)].groupby('region_norm')};curidx={k:g for k,g in s.obs[s.obs.census_year.eq(2021)].groupby('region_norm')}
f=pd.read_csv(O/'baseline39_top100_snapshot.csv',dtype=str,keep_default_na=False);f=f[pd.to_numeric(f.population).ge(2000)];rows=[];pairs=[];credited=set();creditpaths=[]
for p in [R/'research_rebuild/evidence/working_full_chain_20261007'/v for v in ['qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','direct_inclusion_transformation_path_native_credit_union.csv']]:
 if p.exists():
  q=pd.read_csv(p,dtype=str,keep_default_na=False);creditpaths.append({'path':str(p),'baseline_read_sha256':sha(p)})
  for col in q.columns:
   if 'source_record_id' in col and not col.endswith('json'):credited.update(q[col])
for z in f.to_dict('records'):
 sid=z['source_record_id'];b=s.by_id.loc[sid];root=s.uf.find(sid);ids=members[root];years=sorted(s.years[root]);current=[s.by_id.loc[i] for i in ids if int(s.by_id.loc[i,'census_year'])==2021];old=[s.by_id.loc[i] for i in ids if int(s.by_id.loc[i,'census_year'])==2002];point=s.point_rows.get(sid);names={b.name_norm}|{p.name_norm for p in current+old};reason='alreadyfull3' if years==[2002,2010,2021] else 'credited_scope_or_qualified' if sid in credited else 'missing_native2002' if 2002 not in years else 'missing_current2021' if 2021 not in years else 'other'
 rows.append({**z,'actual46_component_years':str(years),'actual46_component_ids':json.dumps(ids),'actual46_point_present':bool(point),'actual46_point_json':json.dumps(point,ensure_ascii=False) if point else '', 'absence_reason':reason,'actual46_current_native_names':json.dumps([p.settlement_name for p in current],ensure_ascii=False),'actual46_old_native_names':json.dumps([p.settlement_name for p in old],ensure_ascii=False)})
 if reason in ['alreadyfull3','credited_scope_or_qualified']:continue
 for y,idx in [(2002,oldidx),(2021,curidx)]:
  for _,a in idx.get(b.region_norm,pd.DataFrame()).iterrows():
   # All exact names/types and bounded edit-distance discovery retained; not admission.
   an=a.name_norm;bn=b.name_norm
   exact=an in names;variants=False
   if not exact and abs(len(an)-len(bn))<=2 and len(an)>=4:
    # Bounded one/two textual operations, used only to discover typed/county proofs.
    import difflib
    variants=difflib.SequenceMatcher(None,an,bn).ratio()>=0.78
   if not exact and not variants:continue
   rr=s.uf.find(a.source_record_id);compatible=not(s.years[root]&s.years[rr]) if rr!=root else False;ap=s.point_rows.get(a.source_record_id);dist=distance_km((point['latitude'],point['longitude']),(ap['latitude'],ap['longitude'])) if point and ap else None
   pairs.append({'target2010_source_record_id':sid,'target_name':b.settlement_name,'target_region':b.region_norm,'target_type':b.settlement_type,'target_county':b.district_raw,'target_population':b.population,'candidate_source_record_id':a.source_record_id,'candidate_year':y,'candidate_name':a.settlement_name,'candidate_type':a.settlement_type,'candidate_county':a.district_raw,'candidate_population':a.population,'candidate_component_years':str(sorted(s.years[rr])),'candidate_component_ids':json.dumps(members[rr]),'graph_compatible':compatible,'exact_literal_name':exact,'bounded_variant_discovery_only':variants,'candidate_own_point_json':json.dumps(ap,ensure_ascii=False) if ap else '', 'point_distance_km':dist,'candidate_source_file':a.source_file,'candidate_source_locator':a.source_locator})
pd.DataFrame(rows).to_csv(O/'actual46_priority_component_absence.csv.gz',index=False,compression='gzip');pd.DataFrame(pairs).to_csv(O/'all_regional_name_candidates_before_graph_filter.csv.gz',index=False,compression='gzip');r={'actual_stage':46,'before':s.metrics(),'before_finite':fm.finite_metrics(s),'prioritized_snapshot_rows':len(rows),'absence_reasons':dict(collections.Counter(z['absence_reason'] for z in rows)),'baseline_credit_snapshots_not_future_source_pins':creditpaths,'candidate_pairs_discovery_only':len(pairs)};(O/'scan_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False));print(pd.DataFrame(rows)[['settlement_name','region_norm','population','actual46_component_years','absence_reason','actual46_current_native_names']].to_string(index=False))

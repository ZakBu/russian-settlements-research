import sys,json,math,collections
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km
s=load(39)
# Full selected NP universe indexed before any graph eligibility filter.
idx={y:{k:g for k,g in s.obs[s.obs.census_year.eq(y)&s.obs.is_additive_settlement_record.fillna(False)].groupby(['region_norm','name_norm'],dropna=False)} for y in [2002,2010,2021]}
members=collections.defaultdict(list)
for sid,y in s.obs[['source_record_id','census_year']].itertuples(index=False,name=None):members[s.uf.find(sid)].append(sid)
ordinary={'город','пгт','поселок','село','деревня','хутор','станица','аул','слобода','починок','выселок','сельский населенный пункт','населенный пункт','поселок сельского типа','поселок городского типа','местечко','заимка','улус','кишлак'}
rows=[];held=collections.Counter();types=collections.Counter();eligible=0
for _,n in s.obs[s.obs.census_year.eq(2021)].iterrows():
 root=s.uf.find(n.source_record_id)
 if s.years[root]!={2010,2021} or n.source_record_id not in s.point_rows:continue
 eligible+=1;ids=members[root];bid=next(x for x in ids if int(s.by_id.loc[x,'census_year'])==2010);b=s.by_id.loc[bid];key=(n.region_norm,n.name_norm)
 if b.name_norm!=n.name_norm or b.region_norm!=n.region_norm:held['existing_2010_2021_name_or_region_changed']+=1;continue
 peers=[idx[y].get(key) for y in [2002,2010,2021]]
 if peers[0] is None:held['no_literal_native2002_name_in_region']+=1;continue
 if any(len(x)!=1 for x in peers if x is not None):held['whole_region_literal_name_rivals_in_any_census']+=1;continue
 a=peers[0].iloc[0]
 if s.years[s.uf.find(a.source_record_id)]!={2002}:held['old_component_not2002_only']+=1;continue
 types[(str(a.type_norm),str(b.type_norm),str(n.type_norm))]+=1
 if any(z.type_norm not in ordinary for z in [a,b,n]):held['not_ordinary_typed_native_NP']+=1;continue
 if bid not in s.point_rows:held['2010_own_point_missing']+=1;continue
 np=s.point_rows[n.source_record_id];bp=s.point_rows[bid]
 d=distance_km((np['latitude'],np['longitude']),(bp['latitude'],bp['longitude']))
 if d>5:held['existing_2010_2021_point_conflict']+=1;continue
 if any(x in s.conflicting_point_targets for x in [a.source_record_id,bid,n.source_record_id]):held['unresolved_baseline_point_alternative']+=1;continue
 if a.source_record_id in s.point_rows:
  ap=s.point_rows[a.source_record_id]
  if distance_km((np['latitude'],np['longitude']),(ap['latitude'],ap['longitude']))>5:held['existing_2002_own_point_conflict']+=1;continue
 if any(pd.isna(z.population) or not math.isfinite(float(z.population)) for z in [a,b,n]):held['unknown_native_population']+=1;continue
 def code(v):
  if pd.isna(v):return ''
  t=str(v).strip();return t[:-2] if t.endswith('.0') else t
 ac,nc=code(a.okato),code(n.okato)
 if ac and nc and ac!=nc:held['old_current_native_code_different_needs_crosswalk']+=1;continue
 rows.append({'old_source_record_id':a.source_record_id,'native2010_source_record_id':bid,'current_source_record_id':n.source_record_id,'name':n.settlement_name,'region':n.region_norm,'native02_type':a.settlement_type,'native2010_type':b.settlement_type,'current_type':n.settlement_type,'native02_type_norm':a.type_norm,'native2010_type_norm':b.type_norm,'current_type_norm':n.type_norm,'population2002':a.population,'population2010':b.population,'population2021':n.population,'old_county':a.district_raw,'native2010_county':b.district_raw,'current_county':n.district_raw,'native02_source_file':a.source_file,'native02_source_locator':a.source_locator,'native02_quality':a.population_value_quality,'native02_okato':ac,'current_okato':nc,'current_oktmo':code(n.oktmo),'current_2010_point_distance_km':d,'old_admitted_point_present':a.source_record_id in s.point_rows,'current_own_point_json':json.dumps(np,ensure_ascii=False),'native2010_own_point_json':json.dumps(bp,ensure_ascii=False),'whole_region_literal_name_counts_2002_2010_2021':'[1,1,1]','status':'candidate_pending_grouped_original02_rawleaf_and_existing_scope_check'})
f=pd.DataFrame(rows)
if len(f):f.sort_values('population2002',ascending=False).to_csv(O/'whole_region_unique_native02_candidates.csv.gz',index=False,compression='gzip')
r={'baseline_stage':39,'status':'discovery_only_no_new_identity_admitted','eligible_current_two_year_ownpoint_components':eligible,'candidate_histories':len(f),'candidate_population2002':int(f.population2002.sum()) if len(f) else 0,'candidate_population2010':int(f.population2010.sum()) if len(f) else 0,'candidate_population2021':int(f.population2021.sum()) if len(f) else 0,'holds':dict(held),'type_triplet_counts_before_typed_NP_check':{str(k):v for k,v in types.items()},'top_candidates':f[['name','region','population2002','native02_type_norm','native2010_type_norm','current_type_norm']].sort_values('population2002',ascending=False).head(20).to_dict('records') if len(f) else []}
(O/'screening_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False))

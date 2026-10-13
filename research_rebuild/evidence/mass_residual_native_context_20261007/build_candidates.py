"""Native 2002 two-sided printed-subdivision context to accepted current county; candidates only."""
import sys,json,random,bisect,collections
from pathlib import Path
import pandas as pd,pyarrow.parquet as pq
ROOT=Path('/workspace/russian-settlements-research'); OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
s=load();baseline=s.metrics()
m=pq.read_table(s.inputs[0],columns=['source_record_id','source_sheet','source_row','source_name_raw','municipality_raw','source_native_id','entity_grain_status']).to_pandas()
o=s.obs.merge(m,on='source_record_id');o['root']=o.source_record_id.map(s.uf.find)
for k,col in [('n','name_norm'),('t','type_norm'),('r','region_norm')]:o[k]=o[col].map(normalize)
o['d']=o.district_raw.map(county_key);o['mu']=o.municipality_raw.map(normalize)
whole=o.is_additive_settlement_record.fillna(False)&o.n.ne('')&o.t.ne('')&~o.settlement_name.fillna('').str.contains(r'\(часть',regex=True)
a=o[o.census_year.eq(2002)&whole&~o.source_file.str.contains('official')&o.source_row.notna()].copy();c=o[o.census_year.eq(2021)&whole].copy()
cur_by_root={r.root:r for r in c.itertuples()};anchor={}
for r in a.itertuples():
 q=cur_by_root.get(r.root)
 if q is not None and q.d and q.source_record_id in s.point_rows and r.n==q.n and r.t==q.t:
  p=s.point_rows[q.source_record_id]
  if str(p.get('coordinate_source_record_id',''))==q.source_record_id and not any(v in normalize(p.get('point_origin_kind')) for v in ['retrospective','continuity','representative']):anchor[r.source_record_id]=q
# Restrict to the exact original printed administrative group. Group county mapping requires >=3 agreeing accepted anchors.
groupcols=['source_file','source_sheet','r','d','mu'];contexts={};groups={};groupstatus=collections.Counter()
for key,g in a.groupby(groupcols,dropna=False):
 vals=[(r,anchor[r.source_record_id]) for r in g.itertuples() if r.source_record_id in anchor]
 counties={q.d for r,q in vals}
 if len(vals)<3:groupstatus['fewer_than_3_anchors']+=1;continue
 if len(counties)!=1:groupstatus['current_county_disagreement']+=1;continue
 county=next(iter(counties));vals.sort(key=lambda x:x[0].source_row);positions=[r.source_row for r,q in vals]
 for r in g.itertuples():
  groups[r.source_record_id]=county
  j=bisect.bisect_left(positions,r.source_row)
  if j==0 or j==len(vals):continue
  lo,lq=vals[j-1];hi,hq=vals[j]
  if r.source_row-lo.source_row>20 or hi.source_row-r.source_row>20:continue
  if lo.source_record_id==r.source_record_id or hi.source_record_id==r.source_record_id:continue
  contexts[r.source_record_id]=(county,lo,lq,hi,hq)
# Full competitor universes, including already complete chains. Unknown county old competitors block.
a['inferred']=a.source_record_id.map(groups).fillna('');oldgroups={k:list(g.source_record_id) for k,g in a.groupby(['n','t','r','inferred'])}; currentgroups={k:list(g.source_record_id) for k,g in c.groupby(['n','t','r','d'])}
unknown=set(tuple(x) for x in a[a.inferred.eq('')][['n','t','r']].itertuples(index=False,name=None))
eventpath=ROOT/'research_rebuild/evidence/event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
event_ids=set(pd.read_csv(eventpath,dtype=str,usecols=['source_record_id']).source_record_id) if eventpath.exists() else set()
point_collisions=collections.Counter((s.by_id.loc[i,'census_year'],p['latitude'],p['longitude']) for i,p in s.point_rows.items())
candidates=[];holds=collections.Counter()
for r in a.itertuples():
 if s.years[r.root]=={2002,2010,2021}:continue
 ctx=contexts.get(r.source_record_id)
 if ctx is None:continue
 county,lo,lq,hi,hq=ctx;key=(r.n,r.t,r.r,county)
 if (r.n,r.t,r.r) in unknown:holds['old_same_name_unknown_context']+=1;continue
 if len(oldgroups.get(key,[]))!=1:holds['old_context_competitor']+=1;continue
 targets=currentgroups.get(key,[])
 if len(targets)!=1:holds['current_context_competitor_or_missing']+=1;continue
 tid=targets[0];q=s.by_id.loc[tid];qr=s.uf.find(tid)
 if r.source_record_id in event_ids or tid in event_ids:holds['known_event_endpoint']+=1;continue
 if qr==r.root:continue
 if s.years[qr]&s.years[r.root]:holds['same_year_conflict']+=1;continue
 if s.years[qr]|s.years[r.root]!={2002,2010,2021}:holds['no_complete_native_triplet']+=1;continue
 p=s.point_rows.get(tid)
 if p is None or str(p.get('coordinate_source_record_id',''))!=tid or any(v in normalize(p.get('point_origin_kind')) for v in ['retrospective','continuity','representative']):holds['no_current_own_point']+=1;continue
 if point_collisions[(2021,p['latitude'],p['longitude'])]>1:holds['current_point_collision']+=1;continue
 if r.source_record_id in s.conflicting_point_targets or tid in s.conflicting_point_targets:holds['conflicting_point']+=1;continue
 op=s.point_rows.get(r.source_record_id)
 if op and distance_km((op['latitude'],op['longitude']),(p['latitude'],p['longitude']))>5:holds['historical_point_conflict']+=1;continue
 if pd.notna(r.latitude) and pd.notna(r.longitude) and (r.latitude,r.longitude)!=(0,0) and distance_km((r.latitude,r.longitude),(p['latitude'],p['longitude']))>5:holds['raw_coordinate_conflict']+=1;continue
 candidates.append(dict(candidate_status='pending_independent_review',from_source_record_id=r.source_record_id,to_source_record_id=tid,name=r.settlement_name,type=r.settlement_type,region=r.r,population_2002=r.population,source_file=r.source_file,source_sheet=r.source_sheet,source_row=int(r.source_row),source_sha256=r.source_sha256,source_native_id=r.source_native_id,source_name_raw=r.source_name_raw,printed_2002_district=r.district_raw,printed_2002_municipality=r.municipality_raw,inferred_current_county=county,current_district=q.district_raw,lower_2002_anchor=lo.source_record_id,lower_row=int(lo.source_row),lower_2021_anchor=lq.source_record_id,upper_2002_anchor=hi.source_record_id,upper_row=int(hi.source_row),upper_2021_anchor=hq.source_record_id,point_ledger=p['point_ledger_path'],coordinate_source_record_id=p.get('coordinate_source_record_id'),latitude=p['latitude'],longitude=p['longitude']))
f=pd.DataFrame(candidates); f.to_csv(OUT/'candidates.csv',index=False)
random.seed(20261007);sample=random.sample(candidates,min(15,len(candidates)));top=sorted(candidates,key=lambda x:x['population_2002'],reverse=True)[:5]
pd.DataFrame(sample).to_csv(OUT/'fixed15.csv',index=False);pd.DataFrame(top).to_csv(OUT/'top5.csv',index=False)
# Potential only: simulate the candidate unions and point continuity without writing accepted ledgers.
for r in candidates:
 a_id,b_id=r['from_source_record_id'],r['to_source_record_id']
 if s.uf.find(a_id)==s.uf.find(b_id):continue
 s.union(a_id,b_id)
# Carry point only to records in resulting candidate components, explicitly modern representative continuity.
roots={s.uf.find(r['from_source_record_id']) for r in candidates};extra=[r.source_record_id for r in s.obs.itertuples() if s.uf.find(r.source_record_id) in roots]
after=s.metrics(extra_point_ids=extra)
receipt={'status':'candidate_only','route':'two_sided_native_2002_original_printed_subdivision_group_accepted_anchor_context','candidate_edges':len(candidates),'historical_groups':dict(groupstatus),'context_rows':len(contexts),'group_mapped_rows':len(groups),'holds':dict(holds),'baseline':baseline,'simulated_after':after,'potential_full3_population_gain':{y:after[y]['covered_population']-baseline[y]['covered_population'] for y in baseline},'inputs':{str(p):sha(p) for p in s.inputs},'current_county_printed_in_2002_asserted':False,'populations_modified':False}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='inputs'},ensure_ascii=False,indent=2))

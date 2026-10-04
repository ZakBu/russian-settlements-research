"""Recompute strict and scope-aware territorial coverage from accepted observation IDs."""
import hashlib,json
from pathlib import Path
import duckdb
C=Path('/workspace/settlements-work/continuation_20261004');CORE=C/'R4/final_long_preparation/seventh_canonical_long/source_preserving_core.parquet';F=C/'R4/final_long_preparation/seventh_canonical_long/federal_typed_city_continuity.parquet';T=C/'root/accepted_territorial_scope_layers_seventh';S=C/'root/scoped2014_applied/accepted_scoped_observations_2014.parquet';O=C/'root/scoped_joint_coverage_eighth.json'
B=C/'accepted_mass_eighth_reviewed';SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def exclusive_official_source_projection(populations, year, observations, partition_ids):
 """Choose one official assertion per place/year, retaining alternatives elsewhere."""
 projected=populations.copy();removed={};excluded=set()
 if year==2002:
  excluded.update(partition_ids)
  for sid in partition_ids:
   if sid in projected:removed[sid]=projected.pop(sid)
 selected=[r for r in observations if int(r['census_year'])==year]
 for r in selected:
  sid=r['source_record_id'];aliases=set(json.loads(r['same_census_source_alias_record_ids']))
  counterpart=r['preferred_same_census_alternate_selected_source_record_id']
  if counterpart:aliases.add(counterpart)
  excluded.update(aliases-{sid})
  for alt in aliases:
   if alt in projected:removed[alt]=projected.pop(alt)
  projected[sid]=int(r['population'])
 return projected,removed,excluded,selected

def run(points=None, supplemental=None, output=None, residual_output=None, graph=None, official_scope=None):
 global O
 pointpath=Path(points) if points else B/'accepted_point_uses.parquet'
 graphpath=Path(graph) if graph else B/'accepted_identity_edges.parquet'
 graphreceipt=graphpath.parent/'receipt.json'
 assert graphreceipt.is_file(), 'Accepted graph requires its application receipt'
 if output:O=Path(output)
 assert not O.exists(), 'Measurement receipts are immutable; choose a new output'
 con=duckdb.connect(config={'threads':1,'memory_limit':'512MB'})
 con.read_parquet(str(SELECTED)).create_view('sel')
 from collections import defaultdict
 adj=defaultdict(set)
 for a,b in con.execute('select from_source_record_id,to_source_record_id from read_parquet(?)',[str(graphpath)]).fetchall():adj[a].add(b);adj[b].add(a)
 yrs=dict(con.execute('select source_record_id,census_year from sel').fetchall());seen=set();full=set()
 for start in adj:
  if start in seen:continue
  stack=[start];seen.add(start);members=[]
  while stack:
   v=stack.pop();members.append(v)
   for w in adj[v]:
    if w not in seen:seen.add(w);stack.append(w)
  assert len({yrs[v] for v in members})==len(members)
  if {yrs[v] for v in members}=={2002,2010,2021}:full.update(members)
 import pyarrow as pa
 con.register('full_ids',pa.table({'sid':sorted(full)}))
 con.read_parquet(str(pointpath)).create_view('points')
 from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES
 assert {r[0] for r in con.execute('select distinct coordinate_admission_status from points').fetchall()} <= ACCEPTED_COORDINATE_STATUSES
 con.execute("create view core as select s.census_year observation_year,s.source_record_id,s.population population_value,'census' record_type,'settlement' entity_category,f.sid is not null census_full_chain,p.latitude,p.longitude from sel s left join full_ids f on s.source_record_id=f.sid left join points p on s.source_record_id=p.target_source_record_id")

 rows=con.execute("select cast(observation_year as integer),source_record_id,cast(population_value as bigint) from core where record_type='census' and entity_category='settlement' and census_full_chain and latitude is not null and longitude is not null").fetchall();npmap={y:{sid:pop for yr,sid,pop in rows if yr==y} for y in [2002,2010,2021]}
 chains=con.execute('select city,years,source_record_ids_json from read_parquet(?)',[str(F)]).fetchall();all_source=dict(con.execute("select source_record_id,cast(population_value as bigint) from core where record_type='census'").fetchall());feds={y:{} for y in npmap}
 for city,years,ids in chains:
  if years!='2002|2010|2021':continue
  for y,sid in zip([2002,2010,2021],json.loads(ids)):feds[y][sid]=all_source[sid]
 controls={2002:145166731,2010:142856536,2021:147182123};result={}
 m=json.loads((T/'accepted_moscow2002_territorial_override.json').read_text());assert m['decision_status']=='accepted_exclusive_territorial_view_override'
 scoped=con.execute('select current_2021_source_record_id,cast(current_2021_population_context as bigint) from read_parquet(?) where latitude is not null and longitude is not null',[str(S)]).fetchall();assert len(scoped)==len(dict(scoped))==993
 additional_pins=[];supplement_rows=[]
 if supplemental:
  folder=Path(supplemental);receiptpath=folder/'application_receipt.json';receipt=json.loads(receiptpath.read_text());assert receipt['status']=='applied_independently_reviewed22_scoped2014_source_rows_and_identity_point_uses'
  obs=folder/'accepted_scoped_observations.parquet';edge=folder/'accepted_scoped_identity_links.parquet';assert sha(obs)==receipt['outputs'][obs.name] and sha(edge)==receipt['outputs'][edge.name]
  supplement_rows=con.execute('select current_2021_source_record_id,cast(current_2021_population_context as bigint),population_value is not null from read_parquet(?) where latitude is not null and longitude is not null',[str(obs)]).fetchall()
  links=con.execute("select to_source_record_id from read_parquet(?) where decision_status='accepted_scoped_identity_observation_only'",[str(edge)]).fetchall()
  assert len(supplement_rows)==len(links)==22 and {r[0] for r in supplement_rows}=={r[0] for r in links}
  assert not {r[0] for r in supplement_rows}&{r[0] for r in scoped}
  for sid,pop,known in supplement_rows:assert all_source[sid]==pop
  additional_pins=[receiptpath,obs,edge]
 official_rows=[];official_exclusions=[]
 if official_scope:
  import pyarrow.parquet as pq
  folder=Path(official_scope);receiptpath=folder/'application_receipt.json';receipt=json.loads(receiptpath.read_text())
  assert receipt['status']=='applied_reviewed_official_primary_three_place_scoped_trajectories'
  obs=folder/'accepted_scoped_trajectory_projection.parquet';edge=folder/'accepted_scoped_continuity_links.parquet'
  assert sha(obs)==receipt['outputs'][obs.name] and sha(edge)==receipt['outputs'][edge.name]
  official_rows=pq.read_table(obs).to_pylist();links=pq.read_table(edge).to_pylist()
  assert len(official_rows)==9 and len(links)==6
  assert {(r['place'],int(r['census_year'])) for r in official_rows}=={(p,y) for p in receipt['places'] for y in [2002,2010,2021]}
  assert all(r['decision_status']=='accepted_scoped_physical_trajectory_projection' and r['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES for r in official_rows)
  assert all(r['applied_scoped_decision_status']=='accepted_scoped_physical_continuity' for r in links)
  carrier_ids=sorted({r['current_2021_source_record_id'] for r in official_rows})
  carriers={r[0]:(r[1],r[2]) for r in con.execute('select target_source_record_id,latitude,longitude from points where target_source_record_id in(select unnest(?))',[carrier_ids]).fetchall()};assert len(carriers)==3
  for r in official_rows:
   assert carriers[r['current_2021_source_record_id']]==(float(r['latitude']),float(r['longitude']))
   if int(r['census_year'])==2021:assert all_source[r['source_record_id']]==int(r['population'])
  official_exclusions=receipt['excluded_partition_source_record_ids'];assert len(official_exclusions)==2 and sum(all_source[s] for s in official_exclusions)==29533
  additional_pins.extend([receiptpath,obs,edge])
 # Accepted annual territorial edges provide real 2021->2022/23/24 paths for
 # Sevastopol; do not pretend it appeared in Russian censuses2002 or2010.
 annualpath=T/'accepted_annual_federal9_territorial_edges.csv';e=con.execute("select * from read_csv(?,all_varchar=true)",[str(annualpath)]).fetchdf();sev=[r for r in chains if r[0]=='Севастополь'];assert len(sev)==1;sevid=json.loads(sev[0][2])[0];assert len(e[e.from_observation_id==sevid])==3
 covered_ids=set(); excluded_ids=set()
 for y in npmap:
  strict=npmap[y]|feds[y];scop=strict.copy();extra=[]
  if y==2002:
   excluded_ids.update(m['excluded_child_source_record_ids'])
   removed={sid:scop.pop(sid) for sid in m['excluded_child_source_record_ids'] if sid in scop};scop[m['source_record_id']]=m['population'];extra.append({'kind':'exclusive_Moscow2002_published_parent_instead_of_all_children','removed_already_counted_population':sum(removed.values()),'parent_population':m['population']})
  if y==2021:
   for sid,pop in scoped:
    if sid in scop:assert scop[sid]==pop
    else:scop[sid]=pop
   scop[sevid]=all_source[sevid];extra.append({'kind':'accepted_scope2014_to2021_crimea_NP_paths','rows':len(scoped),'population':sum(p for s,p in scoped)});extra.append({'kind':'accepted_Sevastopol2021_to2022_2023_2024_territorial_path','population':all_source[sevid]})
   for sid,pop,known in supplement_rows:
    if sid in scop:assert scop[sid]==pop
    else:scop[sid]=pop
   if supplement_rows:extra.append({'kind':'accepted_supplemental_2014_source_identity_and_point_paths','rows':len(supplement_rows),'current2021_population':sum(r[1] for r in supplement_rows),'known_numeric2014_observations':sum(r[2] for r in supplement_rows),'literal_dash2014_population_remains_unknown':sum(not r[2] for r in supplement_rows),'current2021_population_whose_2014_numeric_population_unknown':sum(r[1] for r in supplement_rows if not r[2])})
  if official_rows:
   before=sum(scop.values());scop,removed,new_exclusions,scoped_year=exclusive_official_source_projection(scop,y,official_rows,official_exclusions)
   excluded_ids.update(new_exclusions)
   extra.append({'kind':'accepted_exclusive_official_primary_three_place_trajectory_projection','places':len(scoped_year),'official_population':sum(int(r['population']) for r in scoped_year),'removed_already_counted_alias_counterpart_or_partition_population':sum(removed.values()),'net_joint_population_change':sum(scop.values())-before,'protected_alternates_remain_in_frozen_selection':True,'boundary_comparability_not_asserted':True})
  covered_ids.update(scop)
  a=sum(strict.values());b=sum(scop.values());result[y]={'control_population':controls[y],'strict_NP_joint_population':sum(npmap[y].values()),'strict_NP_joint_rows':len(npmap[y]),'strict_with_existing_federal_typed_three_census_population':a,'strict_with_federal_percent':100*a/controls[y],'available_scope_joint_population':b,'available_scope_joint_percent':100*b/controls[y],'remaining_population_to_99':max(0,__import__('math').ceil(.99*controls[y])-b),'scope_adjustments':extra}
 if residual_output:
  dest=Path(residual_output);assert not dest.exists()
  con.register('joint_covered_or_excluded_ids',pa.table({'sid':sorted(covered_ids|excluded_ids)}))
  residual=con.execute("select s.source_record_id,s.census_year,s.settlement_name,s.settlement_type,s.region_norm,s.district_raw,s.population,s.population_value_quality,s.source_file,s.source_sheet,s.source_row,s.okato,s.oktmo,s.settlement_id,p.latitude accepted_latitude,p.longitude accepted_longitude,p.coordinate_admission_status,f.sid is not null accepted_full_three_census_chain,case when f.sid is null and p.latitude is null then 'identity_and_point' when f.sid is null then 'identity_path' else 'point' end missing_joint_axis from sel s left join full_ids f on s.source_record_id=f.sid left join points p on s.source_record_id=p.target_source_record_id left join joint_covered_or_excluded_ids j on s.source_record_id=j.sid where j.sid is null").fetch_arrow_table()
  import pyarrow.parquet as pq
  pq.write_table(residual,dest,compression='zstd')
 r={'status':'accepted_graph_with_reviewed_point_and_scoped_increments_joint_measurement','target99_reached_each_year':all(x['remaining_population_to_99']==0 for x in result.values()),'results':result,'definition':'Ordinary accepted coordinate+full Russian3 chain; separate federal territorial chains; replace2002 Moscow childpartition by exactpublishedparent exclusively; Crimea actual2014->21 identity/presence paths (unknown numeric population remains unknown); Sevastopolactual2021->22/23/24 paths; optional reviewed exclusive official-source three-date trajectories preserve alternate values and flags. No invented oldRussianrecords. This scope-aware metric is separate from canonical strict3.','input_pins':{str(p):sha(p) for p in [SELECTED,graphpath,pointpath,graphreceipt,F,S,T/'application_receipt.json',T/'accepted_moscow2002_territorial_override.json',annualpath]+additional_pins},'script_sha256':sha(Path(__file__))}
 if residual_output:r['residual_diagnostic']={'path':str(dest),'sha256':sha(dest),'rows':residual.num_rows}
 O.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--points');p.add_argument('--supplemental');p.add_argument('--output');p.add_argument('--residual-output');p.add_argument('--graph');p.add_argument('--official-scope');a=p.parse_args();run(a.points,a.supplemental,a.output,a.residual_output,a.graph,a.official_scope)

"""Recompute strict and scope-aware territorial coverage from accepted observation IDs."""
import hashlib,json
from pathlib import Path
import duckdb
C=Path('/workspace/settlements-work/continuation_20261004');CORE=C/'R4/final_long_preparation/seventh_canonical_long/source_preserving_core.parquet';F=C/'R4/final_long_preparation/seventh_canonical_long/federal_typed_city_continuity.parquet';T=C/'root/accepted_territorial_scope_layers_seventh';S=C/'root/scoped2014_applied/accepted_scoped_observations_2014.parquet';O=C/'root/scoped_joint_coverage_eighth.json'
B=C/'accepted_mass_eighth_reviewed';SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run():
 con=duckdb.connect(config={'threads':1,'memory_limit':'512MB'})
 con.read_parquet(str(SELECTED)).create_view('sel')
 from collections import defaultdict
 adj=defaultdict(set)
 for a,b in con.execute('select from_source_record_id,to_source_record_id from read_parquet(?)',[str(B/'accepted_identity_edges.parquet')]).fetchall():adj[a].add(b);adj[b].add(a)
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
 con.read_parquet(str(B/'accepted_point_uses.parquet')).create_view('points')
 con.execute("create view core as select s.census_year observation_year,s.source_record_id,s.population population_value,'census' record_type,'settlement' entity_category,f.sid is not null census_full_chain,p.latitude,p.longitude from sel s left join full_ids f on s.source_record_id=f.sid left join points p on s.source_record_id=p.target_source_record_id")

 rows=con.execute("select cast(observation_year as integer),source_record_id,cast(population_value as bigint) from core where record_type='census' and entity_category='settlement' and census_full_chain and latitude is not null and longitude is not null").fetchall();npmap={y:{sid:pop for yr,sid,pop in rows if yr==y} for y in [2002,2010,2021]}
 chains=con.execute('select city,years,source_record_ids_json from read_parquet(?)',[str(F)]).fetchall();all_source=dict(con.execute("select source_record_id,cast(population_value as bigint) from core where record_type='census'").fetchall());feds={y:{} for y in npmap}
 for city,years,ids in chains:
  if years!='2002|2010|2021':continue
  for y,sid in zip([2002,2010,2021],json.loads(ids)):feds[y][sid]=all_source[sid]
 controls={2002:145166731,2010:142856536,2021:147182123};result={}
 m=json.loads((T/'accepted_moscow2002_territorial_override.json').read_text());assert m['decision_status']=='accepted_exclusive_territorial_view_override'
 scoped=con.execute('select current_2021_source_record_id,cast(current_2021_population_context as bigint) from read_parquet(?) where latitude is not null and longitude is not null',[str(S)]).fetchall();assert len(scoped)==len(dict(scoped))==993
 # Accepted annual territorial edges provide real 2021->2022/23/24 paths for
 # Sevastopol; do not pretend it appeared in Russian censuses2002 or2010.
 annualpath=T/'accepted_annual_federal9_territorial_edges.csv';e=con.execute("select * from read_csv(?,all_varchar=true)",[str(annualpath)]).fetchdf();sev=[r for r in chains if r[0]=='Севастополь'];assert len(sev)==1;sevid=json.loads(sev[0][2])[0];assert len(e[e.from_observation_id==sevid])==3
 for y in npmap:
  strict=npmap[y]|feds[y];scop=strict.copy();extra=[]
  if y==2002:
   removed={sid:scop.pop(sid) for sid in m['excluded_child_source_record_ids'] if sid in scop};scop[m['source_record_id']]=m['population'];extra.append({'kind':'exclusive_Moscow2002_published_parent_instead_of_all_children','removed_already_counted_population':sum(removed.values()),'parent_population':m['population']})
  if y==2021:
   for sid,pop in scoped:
    if sid in scop:assert scop[sid]==pop
    else:scop[sid]=pop
   scop[sevid]=all_source[sevid];extra.append({'kind':'accepted_scope2014_to2021_crimea_NP_paths','rows':len(scoped),'population':sum(p for s,p in scoped)});extra.append({'kind':'accepted_Sevastopol2021_to2022_2023_2024_territorial_path','population':all_source[sevid]})
  a=sum(strict.values());b=sum(scop.values());result[y]={'control_population':controls[y],'strict_NP_joint_population':sum(npmap[y].values()),'strict_NP_joint_rows':len(npmap[y]),'strict_with_existing_federal_typed_three_census_population':a,'strict_with_federal_percent':100*a/controls[y],'available_scope_joint_population':b,'available_scope_joint_percent':100*b/controls[y],'remaining_population_to_99':max(0,__import__('math').ceil(.99*controls[y])-b),'scope_adjustments':extra}
 r={'status':'eighth_accepted_scoped_joint_measurement_target99_not_reached','results':result,'definition':'Ordinary accepted coordinate+full Russian3 chain; separate federal territorial chains; replace2002 Moscow childpartition by exactpublishedparent exclusively; Crimea actual2014->21 paths; Sevastopolactual2021->22/23/24 paths. No invented oldRussianrecords. This scope-aware metric is separate from strict3.','input_pins':{str(p):sha(p) for p in [SELECTED,B/'accepted_identity_edges.parquet',B/'accepted_point_uses.parquet',B/'receipt.json',F,S,T/'application_receipt.json',T/'accepted_moscow2002_territorial_override.json',annualpath]},'script_sha256':sha(Path(__file__))};O.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':run()

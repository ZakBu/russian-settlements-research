#!/usr/bin/env python3
"""Recalculate additive settlement coordinate/identity axes on Graph28/29 plus accepted CSV deltas."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import duckdb,pandas as pd
from build_long_table import ACCEPTED_COORDINATE_STATUSES,ACCEPTED_EDGE_STATUSES,UnionFind
REPO=Path(__file__).resolve().parents[2]
OUT=REPO/'research_rebuild/evidence/top100_classifier_bridge_20261005'/'strict_joint_coverage_overlay.json'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EDGES=Path('/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet')
POINTS=Path('/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet')
DELTA=REPO/'research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application'
CODE=REPO/'research_rebuild/evidence/top100_classifier_bridge_20261005'
HIST=REPO/'research_rebuild/evidence/historical_urban_code_residual_20261005'
HCLASS=REPO/'research_rebuild/evidence/historical_classifier_bridge_batch_20261005'
CONTROLS={2002:145166731,2010:142856536,2021:147182123}

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def axes(use_deltas:bool):
 con=duckdb.connect(config={'threads':2,'memory_limit':'2GB'})
 obs=con.execute('select source_record_id,census_year,population,is_additive_settlement_record,population_scope from read_parquet(?)',[str(SELECTED)]).fetchdf()
 uf=UnionFind(obs.source_record_id.astype(str))
 year_sets={str(sid):{int(y)} for sid,y in obs[['source_record_id','census_year']].itertuples(index=False,name=None)}
 def merge(a,b,check=True):
  ra,rb=uf.find(str(a)),uf.find(str(b))
  if ra==rb:return False
  if check and year_sets[ra]&year_sets[rb]:raise RuntimeError('merge would duplicate a census year')
  merged=year_sets[ra]|year_sets[rb]
  uf.union(ra,rb)
  root=uf.find(ra);other=rb if root==ra else ra
  year_sets[root]=merged;year_sets.pop(other,None)
  return True
 for a,b in con.execute("select from_source_record_id,to_source_record_id from read_parquet(?) where relation='same_place' and decision_status in (select unnest(?))",[str(EDGES),sorted(ACCEPTED_EDGE_STATUSES)]).fetchall():merge(a,b,check=False)
 delta_edges=[];delta_points=[]
 if use_deltas:
  for p,cols in [(DELTA/'accepted_identity_edge_delta.csv',('from_id','to_id')),(DELTA/'top60_identity_edge_delta.csv',('from_id','to_id')),(CODE/'accepted_classifier_bridge_delta.csv',('source_record_id_old','source_record_id_current')),(HCLASS/'accepted_identity_edge_delta.csv',('from_source_record_id','to_source_record_id'))]:
   d=pd.read_csv(p);delta_edges.extend((str(a),str(b)) for a,b in d[list(cols)].itertuples(index=False,name=None))
  for p in [DELTA/'top60_point_use_delta.csv',CODE/'old_point_use_delta.csv',HIST/'accepted_point_use_delta.csv',HCLASS/'accepted_retrospective_point_use_delta.csv']:
   d=pd.read_csv(p);delta_points.extend(d.target_source_record_id.astype(str).tolist())
  for a,b in delta_edges:merge(a,b,check=True)
 comp_years={}
 for sid,yr in obs[['source_record_id','census_year']].itertuples(index=False,name=None):comp_years.setdefault(uf.find(str(sid)),set()).add(int(yr))
 # Assert each selected component has no duplicate census year.
 component_year_counts={}
 for sid,yr in obs[['source_record_id','census_year']].itertuples(index=False,name=None):
  key=(uf.find(str(sid)),int(yr));component_year_counts[key]=component_year_counts.get(key,0)+1
 dup=sum(n>1 for n in component_year_counts.values())
 if dup:raise RuntimeError(f'{dup} component-year duplicates')
 pts=con.execute('select target_source_record_id from read_parquet(?) where coordinate_admission_status in (select unnest(?))',[str(POINTS),sorted(ACCEPTED_COORDINATE_STATUSES)]).df()
 point_ids=set(pts.target_source_record_id.astype(str))|set(delta_points)
 obs['year_set']=[comp_years[uf.find(str(sid))] for sid in obs.source_record_id]
 obs['component_linked']=obs.year_set.map(lambda x:len(x)>=2)
 obs['full_chain']=obs.year_set.map(lambda x:{2002,2010,2021}.issubset(x))
 obs['point']=obs.source_record_id.astype(str).isin(point_ids)
 obs['additive']=obs.is_additive_settlement_record.fillna(False)
 output={}
 for y in [2002,2010,2021]:
  d=obs[(obs.census_year==y)&obs.additive]
  axes={
   'accepted_coordinate':d[d.point],
   'identity_any_other_census':d[d.component_linked],
   'coordinate_plus_any_other_census':d[d.point&d.component_linked],
   'full_2002_2010_2021_chain':d[d.full_chain],
   'coordinate_plus_full_chain':d[d.point&d.full_chain],
  }
  output[str(y)]={'selected_additive_rows':int(len(d)),'selected_additive_population':int(d.population.sum()),'official_control':CONTROLS[y]}
  for k,x in axes.items():output[str(y)][k]={'rows':int(len(x)),'population':int(x.population.sum()),'percent_official_control':100*float(x.population.sum())/CONTROLS[y]}
 return output,int(len(delta_edges)),int(len(delta_points)),dup

base,_,_,_=axes(False)
updated,n_edges,n_points,dup=axes(True)
manifest={'scope':'strict additive individual settlement records; denominator is official census control; no federal aggregate or non-census territorial projection included','inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SELECTED,EDGES,POINTS]},'baseline_graph28_graph29':base,'after_accepted_additive_deltas':updated,'delta_counts':{'identity_edges':n_edges,'point_uses':n_points,'same_year_component_conflicts':dup},'national_target_population_fraction':0.99,'population_values_modified':False,'boundary_comparability_asserted':False,'limitations':['This strict metric requires a point and a complete ordinary 2002-2010-2021 identity component for every counted record.','It does not include accepted federal/territorial/scope-aware sidecars and is not interchangeable with the available-year scope metric.','No annual historical claim is used as a census population value.']}
OUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(manifest,ensure_ascii=False,indent=2))

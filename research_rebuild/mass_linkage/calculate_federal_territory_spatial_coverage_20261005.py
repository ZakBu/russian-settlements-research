#!/usr/bin/env python3
"""Recalculate point and strict full-chain axes with a non-double-counting federal-territory overlay."""
from __future__ import annotations
import json
from pathlib import Path
import duckdb,pandas as pd
from build_long_table import ACCEPTED_COORDINATE_STATUSES,ACCEPTED_EDGE_STATUSES,UnionFind
ROOT=Path(__file__).resolve().parents[2]
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EDGES=Path('/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet')
POINTS=Path('/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet')
DELTA=ROOT/'research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application'
CODE=ROOT/'research_rebuild/evidence/top100_classifier_bridge_20261005'
HIST=ROOT/'research_rebuild/evidence/historical_urban_code_residual_20261005'
HCLASS=ROOT/'research_rebuild/evidence/historical_classifier_bridge_batch_20261005'
TERR=ROOT/'research_rebuild/evidence/federal_territory_spatial_overlay_20261005/federal_territory_observations.csv'
OUT=ROOT/'research_rebuild/evidence/federal_territory_spatial_overlay_20261005/coverage_overlay.json'
CONTROLS={2002:145166731,2010:142856536,2021:147182123}

def main():
 c=duckdb.connect(config={'threads':2,'memory_limit':'2GB'})
 o=c.execute('select source_record_id,census_year,population,region_norm,is_additive_settlement_record from read_parquet(?)',[str(SELECTED)]).fetchdf()
 uf=UnionFind(o.source_record_id.astype(str)); ysets={str(s):{int(y)} for s,y in o[['source_record_id','census_year']].itertuples(index=False,name=None)}
 def merge(a,b):
  a,b=uf.find(str(a)),uf.find(str(b))
  if a==b:return
  if ysets[a]&ysets[b]:raise RuntimeError('duplicate census year in federal overlay graph')
  u=ysets[a]|ysets[b];uf.union(a,b);r=uf.find(a);other=b if r==a else a;ysets[r]=u;ysets.pop(other,None)
 for a,b in c.execute("select from_source_record_id,to_source_record_id from read_parquet(?) where relation='same_place' and decision_status in (select unnest(?))",[str(EDGES),sorted(ACCEPTED_EDGE_STATUSES)]).fetchall():merge(a,b)
 edge_deltas=[(DELTA/'accepted_identity_edge_delta.csv',('from_id','to_id')),(DELTA/'top60_identity_edge_delta.csv',('from_id','to_id')),(CODE/'accepted_classifier_bridge_delta.csv',('source_record_id_old','source_record_id_current')),(HCLASS/'accepted_identity_edge_delta.csv',('from_source_record_id','to_source_record_id'))]
 for p,cols in edge_deltas:
  d=pd.read_csv(p)
  for a,b in d[list(cols)].itertuples(index=False,name=None):merge(a,b)
 full=set()
 for sid in o.source_record_id.astype(str):
  if {2002,2010,2021}.issubset(ysets[uf.find(sid)]):full.add(sid)
 pp=c.execute('select target_source_record_id from read_parquet(?) where coordinate_admission_status in (select unnest(?))',[str(POINTS),sorted(ACCEPTED_COORDINATE_STATUSES)]).fetchnumpy()['target_source_record_id']
 point=set(map(str,pp))
 for p in [DELTA/'top60_point_use_delta.csv',CODE/'old_point_use_delta.csv',HIST/'accepted_point_use_delta.csv',HCLASS/'accepted_retrospective_point_use_delta.csv']:
  d=pd.read_csv(p);point.update(d.target_source_record_id.astype(str))
 o['sid']=o.source_record_id.astype(str);o['point']=o.sid.isin(point);o['full']=o.sid.isin(full);o['joint']=o.point&o.full
 terr=pd.read_csv(TERR); regions=set(terr.region_norm)
 summary={'scope':'selected additive census population; federal-city regional rows are replaced by one territory observation for spatial metrics; child NP counts are kept in a separate layer and not double-counted','territory_population_reconciliation':pd.read_csv(TERR.with_name('territory_population_conservation.csv')).to_dict('records'),'by_year':{}}
 for y in (2002,2010,2021):
  d=o[(o.census_year==y)&o.is_additive_settlement_record.fillna(False)].copy(); ordinary=d[~d.region_norm.isin(regions)]
  tr=terr[terr.census_year==y]
  territory=int(tr.territory_population.sum())
  basecoord=int(d.loc[d.point,'population'].sum());basejoint=int(d.loc[d.joint,'population'].sum())
  currentterritory_coord=int(d.loc[d.point&d.region_norm.isin(regions),'population'].sum())
  currentterritory_joint=int(d.loc[d.joint&d.region_norm.isin(regions),'population'].sum())
  spatial_coord=basecoord-currentterritory_coord+territory
  chain_territory=int(tr.loc[tr.territory_key.isin(['RU-FED-MOW','RU-FED-SPB']),'territory_population'].sum())
  spatial_joint=basejoint-currentterritory_joint+chain_territory
  control=CONTROLS[y]
  summary['by_year'][str(y)]={'official_control':control,'selected_additive_population':int(d.population.sum()),
    'ordinary_point_population_before_replacement':basecoord,'federal_region_point_population_before_replacement':currentterritory_coord,
    'territory_population_represented':territory,'spatial_point_population_after_replacement':spatial_coord,'spatial_point_percent_official_control':100*spatial_coord/control,'gap_to_99_spatial_point':max(0,int(.99*control+0.999999)-spatial_coord),
    'ordinary_full_chain_coordinate_population_before_replacement':basejoint,'federal_region_full_chain_coordinate_population_before_replacement':currentterritory_joint,
    'territory_full_chain_population_added':chain_territory,'spatial_point_plus_full_chain_population':spatial_joint,'spatial_point_plus_full_chain_percent_official_control':100*spatial_joint/control,'gap_to_99_joint_official_control':max(0,int(.99*control+0.999999)-spatial_joint)}
 # 2021 census-chain denominator excludes the two regions absent from 2002/2010.
 d21=o[(o.census_year==2021)&o.is_additive_settlement_record.fillna(False)]
 out_scope=d21[d21.region_norm.isin(['крым','севастополь'])]
 outscope=int(out_scope.population.sum())
 base21=summary['by_year']['2021'];den=CONTROLS[2021]-outscope
 base21['out_of_scope_2002_2010_regions_2021_population_selected']=outscope
 base21['selected_2021_crimea_population']=int(d21[d21.region_norm=='крым'].population.sum())
 base21['selected_2021_sevastopol_population']=int(d21[d21.region_norm=='севастополь'].population.sum())
 base21['available_three_census_chain_denominator']=den
 base21['spatial_point_plus_full_chain_percent_available_scope']=100*base21['spatial_point_plus_full_chain_population']/den
 base21['gap_to_99_joint_available_scope']=max(0,int(.99*den+0.999999)-base21['spatial_point_plus_full_chain_population'])
 summary['inputs']={'selected_rows':len(o),'federal_territory_rows':len(terr),'accepted_identity_delta_edges':sum(len(pd.read_csv(p)) for p,_ in edge_deltas),'accepted_point_delta_rows':sum(len(pd.read_csv(p)) for p in [DELTA/'top60_point_use_delta.csv',CODE/'old_point_use_delta.csv',HIST/'accepted_point_use_delta.csv',HCLASS/'accepted_retrospective_point_use_delta.csv'])}
 summary['limitations']=['Territory continuity is a separate overlay and does not alter the physical-settlement identity graph.','Boundary and population comparability remain unasserted; Moscow 2012 territorial expansion is explicitly noted in the territory layer.','Spatial points mark the territory by its named city location; they are not polygon centroids.','The 2021 available-scope denominator removes selected Crimea and Sevastopol populations because they are outside the 2002/2010 Russian census geography.']
 OUT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

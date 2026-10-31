"""Check source identity, accessibility invariants and deliverable GeoJSON."""
import argparse,json
from pathlib import Path
import numpy as np,pandas as pd,shapely

def main():
 a=argparse.ArgumentParser();a.add_argument('--results',type=Path,required=True);q=a.parse_args().results;p=pd.read_parquet(q/'settlement_access.parquet');s=json.loads((q/'summary.json').read_text());assert p.source_record_id.is_unique;assert p.census_year.eq(2021).all();assert p.is_additive_settlement_record.eq(True).all();assert p.working_credit_present.eq(True).all();assert p.accepted_point_present.eq(True).all();assert np.isclose(p.time_minutes_base*1.3,p.time_minutes_slow,equal_nan=True).all();assert np.isclose(p.time_minutes_to_core*1.3,p.time_minutes_to_core_slow,equal_nan=True).all();valid=p.time_minutes_base.notna()&p.time_minutes_to_core.notna();assert (p.loc[valid,'time_minutes_to_core']<=p.loc[valid,'time_minutes_base']+1e-7).all();assert s['bbox_not_truncated_90'] and s['min_core_minutes_at_bbox_edge']>90 and s['min_minutes_at_bbox_edge']>90
 checks={}
 for fn in ['core_isochrones.geojson','point_isochrones.geojson']:
  c=json.loads((q/fn).read_text());assert len(c['features'])==6
  for factor in [1.,1.3]:
   ff=[f for f in c['features'] if f['properties']['speed_time_factor']==factor];ff.sort(key=lambda f:f['properties']['minutes']);prev=shapely.Polygon()
   for f in ff:
    g=shapely.geometry.shape(f['geometry']);assert g.is_valid and not g.is_empty;assert prev.difference(g).area<1e-10;prev=g
  checks[fn]='valid_and_nested'
 for f in q.glob('*.geojson'):
  c=json.loads(f.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON:'+x)));assert c['type']=='FeatureCollection'
 routes=json.loads((q/'sample_routes.json').read_text());assert len(routes['samples'])==5
 for sample in routes['samples']:
  assert np.isclose(sample['road_minutes_forward'],sample['road_minutes_reverse_search'],atol=1e-8,rtol=1e-11)
  assert np.isclose(sample['road_edge_sum_minutes'],sample['road_minutes_forward'],atol=1e-8,rtol=1e-11)
 assert int(p.time_minutes_to_core_slow.le(60).sum())==175;assert int(p.time_minutes_to_core.le(60).sum())==262
 print(json.dumps({'rows':len(p),'source_record_id_unique':True,'additive_credited_records_only':True,'time_and_core_invariants':'pass','bbox_frontier_minutes_point':s['min_minutes_at_bbox_edge'],'bbox_frontier_minutes_core':s['min_core_minutes_at_bbox_edge'],'geometries':checks},ensure_ascii=False))
if __name__=='__main__':main()

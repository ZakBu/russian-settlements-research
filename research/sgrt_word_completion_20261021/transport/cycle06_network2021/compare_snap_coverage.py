#!/usr/bin/env python3
"""Paired snap-source diagnostic, not measured network travel validation."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;OLD=H.parent/'cycle05_axis_extension/settlement_road_snap.parquet'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 new=H/'settlement_road_snap.parquet';n=pd.read_parquet(new);o=pd.read_parquet(OLD,columns=['id','lat','lon','snap_km','road_osm_node']);aliases_path=H.parent/'cycle05_destination_extension7/federal_context_alias_receipt.json';aliases=json.loads(aliases_path.read_text())['aliases'];o['raw_2026_point_id']=o.id
 for alias in aliases:
  assert alias['coordinates_identical'] is True
  oldrow=o[o.id.eq(alias['raw_origin_id'])];newrow=n[n.id.eq(alias['canonical_id'])];assert len(oldrow)==len(newrow)==1;assert np.allclose(oldrow[['lat','lon']].to_numpy(float),newrow[['lat','lon']].to_numpy(float),rtol=0,atol=1e-10);o.loc[o.id.eq(alias['raw_origin_id']),'id']=alias['canonical_id']
 pair=n[['id','name','region','lat','lon','snap_km','road_osm_node','nearest_vertex_distance_tie','point_coordinates_available']].merge(o,on='id',how='left',suffixes=('_2021','_2026'),validate='one_to_one');pair['same_query_coordinate']=(pair.lat_2021-pair.lat_2026).abs().le(1e-10)&(pair.lon_2021-pair.lon_2026).abs().le(1e-10);pair['accepted_2021']=pair.snap_km_2021.le(10);pair['accepted_2026']=pair.snap_km_2026.le(10);pair['connector_distance_change_km']=pair.snap_km_2021-pair.snap_km_2026
 pair.to_parquet(H/'paired_historical2021_vs2026_snap_coverage.parquet',index=False);common=pair[pair.same_query_coordinate];counts=common.groupby(['accepted_2021','accepted_2026']).size();out={'status':'SOURCE_SNAP_COVERAGE_PAIRED_DIAGNOSTIC','source_sha256':{str(p):sha(p) for p in [new,OLD,aliases_path]},'all_point_rows':len(pair),'finite_point_rows':int(pair.point_coordinates_available.sum()),'explicit_federal_context_aliases_applied':len(aliases),'same_query_coordinate_pairs':len(common),'finite_points_without_same_query_coordinate_control':int((pair.point_coordinates_available&~pair.same_query_coordinate).sum()),'paired_acceptance_counts':[{'accepted_2021':bool(a),'accepted_2026':bool(b),'points':int(v)} for (a,b),v in counts.items()],'median_connector_distance_change_km':float(common.connector_distance_change_km.median()),'p99_absolute_connector_distance_change_km':float(common.connector_distance_change_km.abs().quantile(.99)),'different_nearest_OSM_node_fraction':float(common.road_osm_node_2021.ne(common.road_osm_node_2026).mean()),'not_claimed':['observed trip times','pure source-year causal effect','2026 truth for missing2021roads','unchanged road operating conditions']};(H/'paired_snap_coverage_receipt.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()

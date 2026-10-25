#!/usr/bin/env python3
"""Read-only public-route access diagnostic; no observed driveway or barrier-free connector claim."""
from pathlib import Path
import json,sys,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
import argparse
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--prepared-root',type=Path);parser.add_argument('--roads',type=Path);parser.add_argument('--graph-dir',type=Path);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)

root=args.bundle;out=args.output;summaries=[];cases=[];pieces=[]
for folder in ['routes','routes_wb','routes_yandex']:
 for p in sorted((root/folder/'nearest').glob('*.parquet')):
  d=pd.read_parquet(p);local=d.zero_cost_np_assumption.fillna(False);ext=~local&d.cost_minutes.gt(0)&d.point_separation_km.notna();speed=d.point_separation_km/d.cost_minutes*60
  physical=d.provider_input_kind.eq('sites');ordinary=~d.origin_is_additional_context.fillna(False)
  s={'service':p.stem,'rows':len(d),'local_zero':int(local.sum()),'local_zero_physical':int((local&physical).sum()),'local_zero_ordinary':int((local&ordinary).sum()),'local_zero_physical_separation_gt1km':int((local&physical&d.point_separation_km.gt(1)).sum()),'local_zero_physical_separation_gt5km':int((local&physical&d.point_separation_km.gt(5)).sum()),'local_zero_physical_separation_gt20km':int((local&physical&d.point_separation_km.gt(20)).sum()),'local_zero_raw_best_cost_gt20':int((local&d.unconstrained_nearest_cost_minutes.gt(20)).sum()),'local_zero_raw_best_cost_unknown':int((local&d.unconstrained_nearest_cost_minutes.isna()).sum()),'local_zero_origin_not_routable':int((local&~d.road_endpoint_accepted.fillna(False)).sum()),'external_finite':int(ext.sum()),'external_implied_straight_speed_gt130':int((ext&speed.gt(130.00001)).sum()),'external_implied_straight_speed_max_kmh':float(speed[ext].max()),'external_provider_snap_gt1km':int((ext&d.provider_snap_km.gt(1)).sum()),'external_origin_snap_gt2km':int((ext&d.snap_km.gt(2)).sum()),'external_network_zero':int((ext&d.network_minutes.eq(0)).sum())}
  summaries.append(s)
  for kind,mask,sortcol in [('local_farthest_representative',local&physical,'point_separation_km'),('local_raw_cost_gt20',local&d.unconstrained_nearest_cost_minutes.gt(20),'unconstrained_nearest_cost_minutes'),('external_implied_speed',ext,'_speed'),('external_long_origin_connector',ext&d.snap_km.gt(2),'snap_km'),('external_zero_network',ext&d.network_minutes.eq(0),'point_separation_km')]:
   d['_speed']=speed;chosen=d[mask].nlargest(8,sortcol).copy();chosen['diagnostic_kind']=kind;pieces.append(chosen)
  print(s,flush=True)
pd.DataFrame(summaries).to_csv(out/'national_summary.csv',index=False);pd.concat(pieces,ignore_index=True).to_parquet(out/'selected_counterexample_candidates.parquet',index=False,compression='zstd');(out/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2)+'\n')

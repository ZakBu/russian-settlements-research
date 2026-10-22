#!/usr/bin/env python3
"""Standalone source readback; independent stakeholder review remains separate."""
from pathlib import Path
import json,pandas as pd
from shapely import wkb
from shapely.geometry import Point
H=Path(__file__).resolve().parent
old=pd.read_parquet(H.parent/'calibration/services_2021_objects.parquet');new=pd.read_parquet(H/'services_2021_objects_repaired.parquet')
pd.testing.assert_frame_equal(new.iloc[:len(old)][old.columns].reset_index(drop=True),old.reset_index(drop=True),check_dtype=False,check_categorical=False)
rel=pd.read_parquet(H/'service_relations_2021.parquet');geo=[]
for _,r in rel.iterrows():
 g=wkb.loads(r.polygon_wkb);geo.append(bool(g.is_valid and not g.is_empty and g.covers(Point(r.lon,r.lat))))
assert all(geo)
raw=pd.read_parquet(H/'relation_source_ledger.parquet');times=pd.to_datetime(raw.source_last_edit,utc=True);late=times.gt(pd.Timestamp('2021-01-01T21:42:03Z'));assert not late.any()
rt=json.loads((H/'relation_recovery_receipt.json').read_text());assert raw.shape[0]==1774 and raw.geometry_assembled.sum()==len(rel)==1761 and raw.shape[0]-len(rel)==13
q={'status':'SOURCE_RETENTION_GEOMETRY_AND_DATING_READBACK_PASSED','performed_by':'commerce_relation_recovery_author_separate_readback_not_independent_guardian','original_rows_all31fields_unchanged':len(old),'valid_relation_polygons_cover_stored_representative_point':sum(geo),'selected_raw_relation_rows':len(raw),'source_last_edit_max':times.max().isoformat(),'post_snapshot_last_edit_rows':int(late.sum()),'new_features_axis_rows':rt['axis_rows'],'new_source_used_model_agreements':False,'n_checks':6,'n_failed':0}
(H/'source_readback_receipt.json').write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n');print(json.dumps(q,ensure_ascii=False))

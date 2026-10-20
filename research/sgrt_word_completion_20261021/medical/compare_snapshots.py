#!/usr/bin/env python3
"""Compare dated OSM records, not establishment births/deaths."""
from pathlib import Path
import pandas as pd,json,numpy as np
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'observed_change_2021_2026';OUT.mkdir(exist_ok=True)
a=pd.read_parquet(ROOT/'history_20210101/osm_medical_inventory.parquet');b=pd.read_parquet(ROOT/'current_20261019/osm_medical_inventory.parquet')
raw_counts={'2021':len(a),'2026':len(b)}
def common(d):
 mask=d.osm_type.isin(['node','way']) & d.tags_json.map(lambda s:bool((t:=json.loads(s)).get('healthcare') or t.get('amenity') in {'hospital','clinic','doctors','dentist','pharmacy'}))
 return d[mask].copy()
a=common(a);b=common(b)
cols=['object_id','medical_class','lat','lon','baseline_uid','coordinate_candidate_uid','inactive_source_assertion','broad_function']
d=a[cols].merge(b[cols],on='object_id',how='outer',suffixes=('_2021','_2026'),indicator=True)
d['observed_record_change']=d['_merge'].map({'left_only':'observed_in_2021_not_in_2026_medical_extract','right_only':'observed_in_2026_not_in_2021_medical_extract','both':'observed_in_both_dated_medical_extracts'}).astype(str)
d['physical_opening_or_closure_inferred']=False;d=d.drop(columns='_merge');d.to_parquet(OUT/'source_object_change.parquet',index=False)
f=a[['object_id','baseline_uid','medical_class']].merge(b[['object_id','baseline_uid','medical_class']],on='object_id',suffixes=('_2021','_2026'))
r={'raw_extracted_objects_before_comparable_scope':raw_counts,'comparison_scope':'node/way; healthcare=* or amenity=hospital/clinic/doctors/dentist/pharmacy; excludes history-only relations and nursing-home-only predicate','source_objects_2021':len(a),'source_objects_2026':len(b),'record_change_counts':d.observed_record_change.value_counts().to_dict(),'shared_id_class_changed':int((f.medical_class_2021!=f.medical_class_2026).sum()),'interpretation':'Changes in mapped healthcare assertions/OSM identity/category, not measured establishment openings or closures. Node-to-way changes and retagging can change record identity; extract boundaries and community completeness can change. The 2026 layers must not be backcast to 2002/2010/2021.'}
(OUT/'comparison_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False,indent=2))

"""Diagnostic ID continuity only; no current type backcast and no closed-point inference."""
from pathlib import Path
import hashlib,json,math
import pandas as pd

ROOT=Path(__file__).resolve().parent
CURRENT=ROOT.parents[1]/'national/ozon_nutrygo_normalized_20260806.csv'
archive=pd.read_csv(ROOT/'ozon_archived_positive_objects.csv',dtype={'object_id':str})
current=pd.read_csv(CURRENT,dtype={'objectid':str})
assert current.objectid.is_unique
current=current.rename(columns={'lat':'latitude','lon':'longitude'})
joined=archive.merge(current[['objectid','latitude','longitude','city_label','address','raw_p']],
    left_on='object_id',right_on='objectid',how='left',suffixes=('_archive','_2026'),validate='many_to_one')
def shift(row):
    if pd.isna(row.latitude_2026):return None
    a,b=map(math.radians,[row.latitude_archive,row.latitude_2026])
    x=math.sin((b-a)/2)**2
    x+=math.cos(a)*math.cos(b)*math.sin(math.radians(row.longitude_2026-row.longitude_archive)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1,x)))
joined['same_id_coordinate_shift_km']=joined.apply(shift,axis=1)
joined.to_csv(ROOT/'archive_current_ID_audit.csv',index=False)
summary={'archived_evidence_rows':len(archive),'same_ID_in_partial2026_archive':int(joined.objectid.notna().sum()),
    'same_ID_coordinates_within100m':int(joined.same_id_coordinate_shift_km.le(.1).sum()),
    'same_ID_coordinates_shift_gt1km':int(joined.same_id_coordinate_shift_km.gt(1).sum()),
    'current_path':str(CURRENT),'current_sha256':hashlib.sha256(CURRENT.read_bytes()).hexdigest(),
    'archive_absence_not_inferred':True,'missing_current_ID_is_not_closure':True,
    'no_type_backcast':True}
(ROOT/'archive_current_ID_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
api_summaries=[]
for file in sorted(ROOT.glob('ozon_opp_api_positive_points_*.csv')):
    source=pd.read_csv(file,dtype={'object_id':str})
    combo=source.merge(current[['objectid','latitude','longitude','city_label','address','raw_p']],
        left_on='object_id',right_on='objectid',how='left',suffixes=('_archive','_2026'),validate='many_to_one')
    combo['same_id_coordinate_shift_km']=combo.apply(shift,axis=1)
    combo.to_csv(ROOT/(file.stem+'_current_ID_audit.csv'),index=False)
    api_summaries.append({'archive_date':str(source.archive_date.iloc[0]),'archived_points_n':len(source),
        'same_id_current_n':int(combo.objectid.notna().sum()),
        'same_id_coordinates_within100m_n':int(combo.same_id_coordinate_shift_km.le(.1).sum()),
        'same_id_coordinates_shift_gt1km_n':int(combo.same_id_coordinate_shift_km.gt(1).sum()),
        'current_source_partial':True,'missing_ID_not_a_closure':True})
(ROOT/'archived_api_current_ID_summary.json').write_text(json.dumps(api_summaries,ensure_ascii=False,indent=2))
print(json.dumps(api_summaries,ensure_ascii=False,indent=2))

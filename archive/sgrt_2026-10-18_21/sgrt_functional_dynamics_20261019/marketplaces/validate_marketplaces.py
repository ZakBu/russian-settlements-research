"""Checks of source coverage, units, date semantics and identifier conservation."""
from pathlib import Path
import json,hashlib,re
import numpy as np
import pandas as pd
import fitz
R=Path(__file__).resolve().parent

def main():
    from build_marketplaces import source_bytes
    raw=json.loads(source_bytes('wb_all_points_v11.json'))
    source={str(x['id']):x for c in raw if c['country']=='ru' for x in c['items']}
    f=pd.read_parquet(R/'wb_delivery_locations_ru_20261019.parquet')
    q=pd.read_parquet(R/'wb_pvz_focus_ru_20261019.parquet')
    obj=pd.read_csv(R/'objects.csv');pp=pd.read_csv(R/'pickpoint_extracted_202102.csv')
    checks={}
    checks['russia_id_conservation']=set(f.source_object_id.astype(str))==set(source)
    checks['ids_unique']=bool(f.object_id.is_unique)
    checks['coordinate_axis_exact']=all(tuple(source[str(r.source_object_id)]['coordinates'])==(r.latitude,r.longitude)for r in f.itertuples())
    checks['addresses_exact']=all(source[str(r.source_object_id)]['address']==r.address for r in f.itertuples())
    checks['focus_subset']=set(q.source_object_id)==set(f[f.typePoint.isin([8,34])].source_object_id)
    checks['status_partition']=q.link_status.value_counts().sum()==len(q)
    checks['unresolved_not_assigned']=bool(q.loc[q.link_status!='name_coordinate_concordance','settlement_uid'].isna().all())
    checks['no_inferred_opening_date']=bool(f.opening_date.isna().all()and obj.opening_date.isna().all())
    checks['no_inferred_external_catchment']=bool(not f.external_catchment_evidence.any()and not obj.external_catchment_evidence.any())
    checks['matched_distance_constraint']=bool(f.loc[f.link_status=='name_coordinate_concordance','settlement_axis_distance_km'].le(10+1e-9).all())
    d=fitz.open(R/'sources/pickpoint_february_2021.pdf')
    source_rows=sum(sum(w[4]=='ПВЗ:' for w in p.get_text('words'))for p in d)
    checks['pickpoint_source_row_coverage']=source_rows==len(pp)==3005
    checks['pickpoint_page_bounds']=bool(pp.source_page.between(1,len(d)).all())
    counts=pd.read_csv(R/'lower_poochye_counts_2025.csv')
    checks['published_aggregate_not_object_replicated']=len(counts)==32 and not obj.source_id.eq('MSU_HSE_PVZ2025').any()
    checks['published_aggregate_conservation']=int(counts['count'].sum())==273
    checks['source_json_sha256']=hashlib.sha256(source_bytes('wb_all_points_v11.json')).hexdigest()=='70e785a362eb5bd4f1de6ba26bf67d5944021e0c0602e7f851d4b5cc3a9c5154'
    duplicates=pp[pp.duplicated(['source_region','address'],keep=False)]
    duplicates.to_csv(R/'pickpoint_shared_address_audit.csv',index=False)
    checks={k:bool(v)for k,v in checks.items()}
    res={'checks':checks,'passed':int(sum(checks.values())),'total':len(checks),'pickpoint_shared_address_records':len(duplicates),
      'pickpoint_address_keys':int(pp[['source_region','address']].drop_duplicates().shape[0]),
      'wb_focus_shared_coordinate_records':int(q.duplicated(['latitude','longitude'],keep=False).sum()),
      'wb_focus_matched_settlements':int(q.settlement_uid.nunique()),
      'note':'Shared address/coordinate is retained; it may mean different rooms, co-location or duplicate records. No automatic fraud/identity conclusion.'}
    (R/'VALIDATION.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
    print(json.dumps(res,ensure_ascii=False,indent=2));assert all(checks.values())

if __name__=='__main__':main()

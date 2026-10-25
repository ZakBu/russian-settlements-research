"""Local verification of provenance and normalized positive evidence."""
from pathlib import Path
import hashlib,json
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
requests=json.loads((ROOT/'query_manifest.json').read_text())['requests_and_saved_responses']
for request in requests:
    assert hashlib.sha256((ROOT/request['body']).read_bytes()).hexdigest()==request['sha256']
for date,n in [('20230319',3444),('20240609',1885)]:
    d=pq.read_table(ROOT/f'ozon_opp_api_positive_points_{date}.parquet').to_pandas()
    assert len(d)==n and d.object_id.is_unique
    assert d.latitude.between(-90,90).all()and d.longitude.between(-180,180).all()
    assert d.opening_date.isna().all()
    assert not d.spatial_query_boundary_known.any()
    assert json.loads((ROOT/f'archived_api_summary_{date}.json').read_text())['CDX_SHA1_verified']
geo=pq.read_table(ROOT/'ozon_archived_positive_objects.parquet').to_pandas()
assert len(geo)==32 and geo.object_id.nunique()==32
assert not geo.duplicated(['archive_timestamp','source_url','object_id']).any()
assert set(geo.archive_date.str[:4])=={'2021','2022','2023','2024','2025'}
assert geo.cdx_digest_verified.all()and geo.opening_date.isna().all()
x=pd.read_csv(ROOT/'ozon_seller_acceptance_xlsx_undated_candidate.csv.gz')
assert len(x)==36958 and x.technical_name.nunique()==36958
assert x.observation_date.isna().all()and x.latitude.isna().all()and x.longitude.isna().all()
assert x.numeric_Ozon_object_id.isna().all()
assert x.xlsx_core_created.eq('2025-01-23T01:25:08Z').all()
assert x.git_commit_date.eq('2026-04-16T09:45:22Z').all()
print('PASS: receipts, both API snapshots,32geoobjects,36958undated XLSX candidates and date separation verified.')

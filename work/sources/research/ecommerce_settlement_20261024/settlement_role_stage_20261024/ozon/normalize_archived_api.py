"""Normalize archived official partner-map point response, without claiming complete coverage."""
from pathlib import Path
from urllib.parse import urlparse
import argparse,base64,gzip,hashlib,json
from collections import Counter
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
RAW=ROOT/'raw'
parser=argparse.ArgumentParser()
parser.add_argument('--date',choices=['20230319','20240609'],default='20230319')
args=parser.parse_args()
date=args.date[:4]+'-'+args.date[4:6]+'-'+args.date[6:8]
body=RAW/f'opp_search{args.date}.body'
meta=json.loads(body.with_name(body.name+'.request.json').read_text())
assert meta['status']==200
assert hashlib.sha256(body.read_bytes()).hexdigest()==meta['sha256']
cdx=json.loads((RAW/'cdx_opp_pickpoint_allcaptures.json').read_text())
index=[dict(zip(cdx[0],x))for x in cdx[1:]]
record=next(x for x in index if x['original']=='https://opp-api.ozon.ru/pick-point/search'and x['timestamp'].startswith(args.date))
digest=base64.b32encode(hashlib.sha1(body.read_bytes()).digest()).decode().rstrip('=')
assert digest==record['digest']
assert meta['resolved_url']==f"https://web.archive.org/web/{record['timestamp']}id_/{record['original']}"
payload=gzip.decompress(body.read_bytes())if body.read_bytes()[:2]==b'\x1f\x8b'else body.read_bytes()
points=json.loads(payload)['pickPoints']
rows=[]
for point in points:
    coords=point['coordinates']
    assert -90<=coords['lat']<=90 and -180<=coords['lon']<=180
    rows.append({'archive_date':date,'archive_timestamp':record['timestamp'],
        'object_id':str(point['pointId']),'latitude':coords['lat'],'longitude':coords['lon'],
        'isOwn_raw':point['isOwn'],'status_raw':point.get('status'),'name':None,'address':None,
        'source_url':record['original'],'archive_url':meta['resolved_url'],
        'source_kind':'official public partner-map pick-point/search archived response',
        'source_body':str(body.relative_to(ROOT)),'source_sha256':meta['sha256'],
        'observed_request_payload':None,'spatial_query_boundary_known':False,
        'catalogue_completeness_verified':False,'opening_date':None})
df=pd.DataFrame(rows)
assert len(df)=={'20230319':3444,'20240609':1885}[args.date]and df.object_id.is_unique
df.to_csv(ROOT/f'ozon_opp_api_positive_points_{args.date}.csv',index=False)
pq.write_table(pa.Table.from_pandas(df,preserve_index=False),ROOT/f'ozon_opp_api_positive_points_{args.date}.parquet')
summary={'archive_date':date,'archive_timestamp':record['timestamp'],
    'official_source_url':record['original'],'archive_url':meta['resolved_url'],
    'CDX_SHA1_verified':True,'sha256':meta['sha256'],'objects_n':len(df),
    'unique_ids':int(df.object_id.nunique()),'all_coordinates_valid':True,
    'observed_coordinate_bbox':{'min_lat':float(df.latitude.min()),'max_lat':float(df.latitude.max()),
        'min_lon':float(df.longitude.min()),'max_lon':float(df.longitude.max())},
    'isOwn_raw_counts':{str(k):v for k,v in Counter(df.isOwn_raw).items()},
    'status_raw_counts':{str(k):v for k,v in Counter(df.status_raw).items()},
    'geographic_scope':'Observed coordinates in Moscow/Moscow-region vicinity; not national',
    'selection_limits':'Original POST body/viewport, filtering and completeness not established. Bounding box of returned points is not a verified survey boundary.',
    'semantics_limits':'IDs and coordinates are a dated public-map positive signal. Active customer service status and opening dates are not independently established.',
    'source_derivation':'Archived pvz-map.ozon.ru app.49bd8e8.js identifies production opp-api.ozon.ru; fetchGeoPickpoints invokes getPickPoints(viewPort,isOwn:null), returns pickPoints.',
    'no_current_type_backcast':True,'no_missing_as_absence':True,'opening_date_inferred':False}
(ROOT/f'archived_api_summary_{args.date}.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
if args.date=='20230319':
    (ROOT/'archived_api_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))

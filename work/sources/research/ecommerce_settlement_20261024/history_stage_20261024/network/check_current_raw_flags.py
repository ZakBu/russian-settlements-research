"""Audit pinned raw2026 catalogue against accepted objects and historical flags."""
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json

import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
RAW=ROOT/'raw'
CURRENT=ROOT.parents[1].parents[1]/'wb20261021_objects.parquet'
body=(RAW/'WB_source20261021.json.gz').read_bytes()
tree=json.loads((RAW/'accepted_repo_20261021_tree.json').read_text())
path='research/sgrt_word_replication_20261021/commerce/sources/wb_20261021.json.gz'
entry=next(x for x in tree['tree']if x['path']==path)
blob=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
assert blob==entry['sha']
ru=next(x['items']for x in json.loads(gzip.decompress(body))if x['country']=='ru')
current=pq.read_table(CURRENT).to_pylist()
oldmap={str(x['id']):x for x in ru}
assert len(ru)==len(oldmap)==len(current)==91043
assert set(oldmap)=={x['source_object_id']for x in current}
for row in current:
    raw=oldmap[row['source_object_id']]
    assert raw['coordinates']==[row['latitude'],row['longitude']]
    assert raw['typePoint']==row['typePoint']
    assert raw.get('fittingRooms')==row['fitting_rooms']
flags={key:dict(Counter(str(row.get(key))for row in ru))for key in ['dtype','isWb','pickupType','typePoint']}
key_counts=dict(Counter(key for row in ru for key in row))
history=pq.read_table(ROOT/'wb_history_normalized.parquet').to_pandas()
records=[]
for date,g in history[history.source_country.eq('ru')].groupby('archive_date'):
    raw_profile=g.dtype.eq(0)&g.isWb.eq(True)&g.pickupType.isin([3,4])
    records.append({'archive_date':date,'ru_objects_n':len(g),
        'dtype0_isWbtrue_n':int((g.dtype.eq(0)&g.isWb.eq(True)).sum()),
        'dtype0_isWbtrue_pickupType3or4_n':int(raw_profile.sum()),
        'raw_profile_share_ru':float(raw_profile.mean()),
        'profile_is_semantic_client_classification':False})
pd.DataFrame(records).to_csv(ROOT/'historical_raw_flag_profile.csv',index=False)
audit={'pinned_source_url':json.loads((RAW/'WB_source20261021.request.json').read_text())['url'],
    'git_blob_matches_tree':True,'git_blob':blob,'sha256':hashlib.sha256(body).hexdigest(),
    'raw2026_observation_date':'2026-10-21','raw2026_ru_objects_n':len(ru),
    'raw2026_fields_presence_n':key_counts,'raw2026_flag_distributions':flags,
    'exact_accepted_2026_ID_coordinate_type_fitting_matches_n':len(current),
    'common_2022_2026_dtype_isWb_pickupType_profile_possible':False,
    'reason':'All three raw fields are absent from every2026record; props not decoded or used as a substitute.',
    'within_scheme_design':'2022-11-18 vs2023-01-01: same all-poo-fr-v2 URL and raw schema; explicit dtype0/isWbtrue/pickupType3or4 profile, without interpreting codes as a validated service class.',
    'not_guaranteed':'Same raw schema does not prove stable completeness, operating status or equivalent physical services.',
    'date_not_opening':True}
(ROOT/'raw2026_comparability_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
print('PASS: pinned Git blob and all91043ID/coordinate/type/fitting records match accepted21.10.2026 objects.')
print('Raw2026 dtype/isWb/pickupType absent in all91043records; no common raw-flag profile across2022/2026.')
print(pd.DataFrame(records).to_string(index=False))

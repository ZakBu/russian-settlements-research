"""Verify archive bodies; normalize object-level WB history; audit ID continuity.

PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 verify_history.py
Reads previously acquired source bodies only. Does not change existing inputs.
"""
from pathlib import Path
import base64
from collections import Counter
import hashlib
import json
import math

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'raw'
RESEARCH = ROOT.parents[1]
CURRENT = RESEARCH.parents[1] / 'wb20261021_objects.parquet'


def digest(body):
    return base64.b32encode(hashlib.sha1(body).digest()).decode().rstrip('=')


def distance(lat1, lon1, lat2, lon2):
    if any(x is None for x in [lat1, lon1, lat2, lon2]):
        return None
    r = math.pi / 180
    a = math.sin((lat2-lat1)*r/2)**2
    a += math.cos(lat1*r)*math.cos(lat2*r)*math.sin((lon2-lon1)*r/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1, a)))


def main():
    cdx = {}
    for file in RAW.glob('wayback*.response.json'):
        try:
            rows = json.loads(file.read_bytes())
        except (ValueError, UnicodeDecodeError):
            continue
        if rows:
            for values in rows[1:]:
                record = dict(zip(rows[0], values))
                cdx[(record['timestamp'], record['original'])] = record
    normalized = []
    snapshots = []
    for file in sorted(RAW.glob('WB_archive[0-9]*.json')):
        if '.request.' in file.name:
            continue
        metadata = json.loads(file.with_suffix('.request.json').read_text())
        header = {k.lower():v for k,v in metadata['headers'].items()}
        ts = metadata['resolved_url'].split('/web/')[1].split('id_/')[0]
        original = metadata['resolved_url'].split('id_/')[1]
        compressed = file.with_suffix('.responsebody.gz').read_bytes()
        expected = cdx[(ts, original)]
        assert digest(compressed) == expected['digest'], file.name
        assert hashlib.sha256(compressed).hexdigest() == metadata['sha256']
        assert hashlib.sha256(file.read_bytes()).hexdigest() == metadata['decoded_sha256']
        data = json.loads(file.read_bytes())
        country_counts = {r['country']: len(r['items']) for r in data}
        ru = next(r['items'] for r in data if r['country'] == 'ru')
        assert len({r['id'] for r in ru}) == len(ru)
        keys = Counter(k for row in ru for k in row)
        info = {'archive_timestamp': ts, 'observation_date': ts[:4]+'-'+ts[4:6]+'-'+ts[6:8],
                'timestamp_definition': 'Wayback capture of operator catalogue; not opening date',
                'archive_memento_datetime': header.get('memento-datetime'),
                'original_http_date': header.get('x-archive-orig-date'),
                'original_last_modified': header.get('x-archive-orig-last-modified'),
                'original_url': original, 'archive_url': metadata['resolved_url'],
                'requested_archive_url': metadata['url'],
                'country_counts': country_counts, 'ru_unique_ids': len(ru),
                'keys_present_n': dict(keys), 'cdx_digest_matches_raw_gzip': True,
                'typePoint_counts': dict(Counter(str(r.get('typePoint')) for r in ru)),
                'pickupType_counts': dict(Counter(str(r.get('pickupType')) for r in ru)),
                'isWb_counts': dict(Counter(str(r.get('isWb')) for r in ru)),
                'dtype_counts': dict(Counter(str(r.get('dtype')) for r in ru)),
                'status_counts': dict(Counter(str(r.get('status')) for r in ru)),
                'decoded_json': str(file.relative_to(ROOT)),
                'decoded_sha256': metadata['decoded_sha256'],
                'raw_response_sha256': metadata['sha256'],
                'license': 'No explicit open data licence found in JSON/HTTP metadata; no redistribution licence asserted',
                'coverage': 'operator country=ru section; not an independently verified geographic boundary or complete active registry'}
        snapshots.append(info)
        for country in data:
            for row in country['items']:
                coords = row.get('coordinates') or [None, None]
                lat, lon = coords[:2]
                normalized.append({'archive_date': info['observation_date'],
                    'archive_timestamp': ts, 'source_object_id': str(row['id']),
                    'source_country': country['country'], 'latitude': lat, 'longitude': lon,
                    'address': row.get('address'), 'typePoint': row.get('typePoint'),
                    'pickupType': row.get('pickupType'), 'dtype': row.get('dtype'),
                    'isWb': row.get('isWb'), 'isHkn': row.get('isHkn'),
                    'isSortCenter': row.get('isSortCenter'),
                    'isExternalPostamat': row.get('isExternalPostamat'),
                    'source_status': row.get('status'), 'fitting_rooms': row.get('fittingRooms'),
                    'work_time': row.get('workTime'), 'source_url': original,
                    'historical_typePoint_8_34': row.get('typePoint') in [8,34],
                    'historical_typePoint_known': row.get('typePoint') is not None,
                    'fitting_rooms_at_least1_observed': row.get('fittingRooms') is not None and row.get('fittingRooms') >= 1,
                    'client_point_confirmed_from_flags': None,
                    'opening_date': None})
    history = pd.DataFrame(normalized)
    assert len(snapshots) == 7
    assert not history.duplicated(['archive_date', 'source_country', 'source_object_id']).any()
    assert history.latitude.notna().all() and history.longitude.notna().all()
    assert history.latitude.between(-90,90).all() and history.longitude.between(-180,180).all()
    pq.write_table(pa.Table.from_pandas(history, preserve_index=False), ROOT/'wb_history_normalized.parquet')
    history[history.source_country.eq('ru')].to_csv(ROOT/'wb_history_ru_normalized.csv.gz',index=False,compression='gzip')
    current = pq.read_table(CURRENT).to_pandas()
    assert current.source_object_id.is_unique
    rows = []
    transitions = []
    fitting_profiles = []
    fitting_transitions = []
    for date,g in list(history[history.source_country.eq('ru')].groupby('archive_date')) + [('2026-10-21',current)]:
        fitting_profiles.append({'date':date,'objects_n':len(g),
            'fitting_rooms_field_present_n':int(g.fitting_rooms.notna().sum()),
            'fitting_rooms_missing_n':int(g.fitting_rooms.isna().sum()),
            'fitting_rooms_ge1_n':int(g.fitting_rooms.ge(1).sum()),
            'fitting_rooms_zero_n':int(g.fitting_rooms.eq(0).sum()),
            'fitting_rooms_min':float(g.fitting_rooms.min()),
            'fitting_rooms_max':float(g.fitting_rooms.max())})
    for date, old in history[history.source_country.eq('ru')].groupby('archive_date'):
        joined = old.merge(current[['source_object_id','latitude','longitude','typePoint','focus_types_8_34','fitting_rooms',
                                    'baseline_uid','federal_territory_uid','link_status']],
                           on='source_object_id',suffixes=('_archive','_2026'),how='inner',validate='one_to_one')
        joined['same_id_coordinate_shift_km'] = joined.apply(lambda r:distance(
            r.latitude_archive,r.longitude_archive,r.latitude_2026,r.longitude_2026),axis=1)
        shift=joined.same_id_coordinate_shift_km
        rows.append({'archive_date': date,'ru_catalogue_objects_n': len(old),
            'same_id_in_current_n':len(joined),'not_same_id_in_current_n':len(old)-len(joined),
            'same_id_share':len(joined)/len(old), 'shift_median_km':float(shift.median()),
            'same_id_shift_le100m_n':int(shift.le(.1).sum()),
            'same_id_shift_le1km_n':int(shift.le(1).sum()),
            'same_id_shift_gt1km_n':int(shift.gt(1).sum()),
            'current_type_not_backcast':True})
        joined[['archive_date','source_object_id','source_country','typePoint_archive','typePoint_2026',
                'latitude_archive','longitude_archive','latitude_2026','longitude_2026',
                'same_id_coordinate_shift_km','baseline_uid','federal_territory_uid','link_status']].to_csv(
                    ROOT/f'WB_same_id_current_{date}.csv.gz',index=False,compression='gzip')
        typejoin=joined.assign(archive_type=joined.typePoint_archive.fillna(-1).astype(int),
                             current_type=joined.typePoint_2026.fillna(-1).astype(int))
        def fit_status(value):
            if pd.isna(value):
                return 'missing'
            return 'positive' if value >= 1 else 'zero'
        typejoin['archive_fit_status']=typejoin.fitting_rooms_archive.map(fit_status)
        typejoin['current_fit_status']=typejoin.fitting_rooms_2026.map(fit_status)
        for stable in [False,True]:
            sub=typejoin[typejoin.same_id_coordinate_shift_km.le(.1)] if stable else typejoin
            for (a,b),group in sub.groupby(['archive_type','current_type']):
                transitions.append({'archive_date':date,'only_same_id_within100m':stable,
                    'archive_typePoint':a,'current_typePoint':b,'objects_n':len(group)})
            for (a,b),group in sub.groupby(['archive_fit_status','current_fit_status']):
                fitting_transitions.append({'archive_date':date,'only_same_id_within100m':stable,
                    'archive_fitting_rooms_status':a,'current_fitting_rooms_status':b,'objects_n':len(group)})
    pd.DataFrame(rows).to_csv(ROOT/'WB_id_continuity.csv',index=False)
    pd.DataFrame(transitions).to_csv(ROOT/'WB_type_transitions.csv',index=False)
    pd.DataFrame(fitting_profiles).to_csv(ROOT/'fitting_rooms_profiles.csv',index=False)
    pd.DataFrame(fitting_transitions).to_csv(ROOT/'fitting_rooms_transitions.csv',index=False)
    manifest={'retrieved_on':'2026-10-24','historical_snapshots':snapshots,
        'normalized_rows_all_countries':len(history),'normalized_ru_rows':int(history.source_country.eq('ru').sum()),
        'current_comparison_input':str(CURRENT),'current_input_sha256':hashlib.sha256(CURRENT.read_bytes()).hexdigest(),
        'source_date_vs_commit':'Wayback memento/original HTTP dates; no Git commit date substituted for observation',
        'classification_warning':'pickupType,isWb,dtype are raw source flags with unverified changing semantics; client_point_confirmed_from_flags left unknown; current types not backcast',
        'status':'7 historical operator catalogue bodies acquired and archive digests verified; no full Ozon historical snapshot acquired'}
    (ROOT/'acquisition_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({'snapshots':len(snapshots),'rows_all':len(history),'rows_ru':manifest['normalized_ru_rows'],
        'ru_snapshot_sizes':[(s['observation_date'],s['ru_unique_ids'])for s in snapshots],
        'archive_digests_verified':True},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

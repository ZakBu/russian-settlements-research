"""Project reviewed named GeoKLADR city claims into pending point uses.

The independently reviewed source claims remain separate from application
approval. Current provider coordinates are a concordance screen only.
"""
from pathlib import Path
import argparse
import json
import pandas as pd
from .coverage import sha
from .apply_coordinate_extensions import base_use

RAW = Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
RAW2009 = Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql')


def stage(candidates, review_path, base, output):
    if output.exists():
        raise FileExistsError('Immutable application output already exists')
    review = json.loads(review_path.read_text())
    if review['decision'] != 'APPROVE_BOUNDED_CURRENT_CITY_HISTORICAL_POINT_DELTA':
        raise ValueError('Explicit bounded source-claim review required')
    pins = review['artifact_sha256']
    if pins.get('stage_candidates') != sha(candidates):
        raise ValueError('Candidate claims differ from independent review')
    ids = review['approved_target_source_record_ids']
    claims = pd.read_parquet(candidates)
    if not ids or len(ids) != len(set(ids)) or not set(ids).issubset(claims.source_record_id):
        raise ValueError('Invalid reviewed target set')
    claims = claims[claims.source_record_id.isin(ids)]
    existing = set(pd.read_parquet(base, columns=['target_source_record_id']).target_source_record_id)
    if existing & set(ids):
        raise ValueError('Reviewed current-city target already has a point')
    raw_sha, class_sha = sha(RAW), sha(RAW2009)
    rows = []
    for r in claims.itertuples(index=False):
        if not r.candidate_only_direct_geokladr_2011_point or r.admission_allowed:
            raise ValueError('Source claim is not a pending passed candidate')
        if r.source_sha256_2011 != raw_sha or r.source_sha256_2009 != class_sha:
            raise ValueError('Raw historical asset hash differs')
        locator = f'raw_dbf_record_number_1based={int(r.record_number_1based)};byte_offset_0based={int(r.record_byte_offset_0based)}'
        row = base_use(r.source_record_id, 2021, r.latitude_from_lat, r.longitude_from_long,
                       'GeoKLADR2011:OKATO:' + r.historical_okato_2011_raw,
                       r.name_raw_2011, r.settlement_type_raw, r.region_norm,
                       str(RAW), int(r.record_number_1based), raw_sha, locator,
                       'Named typed GeoKLADR 2011 city point; accepted 2010–2021 same-place edge and current provider concordance within 1 km',
                       'reviewed_current_city_direct_named_geokladr_2011_point_v1', {
                           'admission_allowed': False,
                           'coordinate_application_family': 'H_current_city_named_historical_point',
                           'point_origin_file': str(RAW), 'point_origin_sha256': raw_sha,
                           'point_origin_locator': locator, 'point_origin_kind': 'geokladr_2011_raw_dbf_coordinate',
                           'point_claim_artifact_file': str(candidates), 'point_claim_artifact_sha256': sha(candidates),
                           'source_okato_raw': r.historical_okato_2011_raw, 'source_oktmo_raw': r.oktmo,
                           'historical_classifier_source_sha256': class_sha,
                           'historical_classifier_source_line_1based': int(r.source_line_1based),
                           'historical_geo_to_provider_km': r.modern_provider_to_historical_point_km,
                           'current_provider_point_role': 'concordance screen only; not point origin or identifier binding',
                           'supporting_identity_edge_decision_id': r.identity_edge_decision_id,
                           'source_claim_independent_review_sha256': sha(review_path),
                           'application_inference_kind': 'named_2011_city_representative_point_current_spatial_continuity',
                           'direct_historical_coordinate_measurement': False,
                           'population_scope_comparability_asserted': False,
                           'lineage_event_roles_json': '[]',
                       })
        rows.append(row)
    output.mkdir(parents=True)
    p = output / 'staged_point_uses.parquet'
    pd.DataFrame(rows).to_parquet(p, index=False)
    receipt = {'status': 'staged_pending_application_review', 'staged_rows': len(rows),
               'staged_population': int(claims.population.sum()), 'builder_sha256': sha(Path(__file__)),
               'inputs': {str(v): sha(v) for v in [candidates, review_path, base, RAW, RAW2009]},
               'staged_point_uses_sha256': sha(p)}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ['candidates', 'review', 'base', 'output']:
        ap.add_argument('--' + k, required=True, type=Path)
    a = ap.parse_args()
    print(json.dumps(stage(a.candidates, a.review, a.base, a.output), ensure_ascii=False))

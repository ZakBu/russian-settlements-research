"""Candidate-only staging for direct GeoKladr 2011 points on current cities.

The point origin is the named 2011 GeoKladr city row. A near current provider
point is used only as a 1 km concordance screen; provider identifiers are not
bound or admitted by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import numpy as np

from .coordinate_ledger import SELECTED_DEFAULT, haversine_array

ROOT = Path('/workspace/settlements-work')
DEFAULT_OUT = ROOT / 'continuation_20261003/current_city_historical_stage_v1'
INPUTS = {
    'historical_named_v4': ROOT / 'coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet',
    'accepted_points_v1': ROOT / 'coordinates/accepted_final_v1/accepted_point_uses.parquet',
    'legacy_conflict_holds_v1': ROOT / 'coordinates/accepted_final_v1/additional_legacy_point_conflict_holds.parquet',
    'accepted_graph_v2': ROOT / 'identity/accepted_historical_v2/accepted_identity_edges.parquet',
    'coordinate_screen': ROOT / 'coordinates/ledger/coordinate_screen.parquet',
    'historical_city_event_review_v1': ROOT / 'continuation_20261003/historical_city_review_v1/review.json',
    'selected_r2': SELECTED_DEFAULT,
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _raw(v) -> str:
    if v is None or pd.isna(v):
        return ''
    return str(v).strip()


def _truth(v) -> bool:
    return isinstance(v, (bool, np.bool_)) and bool(v)


def city_code_bridge_ok(code2009, code2011, kod3, kind2009, kind2011) -> bool:
    """Allow only exact typed-city 8 digit + literal DBF KOD3 000 bridge."""
    a, b = _raw(code2009), _raw(code2011)
    return (
        kind2009 == 'город' and kind2011 == 'г'
        and re.fullmatch(r'\d{8}', a) is not None
        and re.fullmatch(r'\d{11}', b) is not None
        and b == a + '000' and _raw(kod3) == '000'
    )


def _valid_point(lat, lon) -> bool:
    try:
        a, b = float(lat), float(lon)
        return -90 <= a <= 90 and -180 <= b <= 180
    except (TypeError, ValueError):
        return False


def stage_row(row: dict, graph_ok: bool, conflict_hold: bool) -> dict:
    dist = row.get('modern_provider_to_historical_point_km')
    try:
        dist = float(dist)
    except (TypeError, ValueError):
        dist = float('nan')
    gates = {
        'selected_2021_city_np': row.get('census_year') == 2021 and row.get('type_norm') == 'город'
            and _truth(row.get('is_additive_settlement_record'))
            and row.get('entity_grain_status') not in {'aggregate', 'municipality', 'region'},
        'raw_source_full_grain_np': _truth(row.get('screen_source_object_is_naselenniy_punkt'))
            and not _truth(row.get('screen_source_is_aggregate_scope'))
            and _raw(row.get('screen_raw_object_level')).casefold() in {'населенный пункт', 'населённый пункт'},
        'historical_named_point_claim': _truth(row.get('historical_named_point_candidate')),
        'exact_name_and_type': _truth(row.get('historical_name_exact')) and _truth(row.get('historical_type_exact')),
        'exact_expected_region': _raw(row.get('historical_point_modern_region')) == _raw(row.get('region_norm'))
            and bool(_raw(row.get('region_norm'))),
        'source_city_unique': row.get('source_region_name_type_count') == 1
            and row.get('historical_key_region_name_type_count') == 1
            and not _truth(row.get('possible_unlocated_historical_competitor')),
        'literal_city_code_bridge': city_code_bridge_ok(
            row.get('historical_okato_2009_raw'), row.get('historical_okato_2011_raw'),
            row.get('kod3_raw_text'), row.get('status'), row.get('settlement_type_raw')),
        'geo_point_valid': _valid_point(row.get('latitude_from_lat'), row.get('longitude_from_long')),
        'accepted_collision_free_2010_same_place_edge': bool(graph_ok),
        'no_known_point_veto_event_role': not _truth(row.get('event_role_point_veto')),
        'provider_point_within_1km_concordance': pd.notna(dist) and dist <= 1.0,
        'no_known_conflict_hold': not conflict_hold,
    }
    passed = all(gates.values())
    hold_reasons = [key for key, value in gates.items() if not value]
    return {
        **row,
        **{f'gate_{k}': bool(v) for k, v in gates.items()},
        'candidate_only_direct_geokladr_2011_point': bool(passed),
        'candidate_status': 'candidate_requires_independent_review' if passed else 'hold_or_incomplete',
        'hold_reasons_json': json.dumps(hold_reasons, ensure_ascii=False),
        'point_origin': 'GeoKladr OKATO 2011 raw named city point',
        'point_origin_latitude': row.get('latitude_from_lat'),
        'point_origin_longitude': row.get('longitude_from_long'),
        'provider_point_role': '1km concordance screen only; not point origin, measurement, or FIAS binding',
        'provider_level_or_identifier_admitted': False,
        'measurement_date_unknown': True,
        'population_boundary_comparability_asserted': False,
        'boundary_change_interpretation': 'Any parent/child boundary context is annotation only; it does not establish point relocation.',
        'admission_allowed': False,
    }


def fixed_stratified_sample(df: pd.DataFrame) -> pd.DataFrame:
    """Stable sample: up to two rows per region, sorted by source ID."""
    if df.empty:
        return df.copy()
    sample = (df.sort_values(['region_norm', 'source_record_id'])
                .groupby('region_norm', sort=True, group_keys=False).head(2))
    return sample.reset_index(drop=True)


def _reason_population(df: pd.DataFrame) -> dict:
    totals = {}
    for r in df.to_dict('records'):
        for reason in json.loads(r['hold_reasons_json']):
            totals[reason] = totals.get(reason, 0) + int(r.get('population') or 0)
    return totals


def build(output: Path = DEFAULT_OUT, selected_path: Path = SELECTED_DEFAULT) -> dict:
    if output.exists():
        raise FileExistsError(f'Immutable stage path already exists: {output}')
    paths = dict(INPUTS)
    paths['selected_r2'] = selected_path
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    hist = pd.read_parquet(paths['historical_named_v4'])
    accepted = pd.read_parquet(paths['accepted_points_v1'], columns=['target_source_record_id'])
    held_ids = set(pd.read_parquet(paths['legacy_conflict_holds_v1'], columns=['target_source_record_id'])
                   .target_source_record_id.astype(str))
    selected = pd.read_parquet(paths['selected_r2'], columns=[
        'source_record_id', 'census_year', 'settlement_name', 'settlement_type',
        'region_norm', 'population', 'population_scope', 'is_additive_settlement_record',
        'entity_grain_status'])
    selected21 = selected[selected.census_year.eq(2021)].copy()
    if selected21.source_record_id.astype(str).duplicated().any():
        raise ValueError('2021 selected source IDs are not unique')
    h = hist[(hist.census_year.eq(2021)) & hist.type_norm.eq('город')
             & hist.historical_named_point_candidate.eq(True)].copy()
    h = h.merge(selected21[['source_record_id', 'population_scope', 'entity_grain_status']],
                on='source_record_id', how='inner', suffixes=('', '_selected'), validate='one_to_one')
    h = h[~h.source_record_id.isin(set(accepted.target_source_record_id.astype(str)))].copy()

    graph = pd.read_parquet(paths['accepted_graph_v2'], columns=[
        'relation', 'from_source_record_id', 'from_year', 'to_source_record_id', 'to_year',
        'decision_status', 'decision_class', 'decision_rule', 'decision_id'])
    graph = graph[(graph.relation.eq('same_place')) & graph.from_year.astype(str).eq('2010')
                  & graph.to_year.astype(str).eq('2021')].copy()
    edge_count = graph.groupby('to_source_record_id').size()
    graph_ok = set(edge_count[edge_count.eq(1)].index.astype(str))
    graph_one = graph[graph.to_source_record_id.astype(str).isin(graph_ok)].drop_duplicates('to_source_record_id')
    graph_cols = graph_one[['to_source_record_id', 'from_source_record_id', 'decision_id',
                            'decision_status', 'decision_rule']].rename(columns={
                                'to_source_record_id': 'source_record_id',
                                'from_source_record_id': 'identity_2010_source_record_id',
                                'decision_id': 'identity_edge_decision_id',
                                'decision_status': 'identity_edge_status',
                                'decision_rule': 'identity_edge_rule'})
    h = h.merge(graph_cols, on='source_record_id', how='left', validate='one_to_one')
    h['graph_unique_direct_edge'] = h.source_record_id.isin(graph_ok)
    event_review = json.loads(paths['historical_city_event_review_v1'].read_text())
    event_roles = pd.DataFrame(event_review.get('event_role_hits_within_1km', []))
    if event_roles.empty:
        event_veto_by_2010 = {}
        event_ids_2010 = set()
    else:
        event_veto_by_2010 = (event_roles.groupby('target_source_record_id').point_veto
                              .any().to_dict())
        event_ids_2010 = set(event_roles.target_source_record_id.astype(str))
    h['event_role_point_veto'] = h.identity_2010_source_record_id.map(event_veto_by_2010).fillna(False)
    h['event_role_present'] = h.identity_2010_source_record_id.astype(str).isin(event_ids_2010)

    screen_cols = ['source_record_id', 'provider_latitude', 'provider_longitude',
                   'provider_fias_level', 'provider_general_fias_id', 'provider_settlement_fias_id',
                   'provider_general_fias_duplicate_count', 'provider_settlement_fias_duplicate_count',
                   'provider_coordinate_duplicate_count', 'wikidata_p625_valid_wgs84_point_count',
                   'wikidata_p625_nearest_distance_km', 'wikidata_p625_farthest_distance_km',
                   'wikidata_p625_nearest_over_0_5km_screen', 'wikidata_p625_any_point_over_5km_screen', 'baseline_provider_coordinate_conflict',
                   'baseline_coordinate_review_required', 'prior_coordinate_admission_exists',
                   'census_municipality_upper_raw', 'census_municipality_lower_raw',
                   'source_object_is_naselenniy_punkt', 'source_is_aggregate_scope', 'raw_object_level']
    screen = pd.read_parquet(paths['coordinate_screen'], columns=screen_cols).rename(columns={
        'provider_latitude': 'provider_screen_latitude',
        'provider_longitude': 'provider_screen_longitude',
        'source_object_is_naselenniy_punkt': 'screen_source_object_is_naselenniy_punkt',
        'source_is_aggregate_scope': 'screen_source_is_aggregate_scope',
        'raw_object_level': 'screen_raw_object_level',
        'baseline_provider_coordinate_conflict': 'screen_baseline_provider_coordinate_conflict',
    })
    h = h.merge(screen, on='source_record_id', how='left', validate='one_to_one')
    h['modern_provider_to_historical_point_km'] = haversine_array(
        h.provider_screen_latitude, h.provider_screen_longitude, h.latitude_from_lat, h.longitude_from_long)
    h['p625_unresolved_conflict'] = (
        h.wikidata_p625_any_point_over_5km_screen.fillna(False).astype(bool)
        | h.wikidata_p625_nearest_over_0_5km_screen.fillna(False).astype(bool)
        | pd.to_numeric(h.wikidata_p625_valid_wgs84_point_count, errors='coerce').gt(1)
        | pd.to_numeric(h.wikidata_p625_farthest_distance_km, errors='coerce').gt(5)
    )
    h['known_legacy_hold'] = h.source_record_id.astype(str).isin(held_ids)
    h['source_coordinate_conflict_hold'] = (h.p625_unresolved_conflict | h.known_legacy_hold
        | h.screen_baseline_provider_coordinate_conflict.fillna(False).astype(bool))
    out = pd.DataFrame(stage_row(row, bool(row.get('graph_unique_direct_edge')),
                                 bool(row.get('source_coordinate_conflict_hold')))
                       for row in h.to_dict('records'))
    accepted_out = out[out.candidate_only_direct_geokladr_2011_point].copy()
    sample = fixed_stratified_sample(accepted_out)
    summary = (out.assign(population=pd.to_numeric(out.population, errors='coerce').fillna(0))
               .groupby('candidate_status', dropna=False)
               .agg(records=('source_record_id', 'size'), recorded_population=('population', 'sum'))
               .reset_index())
    output.mkdir(parents=True)
    out.to_parquet(output / 'all_current_city_historical_point_candidates.parquet', index=False)
    accepted_out.to_parquet(output / 'strong_rule_candidates.parquet', index=False)
    sample.to_csv(output / 'fixed_stratified_sample.csv', index=False)
    out[['source_record_id', 'settlement_name', 'region_norm', 'population', 'candidate_status',
         'hold_reasons_json', 'historical_okato_2009_raw', 'historical_okato_2011_raw',
         'name_raw_2009', 'name_raw_2011', 'status', 'settlement_type_raw', 'long_raw_text', 'lat_raw_text',
         'kod3_raw_text', 'source_sha256_2009', 'source_sha256_2011', 'record_number_1based',
         'record_byte_offset_0based', 'identity_2010_source_record_id', 'identity_edge_decision_id',
         'modern_provider_to_historical_point_km', 'wikidata_p625_valid_wgs84_point_count',
         'wikidata_p625_nearest_over_0_5km_screen', 'screen_baseline_provider_coordinate_conflict',
         'event_role_point_veto', 'known_legacy_hold', 'p625_unresolved_conflict']].to_csv(output / 'candidate_and_hold_register.csv', index=False)
    receipt = {
        'status': 'candidates_only_no_admissions',
        'rule': 'Direct GeoKladr 2011 named city point; exact typed 2009 city code8 plus raw Geo KOD3 000 code11; exact name/type/expected region and unique source grain; one accepted direct 2010->2021 same_place edge; provider point <=1 km as concordance screen only; known conflicts held.',
        'inputs': {k: {'path': str(v), 'sha256': sha(v)} for k, v in paths.items()},
        'raw_provenance_fields': ['source_sha256_2009', 'source_sha256_2011', 'historical_okato_2009_raw', 'historical_okato_2011_raw', 'kod3_raw_text', 'record_number_1based', 'record_byte_offset_0based', 'identity_2010_source_record_id', 'identity_edge_decision_id'],
        'event_crosscheck': {'register': 'historical_city_review_v1 event_role_hits_within_1km',
                             'matched_2010_endpoint_roles': int(h.event_role_present.sum()),
                             'point_veto_matches': int(h.event_role_point_veto.fillna(False).sum()),
                             'note': 'Only exact accepted 2010 graph endpoints were joined; no event role is inferred from name or parent code.'},
        'candidate_records': int(accepted_out.shape[0]),
        'candidate_recorded_population': int(pd.to_numeric(accepted_out.population).sum()),
        'held_records': int((~out.candidate_only_direct_geokladr_2011_point).sum()),
        'held_recorded_population': int(pd.to_numeric(out.loc[~out.candidate_only_direct_geokladr_2011_point, 'population']).sum()),
        'all_input_rows': int(out.shape[0]),
        'candidate_ids': accepted_out.source_record_id.astype(str).tolist(),
        'hold_population_by_reason': _reason_population(out),
        'summary_by_status': summary.to_dict('records'),
        'sample_rule': 'Deterministic: first two candidates per current source region after ascending exact source_record_id sort.',
        'sample_ids': sample.source_record_id.astype(str).tolist(),
        'limitations': [
            'All rows are candidate-only; point dates remain unknown and population boundary comparability is not asserted.',
            'The 1 km provider comparison is a screen only and does not claim measurement independence or bind provider IDs.',
            'The pre-existing 775 proof is not independent review of this newly scoped candidate use.',
            'Population equality, parent/child boundary changes, and provider object levels do not establish point relocation or identity.',
        ],
    }
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    receipt['outputs'] = {p.name: sha(p) for p in output.iterdir()
                          if p.is_file() and p.name != 'receipt.json'}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=DEFAULT_OUT)
    p.add_argument('--selected', type=Path, default=SELECTED_DEFAULT)
    a = p.parse_args()
    print(json.dumps(build(a.output, a.selected), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

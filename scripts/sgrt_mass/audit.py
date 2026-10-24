#!/usr/bin/env python3
"""Inspect mass nearest-service scenarios without turning them into observed flows.

The published planning benchmarks are a scenario screen, not a fitted travel
model, a Russian law compliance assessment or evidence of actual service use.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PLANNING_SOURCE_ID = 'SP42_2016_WEB2024_SERVICE_ACCESS'
# Exact service codes only: a generic "education"/"healthcare" is not screened
# as if it were a known stage or level of treatment.
TRANSPORT_BENCHMARKS = {
    'medical_primary_fap': 30., 'medical_fap': 30., 'fap': 30.,
    'medical_primary_physician': 30., 'medical_ambulatory': 30.,
    'primary_physician': 30., 'primary_care': 30.,
    'medical_basic_primary': 30., 'medical_physician_primary': 30.,
    'school_primary': 15.,
    'school_basic': 30., 'school_upper': 30., 'school_secondary': 30.,
    # 1–9 combines primary and basic; the source cannot justify a 15-minute
    # classification for all these children. Use only the broader scenario.
    'school_lower_secondary': 30.,
    'school_general': 30.,
}
PRESCHOOL_CODES = {'preschool', 'education_preschool', 'kindergarten', 'preschool_official2025', 'preschool_official'}
LOCAL_PRESENT = {'known_service_present', 'known_present', 'observed', 'present', 'mapped_present', 'known_local_supply', 'observed_present'}
LOCAL_PROXY = {'proxy_present'}
BACKED_EVIDENCE = {'normative_attachment', 'provider_reported_service', 'observed_flow'}
CANDIDATE_CLASSES = {'conditional_within_transport_benchmark', 'conditional_within_spatial_necessary_screen', 'conditional_school_stage_unknown_within_primary_time_screen', 'conditional_school_stage_unknown_within_basic_time_screen'}


def haversine_km(lon1, lat1, lon2, lat2):
    """Great-circle NP-point separation, not walking/driving path distance."""
    lon1, lat1, lon2, lat2 = np.deg2rad([np.asarray(x, dtype=float) for x in (lon1, lat1, lon2, lat2)])
    a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def canonical_assignments(assignments: pd.DataFrame) -> pd.DataFrame:
    frame = assignments.copy()
    if 'origin_id' not in frame and 'source_record_id' in frame:
        frame = frame.rename(columns={'source_record_id': 'origin_id'})
    if 'provider_settlement_id' not in frame:
        for alternative in ['selected_provider_source_record_id', 'selected_provider_settlement_id', 'primary_candidate_id', 'destination_id']:
            if alternative in frame:
                frame['provider_settlement_id'] = frame[alternative]
                break
    if 'cost_minutes' not in frame and 'primary_cost_minutes' in frame:
        frame['cost_minutes'] = frame.primary_cost_minutes
    required = {'origin_id', 'service_code', 'provider_settlement_id', 'cost_minutes'}
    if not required.issubset(frame):
        raise ValueError(f'missing assignment fields: {sorted(required-set(frame))}')
    frame['cost_minutes'] = pd.to_numeric(frame.cost_minutes, errors='raise')
    if 'provider_site_id' not in frame:
        site_column = next((column for column in ['selected_provider_id', 'provider_id'] if column in frame), None)
        frame['provider_site_id'] = frame[site_column] if site_column else None
    frame['center_identity_status'] = np.where(frame.provider_settlement_id.notna(), 'known_settlement_id', np.where(frame.provider_site_id.notna(), 'unresolved_center_settlement_identity', 'no_selected_center'))
    frame['center_key'] = None
    has_np = frame.provider_settlement_id.notna()
    frame.loc[has_np, 'center_key'] = 'np:' + frame.loc[has_np, 'provider_settlement_id'].astype(str)
    has_site_only = ~has_np & frame.provider_site_id.notna()
    frame.loc[has_site_only, 'center_key'] = 'site:' + frame.loc[has_site_only, 'provider_site_id'].astype(str)
    return frame


def enrich_geometry(assignments: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    frame = canonical_assignments(assignments)
    nodes = nodes.copy()
    if nodes.source_record_id.duplicated().any():
        raise ValueError('duplicate census node source_record_id')
    for target, alternatives in {'lat': ['latitude', 'accepted_latitude_2021'], 'lon': ['longitude', 'accepted_longitude_2021'], 'region': ['region_norm_2021'], 'name': ['settlement_name_2021'], 'settlement_type': ['settlement_type_2021']}.items():
        if target not in nodes:
            found = next((field for field in alternatives if field in nodes), None)
            nodes[target] = nodes[found] if found else np.nan
    fields = ['source_record_id', 'name', 'region', 'settlement_type', 'lon', 'lat']
    # Add immutable upstream context under prefixed names to avoid relying on
    # a route table's potentially stale place labels.
    origins = nodes[fields].rename(columns={c: 'origin_'+c for c in fields if c != 'source_record_id'})
    providers = nodes[fields].rename(columns={c: 'provider_'+c for c in fields if c != 'source_record_id'})
    frame = frame.drop(columns='source_record_id', errors='ignore')
    frame = frame.drop(columns=[c for c in origins if c != 'source_record_id' and c in frame], errors='ignore')
    frame = frame.drop(columns=[c for c in providers if c != 'source_record_id' and c in frame], errors='ignore')
    frame = frame.merge(origins, left_on='origin_id', right_on='source_record_id', how='left', validate='many_to_one').drop(columns='source_record_id')
    frame = frame.merge(providers, left_on='provider_settlement_id', right_on='source_record_id', how='left', validate='many_to_one').drop(columns='source_record_id')
    frame['provider_geometry_kind'] = 'accepted_settlement_point'
    for standard, alternative in [('selected_provider_lat','selected_provider_site_lat'), ('selected_provider_lon','selected_provider_site_lon')]:
        if standard not in frame and alternative in frame:
            frame[standard] = frame[alternative]
    if 'selected_provider_lat' in frame and 'selected_provider_lon' in frame:
        site_geometry = frame.selected_provider_lat.notna() & frame.selected_provider_lon.notna()
        frame.loc[site_geometry, 'provider_lat'] = frame.loc[site_geometry, 'selected_provider_lat']
        frame.loc[site_geometry, 'provider_lon'] = frame.loc[site_geometry, 'selected_provider_lon']
        frame.loc[site_geometry, 'provider_geometry_kind'] = 'physical_object_point'
    frame['provider_name'] = frame.provider_name.fillna(frame.provider_site_id)
    frame['point_separation_km'] = haversine_km(frame.origin_lon, frame.origin_lat, frame.provider_lon, frame.provider_lat)
    return frame


def classify_service_screen(assignments: pd.DataFrame, nodes: pd.DataFrame, *, nonadditive_context_ids=()) -> pd.DataFrame:
    """Annotate, preserve raw long links, and exclude them from screened units.

    No raw nearest row is promoted to a confirmed attachment. Even a short route
    remains conditional on completeness, dated service eligibility and capacity.
    """
    frame = enrich_geometry(assignments, nodes)
    local = frame.origin_id.eq(frame.provider_settlement_id) & frame.provider_settlement_id.notna()
    selected = frame.center_key.notna() & np.isfinite(frame.cost_minutes)
    frame['is_local'] = local
    frame['center_population_role'] = np.where(frame.provider_settlement_id.isin(set(nonadditive_context_ids)), 'external_context_nonadditive', np.where(frame.provider_settlement_id.notna(),'ordinary_settlement_center','unresolved_settlement_identity'))
    frame['screen_class'] = 'unresolved_no_known_candidate_or_route'
    frame.loc[selected, 'screen_class'] = 'service_screen_not_defined'
    frame['planning_benchmark_minutes'] = frame.service_code.map(TRANSPORT_BENCHMARKS)
    frame['planning_benchmark_point_radius_km'] = np.nan
    transport = selected & frame.planning_benchmark_minutes.notna()
    frame.loc[transport & (frame.cost_minutes <= frame.planning_benchmark_minutes), 'screen_class'] = 'conditional_within_transport_benchmark'
    frame.loc[transport & (frame.cost_minutes > frame.planning_benchmark_minutes), 'screen_class'] = 'outside_transport_benchmark'
    general_school = selected & frame.service_code.eq('school_general')
    frame['school_stage_unknown'] = frame.service_code.eq('school_general')
    frame.loc[general_school & (frame.cost_minutes <= 15), 'screen_class'] = 'conditional_school_stage_unknown_within_primary_time_screen'
    frame.loc[general_school & (frame.cost_minutes > 15) & (frame.cost_minutes <= 30), 'screen_class'] = 'conditional_school_stage_unknown_within_basic_time_screen'
    preschool = selected & frame.service_code.isin(PRESCHOOL_CODES)
    origin_type = frame.origin_settlement_type.fillna('').astype(str).str.lower()
    urban = origin_type.isin({'город', 'пгт', 'поселок городского типа', 'посёлок городского типа', 'рабочий поселок', 'рабочий посёлок'})
    rural = origin_type.isin({'село', 'деревня', 'поселок', 'посёлок', 'хутор', 'станица', 'аул', 'починок', 'слобода', 'выселок', 'заимка'})
    frame['benchmark_context'] = np.where(rural, 'source_rural_context', np.where(urban, 'urban_context_transfer_if_rural_transport_benchmark', 'settlement_type_context_unknown'))
    frame.loc[preschool & urban, 'planning_benchmark_point_radius_km'] = .3
    frame.loc[preschool & rural, 'planning_benchmark_point_radius_km'] = .5
    spatial_known = preschool & frame.planning_benchmark_point_radius_km.notna() & frame.point_separation_km.notna()
    frame.loc[spatial_known & (frame.point_separation_km <= frame.planning_benchmark_point_radius_km), 'screen_class'] = 'conditional_within_spatial_necessary_screen'
    frame.loc[spatial_known & (frame.point_separation_km > frame.planning_benchmark_point_radius_km), 'screen_class'] = 'outside_spatial_necessary_screen'
    frame.loc[preschool & ~spatial_known, 'screen_class'] = 'preschool_geographic_screen_unknown'
    frame.loc[local & selected, 'screen_class'] = 'local_known_service_candidate'
    # A zero at the NP point says nothing about actual within-city access.
    frame['same_settlement_access_to_building_estimated'] = False
    frame['benchmark_class'] = frame.screen_class
    frame['screen_source_id'] = np.where(frame.service_code.isin(set(TRANSPORT_BENCHMARKS) | PRESCHOOL_CODES), PLANNING_SOURCE_ID, None)
    frame['transport_benchmark_mode'] = np.where(frame.service_code.isin(TRANSPORT_BENCHMARKS), 'planning_transport_not_verified_school_bus_or_actual_trip', None)
    # Compatibility alias: this formerly meant 'not proved same NP'. New users
    # must distinguish a confirmed cross-NP relation from unknown site identity.
    frame['screened_external_candidate'] = ~local & frame.screen_class.isin(CANDIDATE_CLASSES)
    frame['screened_external_identity_confirmed'] = frame.provider_settlement_id.notna() & ~local & frame.screen_class.isin(CANDIDATE_CLASSES)
    frame['screened_candidate_np_relation_unknown'] = frame.provider_settlement_id.isna() & frame.provider_site_id.notna() & frame.screen_class.isin(CANDIDATE_CLASSES)
    frame['raw_nearest_is_established_attachment'] = False
    frame['incomplete_supply_may_change_candidate'] = True
    if 'local_supply_status' not in frame:
        frame['local_supply_status'] = 'unknown'
    frame['local_supply_unknown'] = ~frame.local_supply_status.fillna('unknown').isin(LOCAL_PRESENT | {'confirmed_absent', 'confirmed_absent_in_input'})
    return frame


def check_assignments(assignments: pd.DataFrame, nodes: pd.DataFrame, supply: pd.DataFrame | None = None, *, accepted_supply_statuses=('observed',), allowed_provider_context_ids=()) -> pd.DataFrame:
    """Return concrete offending rows. Empty output does not validate real flows."""
    frame = canonical_assignments(assignments)
    violations = []
    def capture(mask, reason):
        for row in frame.loc[mask, ['origin_id', 'service_code', 'provider_settlement_id', 'cost_minutes']].to_dict('records'):
            violations.append(dict(check=reason, **row))
    capture(frame.duplicated(['origin_id', 'service_code'], keep=False), 'duplicate_origin_service')
    capture(frame.cost_minutes.notna() & ((frame.cost_minutes < 0) | ~np.isfinite(frame.cost_minutes)), 'invalid_numeric_cost')
    capture(frame.origin_id.isna() | ~frame.origin_id.isin(nodes.source_record_id), 'unknown_origin')
    capture(frame.provider_settlement_id.notna() & ~frame.provider_settlement_id.isin(set(nodes.source_record_id) | set(allowed_provider_context_ids)), 'unknown_provider_settlement')
    selected = frame.center_key.notna()
    capture(selected & frame.cost_minutes.isna(), 'selected_provider_without_cost')
    local = frame.origin_id.eq(frame.provider_settlement_id) & selected
    physical_geometry = pd.Series(False, index=frame.index)
    for lat_field in ['selected_provider_lat','selected_provider_site_lat']:
        if lat_field in frame:
            physical_geometry = physical_geometry | frame[lat_field].notna()
    zero_np_assumption = frame.get('zero_cost_np_assumption', pd.Series(False,index=frame.index)).map(lambda value: str(value).lower() in {'true','1'})
    capture(local & (~physical_geometry | zero_np_assumption) & frame.cost_minutes.notna() & (frame.cost_minutes.abs() > 1e-6), 'same_np_baseline_not_zero')
    for field in ['observed_flow', 'assignment_established', 'established_flow', 'raw_nearest_is_established_attachment']:
        if field in frame:
            true = frame[field].map(lambda value: str(value).lower() in {'true', '1'})
            capture(true, 'model_row_claimed_as_observed_or_established:'+field)
    if 'network_minutes' in frame and 'connector_minutes' in frame:
        error = (frame.network_minutes+frame.connector_minutes-frame.cost_minutes).abs()
        capture(error > .001, 'network_connector_cost_mismatch')
    if 'local_supply_status' in frame:
        known = frame.local_supply_status.isin(LOCAL_PRESENT | LOCAL_PROXY)
        if 'known_local_supply' in frame:
            known = known | frame.known_local_supply.map(lambda value: str(value).lower() in {'true', '1'})
        provably_not_local = frame.provider_settlement_id.notna() & ~local
        no_choice = frame.center_key.isna()
        capture(known & (provably_not_local | no_choice | frame.cost_minutes.isna()), 'known_same_service_local_not_retained')
    if supply is not None:
        supply = supply.copy()
        if 'source_record_id' not in supply or 'service_code' not in supply:
            raise ValueError('supply requires source_record_id and service_code')
        if 'supply_status' in supply:
            supply = supply[supply.supply_status.isin(set(accepted_supply_statuses))]
        valid = set(zip(supply.source_record_id, supply.service_code))
        not_backed = pd.Series([pair not in valid for pair in zip(frame.provider_settlement_id, frame.service_code)], index=frame.index)
        if 'provider_id' in supply:
            valid_sites = set(zip(supply.provider_id, supply.service_code))
            site_backed = pd.Series([pair in valid_sites for pair in zip(frame.provider_site_id, frame.service_code)], index=frame.index)
            not_backed = not_backed & ~site_backed
        capture(selected & not_backed, 'selected_service_not_backed_by_supply')
    return pd.DataFrame(violations, columns=['check', 'origin_id', 'service_code', 'provider_settlement_id', 'cost_minutes'])


def _safe_stat(series, method='median', q=None):
    values = series.dropna()
    if values.empty:
        return np.nan
    return float(values.quantile(q)) if q is not None else float(getattr(values, method)())


def aggregate_units(screened: pd.DataFrame) -> pd.DataFrame:
    """Candidate stars, not continuous polygon regions or a full partition."""
    chosen = screened[screened.screened_external_candidate | screened.screen_class.eq('local_known_service_candidate')].copy()
    rows = []
    for (service, center_key), group in chosen.groupby(['service_code', 'center_key'], dropna=False):
        provider = group.provider_settlement_id.iloc[0]
        ext = group[group.screened_external_identity_confirmed]
        associated = group[group.screened_candidate_np_relation_unknown]
        known_local = bool(group.is_local.any())
        if len(ext):
            family = 'conditional_local_service_candidate'
        else:
            family = 'known_service_without_screened_external_members'
        if group.center_identity_status.eq('unresolved_center_settlement_identity').all():
            family = 'unresolved_center_settlement_identity'
        if group.center_population_role.eq('external_context_nonadditive').all():
            family = 'external_context_nonadditive'
        metadata = {}
        for output, input_field, fallback in [('provider_source_ids_json','selected_source_ids_json','selected_provider_source_id'), ('provider_document_years_json','selected_source_years_json',None), ('provider_observation_years_json','selected_observation_years_json','selected_provider_observation_year'), ('provider_match_statuses_json','selected_match_statuses_json',None)]:
            values = group[input_field].dropna() if input_field in group else pd.Series(dtype=object)
            if len(values):
                metadata[output] = values.iloc[0]
            elif fallback and fallback in group:
                metadata[output] = json.dumps(sorted(set(group[fallback].dropna().astype(str))))
            else:
                metadata[output] = None
        rows.append(dict(unit_id=service+'|'+str(center_key), service_code=service,
                         provider_settlement_id=provider, provider_site_id=group.provider_site_id.iloc[0],
                         center_identity_status=group.center_identity_status.iloc[0],
                         center_population_role=group.center_population_role.iloc[0], provider_name=group.provider_name.iloc[0],
                         provider_region=group.provider_region.iloc[0],
                         unit_type=family, has_local_origin=known_local,
                         external_records=len(ext), external_local_supply_unknown=int(ext.local_supply_unknown.sum()),
                         external_positive_credited_records=int((pd.to_numeric(ext.credited_population_2021,errors='coerce')>0).sum()) if 'credited_population_2021' in ext else None,
                         associated_origin_records=len(associated),
                         associated_positive_credited_records=int((pd.to_numeric(associated.credited_population_2021,errors='coerce')>0).sum()) if 'credited_population_2021' in associated else None,
                         associated_np_relation='unknown_not_proved_external' if len(associated) else 'not_applicable',
                         median_associated_minutes=_safe_stat(associated.cost_minutes),
                         p90_associated_minutes=_safe_stat(associated.cost_minutes,q=.9),
                         max_associated_minutes=_safe_stat(associated.cost_minutes,'max'),
                         max_associated_point_radius_km=_safe_stat(associated.point_separation_km,'max'),
                         median_external_minutes=float(ext.cost_minutes.median()) if len(ext) else np.nan,
                         p90_external_minutes=float(ext.cost_minutes.quantile(.9)) if len(ext) else np.nan,
                         max_external_minutes=float(ext.cost_minutes.max()) if len(ext) else np.nan,
                         p95_point_radius_km=_safe_stat(ext.point_separation_km, q=.95),
                         max_point_radius_km=_safe_stat(ext.point_separation_km, 'max'),
                         source_date='see_explicit_provider_document_and_observation_years_separately', established_sgrt=False,
                         **metadata,
                         geometry_kind='settlement_points_not_reconstructed_boundary'))
    return pd.DataFrame(rows)


def time_distributions(screened: pd.DataFrame) -> pd.DataFrame:
    records = []
    for (service, region, screen), group in screened.groupby(['service_code', 'origin_region', 'screen_class'], dropna=False):
        times = group.cost_minutes.dropna()
        records.append(dict(service_code=service, origin_region=region, screen_class=screen,
                            origin_records=len(group), recorded_costs=len(times),
                            median_minutes=_safe_stat(times), p90_minutes=_safe_stat(times,q=.9),
                            p99_minutes=_safe_stat(times,q=.99), max_minutes=_safe_stat(times,'max'),
                            over_30_minutes=int((times>30).sum()), over_60_minutes=int((times>60).sum()),
                            median_point_separation_km=_safe_stat(group.point_separation_km)))
    return pd.DataFrame(records)


def check_service_evidence(evidence: pd.DataFrame, raw_sites: pd.DataFrame) -> pd.DataFrame:
    """Return real source rows admitted as broad primary despite contrary evidence."""
    required = {'object_id','service_code'}
    if not required.issubset(evidence):
        raise ValueError('evidence needs object_id/service_code')
    if raw_sites.object_id.duplicated().any():
        raise ValueError('raw source object_id is not unique')
    joined = evidence.merge(raw_sites,on='object_id',how='left',validate='many_to_one',suffixes=('','_raw'),indicator=True)
    violations = []
    for row in joined.to_dict('records'):
        reasons = []
        if row['_merge']!='both':
            reasons.append('service_evidence_missing_raw_source_row')
        for flag in ['registered_exclusion_present','source_year_conflict_with_inventory']:
            if str(row.get(flag,'')).lower() in {'true','1'}:
                reasons.append('source_exclusion_not_respected:'+flag)
        if row['service_code'] in {'medical_basic_primary','medical_physician_primary'}:
            for flag in ['restricted_access_signal','pediatric_only_signal','school_or_preschool_medical_scope_signal']:
                if str(row.get(flag,'')).lower() in {'true','1'}:
                    reasons.append('broad_primary_incompatible_source_role:'+flag)
            name = str(row.get('subdivision_name','')).casefold()
            if re.search(r'помощ.{0,35}несовершеннолетн.{0,35}образовательн|медицинск.{0,15}кабинет.{0,20}(?:школ|дошкольн)|(?:школ|дошкольн).{0,20}медицинск.{0,15}кабинет',name):
                reasons.append('school_limited_care_not_general_primary_offer')
        for reason in reasons:
            violations.append({'check':reason,'object_id':row['object_id'],'service_code':row['service_code'],
                               'subdivision_name':row.get('subdivision_name'),
                               'source_part':row.get('source_part_raw',row.get('source_part')),
                               'source_row':row.get('source_row_raw',row.get('source_row'))})
    return pd.DataFrame(violations,columns=['check','object_id','service_code','subdivision_name','source_part','source_row'])


def check_metric_aggregation(metrics: pd.DataFrame) -> pd.DataFrame:
    """Explicitly reject summing a repeated municipal total over its settlements."""
    needed = {'measure_id', 'source_grain', 'aggregation_method'}
    if not needed.issubset(metrics):
        raise ValueError(f'metric table missing {sorted(needed-set(metrics))}')
    bad = metrics.source_grain.isin({'municipality', 'region', 'district', 'selsoviet'}) & metrics.aggregation_method.isin({'sum_over_settlements', 'sum_over_nodes', 'sum_members'})
    return metrics.loc[bad].assign(check='municipal_total_cannot_be_summed_over_settlements')


def select_resolved_normative_pairs(attachments: pd.DataFrame,
                                   quarantine: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the frozen reviewed source rules, never select by model distance.

    A quarantine is mandatory: literal locality equality alone did not resolve
    six reviewed source-context conflicts. Missing partial/address/spatial flags
    are not positive identity evidence. This selector cannot discover new
    geographical conflicts and must not be advertised as a blind holdout.
    """
    keys = ['source_id','sheet','excel_row_1based']
    required = {*keys,'origin_id','destination_id','origin_present_in_spatial2021',
                'destination_present_in_spatial2021','origin_is_partial_address_scope'}
    if not required.issubset(attachments):
        raise ValueError('normative attachments lack source/identity flags: '+str(sorted(required-set(attachments))))
    if not set(keys).issubset(quarantine):
        raise ValueError('reviewed quarantine must contain source_id/sheet/excel_row_1based')
    if quarantine[keys].isna().any().any():
        raise ValueError('quarantine source keys cannot be missing')
    source = attachments.drop(columns='context_conflict',errors='ignore').merge(
        quarantine[keys].drop_duplicates().assign(context_conflict=True),
        on=keys,how='left',validate='many_to_one')
    source['context_conflict'] = source.context_conflict.eq(True)
    resolved = source.origin_id.notna() & source.destination_id.notna()
    resolved &= source.origin_present_in_spatial2021.eq(True)
    resolved &= source.destination_present_in_spatial2021.eq(True)
    resolved &= source.origin_is_partial_address_scope.eq(False)
    resolved &= ~source.context_conflict
    external = source[resolved & source.origin_id.ne(source.destination_id)]
    return source, external.drop_duplicates(['origin_id','destination_id']).copy()


def compare_normative_pairs(relations: pd.DataFrame, assignments: pd.DataFrame,
                            supply: pd.DataFrame) -> pd.DataFrame:
    """Compare pre-resolved independent pairs; never fit or claim trip accuracy.

    Caller must supply the nonconflicting, nonpartial source relations. Provider
    coverage is evaluated independently of agreement, and a covered provider
    does not imply that its service tier matches the normative document.
    """
    if relations[['origin_id', 'destination_id']].isna().any().any():
        raise ValueError('normative pairs must already have resolved identities')
    expected = relations.groupby('origin_id').destination_id.agg(lambda x: sorted(set(x)))
    frame = canonical_assignments(assignments)
    if frame.duplicated(['origin_id','service_code']).any():
        raise ValueError('duplicate predicted origin/service')
    observed = supply[supply.supply_status.eq('observed')]
    rows = []
    for service, group in frame.groupby('service_code'):
        prediction = group.set_index('origin_id')
        known = set(observed.loc[observed.service_code.eq(service),'source_record_id'])
        for origin, destinations in expected.items():
            present = origin in prediction.index
            row = prediction.loc[origin] if present else None
            candidate = row.provider_settlement_id if present else None
            rows.append(dict(origin_id=origin,service_code=service,
                normative_destination_ids=json.dumps(destinations,ensure_ascii=False),
                provider_settlement_id=candidate,
                cost_minutes=row.cost_minutes if present else np.nan,
                origin_in_model_frame=present,
                candidate_present=pd.notna(candidate),
                any_normative_provider_in_observed_service_supply=bool(set(destinations)&known),
                agreement=pd.notna(candidate) and candidate in destinations,
                evidence_kind='normative_attachment_not_observed_trip',
                service_tier_equivalence_established=False,
                parameters_fitted_to_these_pairs=False,
                preregistered_blind_holdout=False))
    return pd.DataFrame(rows)


def run_normative_comparison(attachments_path, quarantine_path, supply_path,
                             assignment_paths, output):
    """Rebuild pair selection and current-source comparisons from frozen inputs."""
    paths = [Path(attachments_path),Path(quarantine_path),Path(supply_path),
             *(Path(path) for path in assignment_paths)]
    source, pairs = select_resolved_normative_pairs(read_table(paths[0]),read_table(paths[1]))
    supply = read_table(paths[2])
    assignments = pd.concat([read_table(path) for path in paths[3:]],ignore_index=True)
    result = compare_normative_pairs(pairs,assignments,supply)
    output = Path(output); output.mkdir(parents=True,exist_ok=True)
    source.to_parquet(output/'medical_attachments_with_context_flags.parquet',index=False)
    pairs.to_parquet(output/'resolved_normative_pairs.parquet',index=False)
    result.to_parquet(output/'pair_level_comparison.parquet',index=False)
    result.to_csv(output/'pair_level_comparison.csv',index=False)
    summaries = []
    for service, group in result.groupby('service_code'):
        summaries.append(dict(service_code=service,origins=len(group),
            origin_in_model_frame=int(group.origin_in_model_frame.sum()),
            candidate_present=int(group.candidate_present.sum()),
            normative_provider_in_current_service_supply=int(group.any_normative_provider_in_observed_service_supply.sum()),
            agreement=int(group.agreement.sum()),
            agreement_given_supply_present=int((group.agreement & group.any_normative_provider_in_observed_service_supply).sum())))
    summary = dict(source_rows=len(source),source_context_conflict_rows=int(source.context_conflict.sum()),
        resolved_external_pairs=len(pairs),resolved_origins=int(pairs.origin_id.nunique()),
        source_document_dates=sorted(set(source.document_date.dropna().astype(str))) if 'document_date' in source else [],
        normative_not_observed_trip=True,service_tiers_not_proven_equivalent=True,
        blind_holdout=False,parameters_fitted_or_selected=False,
        selection_rules=['resolved origin and destination IDs','both present in accepted spatial2021',
                         'origin_is_partial_address_scope exactly false','exclude reviewed quarantine source keys',
                         'origin differs from destination','deduplicate origin/destination pairs'],
        summaries=summaries,input_sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        audit_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def extract_argayash_provider_cards(web_text: str) -> pd.DataFrame:
    """Parse factual addresses from the saved official-page web-reader extract.

    This is a frozen cached-text source, not a claim that original HTML was
    downloaded or that all listed facilities were operating on retrieval day.
    Phone/availability placeholders remain uninterpreted literal evidence.
    """
    lines = []
    for raw in web_text.splitlines():
        match = re.match(r'L(\d+):\s*(.*)',raw)
        if match:
            lines.append((int(match.group(1)),match.group(2)))
    titles = []
    for position,(number,value) in enumerate(lines):
        match = re.match(r'【\d+†((?:ФАП|ЦОВП)\b[^】]*)】$',value)
        if match:
            titles.append((position,number,match.group(1)))
    records = []
    for index,(position,number,name) in enumerate(titles):
        stop = titles[index+1][0] if index+1<len(titles) else len(lines)
        block = lines[position+1:stop]
        address = next(((n,value) for n,value in block if re.match(r'^\d{6},',value)),None)
        if address is None:
            raise ValueError('named provider card lacks a literal postal address: '+name)
        ambiguous = [value for _,value in block if value=='Временно недоступен']
        records.append(dict(object_id='argayash_web:'+str(number),subdivision_name=name,
                            activity_address=address[1],source_region_literal='Челябинская область',
                            district_context='Аргаяшский район',source_id='ARGCRB74_UNDATED_PROVIDER_LIST',
                            source_url='https://argcrb74.ru/fap-i-ambulatoriy/',
                            source_kind='official_provider_page_web_reader_cached_text',
                            source_text_fetched_date='2026-10-24',
                            document_date=None,observation_year=None,
                            source_year_basis='undated_page_no_transfer_of_crawl_date_to_observation',
                            service_code='medical_basic_primary' if name.startswith('ФАП') else 'medical_physician_primary',
                            listing_status='listed_in_official_provider_directory',
                            literal_ambiguous_status='|'.join(ambiguous) if ambiguous else None,
                            actual_operational_status_checked=False,
                            source_locator=f'web_reader_lines{number}-{address[0]}',
                            original_html_downloaded=False,
                            source_extract_sha256=hashlib.sha256(web_text.encode('utf-8')).hexdigest()))
    return pd.DataFrame(records)


def read_table(path):
    return pd.read_parquet(path) if path.suffix.lower() == '.parquet' else pd.read_csv(path)


def main():
    if len(sys.argv)>1 and sys.argv[1]=='compare-normative':
        parser=argparse.ArgumentParser(description='Recompute dated normative pairs; not trip accuracy')
        parser.add_argument('--attachments',type=Path,required=True)
        parser.add_argument('--quarantine',type=Path,required=True)
        parser.add_argument('--supply',type=Path,required=True)
        parser.add_argument('--assignments',type=Path,required=True,nargs='+')
        parser.add_argument('--output',type=Path,required=True)
        args=parser.parse_args(sys.argv[2:])
        print(json.dumps(run_normative_comparison(args.attachments,args.quarantine,args.supply,args.assignments,args.output),ensure_ascii=False))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assignments', type=Path, required=True, nargs='+')
    parser.add_argument('--nodes', type=Path, required=True)
    parser.add_argument('--supply', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider-context-id', action='append', default=[], help='Explicit nonadditive provider context; does not enlarge allowed origins')
    args = parser.parse_args()
    assignments = pd.concat([read_table(path) for path in args.assignments], ignore_index=True)
    nodes = read_table(args.nodes)
    supply = pd.concat([read_table(path) for path in args.supply], ignore_index=True) if args.supply else None
    errors = check_assignments(assignments, nodes, supply, allowed_provider_context_ids=args.provider_context_id)
    screened = classify_service_screen(assignments, nodes, nonadditive_context_ids=args.provider_context_id)
    units = aggregate_units(screened)
    distributions = time_distributions(screened)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, table in [('screened_assignments',screened), ('candidate_units',units), ('time_distributions',distributions), ('concrete_violations',errors)]:
        table.to_parquet(args.output/(name+'.parquet'), index=False)
        if name != 'screened_assignments':table.to_csv(args.output/(name+'.csv'), index=False)
    summary = {'origin_service_rows':len(screened),'candidate_units':len(units),
               'concrete_violations':len(errors),'established_sgrt':False,
               'allowed_nonadditive_provider_context_ids':args.provider_context_id,
               'input_sha256':{str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in [*args.assignments,args.nodes,*(args.supply or [])]},
               'audit_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.output/'audit_run.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))
    if len(errors):raise SystemExit(1)


if __name__ == '__main__':
    main()

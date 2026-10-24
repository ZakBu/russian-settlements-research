#!/usr/bin/env python3
"""Prepare dated, source-linked pilot supply. Does not modify the census foundation."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

PILOT_REGIONS = ['удмуртская', 'ленинградская', 'челябинская', 'вологодская']
INPUT_PATHS = {
    'legacy_axis': 'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',
    'medical2021': 'research/sgrt_word_completion_20261021/medical/history_20210101/osm_medical_inventory.parquet',
    'education2021': 'research/sgrt_word_completion_20261021/education/education_objects_2021.parquet',
    'udmurt2025': 'research/sgrt_word_completion_20261021/medical/udmurt_official_2025/physical_fap_inventory.parquet',
    'lo2024': 'research/sgrt_word_completion_20261021/validation/medical_territories_2024_all_rows.parquet',
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def norm(text):
    import re, unicodedata
    value = unicodedata.normalize('NFKC', str(text)).lower().replace('ё', 'е')
    value = re.sub(r'^(город|г\.|село|с\.|деревня|д\.|пос[её]лок|п\.|пгт\.?|рп\.?|станица|ст-ца)\s*', '', value)
    return re.sub(r'[^а-яa-z0-9]', '', value)


def prepare(population_root, input_root, output, catalog_path, udmurt_workbook=None):
    output.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(catalog_path.read_text())
    files = {r['path']: r for r in catalog['files']}
    provenance = []
    for label, rel in INPUT_PATHS.items():
        path = input_root / rel
        row = files[rel]
        expected = catalog['objects'][row['blob']]['sha256']
        observed = sha256(path)
        if observed != expected: raise ValueError(f'Catalogue checksum mismatch: {rel}')
        provenance.append({'label': label, 'path': rel, 'sha256': observed,
                           'bytes': path.stat().st_size, 'asset': row.get('asset')})

    long = pd.read_parquet(population_root / 'data/population/settlements_census_long.parquet')
    federal = pd.read_csv(population_root / 'data/population/federal_territories.csv')
    federal = federal[federal.census_year.eq(2021)].copy()
    federal_source_ids = set(federal.population_source_record_id.dropna())
    raw_current = long[long.census_year.eq(2021) & long.is_additive_settlement_record].copy()
    current = raw_current[~raw_current.source_record_id.isin(federal_source_ids)].copy()
    axis = pd.read_parquet(input_root / INPUT_PATHS['legacy_axis'])
    bridge = axis[['id', 'source_record_id_2021', 'root', 'region', 'name', 'lat', 'lon']].copy()
    bridge.columns = ['legacy_id', 'source_record_id', 'legacy_root', 'legacy_region', 'legacy_name', 'legacy_lat', 'legacy_lon']
    bridge = bridge[bridge.source_record_id.notna()].copy()
    counts = bridge.source_record_id.value_counts()
    bridge['source_id_mapping_unique'] = bridge.source_record_id.map(counts).eq(1)
    bridge['present_in_primary_2021'] = bridge.source_record_id.isin(current.source_record_id)
    bridge.to_parquet(output / 'source_bridge.parquet', index=False)
    goodbridge = bridge[bridge.source_id_mapping_unique & bridge.present_in_primary_2021].copy()
    idmap = goodbridge.set_index('legacy_id').source_record_id
    # Keep additive records with an accepted point, including zero-population/noncredited rows.
    # Working-credit flag is retained so population totals can be recomputed at the accepted grain.
    pts = current[current.accepted_point_present].copy()
    pts = pts.rename(columns={'settlement_name': 'name', 'region_norm': 'region',
                              'population': 'population_raw', 'effective_population': 'population',
                              'accepted_latitude': 'lat', 'accepted_longitude': 'lon'})
    cols = ['source_record_id', 'root', 'name', 'settlement_type', 'region', 'district_raw', 'population',
            'population_raw', 'population_overlay_applied', 'population_value_quality', 'working_credit_present',
            'accepted_point_present', 'coordinate_admission_status', 'lat', 'lon', 'census_year']
    pts = pts[cols].merge(goodbridge[['source_record_id', 'legacy_id']], on='source_record_id', how='left', validate='one_to_one')
    for year in (2002, 2010):
        ys = long[long.census_year.eq(year)][['root', 'source_record_id', 'population', 'effective_population', 'working_credit_present']].copy()
        # A graph component with more than one record in a census is not summed here.
        ys = ys[~ys.root.duplicated(keep=False)]
        ys = ys.rename(columns={c: f'{c}_{year}' for c in ys if c != 'root'})
        pts = pts.merge(ys, on='root', how='left', validate='many_to_one')
    pts['population_2021'] = pts.population
    pts['credited_population_2021'] = pts.population.where(pts.working_credit_present)
    for year in (2002, 2010):
        pts[f'credited_population_{year}'] = pts[f'effective_population_{year}'].where(pts[f'working_credit_present_{year}'].eq(True))
    pts['in_pilot'] = pts.region.isin(PILOT_REGIONS)
    pts.to_parquet(output / 'settlements_all_2021.parquet', index=False)
    pilot = pts[pts.in_pilot].copy()
    pilot.to_parquet(output / 'settlements.parquet', index=False)
    current_index = pts.set_index('source_record_id')
    metadata = current_index[['root', 'name', 'region', 'population', 'lat', 'lon', 'working_credit_present', 'credited_population_2021']].copy()
    metadata['population_role'] = 'settlement_census_observation'

    raw_objects = []
    m = pd.read_parquet(input_root / INPUT_PATHS['medical2021'])
    m = m[m.broad_function.eq('healthcare') & ~m.inactive_source_assertion].copy()
    med_order = {
        'fap_name_assertion': 'primary_fap', 'ambulatory_name_assertion': 'primary_ambulatory',
        'polyclinic_name_assertion': 'primary_polyclinic',
        'central_district_hospital_name_assertion': 'district_hospital',
        'district_local_hospital_name_assertion': 'district_hospital',
        'regional_hospital_name_assertion': 'regional_hospital',
    }
    m['function'] = 'healthcare'
    m['service_order'] = m.medical_class.map(med_order).fillna('unspecified_healthcare')
    m['source_id'] = 'OSM_RUSSIA_20210101_MEDICAL'
    m['source_object_id'] = m.object_id
    m['observation_year'] = 2021
    m['object_name'] = m['name']
    m['canonical_object_id'] = m.object_id
    m['object_locality'] = m.source_address_locality
    m['object_address'] = m.addr_full
    for scenario, ids in [
        ('strict_address', m.baseline_uid),
        ('spatial_proxy', m.baseline_uid.combine_first(m.coordinate_candidate_uid.where(m.link_status.eq('strong_coordinate_candidate_le1km_not_identity_accepted')))),
    ]:
        x = m.copy(); x['scenario'] = scenario; x['legacy_id'] = ids; raw_objects.append(x)
    e = pd.read_parquet(input_root / INPUT_PATHS['education2021'])
    def education_inactive(raw):
        tags = json.loads(raw)
        return any(str(tags.get(k)).lower() in {'yes', 'true', '1'} for k in ('disused', 'abandoned', 'demolished')) or bool(tags.get('disused:amenity'))
    education_inactive_mask = e.tags_json.map(education_inactive)
    excluded_inactive_education_objects = int(education_inactive_mask.sum())
    e = e[~education_inactive_mask].copy()
    e['function'] = 'education'
    e['service_order'] = e.education_group
    e['source_id'] = 'OSM_RUSSIA_20210101_EDUCATION'
    e['source_object_id'] = e.site_id
    e['observation_year'] = 2021
    e['object_name'] = e['name']
    e['canonical_object_id'] = e.canonical_site_id
    e['object_locality'] = e.source_address_locality
    e['object_address'] = None
    for scenario, ids in [('strict_address', e.baseline_uid), ('spatial_proxy', e.baseline_uid.combine_first(e.candidate_uid))]:
        x = e.copy(); x['scenario'] = scenario; x['legacy_id'] = ids; raw_objects.append(x)
    objects = pd.concat(raw_objects, ignore_index=True)
    objects['source_record_id'] = objects.legacy_id.map(idmap)
    objects['match_status'] = np.where(objects.source_record_id.isna(), 'unresolved_or_not_in_accepted2021', 'exact_source_record_bridge')
    objects['value_status'] = 'proxy'
    objects['capacity_value'] = np.nan
    objects['capacity_unit'] = None
    objects['capacity_status'] = 'unknown'
    keep = ['source_id', 'source_object_id', 'canonical_object_id', 'scenario', 'function', 'service_order', 'observation_year',
            'source_record_id', 'legacy_id', 'match_status', 'link_status', 'object_name', 'object_locality', 'object_address',
            'lat', 'lon', 'value_status', 'capacity_value', 'capacity_unit', 'capacity_status']
    objects = objects[keep].rename(columns={'lat': 'object_lat', 'lon': 'object_lon'})
    objects.to_parquet(output / 'source_objects_2021.parquet', index=False)
    joined = objects[objects.source_record_id.isin(metadata.index)].merge(metadata, left_on='source_record_id', right_index=True, how='left', validate='many_to_one')
    group = ['source_record_id', 'scenario', 'function', 'service_order', 'observation_year']
    # Education source has an explicit node/way duplicate candidate grouping. Medical
    # objects have no validated cross-geometry deduplication: count is a count of assertions.
    supply = joined.groupby(group, dropna=False).agg(object_count_proxy=('canonical_object_id', 'nunique')).reset_index()
    supply['center_id'] = supply.source_record_id
    supply['supply_value'] = 1.0  # Presence experiment; not one bed/place or measured capacity.
    supply['supply_status'] = 'proxy'
    supply['supply_unit'] = 'binary_source_presence_not_capacity'
    supply = supply.merge(metadata, left_on='source_record_id', right_index=True, how='left', validate='many_to_one')
    supply['legacy_id'] = supply.source_record_id.map(pts.set_index('source_record_id').legacy_id)
    supply.to_parquet(output / 'supply_all_2021.parquet', index=False)
    supply[supply.region.isin(PILOT_REGIONS)].to_parquet(output / 'supply.parquet', index=False)
    count_proxy = supply.copy()
    count_proxy['supply_value'] = count_proxy.object_count_proxy.astype(float)
    count_proxy['supply_unit'] = 'distinct_OSM_assertions_education_named_duplicate_groups_not_measured_capacity'
    count_proxy.to_parquet(output / 'supply_count_proxy_all_2021.parquet', index=False)
    count_proxy[count_proxy.region.isin(PILOT_REGIONS)].to_parquet(output / 'supply_count_proxy.parquet', index=False)


    # Federal cities are separate territorial aggregates. They must not disappear
    # from external alternatives because their ordinary census rows lack admitted points.
    anchor_rows = []
    for r in federal.itertuples(index=False):
        anchor_rows.append({
            'center_id': 'ctx:' + r.territory_key, 'source_record_id': None, 'root': None,
            'legacy_id': 'ctx:' + r.territory_key, 'name': r.territory_name, 'region': r.region_norm,
            'lat': r.latitude, 'lon': r.longitude, 'population': float(r.territory_population),
            'population_2021': float(r.territory_population),
            'credited_population_2021': np.nan, 'population_role': 'external_context_nonadditive',
            'population_source_record_id': r.population_source_record_id,
            'population_scope': 'federal_city_territory_not_individual_settlement',
            'working_credit_present': False, 'external_context_anchor': True,
            'is_additive_settlement_record': False, 'census_year': 2021,
            'coordinate_source_record_id': r.coordinate_source_record_id,
            'coordinate_source_locator': r.coordinate_source_locator,
            'coordinate_source_quality': r.coordinate_source_quality,
            'coordinate_measurement_date_unknown': True,
        })
    anchors = pd.DataFrame(anchor_rows)
    anchors.to_parquet(output / 'external_context_anchors.parquet', index=False)
    city_ids = {norm(r['name']): r['center_id'] for r in anchor_rows}
    context = objects[objects.object_locality.map(norm).isin(city_ids)].copy()
    context['center_id'] = context.object_locality.map(norm).map(city_ids)
    context['source_record_id'] = None  # Never invent an ordinary census observation.
    ac = anchors.set_index('center_id')
    context['anchor_lat'] = context.center_id.map(ac.lat)
    context['anchor_lon'] = context.center_id.map(ac.lon)
    radians = np.radians(context[['object_lat', 'object_lon', 'anchor_lat', 'anchor_lon']].to_numpy())
    h = np.sin((radians[:,0]-radians[:,2])/2)**2 + np.cos(radians[:,0])*np.cos(radians[:,2])*np.sin((radians[:,1]-radians[:,3])/2)**2
    context['object_to_representative_anchor_km'] = 2*6371.0088*np.arcsin(np.sqrt(np.clip(h,0,1)))
    context['context_link_eligible'] = context.object_to_representative_anchor_km.le(100)
    context['context_link_rule'] = 'explicit_OSM_city_locality_literal_and_le100km_coordinate_sanity_not_verified_city_polygon'
    assert not set(context.source_record_id.dropna()).intersection(pts.source_record_id)
    ordinary_object_keys = set(map(tuple, joined[['source_id', 'source_object_id', 'scenario']].to_numpy()))
    context_object_keys = set(map(tuple, context[['source_id', 'source_object_id', 'scenario']].to_numpy()))
    assert not ordinary_object_keys.intersection(context_object_keys), 'Duplicate ordinary/context object'
    context.to_parquet(output / 'context_source_objects_2021.parquet', index=False)
    cs = context[context.context_link_eligible].groupby(['center_id', 'scenario', 'function', 'service_order', 'observation_year']).canonical_object_id.nunique().rename('object_count_proxy').reset_index()
    cs = cs.merge(anchors, on='center_id', how='left', validate='many_to_one')
    cs['supply_value'] = 1.0
    cs['supply_status'] = 'proxy'
    cs['supply_unit'] = 'binary_explicit_OSM_city_address_presence_not_capacity'
    cs['context_supply_geography'] = 'territorial_aggregate_at_representative_anchor_not_true_intraurban_destinations'
    cs.to_parquet(output / 'supply_context2021.parquet', index=False)
    cc = cs.copy(); cc['supply_value'] = cc.object_count_proxy.astype(float)
    cc['supply_unit'] = 'distinct_OSM_city_address_assertions_not_measured_capacity'
    cc.to_parquet(output / 'supply_context_count_proxy2021.parquet', index=False)

    # Re-read the independent official list by name uniqueness in accepted 2021 Udmurt records.
    # The document contains no site coordinates and is a selected planning list, not an operation register.
    fap = pd.read_parquet(input_root / INPUT_PATHS['udmurt2025'])
    fresh_workbook_check = None
    if udmurt_workbook is not None:
        expected_raw_sha = '34322c8ef538efa79617af0f80ecc330c99d7f60539216478ef4e6f64dcd070c'
        if sha256(udmurt_workbook) != expected_raw_sha:
            raise ValueError('Official Udmurt workbook differs from dated source; inspect as a new version')
        rows = []
        for sheet, frame in pd.read_excel(udmurt_workbook, sheet_name=None, header=None).items():
            for i, row in frame.iterrows():
                if pd.isna(pd.to_numeric(row.iloc[0], errors='coerce')) or not isinstance(row.iloc[2], str):
                    continue
                rows.append({'record_id': f'RMIAC18:2025:{sheet}:{i+1}',
                             'source_locality': str(row.iloc[3]) if pd.notna(row.iloc[3]) else None,
                             'physical_site_name': row.iloc[2], 'parent_organization': row.iloc[1]})
        fresh = pd.DataFrame(rows).set_index('record_id').sort_index()
        old = fap.set_index('record_id')[fresh.columns].sort_index()
        if not fresh.equals(old):
            raise ValueError('Official workbook rows differ from preserved extraction')
        fresh_workbook_check = {'raw_sha256': expected_raw_sha, 'rows_reread': len(fresh),
                                'rows_equal_preserved_extraction': True,
                                'url': 'https://rmiac18.ru/upload/iblock/951/ip0qw4d8o7jfyels8z0quirpq4g39zlv/5.-Prilozhenie-5-Internet-v-FAP.xlsx',
                                'scope': 'selected_FAP_requiring_internet_2026_not_complete_operating_registry'}
    ud = current[current.region_norm.eq('удмуртская')].copy()
    ud['_norm'] = ud.settlement_name.map(norm)
    named = ud.groupby('_norm').source_record_id.agg(list)
    fap['accepted2021_candidates'] = fap.source_locality.map(lambda x: named.get(norm(x), []))
    fap['source_record_id'] = fap.accepted2021_candidates.map(lambda a: a[0] if len(a) == 1 else None)
    fap['match_status'] = fap.accepted2021_candidates.map(lambda a: 'normalized_name_unique_in_source_region' if len(a) == 1 else 'homonym_needs_district' if len(a) > 1 else 'not_found')
    fap['accepted2021_candidates_json'] = fap.accepted2021_candidates.map(json.dumps)
    fap.drop(columns='accepted2021_candidates').to_parquet(output / 'udmurt_fap_2025_crosswalk.parquet', index=False)
    fs = fap[fap.source_record_id.isin(metadata.index)].groupby('source_record_id').record_id.nunique().rename('object_count_proxy').reset_index()
    fs['center_id'] = fs.source_record_id;fs['scenario'] = 'official_selected_planning_list_2025';fs['function'] = 'healthcare';fs['service_order'] = 'primary_fap';fs['observation_year'] = pd.Series(pd.NA, index=fs.index, dtype='Int64');fs['document_catalogue_year'] = 2025;fs['planning_target_year'] = 2026;fs['document_modified_metadata'] = '2025-12-23T04:29:35Z';fs['value_status'] = 'proxy';fs['supply_value'] = 1.0;fs['supply_status'] = 'proxy';fs['supply_unit'] = 'named_FAP_FP_planning_list_not_verified_operating_capacity'
    fs = fs.merge(metadata, left_on='source_record_id', right_index=True, how='left', validate='one_to_one')
    fs['legacy_id'] = fs.source_record_id.map(pts.set_index('source_record_id').legacy_id)
    dated_fields = ['document_catalogue_year', 'planning_target_year', 'document_modified_metadata', 'value_status']
    fs = fs[[c for c in fs.columns if c not in dated_fields] + dated_fields]
    fs.to_parquet(output / 'supply_official_udmurt_2025.parquet', index=False)

    # Normative attachment relationships are retained as independent observations;
    # they are not a source of hidden medical capacity or trips.
    rel = pd.read_parquet(input_root / INPUT_PATHS['lo2024'])
    rel['legacy_origin_id'] = rel.origin_id; rel['legacy_destination_id'] = rel.destination_id
    rel['origin_id'] = rel.legacy_origin_id.map(idmap); rel['destination_id'] = rel.legacy_destination_id.map(idmap)
    rel['origin_present_in_spatial2021'] = rel.origin_id.isin(metadata.index)
    rel['destination_present_in_spatial2021'] = rel.destination_id.isin(metadata.index)
    rel['observation_year'] = pd.NA
    rel['document_year'] = 2023
    rel['historical_filename_year_label'] = 2024
    rel['temporal_reference'] = 'document_issued_2023-11-29_application_year_not_independently_assumed'
    rel['function'] = 'healthcare'
    rel['evidence_kind'] = 'normative_primary_care_attachment_not_observed_trip'
    rel['locator'] = rel.sheet + ':row=' + rel.excel_row_1based.astype(str)
    rel['source_url'] = 'https://lofoms.spb.ru/files/reshenie_2023_15_pril3_1.xls?1'
    rel.to_parquet(output / 'medical_attachments_lo_2024.parquet', index=False)

    official_overlap = {}
    official_ids = set(fs.source_record_id)
    for scenario in ['strict_address', 'spatial_proxy']:
        observed_med = supply[supply.scenario.eq(scenario) & supply.function.eq('healthcare')]
        official_overlap[scenario] = {
            'planning_list_unique_settlements': len(official_ids),
            'any_healthcare_source_presence_overlap': len(official_ids.intersection(observed_med.source_record_id)),
            'FAP_name_source_presence_overlap': len(official_ids.intersection(observed_med[observed_med.service_order.eq('primary_fap')].source_record_id)),
            'interpretation': 'different_years_selected_planning_list_not_network_sensitivity_or_closures',
        }
    (output / 'udmurt_source_overlap.json').write_text(json.dumps(official_overlap, ensure_ascii=False, indent=2) + '\n')
    rows = []
    funcs = [('healthcare', 'all_orders'), ('education', 'all_orders')]
    for region, region_points in pilot.groupby('region'):
        for scenario in ['strict_address', 'spatial_proxy']:
            for function, order in funcs:
                observed = supply[supply.region.eq(region) & supply.scenario.eq(scenario) & supply.function.eq(function)]
                n = observed.source_record_id.nunique()
                rows.append({'region': region, 'function': function, 'scenario': scenario, 'year': 2021,
                             'settlements_with_accepted_point': len(region_points), 'source_presence_settlements': n,
                             'unknown_settlements': len(region_points) - n, 'confirmed_absence_settlements': 0,
                             'presence_share': n / len(region_points), 'capacity_known_settlements': 0})
    size_rows = []
    size_bins = [-1, 0, 99, 999, 9999, float('inf')]
    size_labels = ['zero', '1_99', '100_999', '1000_9999', '10000_plus']
    for region, rp in pilot.groupby('region'):
        rp = rp.copy()
        rp['population_band'] = pd.cut(rp.population, size_bins, labels=size_labels).astype(str)
        for scenario in ['strict_address', 'spatial_proxy']:
            for function in ['healthcare', 'education']:
                ids = set(supply[supply.region.eq(region) & supply.scenario.eq(scenario) & supply.function.eq(function)].source_record_id)
                for band, group in rp.groupby('population_band'):
                    n = int(group.source_record_id.isin(ids).sum())
                    size_rows.append({'region': region, 'function': function, 'scenario': scenario, 'population_band': band, 'settlements': len(group), 'source_presence_settlements': n, 'unknown_settlements': len(group)-n, 'confirmed_absent': 0, 'presence_share': n/len(group)})
    pd.DataFrame(size_rows).to_csv(output / 'coverage_by_population.csv', index=False)
    coverage = pd.DataFrame(rows)
    coverage.to_csv(output / 'coverage.csv', index=False)
    summary = {
        'population_foundation_changed': False,
        'spatial_reference_year': 2021,
        'excluded_education_explicitly_inactive_source_objects': excluded_inactive_education_objects,
        'primary_2021_additive_rows_before_federal_separation': len(raw_current),
        'federal_territory_source_records_excluded_from_ordinary': len(raw_current)-len(current),
        'primary_2021_additive_ordinary_rows': len(current),
        'primary_2021_with_accepted_point': len(pts),
        'excluded_no_accepted_point_2021': int((~current.accepted_point_present).sum()),
        'pilot_rows_by_region': pilot.groupby('region').size().to_dict(),
        'pilot_working_credit_by_region': pilot.groupby('region').working_credit_present.sum().astype(int).to_dict(),
        'pilot_uncredited_positive_records': pilot[(~pilot.working_credit_present) & pilot.population.gt(0)].groupby('region').size().to_dict(),
        'pilot_credited_population2021': pilot.groupby('region').credited_population_2021.sum().to_dict(),
        'uncredited_population_rule': 'Keep source values and spatial rows; use credited_population_YEAR for accepted population sums, NULL is not zero',
        'external_context_anchors': anchors[['center_id', 'name', 'population']].to_dict('records'),
        'external_context_supply_rows': len(cs),
        'external_context_source_objects_by_city_function': context[context.context_link_eligible & context.scenario.eq('strict_address')].groupby(['center_id','function']).size().rename('objects').reset_index().to_dict('records'),
        'external_context_excluded_sanity_rows': int((~context.context_link_eligible).sum()),
        'bridge_rows': len(bridge),
        'bridge_accepted_2021_unique_rows': len(goodbridge),
        'pilot_rows_without_legacy_bridge': int(pilot.legacy_id.isna().sum()),
        'official_udmurt_rows': len(fap),
        'official_udmurt_fresh_workbook_check': fresh_workbook_check,
        'official_udmurt_matching_status': fap.match_status.value_counts().to_dict(),
        'official_udmurt_spatial_settlements': int(len(fs)),
        'official_udmurt_scope': 'selected_FAP_FP_in_2025_catalogue_of_internet_connection_needs_in_2026_not_complete_network_not_verified_operation',
        'medical_attachment_rows': len(rel),
        'medical_attachment_origin_mapped': int(rel.origin_id.notna().sum()),
        'medical_attachment_destination_mapped': int(rel.destination_id.notna().sum()),
        'medical_attachment_both_spatial_not_partial': int((rel.origin_present_in_spatial2021 & rel.destination_present_in_spatial2021 & ~rel.origin_is_partial_address_scope).sum()),
        'medical_attachment_scope': 'document_issued_2023-11-29_normative_attachment_historical_filename_label2024_not_observed_trip_or_census_population',
        'coverage': rows,
        'inputs': provenance,
        'limitations': [
            'OSM_20210101_snapshot_is_not_census_day_and_missing_is_unknown',
            'source_address_links_and_spatial_proxies_are_separate_scenarios',
            'legacy_spatial_candidates_are_not_revalidated_settlement_boundaries',
            'binary_source_presence_is_not_capacity',
            'medical_objects_may_duplicate_same_physical_site',
            'contemporary_planning2025_and_document2023_attachments_not_backdated_to2021',
        ],
    }
    (output / 'preparation_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs', 'coverage']}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--population-root', type=Path, required=True)
    p.add_argument('--input-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--catalog', type=Path, default=Path('data/catalog.json'))
    p.add_argument('--udmurt-workbook', type=Path, help='Optional original XLSX for independent row-by-row readback')
    a = p.parse_args()
    prepare(a.population_root, a.input_root, a.output, a.catalog, a.udmurt_workbook)

if __name__ == '__main__': main()

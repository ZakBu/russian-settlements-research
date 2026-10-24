#!/usr/bin/env python3
"""National education sites and NP presence for bottom-up service systems.

Institution coordinates, settlement identity, source date and programme evidence
remain independent. A nearest census point supplies geographic context only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts/sgrt_mass'))
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.education import osm_lifecycle_reason, osm_temporal_status
from scripts.sgrt_mass.match import normalize_name, normalize_region
from scripts.sgrt_mass.site_geometry import sphere_xyz, chord_km

GROUPS = {'school': 'school_general', 'preschool': 'preschool',
          'college': 'vocational_education', 'university': 'higher_education'}
STRICT = 'explicit_locality_and_exact_legacy_census_bridge'
FEDERAL_CITY_IDS = {
    'москва': '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:64748',
    'санкт петербург': '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:126656',
    'севастополь': '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:121540',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path.with_suffix('.parquet'), index=False, compression='zstd')


def safe_tags(value):
    try:
        result = json.loads(value) if isinstance(value, str) else {}
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def lifecycle_reason(value):
    """Preserve legacy exclusions and additional explicit inactive feature tags."""
    tags = safe_tags(value)
    reasons = [osm_lifecycle_reason(json.dumps(tags))]
    for key in ['demolished', 'razed', 'removed', 'destroyed', 'closed']:
        if str(tags.get(key, '')).strip().lower() == 'yes':
            reasons.append(key + '=yes')
    for key in ['disused:amenity', 'abandoned:amenity', 'demolished:amenity',
                'razed:amenity', 'removed:amenity', 'destroyed:amenity']:
        if tags.get(key) in {'school', 'kindergarten', 'college', 'university'}:
            reasons.append(key + '=' + str(tags[key]))
    return '|'.join(reason for reason in reasons if reason)


def non_general_school_reason(group, name, value):
    if group == 'specialized_non_general_school':
        return 'source_inventory_specific_non_general_classification'
    if group != 'school':
        return ''
    tags = safe_tags(value)
    specialized = {'music','musical','art','arts','sport','sports','dance','dancing',
                   'driving','driving_school','language','languages','english'}
    for key in ['school','school:type','school:subject','education:type','education']:
        if str(tags.get(key,'')).strip().lower() in specialized:
            return 'explicit_non_general_tag:' + key + '=' + str(tags[key])
    text = '' if name is None or pd.isna(name) else str(name).lower().replace('ё','е')
    general = re.search(r'общеобразовательн|гимнази|\bлицей\b|\bсош\b|(?:начальн|основн|средн)\w*\s+школ',text)
    if not general and re.search(r'музыкальн\w*\s+школ|художественн\w*\s+школ|спортивн\w*\s+школ|\bдюсш\b|\bсдюсшор\b|\bсшор\b|автошкол|школ\w*\s+вождени|школ\w*\s+танц|хореографическ\w*\s+школ|языков\w*\s+школ|школ\w*\s+(?:иностранных\s+языков|английского|немецкого|французского|китайского)',text):
        return 'explicit_non_general_school_name_not_general_programme'
    return ''


def parse_literal_levels(value, minimum=0, maximum=8):
    """Only literal numeric lists/ranges; a school name is never a programme."""
    if value is None or pd.isna(value):
        return []
    literal = str(value).strip()
    if not re.fullmatch(r'\d{1,2}(?:\s*[-;,]\s*\d{1,2})*', literal):
        return []
    values = set()
    for item in re.split(r'[;,]', literal):
        pieces = [int(x.strip()) for x in item.split('-')]
        if len(pieces) == 1:
            values.add(pieces[0])
        elif pieces[0] <= pieces[1]:
            values.update(range(pieces[0], pieces[1] + 1))
        else:
            return []
    if any(v < minimum or v > maximum for v in values):
        return []
    return sorted(values)


def identity_bridge(legacy, reference):
    current = reference[reference.source_record_id.notna()]
    bridge = legacy[legacy.root.notna() & legacy.source_record_id_2021.notna()].merge(
        current[['root', 'source_record_id', 'name', 'region', 'population_role']].rename(columns={'name':'reference_name','region':'reference_region'}),
        left_on=['root', 'source_record_id_2021'], right_on=['root', 'source_record_id'],
        how='inner', validate='one_to_one', suffixes=('_legacy', '_census'))
    if not bridge.id.is_unique:
        raise ValueError('Legacy identity bridge repeats an object key')
    return bridge.set_index('id')


def geographic_context(sites, reference, city_context=None):
    """Assign regional context without promoting distance into NP identity."""
    result = sites.copy()
    reference = reference[reference.source_record_id.notna()].copy()
    ref = reference.set_index('source_record_id')
    regions = set(reference.region.dropna())
    explicit_region = result.source_address_state.map(normalize_region)
    result['region'] = explicit_region.where(explicit_region.isin(regions))
    result['region_basis'] = np.where(result.region.notna(), 'literal_source_address_region', 'unknown')
    owner_region = result.source_record_id.map(ref.region)
    use = result.region.isna() & owner_region.notna()
    result.loc[use, 'region'] = owner_region[use]
    result.loc[use, 'region_basis'] = 'explicit_settlement_identity_region'
    # A literal locality unique to one region can locate the region without
    # asserting a precise institution -> census-record identity.
    names = reference.assign(name_normalized=reference.name.map(normalize_name))
    names = names[names.name_normalized.ne('')]
    unique = names.groupby('name_normalized').region.nunique()
    name_region = names[names.name_normalized.isin(unique[unique.eq(1)].index)].drop_duplicates('name_normalized').set_index('name_normalized').region
    named = result.source_address_locality.map(normalize_name).map(name_region)
    use = result.region.isna() & named.notna()
    result.loc[use, 'region'] = named[use]
    result.loc[use, 'region_basis'] = 'source_locality_name_unique_region_not_np_identity'
    geographic_reference = reference.copy()
    geographic_reference['derived_city_coordinate_for_geographic_context'] = False
    if city_context is not None:
        context = city_context.set_index('source_record_id')
        for col in ['lat','lon']:
            fill = geographic_reference.source_record_id.map(context[col])
            use = geographic_reference[col].isna() & fill.notna()
            geographic_reference.loc[use,col] = fill[use]
            geographic_reference.loc[use,'derived_city_coordinate_for_geographic_context'] = True
    georef = geographic_reference[np.isfinite(geographic_reference.lat) & np.isfinite(geographic_reference.lon)].copy()
    georef = georef.sort_values('source_record_id').reset_index(drop=True)
    valid = result.coordinate_valid
    result['nearest_reference_source_record_id'] = None
    result['nearest_reference_region'] = None
    result['nearest_reference_distance_km'] = np.nan
    result['nearest_reference_uses_derived_city_coordinate'] = False
    if len(georef) and valid.any():
        tree = cKDTree(sphere_xyz(georef.lat, georef.lon))
        distance, index = tree.query(sphere_xyz(result.loc[valid, 'site_lat'], result.loc[valid, 'site_lon']))
        nearest = georef.iloc[index]
        result.loc[valid, 'nearest_reference_source_record_id'] = nearest.source_record_id.to_numpy()
        result.loc[valid, 'nearest_reference_region'] = nearest.region.to_numpy()
        result.loc[valid, 'nearest_reference_distance_km'] = chord_km(distance)
        result.loc[valid, 'nearest_reference_uses_derived_city_coordinate'] = nearest.derived_city_coordinate_for_geographic_context.to_numpy()
    result['nearest_reference_is_identity'] = False
    use = result.region.isna() & result.nearest_reference_region.notna()
    result.loc[use, 'region'] = result.loc[use, 'nearest_reference_region']
    result.loc[use, 'region_basis'] = 'nearest_reference_geographic_proxy_not_identity_or_boundary'
    result['region_is_proxy'] = result.region_basis.eq('nearest_reference_geographic_proxy_not_identity_or_boundary')
    return result


def build_sites(objects, reference, legacy, city_context=None):
    required = {'site_id', 'education_group', 'source_snapshot', 'lat', 'lon', 'tags_json'}
    if not required <= set(objects):
        raise ValueError('Missing source fields: ' + repr(sorted(required-set(objects))))
    frame = objects.copy().reset_index(drop=True)
    if frame.site_id.duplicated().any():
        raise ValueError('Repeated OSM object identity; resolve source conflict before routing')
    for col in ['baseline_uid', 'candidate_uid', 'source_address_locality', 'source_address_state',
                'possible_duplicate_of', 'source_start_date', 'source_end_date', 'source_capacity',
                'source_isced_level', 'source_grades', 'name', 'link_status']:
        if col not in frame:
            frame[col] = None
    frame['provider_id'] = frame.site_id
    frame['source_object_id'] = frame.site_id
    frame['source_record_id'] = None
    frame['legacy_id'] = frame.baseline_uid.fillna(frame.candidate_uid)
    bridge = identity_bridge(legacy, reference)
    linked_name = frame.legacy_id.map(bridge.reference_name)
    explicit = frame.link_status.eq('explicit_address_locality_unique_within5km')
    locality = frame.source_address_locality.map(normalize_name)
    agrees = locality.ne('') & locality.eq(linked_name.map(normalize_name))
    owner = frame.legacy_id.map(bridge.source_record_id)
    strict = explicit & agrees & owner.notna()
    owner_region = frame.legacy_id.map(bridge.reference_region)
    address_region = frame.source_address_state.map(normalize_region)
    frame['literal_region_conflicts_with_legacy_identity'] = strict & address_region.isin(set(reference.region.dropna())) & address_region.ne(owner_region)
    strict &= ~frame.literal_region_conflicts_with_legacy_identity
    frame.loc[strict, 'source_record_id'] = owner[strict]
    frame['current_identity_status'] = np.where(strict, STRICT, 'unresolved_settlement_identity')
    frame.loc[frame.literal_region_conflicts_with_legacy_identity,'current_identity_status'] = 'held_literal_region_identity_conflict'
    # An explicit federal-city address is not limited to five kilometres from
    # its representative point. It supplies a named city identity; its census
    # population role remains separate and is not promoted to ordinary NP.
    for city, sid in FEDERAL_CITY_IDS.items():
        if sid not in set(reference.source_record_id.dropna()):
            continue
        city_tag = frame.tags_json.map(lambda x: safe_tags(x).get('addr:city'))
        city_address = frame.source_address_locality.map(normalize_name).eq(city) & city_tag.map(normalize_name).eq(city)
        nonconflicting = address_region.eq('') | address_region.eq(city)
        use = frame.source_record_id.isna() & city_address & nonconflicting
        frame.loc[use,'source_record_id'] = sid
        frame.loc[use,'current_identity_status'] = 'literal_federal_city_address_nonconflicting_region'
    frame['identity_status'] = frame.current_identity_status
    frame['spatial_proxy_source_record_id'] = owner.where(~strict)
    ref = reference[reference.source_record_id.notna()].set_index('source_record_id')
    frame['census_population_role'] = frame.source_record_id.map(ref.population_role)
    frame['is_federal_city_context'] = frame.source_record_id.isin(FEDERAL_CITY_IDS.values())
    frame['population_role'] = frame.census_population_role.mask(frame.is_federal_city_context,'external_context_nonadditive')
    frame['education_group_original'] = frame.education_group
    frame['non_general_school_reason'] = [non_general_school_reason(a,b,c) for a,b,c in zip(frame.education_group,frame['name'],frame.tags_json)]
    frame.loc[frame.non_general_school_reason.ne(''),'education_group'] = 'specialized_non_general_school'
    frame['service_code'] = frame.education_group.map(GROUPS)
    frame['source_service_code'] = frame.service_code
    frame['site_lat'] = pd.to_numeric(frame.lat, errors='coerce')
    frame['site_lon'] = pd.to_numeric(frame.lon, errors='coerce')
    frame['coordinate_valid'] = np.isfinite(frame.site_lat) & np.isfinite(frame.site_lon) & frame.site_lat.between(-90,90) & frame.site_lon.between(-180,180)
    dates = pd.to_datetime(frame.source_snapshot, utc=True, errors='coerce')
    if dates.isna().any():
        raise ValueError('Source snapshot has no explicit parseable date')
    frame['observation_year'] = dates.dt.year.astype(int)
    frame['source_year'] = frame.observation_year
    frame['source_id'] = dates.dt.strftime('OSM_GEOFABRIK_EDUCATION_%Y%m%d')
    frame['temporal_status'] = [osm_temporal_status(a,b,c.strftime('%Y-%m-%d')) for a,b,c in zip(frame.source_start_date,frame.source_end_date,dates)]
    frame['lifecycle_exclusion_reason'] = frame.tags_json.map(lifecycle_reason)
    frame['eligible'] = frame.service_code.notna() & frame.coordinate_valid & frame.possible_duplicate_of.isna() & frame.lifecycle_exclusion_reason.eq('') & ~frame.temporal_status.isin(['ended_before_snapshot','started_after_snapshot'])
    frame['supply_status'] = 'observed'
    frame.loc[frame.service_code.isna(), 'supply_status'] = 'excluded_specialized_non_general_education'
    frame.loc[~frame.coordinate_valid, 'supply_status'] = 'excluded_invalid_coordinate'
    frame.loc[frame.possible_duplicate_of.notna(), 'supply_status'] = 'excluded_source_duplicate'
    frame.loc[frame.lifecycle_exclusion_reason.ne(''), 'supply_status'] = 'excluded_lifecycle'
    frame.loc[frame.temporal_status.isin(['ended_before_snapshot','started_after_snapshot']), 'supply_status'] = 'excluded_temporal'
    frame['eligible_site_supply'] = frame.eligible
    frame['site_evidence_kind'] = 'mapped_education_feature_at_explicit_OSM_snapshot'
    frame['evidence_quality'] = 'mapped_type_not_verified_current_operation_capacity_or_admission'
    frame['location_precision'] = 'source_node_or_polygon_representative_not_confirmed_entrance'
    frame['geometry_direct'] = True
    frame['capacity_raw'] = frame.source_capacity
    frame['capacity_total'] = np.nan
    frame['capacity_used_as_weight'] = False
    frame['actual_operational_status_checked'] = False
    programs=[]
    for isced, grades in zip(frame.source_isced_level,frame.source_grades):
        programs.append(json.dumps({'isced_literal':None if isced is None or pd.isna(isced) else str(isced),
            'isced_levels':parse_literal_levels(isced),'grades_literal':None if grades is None or pd.isna(grades) else str(grades),
            'grades_list':parse_literal_levels(grades,1,12),'inferred_from_name':False,
            'complete_stage_offering_established':False},ensure_ascii=False))
    frame['school_program_evidence_json'] = programs
    frame['grades_known'] = frame.service_code.eq('school_general') & pd.Series([
        bool(set(parse_literal_levels(a))&{1,2,3} or parse_literal_levels(b,1,12)) for a,b in zip(frame.source_isced_level,frame.source_grades)],index=frame.index)
    frame['grade_evidence_basis'] = np.where(frame.grades_known,'literal_OSM_programme_tag_partial_not_verified_full_stage_or_admission','unknown_school_programme_not_inferred_from_name')
    frame['grade_inferred_from_name_or_population'] = False
    frame['daily_service_candidate'] = frame.service_code.isin(['school_general','preschool'])
    frame['spatial_level_assigned'] = False
    frame['established_flow'] = False
    return geographic_context(frame, reference,city_context)


def school_orders(sites):
    rows = []
    for item in sites[sites.service_code.eq('school_general')].itertuples():
        levels = parse_literal_levels(item.source_isced_level)
        grades = parse_literal_levels(item.source_grades,1,12)
        for level, code in [(1,'school_primary'),(2,'school_lower_secondary'),(3,'school_upper_secondary')]:
            group = {1:set(range(1,5)),2:set(range(5,10)),3:set(range(10,12))}[level]
            if level not in levels and not group.intersection(grades):
                continue
            rows.append({'provider_id':item.provider_id,'source_record_id':item.source_record_id,
                         'service_code':code,'parent_service_code':'school_general',
                         'source_isced_level_literal':item.source_isced_level,
                         'source_grades_literal':item.source_grades,
                         'order_evidence':'literal_OSM_ISCED_tag' if level in levels else 'literal_OSM_grade_list_partial_stage_not_complete_programme',
                         'eligible':item.eligible,'supply_status':item.supply_status,
                         'complete_stage_offering_established':False,
                         'source_id':item.source_id,'observation_year':item.observation_year,
                         'grade_inferred_from_name_or_population':False,
                         'not_added_as_extra_building_or_weight':True})
    return pd.DataFrame(rows)


def np_offers(sites, official, reference):
    ref = reference[reference.source_record_id.notna()].set_index('source_record_id')
    strict = sites[sites.eligible & sites.source_record_id.notna()]
    rows = []
    for (sid,service,year), group in strict.groupby(['source_record_id','service_code','observation_year']):
        rows.append(dict(provider_id=f'osm_np:{year}:{service}:{sid}',source_record_id=sid,
            service_code=service,source_service_code=service,source_id=group.source_id.iloc[0],
            observation_year=int(year),source_year=int(year),supply_status='observed',eligible=True,
            evidence_quality='literal_address_and_exact_census_bridge_mapped_presence',
            location_precision='settlement_presence_with_separate_real_institution_sites',
            source_pool='osm_strict_np_presence',provider_site_ids_json=json.dumps(sorted(group.provider_id)),
            source_records=len(group),capacity_total=np.nan,capacity_unit=None,
            default_external_seed_eligible=False,default_external_seed_reason='use_real_institution_points_not_an_extra_np_centroid',
            established_flow=False))
    observed = official[official.supply_status.eq('observed') & official.source_record_id.notna()].copy()
    present = set(strict.loc[strict.service_code.eq('preschool'),'source_record_id'])
    for item in observed.itertuples():
        rows.append(dict(provider_id=item.provider_id,source_record_id=item.source_record_id,
            service_code='preschool',source_service_code=item.service_code,source_id=item.source_id,
            observation_year=int(item.observation_year),source_year=int(item.observation_year),
            supply_status='observed',eligible=True,
            evidence_quality='positive_primary_Rosstat_NP_total_with_header_and_year_verified',
            location_precision='settlement_point_not_institution',source_pool='official_preschool_np2025',
            provider_site_ids_json='[]',source_records=item.known_positive_source_rows,
            capacity_total=item.capacity_total,capacity_unit=item.capacity_unit,
            default_external_seed_eligible=item.source_record_id not in present,
            default_external_seed_reason='fallback_np_location_only_where_no_strict_OSM_preschool_site' if item.source_record_id not in present else 'real_strict_OSM_point_available_do_not_duplicate_centroid',
            established_flow=False))
    result = pd.DataFrame(rows)
    for col in ['source_record_id','service_code','source_pool','eligible','supply_status','default_external_seed_eligible']:
        if col not in result:
            result[col]=pd.Series(dtype='object')
    result['site_lat'] = result.source_record_id.map(ref.lat)
    result['site_lon'] = result.source_record_id.map(ref.lon)
    result['region'] = result.source_record_id.map(ref.region)
    result['population_role'] = result.source_record_id.map(ref.population_role)
    result['census_population_role'] = result.population_role
    result.loc[result.source_record_id.isin(FEDERAL_CITY_IDS.values()),'population_role'] = 'external_context_nonadditive'
    result['ordinary_spatial_2021'] = result.source_record_id.map(ref.ordinary_spatial_2021).fillna(False).astype(bool)
    result['institution_inventory_is_complete'] = False
    result['capacity_is_vacant_places'] = False
    result['capacity_used_as_weight'] = False
    result['np_offer_rows_are_not_institution_counts'] = True
    return result


def regional_coverage(sites, offers, reference):
    regions = sorted(reference.region.dropna().unique())
    ordinary = reference[reference.ordinary_spatial_2021]
    rows = []
    for region in regions:
        denominator = int(ordinary.region.eq(region).sum())
        subset = sites[sites.region.eq(region)]
        for service in GROUPS.values():
            d = subset[subset.service_code.eq(service)]
            eligible = d[d.eligible]
            own = offers[offers.region.eq(region)&offers.service_code.eq(service)&offers.ordinary_spatial_2021]
            rows.append(dict(region=region,service_code=service,ordinary_spatial_np_denominator=denominator,
                source_objects=len(d),eligible_source_sites=len(eligible),
                sites_with_proxy_region_only=int(eligible.region_is_proxy.sum()),
                sites_with_direct_address_or_identity_region=int((~eligible.region_is_proxy).sum()),
                sites_with_strict_np_identity=int(eligible.source_record_id.notna().sum()),
                strict_ordinary_np_with_known_offer=own.source_record_id.nunique(),
                np_known_offer_fraction=own.source_record_id.nunique()/denominator if denominator else np.nan,
                zero_denominator_reason='nonadditive_federal_context_not_ordinary_settlement_frame' if denominator==0 else None,
                fraction_is_inventory_known_presence_not_completeness_or_accuracy=True,
                no_record_does_not_mean_no_service=True))
    return pd.DataFrame(rows)


def run(current, historical, official, reference_path, legacy_path, output,city_context_path=None):
    output = Path(output);output.mkdir(parents=True,exist_ok=True)
    reference = pd.read_parquet(reference_path);legacy = pd.read_parquet(legacy_path)
    contexts=pd.read_parquet(city_context_path) if city_context_path else None
    sites = build_sites(pd.read_parquet(current),reference,legacy,contexts)
    old = build_sites(pd.read_parquet(historical),reference,legacy,contexts)
    offers = np_offers(sites,pd.read_parquet(official),reference)
    orders = school_orders(sites)
    coverage = regional_coverage(sites,offers,reference)
    save(sites,output/'source_inventory_current')
    save(sites[sites.service_code.notna()],output/'physical_sites')
    save(old[old.service_code.notna()],output/'physical_sites_2021')
    save(offers,output/'np_supply')
    save(orders,output/'tagged_school_orders')
    if not orders.empty:
        order_sites=orders.merge(sites[['provider_id','site_lat','site_lon','source_snapshot','region',
            'location_precision','evidence_quality','population_role','is_federal_city_context']],
            on='provider_id',how='left',validate='many_to_one')
        save(order_sites,output/'physical_school_orders')
    save(coverage,output/'regional_coverage')
    coverage.to_csv(output/'regional_coverage.csv',index=False)
    eligible=sites[sites.eligible]
    old_eligible=old[old.eligible]
    delta=old[['source_object_id','service_code','eligible']].merge(
        sites[['source_object_id','service_code','eligible']],on='source_object_id',how='outer',suffixes=('_2021','_2026'),indicator=True)
    delta['same_ID_is_not_proof_of_unchanged_operation_or_geometry']=True
    save(delta,output/'snapshot_object_comparison')
    summary=dict(scope='National dated education supply, not complete operating inventory or observed travel',
        current_source_snapshots=sorted(sites.source_snapshot.unique()),
        current_objects=len(sites),current_eligible_sites=len(eligible),
        current_status_counts=sites.supply_status.value_counts().to_dict(),
        current_service_counts=eligible.service_code.value_counts().to_dict(),
        eligible_sites_with_strict_np_identity=int(eligible.source_record_id.notna().sum()),
        eligible_sites_without_strict_np_identity=int(eligible.source_record_id.isna().sum()),
        eligible_sites_with_proxy_geographic_region=int(eligible.region_is_proxy.sum()),
        regions_in_reference=int(reference.region.nunique()),
        regions_in_ordinary_spatial_frame=int(reference.loc[reference.ordinary_spatial_2021,'region'].nunique()),
        regions_with_geographically_assigned_eligible_OSM_sites=int(eligible.region.nunique()),
        regions_with_only_proxy_geography=sorted(set(eligible.region)-set(eligible.loc[~eligible.region_is_proxy,'region'])),
        generic_school_sites_without_literal_order_evidence=int(eligible.service_code.eq('school_general').sum()-orders[orders.eligible].provider_id.nunique()),
        tagged_order_site_count=int(orders[orders.eligible].provider_id.nunique()),
        tagged_order_rows=int(orders.eligible.sum()),
        historical_2021_eligible_sites=len(old_eligible),
        historical_2021_status_counts=old.supply_status.value_counts().to_dict(),
        np_offer_rows=len(offers),np_offer_counts=offers.groupby(['source_pool','service_code']).size().rename('rows').reset_index().to_dict('records'),
        official_preschool_fallback_np_seeds=int((offers.source_pool.eq('official_preschool_np2025')&offers.default_external_seed_eligible).sum()),
        capacity_or_site_count_used_as_attraction_weight=False,
        most_recent_OSM_snapshot_not_independent_verification_of_actual_operation=True,
        regional_geographic_proxy_not_settlement_ownership=True,
        data_scope_matches_85_subject_reference_not_unrepresented_later_territories=True,
        no_population_threshold_for_centre_admission=True,
        no_spatial_hierarchy_levels_assigned_from_school_or_city_population=True,
        source_input_sha256={str(p):digest(p) for p in [current,historical,official,reference_path,legacy_path]},
        code_sha256=digest(Path(__file__)))
    if city_context_path:
        summary['source_input_sha256'][str(city_context_path)]=digest(city_context_path)
        summary['city_context_coordinates_used_only_for_regional_geographic_fallback']=True
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--current',type=Path,required=True)
    p.add_argument('--historical',type=Path,required=True)
    p.add_argument('--official',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--legacy',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--city-context',type=Path,help='Derived coordinates fill only missing regional-context points; never assert institution ownership')
    a=p.parse_args();run(a.current,a.historical,a.official,a.reference,a.legacy,a.output,a.city_context)

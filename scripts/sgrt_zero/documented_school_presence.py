"""Append dated, documented NP-only school presence from frozen source cards.

This module reads no live pages and invents no school coordinates. A proxy
presence offer can serve the same NP locally; it cannot seed an external route.
Reference accounting credit is deliberately independent of physical identity.
"""
from __future__ import annotations
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.sgrt_mass.match import normalize_name, normalize_region, normalize_district, norm
from scripts.sgrt_zero.lower_profile_quality import part_inventory

REPO = Path(__file__).resolve().parents[2]
SOURCE_ID = 'DOC_LOCAL_SCHOOLS_20261026'


def _snapshot_path(value, cards_path):
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError('Documented snapshot paths must be relative')
    base = REPO if relative.parts and relative.parts[0] == 'references' else cards_path.parent
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError('Snapshot path leaves its allowed source root')
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _verify_evidence(card, cards_path):
    evidence = card.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('A presence card needs supporting frozen evidence')
    for item in evidence:
        if item.get('http_status') != 200:
            raise ValueError('An admitted source snapshot must have HTTP200')
        if not str(item.get('content_type', '')).lower().startswith('text/html'):
            raise ValueError('School presence requires the reviewed HTML snapshot')
        path = _snapshot_path(item['path'], cards_path)
        payload = path.read_bytes()
        if (hashlib.sha256(payload).hexdigest() != item.get('sha256')
                or len(payload) != item.get('bytes')):
            raise ValueError('School source snapshot SHA/size mismatch: ' + str(path))
        datetime.fromisoformat(item['retrieved_utc'].replace('Z', '+00:00'))


def add_documented_school_presence(offers, reference, cards_path):
    """Return existing offers plus explicit dated cards, never observed flows.

    All supporting evidence of each eligible card is checked. Failed searches
    or unrelated counterexample snapshots elsewhere in the JSON are not read as
    evidence for new offers. Existing implicit source eligibility is preserved.
    """
    cards_path = Path(cards_path)
    payload = cards_path.read_bytes()
    document = json.loads(payload)
    cards = document.get('school_cards', [])
    ids = [c.get('card_id') for c in cards]
    if any(not isinstance(c, str) or not c.strip() for c in ids) or len(ids) != len(set(ids)):
        raise ValueError('Source card IDs must be nonempty and unique')
    if len(offers) and 'provider_id' not in offers:
        raise ValueError('Existing offers need provider IDs')
    if 'provider_id' in offers and offers.provider_id.duplicated().any():
        raise ValueError('Existing provider IDs must be unique')
    existing = set(offers.get('provider_id', pd.Series(dtype=object)).dropna())
    if existing.intersection(ids):
        raise ValueError('Documented card provider already exists')
    ref, _ = part_inventory(reference)
    ref = ref[ref.source_record_id.notna()].copy()
    if ref.source_record_id.duplicated().any():
        raise ValueError('Reference source IDs must be unique')
    ref = ref.set_index('source_record_id')
    added = []
    for card in cards:
        if card.get('eligible_as_dated_documented_presence') is not True:
            continue
        if card.get('service_code') != 'school_general':
            raise ValueError('Documented presence card has a different service')
        if card.get('external_seed') is not False:
            raise ValueError('A documented NP-only school cannot be an external seed')
        if (card.get('site_lat') is not None or card.get('site_lon') is not None
                or card.get('coordinates_inferred') is not False):
            raise ValueError('School building coordinates must not be invented')
        if card.get('historical_supply_needs_current_confirmation') is not True:
            raise ValueError('Dated presence still needs current confirmation')
        sid = card['source_record_id']
        if sid not in ref.index:
            raise ValueError('Documented school refers to an unknown census record')
        row = ref.loc[sid]
        comparisons = [(normalize_name, card['settlement_name'], row['name']),
                       (norm, card['settlement_type'], row['settlement_type_2021']),
                       (normalize_region, card['region'], row['region']),
                       (normalize_district, card['district'], row['district'])]
        if any(not normalizer(value) or normalizer(value) != normalizer(actual)
               for normalizer, value, actual in comparisons):
            raise ValueError('Documented school literal NP/type/region/district conflicts with census ID')
        if (not pd.notna(row.get('population_2021')) or row.population_2021 <= 0
                or row.get('analysis_origin') != True
                or row.part_status != 'unmarked_whole_place_record'):
            raise ValueError('Documented school NP must be positive, whole and active')
        # Source year and observation year are curated separately. Do not infer
        # either one from retrieval or from unrelated dated news on the page.
        if 'source_year' not in card or 'observation_year' not in card:
            raise ValueError('Card must state source and observation year, including explicit null')
        source_year = card['source_year']
        observation_year = card['observation_year']
        for value in [source_year, observation_year]:
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                      or not 1800 <= value <= 2100):
                raise ValueError('Invalid explicit source/observation year')
        snapshot = card['source_snapshot']
        date.fromisoformat(snapshot[:10])
        _verify_evidence(card, cards_path)
        added.append(dict(provider_id=card['card_id'], source_record_id=sid,
            service_code='school_general', source_service_code='school_general',
            source_id=SOURCE_ID, source_pool='documented_local_school_address',
            source_year=source_year, observation_year=observation_year, source_snapshot=snapshot,
            supply_status='proxy', eligible=True, route_eligible=True,
            default_external_seed_eligible=False,
            default_external_seed_reason='dated_np_presence_only_no_geocoded_external_school',
            provider_name=card['institution_name'], source_object_id=card['card_id'],
            site_lat=None, site_lon=None, coordinates_inferred=False,
            location_precision='documented_named_NP_presence_no_school_building_coordinates',
            identity_evidence_tier='documented_official_address_dated_school_presence',
            np_identity_basis='literal_region_district_settlement_type_name_and_street_address',
            evidence_quality='dated_documented_address_proxy_not_current_operation_or_flow',
            source_records=1, capacity_total=None, capacity_unit=None,
            capacity_known=False, capacity_verified=False, capacity_used_as_weight=False, grades_known=False,
            current_operation_verified=False, actual_operational_status_verified=False,
            actual_operational_status_checked=False, school_programme_full_stages_verified=False,
            physical_coordinates_observed=False, observed_flow=False, established_flow=False,
            assignment_established=False, admission_area_verified=False,
            historical_supply_needs_current_confirmation=True,
            historical_source_only=card.get('historical_source_only') is True,
            historical_supply_proxy=card.get('historical_source_only') is True,
            source_temporal_status=card.get('temporal_status'),
            source_page_latest_visible_dated_content=card.get('official_page_content_latest_visible_date'),
            documented_card_json=json.dumps(card, ensure_ascii=False, sort_keys=True),
            documented_cards_sha256=hashlib.sha256(payload).hexdigest(),
            population_role=row.get('population_role'), census_population_role=row.get('population_role'),
            ordinary_spatial_2021=row.get('ordinary_spatial_2021'), region=row['region']))
    if not added:
        return offers.copy()
    original = offers.copy()
    # normalise_input treats a present nullable eligibility column strictly.
    # Adding that column must not turn formerly implicit True rows into False.
    for col in ['eligible', 'route_eligible']:
        if col not in original: original[col] = True
    new = pd.DataFrame(added)
    for col in ['source_year', 'observation_year']:
        new[col] = pd.array(new[col], dtype='Int64')
        if col in original: original[col] = pd.array(original[col], dtype='Int64')
    return pd.concat([original, new], ignore_index=True, sort=False)

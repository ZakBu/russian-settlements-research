"""Repair canonical provider ownership without changing raw source or eligibility.

Named rural school evidence and dated cartographic containment remain distinct
from legacy explicit identities. No nearest-NP or city-population imputation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.sgrt_zero.cartographic_identity_fast import assign_cartographic_identity
from scripts.sgrt_zero.explicit_locality_identity import reconcile_explicit_localities
from scripts.sgrt_zero.education import np_offers as education_offers, school_orders, regional_coverage
from scripts.sgrt_zero.commerce import np_offers as commerce_offers
from scripts.sgrt_zero.lower_profile_quality import sha256
from scripts.sgrt_zero.cartographic_identity import typed_address_locality_claims
from scripts.sgrt_zero.medical_need_review import review_medical_need_scope, review_np_presence_after_site_holds
from scripts.sgrt_zero.documented_school_presence import add_documented_school_presence
from scripts.sgrt_mass.match import normalize_name


def hold_existing_owner_conflicts(frame):
    """Keep the old source claim, but do not use an unresolved owner as supply.

    A stronger historical address may ultimately beat a polygon. Neither claim
    wins automatically; physical cards and their old owners remain inspectable.
    NP aggregates must also respect route_eligible, otherwise the held building
    would be reintroduced as a false zero-cost local offer.
    """
    work = frame.copy()
    old = work.get('source_record_id_before_identity_repair', work.source_record_id)
    held = (old.notna() & work.cartographic_identity_status.eq('held_existing_source_owner_conflict'))
    candidate=work.get('cartographic_candidate_source_record_id',pd.Series(None,index=work.index))
    unresolved_neighbours=work.get('cartographic_contains_other_census_places',pd.Series(False,index=work.index)).fillna(False)
    # A literal conflict may be reported before the old-owner check. Compare
    # identities directly as well; status ordering must not hide the conflict.
    held |= (old.notna() & candidate.notna() & old.ne(candidate) & ~unresolved_neighbours
             & work.cartographic_identity_status.ne('held_overlapping_different_census_localities'))
    work['existing_owner_conflict_requires_review'] = held
    work['source_identity_conflict_reason'] = ''
    work.loc[held, 'route_eligible'] = False
    work.loc[held, 'source_identity_conflict_reason'] = 'legacy_owner_and_dated_named_containment_disagree_no_automatic_winner'
    work.loc[held, 'identity_evidence_tier'] = 'held_existing_owner_cartographic_conflict'
    work.loc[held, 'np_identity_basis'] = 'held_legacy_owner_conflicts_with_dated_cartographic_locality'
    return work


def repair(frame, polygons, reference, *, education=False, fallback_polygons=None):
    original = frame.copy()
    work = frame.copy()
    if 'tags_json' not in work and 'source_tags_json' in work:
        work['tags_json'] = work.source_tags_json
    if 'source_address_full' not in work and 'source_addr_full' in work:
        work['source_address_full'] = work.source_addr_full
    if 'source_address_state' not in work and 'source_region_literal' in work:
        work['source_address_state'] = work.source_region_literal
    work['source_record_id_before_identity_repair'] = work.source_record_id
    work = assign_cartographic_identity(work, polygons)
    work['primary_geometry_candidate_present'] = work.cartographic_geometry_candidate_present
    if fallback_polygons is not None:
        fallback_mask = ~work.primary_geometry_candidate_present
        secondary = assign_cartographic_identity(work.loc[fallback_mask], fallback_polygons)
        for field in secondary:
            if field.startswith('cartographic_') or field == 'verified_boundary_source_record_id':
                work.loc[fallback_mask, field] = secondary[field]
    unknown = work.source_record_id.isna()
    work['identity_evidence_tier'] = np.where(unknown, 'unknown', 'legacy_explicit_or_registry')
    work['identity_repair_applied'] = False
    if 'np_identity_basis' not in work:
        work['np_identity_basis'] = work.get('current_identity_status', 'legacy_identity_basis_in_source')
    # School names are instructional-site evidence only after branch and named
    # honorary-person controls. Shop brands and licence-holder names are not.
    literal_ids = pd.Series(None, index=work.index, dtype=object)
    literal_status = pd.Series('not_used_for_this_domain', index=work.index)
    if education:
        literal = reconcile_explicit_localities(work.loc[unknown], reference)
        for column in literal:
            if column.startswith('explicit_locality_'):
                work[column] = literal[column].reindex(work.index)
        literal_ids.loc[literal.index] = literal.explicit_locality_source_record_id
        literal_status.loc[literal.index] = literal.explicit_locality_identity_status
    strong = unknown & literal_ids.notna() & literal_status.eq('matched_typed_rural_name')
    boundary_id = work.cartographic_accepted_source_record_id
    cartographic = unknown & boundary_id.notna() & work.cartographic_identity_accepted
    # A postal city inside an overgeneralized polygon does not resolve its
    # multiple independent settlements, even if its literal equals the label.
    cartographic &= ~work.cartographic_contains_other_census_places
    if education:
        cartographic &= ~literal_status.str.startswith('held_', na=False)
    work.loc[strong, 'source_record_id'] = literal_ids[strong]
    work.loc[strong, 'identity_evidence_tier'] = 'literal_typed_rural_school_name'
    work.loc[strong, 'np_identity_basis'] = 'literal_typed_rural_school_name_not_legacy_bridge'
    use = cartographic & ~strong
    work.loc[use, 'source_record_id'] = boundary_id[use]
    work.loc[use, 'identity_evidence_tier'] = 'dated_cartographic_locality_containment'
    work.loc[use, 'np_identity_basis'] = 'dated_named_locality_containment_not_legal_address_or_flow'
    changed = strong | use
    work.loc[changed, 'identity_repair_applied'] = True
    work['route_eligible'] = work.get('route_eligible', pd.Series(True, index=work.index)).fillna(False).eq(True)
    work = hold_existing_owner_conflicts(work)
    work['source_location_conflict_reason'] = ''
    ref_names = reference.dropna(subset=['source_record_id']).set_index('source_record_id').name.map(normalize_name)
    conflict_candidates = work.source_record_id_before_identity_repair.isna() & work.cartographic_identity_status.eq('held_literal_locality_conflict')
    fields = [c for c in ['tags_json', 'source_addr_full', 'source_address_full', 'activity_address',
                         'cartographic_candidate_source_record_id'] if c in work]
    for idx, values in zip(work.index[conflict_candidates], work.loc[conflict_candidates, fields].itertuples(index=False, name=None)):
        data = dict(zip(fields, values))
        target_name = ref_names.get(data.get('cartographic_candidate_source_record_id'))
        claims = {c['name'] for c in typed_address_locality_claims(data) if c['rural_or_town']}
        if claims and target_name and claims - {target_name}:
            work.at[idx, 'route_eligible'] = False
            work.at[idx, 'source_location_conflict_reason'] = 'typed_full_activity_locality_conflicts_with_mapped_coordinates'
    for field in ['current_identity_status', 'identity_status']:
        if field in work:
            work.loc[changed, field] = work.loc[changed, 'np_identity_basis']
    reference = reference.dropna(subset=['source_record_id']).set_index('source_record_id')
    for field in ['population_role', 'census_population_role', 'source_population_role']:
        if field in work:
            work.loc[changed, field] = work.loc[changed, 'source_record_id'].map(reference.population_role)
    if 'is_federal_city_context' in work:
        work.loc[changed, 'is_federal_city_context'] = work.loc[changed, 'source_record_id'].map(reference.population_role).eq('external_context_nonadditive')
    work['institution_operation_and_capacity_not_verified_by_identity_repair'] = True
    work['cartographic_boundary_is_legal_or_observed_assignment'] = False
    raw_fields = [c for c in ['name', 'source_name', 'tags_json', 'source_tags_json', 'site_lat',
                             'site_lon', 'lat', 'lon', 'service_code', 'eligible', 'supply_status'] if c in original]
    for field in raw_fields:
        pd.testing.assert_series_equal(original[field], work[field], check_names=False)
    if not work.loc[~unknown, 'source_record_id'].equals(original.loc[~unknown, 'source_record_id']):
        raise ValueError('Existing source owners must not be replaced by polygons')
    summary = {'source_rows': len(work), 'owners_before': int(original.source_record_id.notna().sum()),
               'owners_after': int(work.source_record_id.notna().sum()),
               'new_literal_school_owners': int(strong.sum()), 'new_cartographic_owners': int(use.sum()),
               'cartographic_status_counts': work.cartographic_identity_status.value_counts().to_dict(),
               'raw_fields_and_eligibility_unchanged': raw_fields,
               'existing_owners_preserved': True}
    if 'eligible' in work:
        admitted = work.eligible.fillna(False)
    else:
        admitted = work.supply_status.isin(['observed', 'proxy'])
    summary['eligible_ownership_before'] = int((admitted & original.source_record_id.notna()).sum())
    summary['eligible_ownership_after'] = int((admitted & work.route_eligible & work.source_record_id.notna()).sum())
    summary['existing_owner_conflict_held_rows'] = int(work.existing_owner_conflict_requires_review.sum())
    summary['new_location_conflicts_held_from_external_routing'] = int((admitted & ~work.route_eligible).sum())
    summary['new_eligible_ownership_by_boundary_source'] = work.loc[admitted & use, 'cartographic_source_dataset'].value_counts().to_dict()
    return work, summary


def save(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression='zstd')


def run(args):
    if (args.output / 'summary.json').exists():
        raise FileExistsError('A finished identity repair is immutable')
    reference = pd.read_parquet(args.bundle / 'context/analysis_reference.parquet')
    code_paths = [Path(__file__), *[Path(__file__).with_name(name) for name in
                  ['education.py', 'commerce.py', 'cartographic_identity.py', 'cartographic_identity_fast.py',
                   'explicit_locality_identity.py', 'medical_need_review.py','documented_school_presence.py']]]
    code_before = {str(p): sha256(p) for p in code_paths}
    polygons = pd.read_parquet(args.polygons)
    fallback = pd.read_parquet(args.fallback_polygons) if args.fallback_polygons else None
    summary = {'cartographic_source_sha256': sha256(args.polygons), 'source_inputs': {},
               'no_nearest_settlement_assignment': True, 'observed_trips_established': False}
    if args.fallback_polygons:
        summary['fallback_source_sha256'] = sha256(args.fallback_polygons)
    sources = [('education', args.education / 'source_inventory_current.parquet'),
               ('commerce', args.commerce / 'sites.parquet'),
               ('health', args.bundle / 'health/public_scope_corrected/physical_sites.parquet'),
               ('food_host', args.bundle / 'commerce/fivepost/sites_grocery_current_host_proxy.parquet')]
    cards_path=args.documented_school_cards
    cards=json.loads(cards_path.read_text())
    extra_paths=[args.bundle/'context/analysis_reference.parquet',args.polygons,cards_path,
                 args.bundle/'inputs/preschool.parquet',args.bundle/'health/public_scope_corrected/np_supply.parquet']
    if args.fallback_polygons:extra_paths.append(args.fallback_polygons)
    extra_paths += [REPO/e['path'] for card in cards['school_cards'] for e in card['evidence']]
    all_input_paths=list(dict.fromkeys([p for _,p in sources]+extra_paths))
    initial_inputs = {str(p): sha256(p) for p in all_input_paths}
    for domain, path in sources:
        source = pd.read_parquet(path)
        repaired, stats = repair(source, polygons, reference, education=domain == 'education', fallback_polygons=fallback)
        if domain == 'health':
            repaired = review_medical_need_scope(repaired)
            stats['medical_scope_held_rows'] = int(repaired.need_scope_review_reason.ne('').sum())
            stats['medical_scope_hold_reasons'] = repaired.loc[repaired.need_scope_review_reason.ne(''), 'need_scope_review_reason'].value_counts().to_dict()
        target = args.output / domain
        filename = 'source_inventory_current.parquet' if domain == 'education' else 'physical_sites.parquet' if domain == 'health' else 'sites.parquet'
        save(repaired, target / filename)
        ledger = repaired[repaired.identity_repair_applied | repaired.cartographic_identity_status.str.startswith('held_')]
        save(ledger, target / 'identity_repair_ledger.parquet')
        if domain == 'education':
            save(repaired[repaired.service_code.notna()], target / 'physical_sites.parquet')
            official = pd.read_parquet(args.bundle / 'inputs/preschool.parquet')
            offers=add_documented_school_presence(education_offers(repaired,official,reference),reference,cards_path)
            save(offers, target / 'np_supply.parquet')
            stats['documented_dated_school_np_offers']=int(offers.source_id.eq('DOC_LOCAL_SCHOOLS_20261026').sum())
            save(school_orders(repaired), target / 'tagged_school_orders.parquet')
            save(regional_coverage(repaired, pd.read_parquet(target / 'np_supply.parquet'), reference), target / 'regional_coverage.parquet')
        elif domain in {'commerce', 'food_host'}:
            save(commerce_offers(repaired, accepted_statuses=('observed','proxy') if domain == 'food_host' else ('observed',)), target / 'supply.parquet')
        else:
            # Keep independent federal/official presence; do not reintroduce a
            # held OSM building through its older aggregate zero-cost offer.
            offers = review_np_presence_after_site_holds(pd.read_parquet(
                args.bundle / 'health/public_scope_corrected/np_supply.parquet'), repaired)
            save(offers, target / 'np_supply.parquet')
            stats['aggregate_presence_held_rows'] = int(offers.site_hold_np_presence_review_reason.ne('').sum())
        (target / 'summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2) + '\n')
        summary[domain] = stats
        summary['source_inputs'][str(path)] = sha256(path)
        print(domain, json.dumps(stats, ensure_ascii=False), flush=True)
    if initial_inputs != {str(p): sha256(p) for p in all_input_paths}:
        raise ValueError('Source inputs changed during identity repair')
    if code_before != {str(p): sha256(p) for p in code_paths}:
        raise ValueError('Identity interpretation code changed during repair')
    summary['code_sha256'] = code_before
    summary['source_inputs_unchanged'] = True
    summary['all_source_input_sha256']=initial_inputs
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ['bundle', 'education', 'commerce', 'polygons', 'output']:
        p.add_argument('--' + flag, type=Path, required=True)
    p.add_argument('--fallback-polygons', type=Path)
    p.add_argument('--documented-school-cards',type=Path,default=REPO/
                   'references/provenance/official_local_school_cards_20261026.json')
    run(p.parse_args())

#!/usr/bin/env python3
"""Recover national education evidence without treating missing records as absent schools.

Run from any directory. Reads frozen research inputs and writes only this directory.
Modern POI, legal entities, official inventories, and statutory catchments stay separate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RESEARCH = REPO / 'research'
OLD = RESEARCH / 'sgrt_opornost_20261019'
HISTORY = RESEARCH / 'sgrt_functional_dynamics_20261019/history'
MASTER = RESEARCH / 'sgrt_national_integration_20261019/core/feature_master.parquet'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def norm(value):
    return re.sub(r'[^а-яa-z0-9]+', ' ', str(value).lower().replace('ё', 'е')).strip()


def write(df, name):
    df.to_parquet(HERE / f'{name}.parquet', index=False)
    if len(df) < 5000:
        df.to_csv(HERE / f'{name}.csv', index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', type=Path, default=MASTER)
    args = parser.parse_args()
    inputs = [args.master, OLD / 'data/school_inventory_linked.csv',
              OLD / 'model/documented_graph/service_edges_calculated.csv',
              HISTORY / 'school_inventory_by_year.csv', HISTORY / 'edges_by_year.csv',
              HISTORY / 'uchaly_school_provider_sites_2025.csv',
              HISTORY / 'uchaly_school_physical_relations_2025.csv',
              HISTORY / 'attachment_transitions.csv', HISTORY / 'konakovo_transitions.csv',
              HISTORY / 'SOURCE_LEDGER.json']
    manifest = [{'file': str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p),
                 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in inputs]
    names = pq.ParquetFile(args.master).schema_arrow.names
    selected = ['id', 'name', 'region', 'type', 'lat', 'lon', 'population_2021']
    selected += [c for c in names if c.startswith('places_') and
                 any(c.endswith('_' + t + '_count') for t in
                     ['school', 'preschool', 'other_education', 'name_signal_school'])]
    selected += [c for c in names if c.startswith('econ_native_') and
                 c.endswith('_education85_legal_entities')]
    master = pd.read_parquet(args.master, columns=list(dict.fromkeys(selected)))
    assert len(master) == 142570 and master.id.notna().all() and master.id.is_unique
    ids = set(master.id)

    # Inventories retain source assertions. Distinct school keys in one document
    # count schools; the same school in several documents is never summed.
    inv = pd.read_csv(inputs[1])
    inv['settlement_uid'] = inv['id']
    inv['source_document_date'] = inv.source_id.map({
        'SV2025': '2025-03-05', 'TV2021': '2021-01-27', 'NV2026': '2026-02-27'})
    inv['document_id'] = inv.source_id
    inv['school_assertion_key'] = inv.inventory_id
    inv['inventory_origin'] = 'official_document_inventory_52_source_rows'
    inv['physical_site_evidence'] = 'settlement_level_official_listing_not_independent_building_survey'
    records = inv.to_dict('records')
    by_context = {}
    for _, r in inv.iterrows():
        by_context.setdefault((norm(r.provider_settlement), norm(r.region)), set()).add(r.id)
    nt = pd.read_csv(inputs[3])
    for i, r in nt.iterrows():
        # 2025 is already included in the full 52-row source inventory.
        if r.year == 2025:
            continue
        u = by_context.get((norm(r.provider_settlement), norm('Свердловская область')), set())
        records.append(dict(settlement_uid=next(iter(u)) if len(u) == 1 else None,
            document_id=r.source_id, source_id=r.source_id,
            source_document_date=r.document_date, school_assertion_key=r.school_key,
            provider_settlement=r.provider_settlement, provider_name=r.provider_name_literal,
            service_level='first_grade_admission_territorial_priority',
            source_url=r.source_url, locator=r.locator,
            inventory_origin='official_nizhnaya_tura_paired_document_inventory',
            physical_site_evidence='official_listed_school_settlement_not_capacity_or_usage',
            region='Свердловская область'))
    uch = pd.read_csv(inputs[5])
    for i, r in uch.iterrows():
        records.append(dict(settlement_uid=r.destination_uid,
            document_id='UCH2025_03224', source_id='UCH2025_03224',
            source_document_date=r.source_date, school_assertion_key=f'UCH_SITE_{i}',
            provider_settlement=r.provider_settlement, provider_name=r.provider_name,
            service_level=r.school_level, source_url=r.source_url,
            locator=f'PDF_page{r.pdf_page}_row{r.source_row}',
            inventory_origin='signed_act_explicit_physical_school_site',
            physical_site_evidence=r.site_status, region='Республика Башкортостан'))
    inventory = pd.DataFrame(records)
    inventory['axis_identity_accepted'] = inventory.settlement_uid.isin(ids)
    inventory['assertion_uid'] = [f'EDU_INV_{i:04d}' for i in range(len(inventory))]
    inventory['is_national_inventory'] = False
    write(inventory, 'official_school_inventory_assertions')

    # Preserve every extracted relation, including unresolved claims. Canonical
    # duplicate source extractions do not multiply pupils/residents or edges.
    rows = []
    base = pd.read_csv(inputs[2])
    for _, r in base[base.link_kind.eq('statutory_school_catchment')].iterrows():
        z = r.to_dict()
        z.update(relation_kind=r.link_kind, function_group='education',
                 document_id=r.source_id, actual_travel_observed=False,
                 source_table='previous_checked_documented_graph')
        if r.source_id == 'SV2025':
            z['document_id'] = 'NT2025'
            z['service_level'] = 'first_grade_admission_territorial_priority'
        rows.append(z)
    for _, r in pd.read_csv(inputs[4]).iterrows():
        z = r.to_dict()
        z.update(document_id=r.source_id, actual_travel_observed=False,
                 source_table='nizhnaya_tura_paired_official_assignments')
        rows.append(z)
    for _, r in pd.read_csv(inputs[6]).iterrows():
        z = r.to_dict()
        z.update(document_id=r.source_id, actual_travel_observed=False,
                 source_table='uchaly_signed_act_physical_school_assignments')
        rows.append(z)
    relations = pd.DataFrame(rows)
    relations['both_axis_ids_accepted'] = (relations.origin_uid.isin(ids) &
                                           relations.destination_uid.isin(ids))
    relations['external_axis_link'] = (relations.both_axis_ids_accepted &
                                        relations.origin_uid.ne(relations.destination_uid))
    relations['evidence_use'] = 'post_development_external_check_not_blind_holdout'
    relations['relation_assertion_uid'] = [f'EDU_REL_{i:04d}' for i in range(len(relations))]
    keycols = ['document_id', 'source_document_date', 'origin_uid', 'destination_uid', 'service_level']
    relations['canonical_key'] = relations[keycols].fillna('UNKNOWN').astype(str).agg('|'.join, axis=1)
    relations['duplicate_source_extraction'] = relations.duplicated('canonical_key', keep=False)
    write(relations, 'statutory_relation_assertions')
    canonical = relations.drop_duplicates('canonical_key').copy()
    write(canonical, 'canonical_statutory_relations')
    external = canonical[canonical.external_axis_link]

    # One row per id: zero count means zero accepted records in this corpus,
    # never an asserted zero in the national school network.
    features = master[['id']].copy()
    physical_cols = [c for c in selected if c.startswith('places_')]
    for c in physical_cols:
        features['edu_' + c] = master[c].to_numpy()
    for qual in ['baseline', 'conditional', 'nearest_candidate']:
        col = f'places_{qual}_school_count'
        features[f'edu_{qual}_school_poi_records'] = master[col].to_numpy()
        features[f'edu_{qual}_school_evidence_positive'] = master[col].gt(0).to_numpy()
    features['edu_baseline_or_conditional_school_poi_records'] = (
        master.places_baseline_school_count + master.places_conditional_school_count).to_numpy()
    features['edu_physical_school_source_release'] = 'Overture_Places_2026-09-23.1'
    features['edu_school_network_completeness'] = 'unknown_incomplete_source_and_linkage'
    features['edu_school_capacity'] = np.nan
    features['edu_school_opening_year'] = np.nan
    features['edu_school_closure_year'] = np.nan
    accepted_inventory = inventory[inventory.axis_identity_accepted]
    per_document = accepted_inventory.groupby(['settlement_uid', 'document_id']).school_assertion_key.nunique()
    site_lower = per_document.groupby(level=0).max()
    features['edu_official_school_sites_documented_lower_bound'] = features.id.map(site_lower).fillna(0).astype('int32')
    features['edu_official_inventory_document_count'] = features.id.map(
        accepted_inventory.groupby('settlement_uid').document_id.nunique()).fillna(0).astype('int16')
    features['edu_documented_external_origins_unique_all_dates'] = features.id.map(
        external.groupby('destination_uid').origin_uid.nunique()).fillna(0).astype('int32')
    features['edu_documented_external_provider_positive'] = features.edu_documented_external_origins_unique_all_dates.gt(0)
    features['edu_documented_assignment_origin_positive'] = features.id.isin(external.origin_uid)
    features['edu_documented_school_site_positive'] = features.edu_official_school_sites_documented_lower_bound.gt(0)
    features['edu_school_physical_or_official_evidence_positive'] = (
        features.edu_baseline_school_evidence_positive | features.edu_documented_school_site_positive)
    for year in range(2011, 2026):
        col = f'econ_native_{year}_education85_legal_entities'
        features[f'edu_legal_education85_entities_{year}'] = master[col].to_numpy()
    features['edu_legal_education85_2011_2025_net_change'] = (
        features.edu_legal_education85_entities_2025 - features.edu_legal_education85_entities_2011)
    features['edu_legal_history_meaning'] = 'registered_entities_not_physical_schools_or_function_closures'
    features['edu_no_record_interpretation'] = 'no_accepted_evidence_not_absence_of_school'
    assert features.id.equals(master.id)
    assert len(features) == len(master) and features.id.is_unique
    write(features, 'settlement_features')

    # Long national legal timeline is a separate observation axis.
    legal = []
    for year in range(2011, 2026):
        n = features[f'edu_legal_education85_entities_{year}']
        legal.append(dict(year=year,axis_settlements=len(master),
                          settlements_positive=int(n.gt(0).sum()),
                          accepted_entity_records=int(n.sum()),
                          meaning='exact_code_registered_education_entities_not_school_inventory'))
    pd.DataFrame(legal).to_csv(HERE / 'national_education_legal_history.csv', index=False)
    transitions = pd.read_csv(inputs[7])
    transitions['history_scope'] = 'Nizhnaya_Tura_selected_positive_statutory_assignments'
    write(transitions, 'nizhnaya_tura_assignment_transitions')
    kt = pd.read_csv(inputs[8])
    kt['history_scope'] = 'Konakovo_three_selected_school_groups_not_complete_district'
    write(kt, 'konakovo_assignment_transitions')
    linked_external = external.groupby('document_id').size().to_dict()
    report = dict(status='PASS', axis_rows=len(features), columns=len(features.columns),
        unique_ids=int(features.id.nunique()), null_ids=int(features.id.isna().sum()),
        master_sha256=manifest[0]['sha256'],
        national_baseline_school_poi_records=int(master.places_baseline_school_count.sum()),
        national_baseline_school_poi_positive_settlements=int(master.places_baseline_school_count.gt(0).sum()),
        national_conditional_additional_school_poi_records=int(master.places_conditional_school_count.sum()),
        national_baseline_or_conditional_school_poi_positive_settlements=int(features.edu_baseline_or_conditional_school_poi_records.gt(0).sum()),
        national_nearest_candidate_school_poi_records_not_accepted=int(master.places_nearest_candidate_school_count.sum()),
        official_inventory_assertions=len(inventory),
        official_inventory_settlements=int(accepted_inventory.settlement_uid.nunique()),
        relation_assertions=len(relations),canonical_relations=len(canonical),
        canonical_external_axis_relations=len(external),
        external_origins_unique=int(external.origin_uid.nunique()),
        external_destinations_unique=int(external.destination_uid.nunique()),
        external_relations_by_document=linked_external,
        source_years=sorted(canonical.source_document_date.dropna().astype(str).str[:4].unique()),
        actual_travel_observed=False, national_school_open_close_history_available=False,
        official_national_inventory_acquired=False,
        documented_assignments_scope='nonrepresentative_selected_official_documents',
        input_bytes_unchanged=all(sha(REPO / r['file']) == r['sha256'] for r in manifest),
        caveats=['No accepted record is not absence of a school.',
                 'Education85 legal entities include broad education, not only schools.',
                 'Modern POI and documents are not backcast to census dates.',
                 'Known normative assignments were seen during earlier development; not blind holdout.',
                 'Capacity and observed pupils/trips are unknown in the national feature layer.'])
    assert report['input_bytes_unchanged']
    (HERE / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (HERE / 'source_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

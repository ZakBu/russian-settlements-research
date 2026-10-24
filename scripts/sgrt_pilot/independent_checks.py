#!/usr/bin/env python3
"""Counterexamples and independent arithmetic checks for the dated pilot.

The quarantine below records source-context conflicts found by comparing literal
rows of the official LO workbook with accepted locality names and districts.
It does not reject long trips on distance alone and does not silently repair IDs.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

# Reviewed source-context contradictions, not tuned by model agreement.
# The original sheet and row are the stable location in the official workbook.
CONTEXT_CONFLICTS = [
    ('Выборгская МБ', 65, 'origin',
     'The workbook places Холодный ручей under Гончаровское settlement and Выборгская МБ; the accepted match is Холодный Ручей in Подпорожский district. Literal-name equality alone is insufficient.'),
    ('Всеволожская КМБ', 94, 'destination',
     'ФАП п. Грибное is recorded under Рахьинское settlement and Всеволожская КМБ; the matched Грибное is in Выборгский district. Provider-site identity is unresolved.'),
    *[('Токсовская МБ', row, 'destination',
       'Врачебная амбулатория Пери is recorded under Лесколовское settlement; the accepted literal match is кордон Пери in Тосненский district. A distinct станция Пери exists in Всеволожский district. No automatic reassignment is made.')
      for row in (60, 64, 65, 66)],
]


def distance_km(lat1, lon1, lat2, lon2):
    a, b, c, d = np.radians([lat1, lon1, lat2, lon2])
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(
        np.sin((a-c)/2)**2 + np.cos(a)*np.cos(c)*np.sin((b-d)/2)**2, 0, 1)))


def period_state(initial, final, years, threshold):
    """Independent vector calculation, without importing the audit's function."""
    a, b = np.asarray(initial, dtype=float), np.asarray(final, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        growth_log = (np.log(b) - np.log(a)) / years
    result = np.full(len(a), 'stable', dtype=object)
    result[growth_log > np.log1p(threshold)+1e-14] = 'growth'
    result[growth_log < np.log1p(-threshold)-1e-14] = 'decline'
    result[(a == 0) & (b > 0)] = 'zero_to_positive'
    result[(a > 0) & (b == 0)] = 'positive_to_zero'
    result[(a == 0) & (b == 0)] = 'zero_both'
    result[~(np.isfinite(a) & np.isfinite(b) & (a >= 0) & (b >= 0))] = 'unknown'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--population', type=Path, required=True, help='Directory containing ordinary_full3.parquet')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--transport', type=Path, help='Optional transport directory for component checks')
    p.add_argument('--models', type=Path, help='Optional parent directory of scenario_outcomes.parquet files')
    p.add_argument('--costs', type=Path, help='Override transport cost file; otherwise prefer combined_costs.parquet')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    s = pd.read_parquet(a.data/'settlements_all_2021.parquet')
    r = pd.read_parquet(a.data/'medical_attachments_lo_2024.parquet')
    w = pd.read_parquet(a.population/'ordinary_full3.parquet')
    if s.source_record_id.duplicated().any() or s.root.duplicated().any():
        raise ValueError('Duplicate accepted settlement ID/root')
    index = s.set_index('source_record_id')
    resolved = r[r.origin_present_in_spatial2021 & r.destination_present_in_spatial2021 & ~r.origin_is_partial_address_scope].copy()
    for field in ['name', 'district_raw', 'lat', 'lon']:
        resolved['origin_'+field] = resolved.origin_id.map(index[field])
        resolved['destination_'+field] = resolved.destination_id.map(index[field])
    resolved['geodesic_km_diagnostic_not_trip_length'] = distance_km(
        resolved.origin_lat, resolved.origin_lon, resolved.destination_lat, resolved.destination_lon)
    flagged = []
    for sheet, row, endpoint, reason in CONTEXT_CONFLICTS:
        rows = r[r.sheet.str.strip().eq(sheet) & r.excel_row_1based.eq(row)].copy()
        if len(rows) != 1:
            raise ValueError(f'Quarantine locator no longer identifies one source row: {sheet}/{row}')
        item = rows.iloc[0]
        flagged.append({'source_id': item.source_id, 'sheet': item.sheet,
            'excel_row_1based': int(item.excel_row_1based), 'endpoint': endpoint,
            'origin_id': item.origin_id, 'destination_id': item.destination_id,
            'origin_literal': item.origin_literal, 'provider_literal': item.provider_literal,
            'municipal_context_literal': item.municipal_context_literal,
            'reason': reason, 'excluded_from_agreement_denominator': True,
            'automatic_repair_applied': False,
            'source_url': item.source_url})
    quarantine = pd.DataFrame(flagged)
    quarantine.to_csv(a.output/'medical_context_quarantine.csv', index=False)
    quarantine.to_parquet(a.output/'medical_context_quarantine.parquet', index=False)
    keys = set(zip(quarantine.sheet.str.strip(), quarantine.excel_row_1based))
    resolved['context_conflict_quarantined'] = [(str(row.sheet).strip(), int(row.excel_row_1based)) in keys for row in resolved.itertuples()]
    resolved.sort_values('geodesic_km_diagnostic_not_trip_length', ascending=False).to_parquet(a.output/'medical_geographic_diagnostics.parquet', index=False)
    sensitivity = []
    for t in (0., .001, .0025, .005):
        states=[]
        for field in ('population', 'effective_population'):
            states.append(np.column_stack([
                period_state(w[f'{field}_2002'], w[f'{field}_2010'], 8, t),
                period_state(w[f'{field}_2010'], w[f'{field}_2021'], 11, t)]))
        changed=(states[0] != states[1]).any(axis=1)
        sensitivity.append({'annual_threshold': t, 'changed_trajectory_numerator': int(changed.sum()),
            'ordinary_full3_denominator': len(w), 'share': float(changed.mean()),
            'separate_zero_transition_states': True, 'is_national_error_rate': False})
    pd.DataFrame(sensitivity).to_csv(a.output/'independent_raw_effective_sensitivity.csv', index=False)
    noncredit=s[s.in_pilot & ~s.working_credit_present].groupby('region').agg(
        source_rows=('population', 'size'), population_sum=('population', 'sum'),
        positive_population_rows=('population', lambda x: int((x>0).sum())))
    noncredit.to_csv(a.output/'noncredit_pilot_records.csv')
    summary={'accepted_spatial_rows': len(s), 'duplicate_ids': int(s.source_record_id.duplicated().sum()),
        'resolved_nonpartial_attachment_rows_before_context_check': len(resolved),
        'quarantined_source_rows': len(quarantine),
        'resolved_rows_after_context_quarantine': int((~resolved.context_conflict_quarantined).sum()),
        'quarantine_rule': 'Six specifically reviewed literal-source vs locality-context contradictions, not a distance cut-off or model-agreement filter',
        'automatic_id_repair_applied': False,
        'medical_attachment_is_observed_trip': False,
        'raw_effective_independent_check': sensitivity,
        'uncredited_settlement_rows_retained_in_spatial_frame': int(noncredit.source_rows.sum()),
        'population_totals_require_explicit_credit_or_scope_rule': True}
    if a.transport:
        cost_path = a.costs or a.transport/('combined_costs.parquet' if (a.transport/'combined_costs.parquet').exists() else 'pilot_costs.parquet')
        costs = pd.read_parquet(cost_path, columns=['origin_id','destination_id','cost_minutes','network_minutes','connector_minutes'])
        finite = costs.cost_minutes.notna()
        component_error = (costs.loc[finite, 'cost_minutes'] - costs.loc[finite, 'network_minutes'] - costs.loc[finite, 'connector_minutes']).abs()
        route_checks = {
            'file': cost_path.name,
            'directed_pairs': len(costs),
            'duplicate_pairs': int(costs.duplicated(['origin_id', 'destination_id']).sum()),
            'negative_costs': int(costs.cost_minutes.lt(0).sum()),
            'maximum_component_rounding_error_minutes': float(component_error.max()),
            'origin_ids_outside_accepted_spatial_frame': int((~costs.origin_id.isin(s.source_record_id)).sum()),
            'destination_ids_outside_accepted_or_federal_context_frame': int((~costs.destination_id.isin(set(s.source_record_id)|{'ctx:RU-FED-MOW','ctx:RU-FED-SPB'})).sum()),
            'diagonal_nonzero_costs': int(costs.loc[costs.origin_id.eq(costs.destination_id), 'cost_minutes'].ne(0).sum()),
        }
        if float(component_error.max()) > 1e-3:
            raise ValueError('Cost no longer equals network plus connectors within 0.001 minutes')
        if any(route_checks[k] for k in ['duplicate_pairs','negative_costs','origin_ids_outside_accepted_spatial_frame','destination_ids_outside_accepted_or_federal_context_frame','diagonal_nonzero_costs']):
            raise ValueError('Transport invariant violation: '+str(route_checks))
        summary['transport_component_checks'] = route_checks
    anchor_path = a.data/'external_context_anchors.parquet'
    if anchor_path.exists():
        anchors = pd.read_parquet(anchor_path)
        supply = pd.read_parquet(a.data/'supply_all_2021.parquet')
        ordinary_federal_supply = supply.center_id.isin(anchors.population_source_record_id.dropna())
        context_objects = pd.read_parquet(a.data/'context_source_objects_2021.parquet')
        ordinary_objects = pd.read_parquet(a.data/'source_objects_2021.parquet')
        actual_ordinary_objects = ordinary_objects[ordinary_objects.source_record_id.isin(s.source_record_id)]
        objkeys = ['source_id', 'source_object_id', 'scenario']
        overlap = actual_ordinary_objects[objkeys].merge(context_objects[context_objects.context_link_eligible][objkeys], on=objkeys, how='inner')
        context_checks = {
            'federal_context_anchors': len(anchors),
            'context_has_no_fabricated_census_source_ids': bool(anchors.source_record_id.isna().all()),
            'context_has_no_fabricated_roots': bool(anchors.root.isna().all()),
            'context_never_working_population_credit': bool((~anchors.working_credit_present).all()),
            'ordinary_supply_rows_on_federal_aggregate_source_id': int(ordinary_federal_supply.sum()),
            'ordinary_and_context_object_assignment_overlap': len(overlap),
        }
        if ordinary_federal_supply.any() or len(overlap):
            raise ValueError('Federal context supply double counting: '+str(context_checks))
        summary['federal_context_checks'] = context_checks
    model_checks = []
    if a.models:
        for path in sorted(a.models.rglob('scenario_outcomes.parquet')):
            outcomes = pd.read_parquet(path)
            keys = [c for c in ['source_record_id','source_scenario','observation_year','function','service_order','decay_family','half_life_minutes','kernel_floor','supply_transform'] if c in outcomes]
            if outcomes.duplicated(keys+['model']).any():
                raise ValueError('Duplicated scenario outcome: '+str(path))
            binary = outcomes[outcomes.supply_transform.eq('binary')] if 'supply_transform' in outcomes else outcomes.iloc[:0]
            functional = binary[binary.model.eq('functional')].set_index(keys)
            nearest = binary[binary.model.eq('nearest')].set_index(keys)
            common = functional.index.intersection(nearest.index)
            differences = functional.loc[common, 'primary_candidate_id'].fillna('__NONE__').ne(nearest.loc[common, 'primary_candidate_id'].fillna('__NONE__'))
            item = {'file': str(path.relative_to(a.models)), 'scenario_rows': len(outcomes),
                'binary_functional_vs_nearest_comparisons': len(common),
                'binary_functional_vs_nearest_disagreements': int(differences.sum()),
                'established_external_links': int(outcomes.established_external_link.sum()),
                'unknown_local_supply_explicitly_flagged': bool(outcomes.loc[outcomes.local_supply_status.eq('unknown'), 'missing_local_supply_could_change_choice'].all()),
                'binary_identity_is_mathematical_not_empirical_validation': True}
            model_checks.append(item)
    summary['model_arithmetic_checks'] = model_checks
    (a.output/'independent_diagnostics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__=='__main__':
    main()

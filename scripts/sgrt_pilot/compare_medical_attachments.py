#!/usr/bin/env python3
"""Compare conditional scenarios with normative attachment records, not trips.

No parameter is fitted or selected here. Report every scenario on the same
resolved origins; omit source-context conflicts explicitly, never by distance.
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def compare(attachments, quarantine, supply_path, outcomes_paths, output):
    source = pd.read_parquet(attachments)
    supply = pd.read_parquet(supply_path)
    conflicts = pd.read_parquet(quarantine)
    keys = ['source_id', 'sheet', 'excel_row_1based']
    source = source.merge(conflicts[keys].drop_duplicates().assign(context_conflict=True), on=keys, how='left', validate='many_to_one')
    source['context_conflict'] = source.context_conflict.eq(True)
    ok = source.origin_id.notna() & source.destination_id.notna()
    ok &= source.origin_present_in_spatial2021 & source.destination_present_in_spatial2021
    ok &= ~source.origin_is_partial_address_scope.fillna(True) & ~source.context_conflict
    relations = source[ok].copy()
    external = relations[relations.origin_id.ne(relations.destination_id)].drop_duplicates(['origin_id', 'destination_id'])
    truth = external.groupby('origin_id').destination_id.agg(set)
    source.to_parquet(output / 'medical_attachments_with_context_flags.parquet', index=False)
    external.to_parquet(output / 'medical_evaluation_external_relations.parquet', index=False)
    metrics, examples = [], []
    fields = ['source_scenario', 'observation_year', 'supply_transform', 'service_order', 'model', 'decay_family', 'half_life_minutes', 'kernel_floor']
    for path in outcomes_paths:
        frame = pd.read_parquet(path)
        frame = frame[frame.function.eq('healthcare')]
        if frame.empty:
            continue
        for values, group in frame.groupby(fields, dropna=False):
            if not group.source_record_id.isin(truth.index).any():
                continue
            if group.source_record_id.duplicated().any():
                raise ValueError('Duplicate prediction key')
            group = group.set_index('source_record_id')
            predicted = group.primary_candidate_id.reindex(truth.index)
            matches = [pd.notna(value) and value in truth.loc[origin] for origin, value in predicted.items()]
            params = dict(zip(fields, values))
            params['run'] = path.parent.name
            observed = supply[supply.function.eq('healthcare') & supply.scenario.eq(params['source_scenario'])]
            if params['service_order'] not in ['broad_recorded_function_not_service_order', 'broad_healthcare', 'all_orders']:
                observed = observed[observed.service_order.eq(params['service_order'])]
            known_providers = set(observed.center_id)
            eligible = pd.Series([bool(truth.loc[origin] & known_providers) for origin in truth.index], index=truth.index)
            eligible_matches = sum(match and bool(eligible.loc[origin]) for origin, match in zip(truth.index, matches))
            present = predicted.notna()
            rows = len(truth)
            metrics.append(params | {
                'resolved_external_origins': rows,
                'origins_in_model_frame': int(truth.index.isin(group.index).sum()),
                'origins_with_positive_candidate': int(present.sum()),
                'origins_exactly_matching_any_normative_provider': int(sum(matches)),
                'agreement_all_resolved_origins': sum(matches) / rows if rows else None,
                'agreement_candidate_present_origins': sum(matches) / int(present.sum()) if present.any() else None,
                'origins_with_any_normative_provider_in_source_supply': int(eligible.sum()),
                'source_provider_coverage_all_resolved_origins': float(eligible.mean()) if rows else None,
                'agreement_source_provider_present_origins': eligible_matches / int(eligible.sum()) if eligible.any() else None,
                'parameters_fitted_to_these_relations': False,
                'preregistered_blind_holdout': False,
                'evidence': 'normative_attachment_not_observed_trip',
            })
            if params['decay_family'] == 'exponential' and params['half_life_minutes'] == 30 and params['kernel_floor'] == 0.05:
                for (origin, value), match in zip(predicted.items(), matches):
                    examples.append(params | {'origin_id': origin, 'primary_candidate_id': value,
                        'normative_destination_ids': json.dumps(sorted(truth.loc[origin]), ensure_ascii=False),
                        'match': match})
    result = pd.DataFrame(metrics)
    result.to_csv(output / 'medical_attachment_model_comparison.csv', index=False)
    pd.DataFrame(examples).to_parquet(output / 'medical_attachment_reference_examples.parquet', index=False)
    summary = {
        'source_rows': len(source), 'source_document_date': '2023-11-29',
        'fresh_source_transcription_checked_separately': True,
        'rows_with_source_context_conflict': int(source.context_conflict.sum()),
        'spatial_nonpartial_nonconflicting_rows': len(relations),
        'unique_external_pairs': len(external), 'unique_external_origins': len(truth),
        'unique_external_providers': int(external.destination_id.nunique()),
        'compared_scenario_rows': len(result),
        'parameters_fitted_or_selected': False,
        'limits': ['Normative attachments are not observed trips',
                   'Cross-date comparison: document2023 vs OSM/road2021',
                   'Only explicitly resolved provider localities; selection bias remains',
                   'Supply orders may differ in broad diagnostic healthcare layer',
                   'Previous inspection of source prevents calling this a blind holdout',
                   'No independence or trip accuracy claim from scenario stability'],
    }
    (output / 'medical_comparison_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attachments', type=Path, required=True)
    p.add_argument('--quarantine', type=Path, required=True)
    p.add_argument('--supply', type=Path, required=True)
    p.add_argument('--outcomes', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    compare(a.attachments, a.quarantine, a.supply, a.outcomes, a.output)

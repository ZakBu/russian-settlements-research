#!/usr/bin/env python3
"""Independent positive-evidence profiles and a diagnostic scale classification.

Care-address IDs are deduplicated across medical services. They are neither
beds nor workers, verified operating facilities, patient flows or calibrated
attraction masses. Missing inventory counts remain unknown. The mixed index
uses population and recorded medical scale only: unequal educational locality
identification makes a joint all-sector index unsuitable for substantive ranks.
The resulting mixture groups are descriptive classes, never SGRT levels.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

CITY_EXAMPLES = ['Москва', 'Санкт-Петербург', 'Саратов', 'Челябинск', 'Екатеринбург', 'Казань']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def medical_counts(evidence, addresses):
    keys = ['UIDSPMO', 'IDADDRESS']
    accepted = addresses.loc[addresses.source_record_id.notna(), [*keys, 'source_record_id']].drop_duplicates()
    if accepted[keys].isna().any().any():
        raise ValueError('Accepted identity needs an exact subdivision-address key')
    if accepted.duplicated(keys).any():
        raise ValueError('A care-address pair has conflicting settlement identities')
    # Address IDs, not services or subdivision rows, define this scale proxy.
    conflicts = accepted.groupby('IDADDRESS').source_record_id.nunique()
    if conflicts.gt(1).any():
        raise ValueError('Address ID assigned to more than one settlement')
    med = evidence.merge(accepted, on=keys, how='inner', validate='many_to_one')
    out = med.groupby('source_record_id').agg(
        medical_care_address_ids_known=('IDADDRESS', 'nunique'),
        medical_subdivision_ids_known=('UIDSPMO', 'nunique'),
        medical_clinical_profiles_known=('medical_need_scope', 'nunique'))
    pair = med[['source_record_id', 'medical_need_scope']].dropna().drop_duplicates()
    frequency = pair.groupby('medical_need_scope').source_record_id.nunique()
    rarity = np.log(len(out) / frequency)
    pair['rarity'] = pair.medical_need_scope.map(rarity)
    out['medical_profile_rarity_score'] = pair.groupby('source_record_id').rarity.sum()
    channels = med.groupby(['source_record_id', 'service_code']).IDADDRESS.nunique().unstack()
    for channel in channels:
        out['care_address_ids_' + channel] = channels[channel]
    return out, {'accepted_address_pairs': len(accepted), 'matched_clinical_rows': len(med),
                 'settlements_with_positive_medical_evidence': len(out),
                 'care_address_ids': med.IDADDRESS.nunique(),
                 'care_address_count_is_capacity': False,
                 'rarity_uses_distinct_settlements_not_raw_service_rows': True}


def feature_counts(frame, *, site_column, prefix, admission_columns=()):
    accepted = frame.source_record_id.notna() & frame.supply_status.eq('observed')
    for column in admission_columns:
        accepted &= frame[column].eq(True)
    selected = frame.loc[accepted].copy()
    if selected[site_column].isna().any():
        raise ValueError('Admitted physical feature has no deduplication identity')
    grouped = selected.groupby(['source_record_id', 'service_code'])[site_column].nunique().unstack()
    grouped.columns = [prefix + c for c in grouped]
    return grouped, {'source_rows': len(frame), 'positive_identified_rows': len(selected),
                     'physical_feature_counts_are_complete_inventory': False}


def assemble(reference, med, education=None, commerce=None, workforce=None):
    ref = reference.loc[reference.source_record_id.notna()].copy()
    if not ref.source_record_id.is_unique:
        raise ValueError('Non-null settlement keys must be unique')
    keys = ['source_record_id', 'name', 'region', 'lat', 'lon', 'population_2021', 'population_role']
    out = ref[keys].set_index('source_record_id').join(med, how='left', validate='one_to_one')
    for extra in [education, commerce]:
        if extra is not None:
            out = out.join(extra, how='left', validate='one_to_one')
    if workforce is not None:
        work = workforce[workforce.source_record_id.notna()].set_index('source_record_id')
        if not work.index.is_unique:
            raise ValueError('Workforce observations need unique settlement identity')
        out = out.join(work[['partial_organisation_workforce_2025', 'partial_workforce_status']],
                       how='left', validate='one_to_one')
    out['medical_inventory_missing_is_not_zero'] = out.medical_care_address_ids_known.isna()
    out['capacity_and_patient_flow_established'] = False
    out['joint_multisector_comparability_established'] = False
    # A positive, own-source stock proxy, independent of any delineated basin.
    out['independent_positive_medical_stock_proxy'] = out.medical_care_address_ids_known
    out['proxy_unit'] = 'registered_care_address_ids_not_beds_or_flows'
    return out.reset_index()


def mixture_fit(values, max_k, seed, n_init=3):
    from sklearn.mixture import GaussianMixture
    models = []
    for k in range(1, min(max_k, len(np.unique(values))) + 1):
        model = GaussianMixture(k, covariance_type='full', n_init=n_init,
                                random_state=seed, reg_covar=1e-5).fit(values[:, None])
        models.append((float(model.bic(values[:, None])), k, model))
    _, best_k, best = min(models, key=lambda row: (row[0], row[1]))
    order = {raw: rank for rank, raw in enumerate(np.argsort(best.means_.ravel()))}
    labels = np.array([order[x] for x in best.predict(values[:, None])], dtype='int64')
    return best, labels, [{'components': k, 'bic': bic} for bic, k, _ in models], best_k


def classify(profiles, *, max_k=10, seed=20261027, bootstrap_repeats=5):
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    out = profiles.copy()
    eligible = (out.population_role.isin(['ordinary_settlement_record', 'external_context_nonadditive'])
                & out.population_2021.gt(0) & out.medical_care_address_ids_known.gt(0))
    if eligible.sum() < 20:
        raise ValueError('Too few positive, comparable observations for a mixture diagnostic')
    a = np.log1p(out.loc[eligible, ['population_2021', 'medical_care_address_ids_known']].to_numpy())
    means, std = a.mean(axis=0), a.std(axis=0)
    if (std <= 0).any():
        raise ValueError('No independent variation in one scale component')
    z = (a - means) / std
    score = z.mean(axis=1)
    _, labels, criteria, chosen = mixture_fit(score, max_k, seed)
    out['population_medical_scale_score'] = np.nan
    out.loc[eligible, 'population_medical_scale_score'] = score
    out['diagnostic_scale_class'] = pd.Series(pd.NA, index=out.index, dtype='Int64')
    out.loc[eligible, 'diagnostic_scale_class'] = labels
    out['scale_class_is_territorial_order'] = False
    out['scale_class_status'] = 'insufficient_positive_comparable_evidence'
    out.loc[eligible, 'scale_class_status'] = 'descriptive_population_medical_mixture_not_sgrt_order'
    rng = np.random.default_rng(seed)
    bootstrap = []
    for repeat in range(bootstrap_repeats):
        positions = rng.choice(len(score), size=max(20, int(.8 * len(score))), replace=False)
        model, _, _, k = mixture_fit(score[positions], max_k, seed + repeat + 1, n_init=2)
        predicted = model.predict(score[:, None])
        bootstrap.append({'repeat': repeat, 'selected_components': k,
                          'ari_against_full_fit': float(adjusted_rand_score(labels, predicted))})
    sensitivity = []
    for population_weight in [.25, .5, .75]:
        alternative = z[:, 0] * population_weight + z[:, 1] * (1 - population_weight)
        _, alt_labels, _, k = mixture_fit(alternative, max_k, seed)
        sensitivity.append({'population_weight': population_weight, 'medical_weight': 1 - population_weight,
                            'selected_components': k, 'ari_against_equal_weight': float(adjusted_rand_score(labels, alt_labels))})
    silhouette = (float(silhouette_score(score[:, None], labels, sample_size=min(1500, len(score)), random_state=seed))
                  if 1 < chosen < len(score) else None)
    summary = {'eligible_profiles': int(eligible.sum()), 'all_reference_records': len(out),
               'selected_components': chosen, 'search_boundary_selected': chosen == max_k,
               'class_counts': {str(k): int(v) for k, v in pd.Series(labels).value_counts().sort_index().items()},
               'bic': criteria, 'silhouette_diagnostic': silhouette, 'bootstrap': bootstrap,
               'weight_sensitivity': sensitivity, 'log_feature_means': means.tolist(),
               'log_feature_standard_deviations': std.tolist(),
               'features': ['log1p(population_2021)', 'log1p(registered_care_address_ids)'],
               'calibration_against_catchment_population': False,
               'mixture_classes_are_sgrt_orders': False, 'medical_stock_is_capacity_or_jobs': False,
               'joint_education_commerce_index_with_unequal_inventory_not_used': True,
               'weights_are_our_explicit_sensitivity_scenarios_not_estimated_effects': True}
    return out, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['reference', 'medical-evidence', 'medical-addresses', 'output']:
        p.add_argument('--' + key, type=Path, required=True)
    for key in ['education', 'commerce', 'workforce']:
        p.add_argument('--' + key, type=Path)
    p.add_argument('--max-k', type=int, default=10)
    p.add_argument('--bootstrap-repeats', type=int, default=5)
    args = p.parse_args()
    inputs = {k: v for k, v in vars(args).items() if isinstance(v, Path) and k != 'output'}
    before = {k: sha(v) for k, v in inputs.items()}
    evidence = pd.read_parquet(args.medical_evidence)
    addresses = pd.read_parquet(args.medical_addresses, columns=['UIDSPMO', 'IDADDRESS', 'source_record_id'])
    medical, medical_audit = medical_counts(evidence, addresses)
    ed = comm = work = None
    audits = {'medical': medical_audit}
    if args.education:
        cols = ['source_record_id', 'canonical_site_id', 'service_code', 'supply_status',
                'np_identity_eligible', 'route_eligible', 'eligible_site_supply']
        ed, audits['education'] = feature_counts(pd.read_parquet(args.education, columns=cols),
            site_column='canonical_site_id', prefix='education_features_',
            admission_columns=['np_identity_eligible', 'route_eligible', 'eligible_site_supply'])
    if args.commerce:
        cols = ['source_record_id', 'canonical_source_site_id', 'service_code', 'supply_status', 'np_identity_eligible', 'route_eligible']
        comm, audits['commerce'] = feature_counts(pd.read_parquet(args.commerce, columns=cols),
            site_column='canonical_source_site_id', prefix='commerce_features_',
            admission_columns=['np_identity_eligible', 'route_eligible'])
    if args.workforce:
        work = pd.read_parquet(args.workforce, columns=['source_record_id', 'partial_organisation_workforce_2025', 'partial_workforce_status'])
    profiles = assemble(pd.read_parquet(args.reference), medical, ed, comm, work)
    profiles, summary = classify(profiles, max_k=args.max_k, bootstrap_repeats=args.bootstrap_repeats)
    examples = []
    for name in CITY_EXAMPLES:
        rows = profiles[profiles.name.eq(name) & profiles.population_2021.notna()]
        if len(rows):
            examples.append(rows.loc[rows.population_2021.idxmax()])
    examples = pd.DataFrame(examples)
    args.output.mkdir(parents=True, exist_ok=True)
    profiles.to_parquet(args.output / 'centrality_profiles.parquet', index=False)
    examples.to_csv(args.output / 'six_city_comparison.csv', index=False)
    summary.update(source_audits=audits, inputs_sha256=before, code_sha256=sha(Path(__file__)))
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    if before != {k: sha(v) for k, v in inputs.items()}:
        raise RuntimeError('Source input changed during analysis')
    print(json.dumps({k: v for k, v in summary.items() if k not in ['bic', 'bootstrap', 'source_audits']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

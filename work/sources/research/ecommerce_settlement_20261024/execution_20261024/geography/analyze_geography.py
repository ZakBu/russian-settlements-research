"""National, descriptive analysis of positive catalogue evidence.

Run from any directory with PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow
python3 analyze_geography.py. Inputs are never modified.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parents[1] / 'national'
COMPARISON = SOURCE / 'ozon_WB_comparison_main_target_experimental.parquet'


def safe_ratio(a, b):
    return float(a / b) if b else None


def aggregate(g):
    pop = g.population_2021
    wb = g.WB_evidence_status.eq('positive')
    oz = g.ozon_pickup_inferred_accepted_5km_count.gt(0)
    either = wb | oz
    out = {'settlements_n': len(g), 'population2021': float(pop.sum()),
           'inhabited2021_n': int(pop.gt(0).sum()),
           'WB_unknown_bridge_n': int(g.WB_evidence_status.str.startswith('unknown').sum())}
    for label, mask in [('WB', wb), ('Ozon', oz), ('either', either), ('both', wb & oz)]:
        out[label + '_positive_np_n'] = int(mask.sum())
        out[label + '_positive_np_share'] = float(mask.mean())
        out[label + '_positive_population2021'] = float(pop[mask].sum())
        out[label + '_positive_population2021_share'] = safe_ratio(pop[mask].sum(), pop.sum())
    out['WB_positive_objects_n'] = int(g.WB_focus20261021_count.fillna(0).sum())
    out['Ozon_pickup_positive_objects_n'] = int(g.ozon_pickup_inferred_accepted_5km_count.sum())
    return out


def grouped(df, cols, filename):
    records = []
    for key, group in df.groupby(cols, observed=True, dropna=False, sort=True):
        if len(cols) == 1:
            key = (key,) if not isinstance(key, tuple) else key
        row = dict(zip(cols, key))
        row.update(aggregate(group))
        records.append(row)
    result = pd.DataFrame(records)
    result.to_csv(OUT / filename, index=False)
    return result


def main():
    small_rows = []
    df = pq.read_table(COMPARISON).to_pandas()
    assert len(df) == 144151
    assert df.source_record_id_2021.is_unique
    assert df.population_2021.notna().all()
    assert df.population_2021.ge(0).all()
    assert df.region_2021.nunique() == 81
    assert df.WB_focus20261021_count.fillna(0).gt(0).equals(df.WB_evidence_status.eq('positive'))
    df['settlement_class'] = np.where(df.type_2021.isin(['город', 'пгт']), 'urban', 'rural')
    df['WB_status'] = df.WB_evidence_status
    df['Ozon_positive_5km'] = df.ozon_pickup_inferred_accepted_5km_count.gt(0)
    national = aggregate(df)
    assert national['WB_positive_np_n'] == 7991
    assert national['Ozon_positive_np_n'] == 16735
    assert national['both_positive_np_n'] == 6415
    by_size = grouped(df, ['size2021'], 'by_size.csv')
    by_class = grouped(df, ['settlement_class'], 'by_class.csv')
    grouped(df, ['type_2021'], 'by_type.csv')
    grouped(df, ['region_2021'], 'by_region.csv')
    grouped(df, ['settlement_class', 'size2021'], 'by_class_size.csv')
    grouped(df, ['platform_category_pickup_5km_baseline'], 'joint_evidence.csv')
    grouped(df, ['WB_status', 'Ozon_positive_5km'], 'joint_with_unknown.csv')
    for name, g in [('all', df), ('rural', df[df.settlement_class.eq('rural')]),
                    ('urban', df[df.settlement_class.eq('urban')])]:
        for cut in [100, 500, 1000, 3000]:
            sub = g[g.population_2021.between(1, cut)]
            row = {'settlement_class': name, 'max_population2021': cut}
            row.update(aggregate(sub))
            small_rows.append(row)
    pd.DataFrame(small_rows).to_csv(OUT / 'small_inhabited.csv', index=False)
    sensitivity = []
    for km in [1, 5, 10]:
        for rule in ['baseline', 'pointshift_sensitivity']:
            wb = df.WB_evidence_status.eq('positive')
            if rule != 'baseline':
                wb = df.WB_evidence_status_sensitivity.eq('positive')
            oz = df[f'ozon_pickup_inferred_accepted_{km}km_count'].gt(0)
            sensitivity.append({'radius_km': km, 'WB_rule': rule,
                'Ozon_positive_np_n': int(oz.sum()), 'WB_positive_np_n': int(wb.sum()),
                'both_positive_np_n': int((oz & wb).sum()),
                'either_positive_np_n': int((oz | wb).sum()),
                'either_positive_population2021': float(df.population_2021[oz | wb].sum()),
                'Ozon_pickup_accepted_objects_n': int(df[f'ozon_pickup_inferred_accepted_{km}km_count'].sum())})
    pd.DataFrame(sensitivity).to_csv(OUT / 'linkage_sensitivity.csv', index=False)
    sensitive_sizes = []
    for (size,), g in df.groupby(['size2021'], observed=True, sort=True):
        for km in [1, 5, 10]:
            wb = g.WB_evidence_status.eq('positive')
            oz = g[f'ozon_pickup_inferred_accepted_{km}km_count'].gt(0)
            sensitive_sizes.append({'size2021': size, 'radius_km': km,
                'settlements_n': len(g), 'either_positive_np_n': int((wb | oz).sum()),
                'either_positive_np_share': float((wb | oz).mean()),
                'Ozon_positive_np_n': int(oz.sum())})
    pd.DataFrame(sensitive_sizes).to_csv(OUT / 'size_linkage_sensitivity.csv', index=False)
    by_size['share_all_settlements'] = by_size.settlements_n / national['settlements_n']
    by_size['share_population2021'] = by_size.population2021 / national['population2021']
    for label in ['WB_positive_objects_n', 'Ozon_pickup_positive_objects_n']:
        by_size['share_' + label] = by_size[label] / by_size[label].sum()
    by_size.to_csv(OUT / 'size_concentration.csv', index=False)
    checks = {'rows': len(df), 'unique_2021_ids': int(df.source_record_id_2021.nunique()),
              'regions': int(df.region_2021.nunique()),
              'group_reconciliation_by_size': int(by_size.settlements_n.sum()) == len(df),
              'group_reconciliation_by_class': int(by_class.settlements_n.sum()) == len(df),
              'expected_positive_counts_verified': True}
    manifest = {'inputs': [], 'method': 'descriptive cross-section, not causal or longitudinal',
                'population_weight': 'own settlement census2021 population, not current2026 customers',
                'WB': '2026-10-21, focus types8/34, bridge-based positive evidence',
                'Ozon': 'third-party declared 2026-08-06, pickup inferred raw_p0, unique exact name within5km',
                'zero': 'no accepted records, not confirmed absence',
                'scope': 'accepted physical credited census2021 records in81 ordinary regions, federal cities separate',
                'national': national, 'checks': checks}
    for path in [COMPARISON]:
        manifest['inputs'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (OUT / 'summary.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({'national': national, 'checks': checks}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

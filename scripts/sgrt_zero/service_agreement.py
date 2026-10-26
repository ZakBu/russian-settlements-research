#!/usr/bin/env python3
"""Audit agreement of three direct service destinations, without assigning SGRT.

The diagnostic separates missing admissible routes from unknown settlement
ownership of a known physical provider. Local supply is a destination at the
origin; it must not disappear from the comparison with external destinations.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from lower_profile_quality import part_inventory, sha256

CORE = ('medical_basic', 'school', 'grocery')
LABELS = {
    'same_external': 'Все три направления — в один другой НП',
    'same_local': 'Все три услуги — в самом НП',
    'two_destinations': 'Три направления — в два НП',
    'three_destinations': 'Три направления — в три НП',
    'unknown_provider_settlement': 'Три направления есть, НП поставщика не везде установлен',
    'partial_admission': 'Допущены только одно или два направления',
    'no_admission': 'Нет допущенных направлений',
}


def analyse(edges, reference):
    core = edges[edges.service_family.isin(CORE)].copy()
    if core.duplicated(['origin_id', 'service_family']).any():
        raise ValueError('Expected one outcome per origin and service family')
    if core.l0_admitted.isna().any():
        raise ValueError('Admission must be explicit, including rejected routes')
    if not core.l0_admitted.isin([True, False]).all():
        raise ValueError('Admission must contain booleans')
    inventory, _ = part_inventory(reference)
    ref = inventory.dropna(subset=['source_record_id']).set_index('source_record_id')
    if not ref.index.is_unique:
        raise ValueError('Reference identities must be unique')
    if not set(core.origin_id) <= set(ref.index):
        raise ValueError('Unmatched origin identity')
    known = core.provider_settlement_id.dropna()
    if not set(known) <= set(ref.index):
        raise ValueError('Unmatched provider identity')
    # The complete scenario, rather than admitted links alone, defines demand.
    family_count = core.groupby('origin_id').service_family.nunique()
    if not family_count.eq(3).all():
        raise ValueError('All three outcomes, including unknowns, are required')
    eligible = (ref.population_role.eq('ordinary_settlement_record')
                & ref.analysis_origin.fillna(False) & ref.population_2021.gt(0)
                & ref.part_status.eq('unmarked_whole_place_record'))
    origins = ref.index[eligible & ref.index.isin(family_count.index)]
    out = ref.loc[origins, ['name', 'region', 'lat', 'lon', 'population_2021',
                            'budget_population_credit']].copy()
    selected = core[core.l0_admitted & core.origin_id.isin(origins)]
    out['admitted_functions'] = selected.groupby('origin_id').size().reindex(origins, fill_value=0)
    out['identified_functions'] = selected.groupby('origin_id').provider_settlement_id.count().reindex(origins, fill_value=0)
    out['distinct_identified_destinations'] = selected.groupby('origin_id').provider_settlement_id.nunique().reindex(origins, fill_value=0)
    out['agreement_class'] = 'partial_admission'
    out.loc[out.admitted_functions.eq(0), 'agreement_class'] = 'no_admission'
    full = out.admitted_functions.eq(3)
    out.loc[full & out.identified_functions.lt(3), 'agreement_class'] = 'unknown_provider_settlement'
    full_known = full & out.identified_functions.eq(3)
    for n, label in [(2, 'two_destinations'), (3, 'three_destinations')]:
        out.loc[full_known & out.distinct_identified_destinations.eq(n), 'agreement_class'] = label
    out['unanimous_destination_id'] = pd.Series(pd.NA, index=out.index, dtype='string')
    same = full_known & out.distinct_identified_destinations.eq(1)
    first = selected.groupby('origin_id').provider_settlement_id.first()
    out.loc[same, 'unanimous_destination_id'] = first.reindex(out.index[same])
    local = out.unanimous_destination_id.eq(out.index.to_series()).fillna(False)
    out.loc[same & local, 'agreement_class'] = 'same_local'
    out.loc[same & ~local, 'agreement_class'] = 'same_external'
    counts = out.agreement_class.value_counts().reindex(LABELS, fill_value=0)
    assert int(counts.sum()) == len(out)
    external = out[out.agreement_class.eq('same_external')]
    summary = {
        'schema': 'sgrt.direct_service_agreement.v1',
        'scope': 'positive ordinary whole settlement records in the complete scenario; population credit is retained, not required',
        'origin_records': len(out),
        'classes': {k: {'label': LABELS[k], 'records': int(v)} for k, v in counts.items()},
        'unanimous_external_destination_count': int(external.unanimous_destination_id.nunique()),
        'observed_trips': False, 'exclusive_sgrt_partition_created': False,
        'local_supply_included_as_origin_destination': True,
        'unknown_provider_settlement_is_not_missing_physical_service': True,
        'partial_admission_is_not_service_absence': True,
    }
    return out.reset_index(names='origin_id'), summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edges', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    columns = ['origin_id', 'service_family', 'provider_settlement_id', 'l0_admitted']
    frame, summary = analyse(pd.read_parquet(args.edges, columns=columns), pd.read_parquet(args.reference))
    args.output.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output / 'service_agreement.parquet', index=False)
    summary['inputs'] = {name: {'file': path.name, 'sha256': sha256(path)}
                         for name, path in [('edges', args.edges), ('reference', args.reference)]}
    summary['code_sha256'] = sha256(Path(__file__))
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()

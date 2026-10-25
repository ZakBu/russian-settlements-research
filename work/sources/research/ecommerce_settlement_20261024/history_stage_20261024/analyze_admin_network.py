"""Network configuration by independently documented administrative context.

No administrative parent is interpreted as an observed shopping catchment.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
KEY = 'source_record_id_2021'


def main():
    core_path = BASE/'national/ozon_WB_comparison_main_target_experimental.parquet'
    context_path = OUT/'centres/settlement_admin_context_main2021.parquet'
    d = pd.read_parquet(core_path)
    c = pd.read_parquet(context_path)
    assert d[KEY].is_unique and c[KEY].is_unique
    assert len(d) == len(c) == 144151
    d = d.merge(c.drop(columns=[x for x in c if x in d and x != KEY]),
                on=KEY, validate='one_to_one')
    assert len(d) == 144151
    lookup = d.set_index(KEY)
    d['wb_positive'] = d.WB_focus20261021_count.gt(0)
    for radius in [1, 5, 10]:
        d[f'either_{radius}km_positive'] = (
            d.wb_positive | d[f'ozon_pickup_inferred_accepted_{radius}km_count'].gt(0))
    roles, systems = [], []
    for vintage in ['20200110', '20211103']:
        known = d[f'context_status_{vintage}'].eq('accepted_administrative_parent_and_centre')
        centre = d[f'admin_centre_positive_{vintage}']
        d['role'] = np.select([centre, known], ['documented_centre', 'other_accepted_member'],
                              default='unknown_context')
        for radius in [1, 5, 10]:
            exposure = f'either_{radius}km_positive'
            for role, g in d.groupby('role'):
                positive = g[exposure]
                roles.append(dict(vintage=vintage, ozon_link_radius_km=radius, role=role,
                                  settlements=len(g), population2021=g.population_2021.sum(),
                                  positive_settlements=int(positive.sum()),
                                  positive_population2021=g.loc[positive, 'population_2021'].sum(),
                                  positive_settlements_pct=100*positive.mean(),
                                  positive_population2021_pct=100*g.loc[positive, 'population_2021'].sum()/g.population_2021.sum()))
        group_col = f'administrative_centre_source_record_id_2021_{vintage}'
        for centre_id, g in d.loc[known].groupby(group_col):
            if centre_id not in lookup.index:
                continue
            centre_row = d.loc[d[KEY].eq(centre_id)].iloc[0]
            others = g.loc[g[KEY].ne(centre_id)]
            inhabited = others.loc[others.population_2021.gt(0)]
            for radius in [1, 5, 10]:
                exposure = f'either_{radius}km_positive'
                centre_positive = bool(centre_row[exposure])
                other_positive_n = int(inhabited[exposure].sum())
                if len(inhabited) == 0:
                    category = 'no_inhabited_other_members_observed'
                elif centre_positive and other_positive_n:
                    category = 'positive_centre_and_other_members'
                elif centre_positive:
                    category = 'positive_centre_no_positive_other_members'
                elif other_positive_n:
                    category = 'positive_other_members_no_positive_centre'
                else:
                    category = 'no_positive_records_in_observed_context'
                systems.append(dict(
                    vintage=vintage, ozon_link_radius_km=radius,
                    centre_source_record_id_2021=centre_id,
                    centre_name=centre_row.name_2021, centre_region=centre_row.region_2021,
                    centre_population2021=centre_row.population_2021,
                    centre_positive=centre_positive,
                    observed_other_members=len(others),
                    observed_inhabited_other_members=len(inhabited),
                    other_population2021=inhabited.population_2021.sum(),
                    positive_inhabited_other_members=other_positive_n,
                    positive_other_population2021=inhabited.loc[inhabited[exposure], 'population_2021'].sum(),
                    observed_municipal_codes=g[f'municipality_oktmo8_{vintage}'].nunique(),
                    category=category,
                ))
    role_table = pd.DataFrame(roles)
    system_table = pd.DataFrame(systems)
    role_table.to_csv(OUT/'admin_roles_network.csv', index=False)
    system_table.to_csv(OUT/'admin_context_network.csv', index=False)
    category = system_table.groupby(['vintage','ozon_link_radius_km','category']).agg(
        centres=('centre_source_record_id_2021','nunique'),
        observed_other_members=('observed_other_members','sum'),
        observed_inhabited_other_members=('observed_inhabited_other_members','sum'),
    ).reset_index()
    category.to_csv(OUT/'admin_context_categories.csv', index=False)
    for (vintage, radius), g in role_table.groupby(['vintage','ozon_link_radius_km']):
        assert g.settlements.sum() == 144151
        assert g.positive_settlements.sum() == int(d[f'either_{radius}km_positive'].sum())
    assert not system_table.duplicated(['vintage','ozon_link_radius_km','centre_source_record_id_2021']).any()
    assert (system_table.positive_inhabited_other_members <= system_table.observed_inhabited_other_members).all()
    summary = {
        'inputs': [{'path': str(p.relative_to(BASE)),
                    'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in [core_path, context_path]],
        'roles2021_5km': role_table.query("vintage == '20211103' and ozon_link_radius_km == 5").to_dict('records'),
        'categories2021_5km': category.query("vintage == '20211103' and ozon_link_radius_km == 5").to_dict('records'),
        'checks': 'PASS: one-to-one merge; all target rows and positive totals reconciled; unique centre contexts; count bounds',
        'limits': [
            'Administrative centres are independently documented proxies, not observed shopping centres.',
            'Contexts contain accepted target members only; incomplete correspondence is explicit.',
            'A shared administrative centre is counted once; its municipal member sets are combined.',
            'No-positive-record categories do not establish absent service.',
            'Network dates2026; administrative contexts2020/2021. This is no network time comparison.',
            'Unchanged administrative codes and names do not establish unchanged boundaries.',
        ],
    }
    (OUT/'admin_network_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k.startswith(('roles','categories'))},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

"""Own-settlement positive pickup evidence outside fixed medium centres.

No access, trips, catchments, opening dates, physical bypass or causal effect is
inferred. Census2021 populations weight 2026 positive catalogue records.
Run from the repository root with .venv-ecommerce/bin/python and pinned bundle.
"""
from pathlib import Path
import hashlib
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'work/ecommerce_dependency_20261026'
BASE = ROOT / 'work/sources/research/ecommerce_settlement_20261024'
KEY = 'source_record_id_2021'
INPUTS = [BASE / 'national/ozon_WB_comparison_main_target_experimental.parquet',
          BASE / 'history_stage_20261024/centres/settlement_admin_context_main2021.parquet',
          BASE / 'settlement_role_stage_20261024/system/centre_system_demography.csv']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    axis, context = [pd.read_parquet(p) for p in INPUTS[:2]]
    system = pd.read_csv(INPUTS[2])
    medium = system.loc[system.medium_primary2002].set_index(KEY)
    assert len(axis) == len(context) == 144151
    assert axis[KEY].is_unique and context[KEY].is_unique
    assert medium.index.is_unique and len(medium) == 1273
    assert set(axis[KEY]) == set(context[KEY])
    comp = axis.set_index(KEY)
    assert axis.population_2021.notna().all() and axis.population_2021.ge(0).all()
    joined = context[[KEY] + [f'{prefix}_{v}'
        for v in ('20200110', '20211103')
        for prefix in ('context_status', 'administrative_centre_source_record_id_2021')]]
    joined = axis.merge(joined, on=KEY, validate='one_to_one')
    all_context_rows, aggregates, regions, pilots = [], [], [], []

    def summarize(frame, params):
        result = dict(params, medium_centres_n=len(frame),
            contexts_with_inhabited_periphery_n=int(frame.periphery_inhabited_n.gt(0).sum()),
            periphery_all_np_n=int(frame.periphery_all_n.sum()),
            periphery_inhabited_np_n=int(frame.periphery_inhabited_n.sum()),
            periphery_population2021=int(frame.periphery_population2021.sum()))
        for source in ('wb', 'ozon', 'either'):
            for field in ('positive_np_n', 'positive_population2021'):
                result[f'{source}_{field}'] = int(frame[f'{source}_{field}'].sum())
            result[f'{source}_contexts_positive_periphery_n'] = int(frame[f'{source}_positive_np_n'].gt(0).sum())
            result[f'{source}_centres_positive_n'] = int(frame[f'{source}_centre_positive'].sum())
            result[f'{source}_contexts_positive_centre_and_periphery_n'] = int((
                frame[f'{source}_centre_positive'] & frame[f'{source}_positive_np_n'].gt(0)).sum())
            result[f'{source}_population2021_share_pct'] = (100 * result[f'{source}_positive_population2021']
                / result['periphery_population2021'] if result['periphery_population2021'] else None)
        for field in ('wb_unknown_np_n', 'wb_unknown_population2021',
                      'neither_positive_np_n', 'neither_positive_population2021'):
            result[field] = int(frame[field].sum())
        assert result['either_positive_np_n'] + result['neither_positive_np_n'] == result['periphery_inhabited_np_n']
        assert result['either_positive_population2021'] + result['neither_positive_population2021'] == result['periphery_population2021']
        return result

    for vintage in ('20200110', '20211103'):
        parent = f'administrative_centre_source_record_id_2021_{vintage}'
        known = joined[f'context_status_{vintage}'].eq('accepted_administrative_parent_and_centre')
        included = joined.loc[known & joined[parent].isin(medium.index)].copy()
        # One source row has one scalar parent. Different vintages never add up.
        assert included[KEY].is_unique
        own = included.loc[included[KEY].eq(included[parent])]
        assert len(own) == 1273 and set(own[KEY]) == set(medium.index)
        assert (included.region_2021.to_numpy() == medium.loc[included[parent], 'region_2021'].to_numpy()).all()
        groups = dict(tuple(included.groupby(parent)))
        # Review three contrasting regions before national aggregation. Every
        # positive pilot row keeps its name/type and known administrative parent.
        for reg in ('тверская', 'краснодарский', 'саха якутия'):
            p = included.loc[included.region_2021.eq(reg)
                & included[KEY].ne(included[parent]) & included.population_2021.gt(0)]
            assert len(p) and p[parent].nunique() > 1
            positive = p.WB_evidence_status.eq('positive') | p.ozon_pickup_inferred_accepted_5km_count.gt(0)
            for row in p.loc[positive].head(5).itertuples(index=False):
                cid = getattr(row, parent)
                pilots.append(dict(vintage=vintage, region=reg, centre_name=medium.at[cid, 'name_2021'],
                    source_record_id_2021=getattr(row, KEY), name=row.name_2021, type=row.type_2021,
                    population2021=int(row.population_2021), wb_status=row.WB_evidence_status,
                    ozon_pickup_records_5km=int(row.ozon_pickup_inferred_accepted_5km_count)))
        for radius in (1, 5, 10):
            for wb_rule in ('baseline', 'pointshift_sensitivity'):
                wb_col = 'WB_evidence_status' + ('_sensitivity' if wb_rule != 'baseline' else '')
                oz_col = f'ozon_pickup_inferred_accepted_{radius}km_count'
                params = dict(vintage=vintage, ozon_identity_radius_km=radius, wb_rule=wb_rule)
                rows = []
                for cid, centre in medium.iterrows():
                    g = groups[cid]
                    outside_all = g.loc[g[KEY].ne(cid)]
                    outside = outside_all.loc[outside_all.population_2021.gt(0)]
                    wb, oz = outside[wb_col].eq('positive'), outside[oz_col].gt(0)
                    either = wb | oz
                    unknown = outside[wb_col].str.startswith('unknown')
                    record = dict(params, centre_id=cid, centre_name=centre.name_2021,
                        region=centre.region_2021, periphery_all_n=len(outside_all),
                        periphery_inhabited_n=len(outside),
                        periphery_population2021=int(outside.population_2021.sum()),
                        wb_unknown_np_n=int(unknown.sum()),
                        wb_unknown_population2021=int(outside.loc[unknown, 'population_2021'].sum()),
                        neither_positive_np_n=int((~either).sum()),
                        neither_positive_population2021=int(outside.loc[~either, 'population_2021'].sum()))
                    for name, mask in [('wb', wb), ('ozon', oz), ('either', either)]:
                        record[f'{name}_positive_np_n'] = int(mask.sum())
                        record[f'{name}_positive_population2021'] = int(outside.loc[mask, 'population_2021'].sum())
                    record['wb_centre_positive'] = bool(comp.at[cid, wb_col] == 'positive')
                    record['ozon_centre_positive'] = bool(comp.at[cid, oz_col] > 0)
                    record['either_centre_positive'] = record['wb_centre_positive'] or record['ozon_centre_positive']
                    rows.append(record)
                frame = pd.DataFrame(rows)
                assert frame.periphery_all_n.sum() + 1273 == len(included)
                assert frame.periphery_population2021.sum() == included.loc[included[KEY].ne(included[parent]), 'population_2021'].sum()
                all_context_rows.append(frame)
                aggregates.append(summarize(frame, params))
                for reg, rg in frame.groupby('region'):
                    regions.append(summarize(rg, dict(params, region=reg)))
    pd.concat(all_context_rows, ignore_index=True).to_csv(OUT/'national_options_contexts.csv', index=False)
    pd.DataFrame(aggregates).to_csv(HERE/'national_options_summary.csv', index=False)
    pd.DataFrame(regions).to_csv(HERE/'national_options_regions.csv', index=False)
    pd.DataFrame(pilots).to_csv(HERE/'national_options_pilot_examples.csv', index=False)
    # Article cases are linked to the existing analytical frame only. This does
    # not establish that the administratively named centre was the shopping
    # destination in an interview; that requires the article's own evidence.
    cases = []
    for name, region in [('Кубань', 'липецкая'), ('Большие Чапурники', 'волгоградская'),
                         ('Большой Мартын', 'воронежская'), ('Красный Холм', 'тверская')]:
        found = axis.loc[axis.name_2021.eq(name) & axis.region_2021.eq(region)]
        if name == 'Красный Холм':
            found = found.loc[found.type_2021.eq('город')]
        assert len(found) == 1
        node = found.iloc[0]
        ctx = context.set_index(KEY).loc[node[KEY]]
        for vintage in ('20200110', '20211103'):
            cid = ctx[f'administrative_centre_source_record_id_2021_{vintage}']
            centre = comp.loc[cid] if cid in comp.index else None
            cases.append(dict(case_name=name, region=region, source_record_id_2021=node[KEY],
                vintage=vintage, context_status=ctx[f'context_status_{vintage}'],
                centre_id=cid, centre_name=centre.name_2021 if centre is not None else None,
                centre_population2002=centre.population_2002 if centre is not None else None,
                centre_in_predefined_1273=cid in medium.index,
                warning='Administrative parent is not observed shopping destination'))
    pd.DataFrame(cases).to_csv(HERE/'case_administrative_links.csv', index=False)
    manifest = dict(inputs=[dict(path=str(p.relative_to(ROOT)), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                            for p in INPUTS],
        method='own-settlement positive pickup records in fixed administrative frames, not customer access or flows',
        population='fixed census2021 counts, not residents2026 or pickup users',
        network_dates={'WB':'2026-10-21', 'Ozon':'third-party declared 2026-08-06'},
        unknown='WB linkage unknown retained; no positive record is not proven absence for either platform',
        geography='accepted census-source 81-region frame; each context vintage separately; no boundary continuity claim',
        source_semantics='WB accepted types8/34; Ozon third-party p=0 inferred pickup, no lockers',
        details='work/ecommerce_dependency_20261026/national_options_contexts.csv')
    (HERE/'national_options_inputs.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(pd.DataFrame(aggregates).loc[lambda x: (x.ozon_identity_radius_km.eq(5)&x.wb_rule.eq('baseline'))].to_string(index=False))


if __name__ == '__main__':
    main()

"""Potential straight-line proximity, never customer flows or treatment effects."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent.parent / 'national' / 'nearest_marketplaces_experimental.parquet'


def main():
    d = pq.read_table(SOURCE).to_pandas()
    assert len(d) == 144149
    assert d.source_record_id.is_unique
    assert d.effective_population.notna().all()
    assert (d.effective_population >= 0).all()
    wb = 'nearest_linked_wb_straight_km'
    oz = 'nearest_experimental_ozon_straight_km'
    both = 'nearest_either_straight_km_experimental'
    assert np.isfinite(d[[wb, oz, both]]).all().all()
    assert np.allclose(d[both], np.minimum(d[wb], d[oz]))
    d = d[d.effective_population > 0].copy()
    assert len(d) == 123137
    rows = []

    def summarize(frame, dimension, group):
        pop = frame.effective_population.sum()
        for radius in (5, 10, 20):
            near_wb = frame[wb] <= radius
            near_either = frame[both] <= radius
            added = near_either & ~near_wb
            rows.append(dict(
                dimension=dimension, group=str(group), radius_km=radius,
                inhabited_settlements=len(frame), census_population2021=float(pop),
                wb_near_settlements=int(near_wb.sum()),
                either_near_settlements=int(near_either.sum()),
                additional_near_settlements=int(added.sum()),
                wb_near_population=float(frame.loc[near_wb, 'effective_population'].sum()),
                either_near_population=float(frame.loc[near_either, 'effective_population'].sum()),
                additional_near_population=float(frame.loc[added, 'effective_population'].sum()),
                wb_near_np_pct=float(100 * near_wb.mean()),
                either_near_np_pct=float(100 * near_either.mean()),
                wb_near_population_pct=float(100 * frame.loc[near_wb, 'effective_population'].sum() / pop),
                either_near_population_pct=float(100 * frame.loc[near_either, 'effective_population'].sum() / pop),
            ))

    summarize(d, 'national', 'accepted_81_regions_inhabited_with_coordinates')
    for field in ('size_2021', 'region_norm'):
        for group, frame in d.groupby(field, observed=True):
            summarize(frame, field, group)
    result = pd.DataFrame(rows)
    assert (result.either_near_settlements >= result.wb_near_settlements).all()
    assert (result.either_near_population <= result.census_population2021).all()
    result.to_csv(OUT / 'proximity_thresholds.csv', index=False)
    national = result[result.dimension == 'national']
    summary = dict(
        source=str(SOURCE.relative_to(OUT.parent.parent)),
        source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        input_rows=144149, inhabited_rows=len(d),
        population2021=float(d.effective_population.sum()),
        median_wb_km=float(d[wb].median()),
        median_either_km=float(d[both].median()),
        thresholds=national.to_dict('records'),
        checks=['unique source_record_id', 'nonnegative population',
                'finite distances', 'either=min(WB,Ozon)',
                'threshold inclusion and population bounds'],
        limitations=[
            'Accepted comparable source territory: 81 ordinary regions; federal cities excluded as targets.',
            'Distances to known accepted points only, measured in straight line from settlement reference points.',
            'WB snapshot2026-10-21 versus unofficial Ozon archive declared2026-08-06: unequal sources and dates.',
            'Adding Ozon to the observed point set is an arithmetic scenario, not a temporal improvement or causal effect.',
            'Population weights are census2021; no claim about resident counts in2026.',
            'No road routing, actual trips, service quality or real catchments measured.',
        ],
    )
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    lines = [
        'Потенциальная близость к известным точкам: национальный расчёт',
        f'Знаменатель: {len(d):,} населённых НП с координатами; население2021={d.effective_population.sum():,.0f}.',
        f'Медиана расстояния: WB {d[wb].median():.3f} км; объединённый набор {d[both].median():.3f} км.',
    ]
    for r in national.to_dict('records'):
        lines.append(
            f"До {r['radius_km']} км: НП WB={r['wb_near_np_pct']:.2f}%, объединённый набор={r['either_near_np_pct']:.2f}%; "
            f"жители2021 WB={r['wb_near_population_pct']:.2f}%, объединённый={r['either_near_population_pct']:.2f}%."
        )
    lines.extend(summary['limitations'])
    (OUT / 'findings.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines[:6]))


if __name__ == '__main__':
    main()

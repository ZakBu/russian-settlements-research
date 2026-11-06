"""Residents' modelled cashless spending exposure; municipal, unweighted summaries."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RAW = ROOT / 'work/ecommerce_national_20261106/sber'
EXPECTED = '9833ddaaee7b2a182ed4cceeed16469031700ea87d508bd976150c6770ef8a61'
assert hashlib.sha256((RAW / 'consumption.parquet').read_bytes()).hexdigest() == EXPECTED
d = pd.read_parquet(RAW / 'consumption.parquet')
dictionary = pd.read_excel(RAW / 'dictionary.xlsx')
categories = {'Продовольствие', 'Здоровье', 'Маркетплейсы', 'Общественное питание', 'Транспорт', 'Все категории'}
months = set(pd.period_range('2023-01', '2024-12', freq='M').astype(str))
keys = ['territory_id', 'date', 'category']
assert set(d.category) == categories and set(d.date) == months
assert not d.duplicated(keys).any() and not d.isna().any().any()
assert np.isfinite(d.value).all() and (d.value >= 0).all()
per_month = d.groupby(['territory_id', 'date']).category.agg(lambda x: set(x))
assert per_month.map(lambda x: x == categories).all()
wide = d.pivot(index=['territory_id', 'date'], columns='category', values='value')
assert (wide['Все категории'] > 0).all()
assert (wide['Маркетплейсы'] <= wide['Все категории']).all()
assert (wide.drop(columns='Все категории').sum(axis=1) <= wide['Все категории']).all()
counts = d.groupby('territory_id').agg(months_observed=('date', 'nunique'), rows=('value', 'size'))
balanced_ids = counts.index[(counts.months_observed == 24) & (counts.rows == 144)]
assert len(balanced_ids) == 2016
current = dictionary[(dictionary.year_from <= 2024) & (dictionary.year_to > 2024)].copy()
assert not current.territory_id.duplicated().any()
assert set(balanced_ids) <= set(current.territory_id)
assert dictionary.groupby('territory_id').region_code.nunique().max() == 1
mapping = current[['territory_id', 'region_code', 'region_name', 'municipal_district_name_short', 'municipal_district_type', 'oktmo']]

# Prespecified regional pilot runs before the all-municipality summary.
pilot_regions = [69, 23, 52]
pilot = mapping[mapping.region_code.isin(pilot_regions)]
manual_ids = [2120, 2121, 1532, 1546, 1553]
checks = []
for tid in manual_ids:
    for year in [2023, 2024]:
        rows = d[(d.territory_id == tid) & d.date.str.startswith(str(year))]
        all_values = rows[rows.category == 'Все категории'].sort_values('date').value.tolist()
        market_values = rows[rows.category == 'Маркетплейсы'].sort_values('date').value.tolist()
        assert len(all_values) == len(market_values) == 12
        # Independent row-list sums, retained with all twelve input values.
        checks.append(dict(territory_id=tid, year=year,
            monthly_all_values=';'.join(map(str, all_values)),
            monthly_marketplace_values=';'.join(map(str, market_values)),
            sum_all=sum(all_values), sum_marketplace=sum(market_values),
            share_pct=100 * sum(market_values) / sum(all_values)))
checks = pd.DataFrame(checks).merge(mapping, on='territory_id', validate='many_to_one')
checks.to_csv(OUT / 'pilot_manual_checks.csv', index=False)
d[d.territory_id.isin(manual_ids)].sort_values(keys).to_csv(OUT / 'pilot_five_municipalities_monthly.csv', index=False)

balanced = d[d.territory_id.isin(balanced_ids)].copy()
balanced['year'] = balanced.date.str[:4].astype(int)
annual = balanced.groupby(['territory_id', 'year', 'category']).value.sum().unstack('category')
annual['marketplace_ratio'] = annual['Маркетплейсы'] / annual['Все категории']
annual['non_marketplace_nominal_rub'] = annual['Все категории'] - annual['Маркетплейсы']
for r in checks.itertuples():
    q = annual.loc[(r.territory_id, r.year)]
    assert q['Все категории'] == r.sum_all and q['Маркетплейсы'] == r.sum_marketplace
    assert abs(100*q.marketplace_ratio-r.share_pct) < 1e-10
final = pd.DataFrame(index=balanced_ids)
final.index.name = 'territory_id'
for year in [2023, 2024]:
    y = annual.xs(year, level='year')
    final[f'all_model_monthly_means_sum_{year}_rub'] = y['Все категории']
    final[f'marketplace_model_monthly_means_sum_{year}_rub'] = y['Маркетплейсы']
    final[f'marketplace_ratio_{year}'] = y.marketplace_ratio
    final[f'non_marketplace_nominal_model_means_sum_{year}_rub'] = y.non_marketplace_nominal_rub
final['marketplace_ratio_change_pp'] = 100*(final.marketplace_ratio_2024-final.marketplace_ratio_2023)
final['non_marketplace_nominal_change_pct'] = 100*(final.non_marketplace_nominal_model_means_sum_2024_rub / final.non_marketplace_nominal_model_means_sum_2023_rub-1)
final['all_nominal_change_pct'] = 100*(final.all_model_monthly_means_sum_2024_rub / final.all_model_monthly_means_sum_2023_rub-1)
final['marketplace_nominal_change_pct'] = 100*(final.marketplace_model_monthly_means_sum_2024_rub / final.marketplace_model_monthly_means_sum_2023_rub-1)
final = final.reset_index().merge(mapping, on='territory_id', validate='one_to_one')
final.to_csv(OUT / 'balanced_municipal_annual.csv', index=False)

def summarize(frame, name):
    r = {'group': name, 'n_municipalities': len(frame)}
    for year in [2023, 2024]:
        v = frame[f'marketplace_ratio_{year}']*100
        for q in [.1, .25, .5, .75, .9]:
            r[f'share_{year}_pct_q{int(q*100)}'] = v.quantile(q) if len(v) else None
    for q in [.1, .25, .5, .75, .9]:
        r[f'share_change_pp_q{int(q*100)}'] = frame.marketplace_ratio_change_pp.quantile(q) if len(frame) else None
    r['share_increased_n'] = int((frame.marketplace_ratio_change_pp > 1e-12).sum())
    r['share_decreased_n'] = int((frame.marketplace_ratio_change_pp < -1e-12).sum())
    r['share_unchanged_n'] = len(frame)-r['share_increased_n']-r['share_decreased_n']
    r['nonmarketplace_nominal_increased_n'] = int((frame.non_marketplace_nominal_change_pct > 1e-12).sum())
    r['nonmarketplace_nominal_decreased_n'] = int((frame.non_marketplace_nominal_change_pct < -1e-12).sum())
    r['nonmarketplace_nominal_growth_median_pct'] = frame.non_marketplace_nominal_change_pct.median() if len(frame) else None
    r['aggregation'] = 'equal weight per observed municipality; NOT national resident weighted spending share'
    return r

summaries = [summarize(final, 'all_balanced')]
for code in pilot_regions:
    summaries.append(summarize(final[final.region_code == code], f'pilot_region_{code}'))
for (code, name), group in final.groupby(['region_code', 'region_name']):
    summaries.append(summarize(group, f'{code}: {name}'))
pd.DataFrame(summaries).to_csv(OUT / 'municipality_distribution_summary.csv', index=False)
coverage = []
observed = set(d.territory_id)
for (code, name), rows in current.groupby(['region_code', 'region_name']):
    ids = set(rows.territory_id)
    coverage.append(dict(region_code=code, region_name=name,
        reference_dictionary_2024_n=len(ids), any_month_observed_n=len(ids & observed),
        balanced_24months_n=len(ids & set(balanced_ids)),
        fraction_balanced_of_dictionary=len(ids & set(balanced_ids))/len(ids)))
pd.DataFrame(coverage).to_csv(OUT / 'regional_coverage.csv', index=False)
counts.reset_index().to_csv(OUT / 'months_observed_by_municipality.csv', index=False)
quality = {'raw_rows': len(d), 'raw_columns': d.columns.tolist(), 'raw_date_min': d.date.min(),
    'raw_date_max': d.date.max(), 'observed_territories_n': d.territory_id.nunique(),
    'territory_months_n': len(wide), 'balanced_territories_n': len(balanced_ids),
    'incomplete_observed_territories_n': int(d.territory_id.nunique()-len(balanced_ids)),
    'balanced_rows': len(balanced), 'balanced_expected_rows': 2016*24*6,
    'raw_duplicate_keys_n': int(d.duplicated(keys).sum()), 'missing_values_n': int(d.isna().sum().sum()),
    'monthly_all_nonpositive_n': int((wide['Все категории'] <= 0).sum()),
    'marketplace_exceeds_all_n': int((wide['Маркетплейсы'] > wide['Все категории']).sum()),
    'known_category_sum_exceeds_all_n': int((wide.drop(columns='Все категории').sum(axis=1)>wide['Все категории']).sum()),
    'current_dictionary_rows': len(current), 'balanced_dictionary_orphans_n': 0,
    'regions_with_no_observed_rows': [r for r in coverage if r['any_month_observed_n']==0],
    'schema_note': 'Description calls the measure consumption; actual Parquet column is value.',
    'unit': 'modelled mean cashless monthly spending of residents, rubles; summing means does not yield total municipal spending',
    'period': 'monthly observations; annual ratio is SUM monthly marketplace model means / SUM monthly all-category model means',
    'limitations': ['not WB/Ozon-specific', 'cashless model, not all household expenditure',
        'no national population or spending weights applied', 'unknown source quality thresholds and missingness mechanism',
        'no merchant locations or OD flows', 'no shape-based centre/periphery classification',
        'nominal residual all-minus-marketplace is not physical consumption or local shops turnover']}
(OUT / 'quality.json').write_text(json.dumps(quality, ensure_ascii=False, indent=2,
    default=lambda x: x.item() if isinstance(x, np.generic) else str(x))+'\n')
print(json.dumps(summaries[:4], ensure_ascii=False, indent=2))

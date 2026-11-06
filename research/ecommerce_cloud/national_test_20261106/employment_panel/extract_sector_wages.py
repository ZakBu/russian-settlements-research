"""Extract wage levels, preserving cumulative periods; never infer worker counts."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RAW = ROOT / 'work/ecommerce_national_20261106/employment_panel/raw'
PARQUET = RAW / 'sber_bdmo_salary.parquet'
EXPECTED_SHA = 'f9a8956ad68c7ec81fac7b2e61ac2494b02b489887ce06204621b5dff29e62f2'
assert hashlib.sha256(PARQUET.read_bytes()).hexdigest() == EXPECTED_SHA
COMMIT = '2688b801792b7d43e4f460d7004bccac374960d2'
URL = f'https://raw.githubusercontent.com/TrueSpearmint/sberindex_hackathon/{COMMIT}/data_in/sberindex/4_bdmo_salary.parquet'
frame = pd.read_parquet(PARQUET)
keys = ['territory_id', 'year', 'period', 'okved_letter']
duplicates = frame[frame.duplicated(keys, keep=False)]
conflicts = (duplicates.groupby(keys).value.nunique() > 1).sum()
assert conflicts == 0
dictionary = pd.read_excel(ROOT / 'work/ecommerce_national_20261106/sber/dictionary.xlsx')
selected_dictionary = dictionary[(dictionary.region_code == 68) & dictionary.municipal_district_name_short.isin(['Котовск', 'Кирсанов', 'Моршанск'])]
assert selected_dictionary.territory_id.nunique() == 3 and len(selected_dictionary) == 3
selected_dictionary.to_csv(OUT / 'salary_territory_dictionary.csv', index=False)
selected = frame[frame.territory_id.isin(selected_dictionary.territory_id) & frame.okved_letter.isin(['0', 'G', 'H'])].copy()
assert not selected.duplicated(keys).any()
assert len(selected) == 3 * 2 * 4 * 3 and selected.value.notna().all()
selected = selected.merge(selected_dictionary[['territory_id', 'oktmo', 'municipal_district_name_short']], on='territory_id', validate='many_to_one')
selected['indicator'] = 'monthly_nominal_wage_excluding_sme'
selected['units'] = 'рублей в месяц'
selected['period_semantics'] = 'накопленный период с начала года; НЕ отдельный квартал'
selected['source_url'] = URL
selected['source_sha256'] = EXPECTED_SHA
selected = selected.sort_values(['territory_id', 'okved_letter', 'year', 'period'])
selected.to_csv(OUT / 'sector_wages_ytd_2023_2024.csv', index=False)
a = selected[selected.year == 2023].rename(columns={'value': 'value_2023'})
b = selected[selected.year == 2024].rename(columns={'value': 'value_2024'})
changes = a.merge(b, on=['territory_id', 'period', 'okved_letter'], validate='one_to_one', suffixes=('', '_later'))
changes['change_pct'] = 100 * (changes.value_2024 / changes.value_2023 - 1)
changes = changes[['territory_id', 'municipal_district_name_short', 'period', 'okved_letter', 'okved_name', 'value_2023', 'value_2024', 'change_pct']]
changes.to_csv(OUT / 'sector_wage_same_period_changes.csv', index=False)
books = pd.read_csv(OUT / 'employment_wage_panel.csv')
books = books[(books.indicator == 'nominal_monthly_wage_rub') & books.year.isin([2023, 2024])]
annual = selected[(selected.okved_letter == '0') & (selected.period == 'январь-декабрь')]
reconcile = annual.merge(books, left_on=['municipal_district_name_short', 'year'], right_on=['city', 'year'], suffixes=('_mirror', '_book'), validate='one_to_one')
reconcile['difference_rub'] = reconcile.value_mirror - reconcile.value_book
reconcile['difference_pct'] = 100 * (reconcile.value_mirror / reconcile.value_book - 1)
reconcile[['city', 'year', 'value_mirror', 'value_book', 'difference_rub', 'difference_pct', 'source_url_mirror', 'source_url_book']].to_csv(OUT / 'salary_book_reconciliation.csv', index=False)
quality = {'raw_rows': len(frame), 'duplicate_excess_rows': int(frame.duplicated(keys).sum()),
    'rows_on_duplicate_keys': len(duplicates), 'conflicting_duplicate_keys': int(conflicts),
    'selected_rows': len(selected), 'selected_expected_rows': 72, 'selected_duplicate_excess': 0,
    'selected_missing_values': int(selected.value.isna().sum()),
    'period_values': sorted(frame.period.unique().tolist()),
    'inference': 'Wage levels only; cumulative periods; no weighted annualization, worker counts or employment shares inferred.',
    'mirror_status': 'third-party repository mirror of a SberIndex hackathon dataset attributed to Rosstat; not directly fetched Rosstat',
    'commit': COMMIT, 'url': URL, 'sha256': EXPECTED_SHA,
    'reconciliation': 'Small annual differences retained as distinct source vintages; not overwritten.'}
(OUT / 'sector_wage_quality.json').write_text(json.dumps(quality, ensure_ascii=False, indent=2) + '\n')
print(changes[changes.period == 'январь-декабрь'].to_string(index=False))

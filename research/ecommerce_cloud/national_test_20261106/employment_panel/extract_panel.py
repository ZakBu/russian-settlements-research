"""Extract explicit indexed primary tables; do not impute unavailable sectors or years."""
from pathlib import Path
from html import unescape
import csv
import json
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RAW = ROOT / 'work/ecommerce_national_20261106/employment_panel/raw'
CITIES = ['Котовск', 'Кирсанов', 'Моршанск']
observations = []

def clean(s):
    return unescape(re.sub('<[^>]*>', '', s)).strip()

def add_rows(rows, years, indicator, url, edition, raw_file):
    for city, values in rows:
        if city not in CITIES:
            continue
        assert len(values) == len(years), (city, values, years)
        for year, value in zip(years, values):
            observations.append(dict(city=city, year=int(year), indicator=indicator,
                value=float(value.replace(',', '.')), source_url=url,
                edition=edition, raw_file=str(raw_file.relative_to(ROOT))))

for filename in ['employment_search_extracts.json', 'employment_scope_extract.json',
                 'wage_search_extracts.json', 'scope_search_extracts.json']:
    raw_file = RAW / filename
    result = json.loads(raw_file.read_text())
    text = '\n'.join(x.get('text', '') for x in result['content'])
    for section in text.split('--------------------------------------------------------------------------------'):
        urls = re.findall(r'https://68\.rosstat\.gov\.ru/storage/mediabank/[^\s)]+', section)
        if not urls:
            continue
        url = urls[0]
        basename = unquote(url.rsplit('/', 1)[-1])
        if basename not in ['RG2022.pdf', 'RG_2024.pdf', 'Rg_2023.pdf', 'СБОРНИК МО_2025.pdf', 'rg_2021.pdf']:
            continue
        indicator = 'employees_excl_sme' if 'СРЕДНЕСПИСОЧНАЯ' in section else 'nominal_monthly_wage_rub'
        edition = {'RG2022.pdf': 2022, 'RG_2024.pdf': 2024, 'Rg_2023.pdf': 2023,
                   'СБОРНИК МО_2025.pdf': 2025, 'rg_2021.pdf': 2021}[basename]
        tables = re.findall(r'<table[^>]*>(.*?)</table>', section, flags=re.S)
        # Truncated index fragments can end before closing </table>.
        if not tables and '<table' in section:
            tables = [section.split('<table', 1)[1]]
        for table in tables:
            years = []
            rows = []
            for tr in re.findall(r'<tr>(.*?)</tr>', table, flags=re.S):
                cells = [clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, flags=re.S)]
                if not years:
                    years = [x for x in cells if re.fullmatch('20[0-9]{2}', x)]
                elif cells and cells[0] in CITIES and len(cells) == len(years) + 1:
                    rows.append((cells[0], cells[1:]))
            if years:
                add_rows(rows, years, indicator, url, edition, raw_file)
        if not tables:
            header = re.search(r'\|\s*(201[0-9])\s*\|\s*(201[0-9]|202[0-9])\s*\|[^\n]+', section)
            if not header:
                continue
            years = re.findall(r'20[0-9]{2}', header.group())
            rows = []
            for city in CITIES:
                matches = re.findall(r'^' + city + r'\s*\|\s*([^\n]+)', section, flags=re.M)
                if matches:
                    values = [x.strip() for x in matches[-1].split('|')]
                    if len(values) == len(years) and all(re.fullmatch(r'[0-9]+(?:,[0-9]+)?', x) for x in values):
                        rows.append((city, values))
            add_rows(rows, years, indicator, url, edition, raw_file)

assert observations, 'No table rows extracted'
# Repeated search queries are acquisition duplicates, not extra vintage checks.
by_edition = {}
for row in observations:
    key = row['city'], row['year'], row['indicator'], row['edition'], row['source_url']
    if key in by_edition:
        assert abs(by_edition[key]['value'] - row['value']) < .001
    by_edition[key] = row
observations = list(by_edition.values())
unique = {}
for row in observations:
    key = row['city'], row['year'], row['indicator']
    if key in unique:
        assert abs(unique[key]['value'] - row['value']) < .001, (key, unique[key], row)
    if key not in unique or row['edition'] > unique[key]['edition']:
        unique[key] = row

with (OUT / 'observations_by_edition.csv').open('w') as f:
    writer = csv.DictWriter(f, lineterminator='\n', fieldnames=list(observations[0]))
    writer.writeheader(); writer.writerows(observations)
cohort_path = ROOT / 'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024/system/centre_system_demography.csv'
with cohort_path.open() as f:
    cohort = {r['name_2021']: r for r in csv.DictReader(f)
              if r['region_2021'] == 'тамбовская' and r['name_2021'] in CITIES}
panel = []
for city in CITIES:
    for year in range(2017, 2025):
        for indicator in ['employees_excl_sme', 'nominal_monthly_wage_rub']:
            row = unique[(city, year, indicator)].copy()
            row.update(source_record_id_2021=cohort[city]['source_record_id_2021'],
                medium_primary2002=cohort[city]['medium_primary2002'],
                geography='городской округ; не автоматически город в исторических границах',
                units='человек: среднее за год' if indicator == 'employees_excl_sme' else 'рублей в месяц: номинальная начисленная',
                coverage='организации без субъектов малого предпринимательства',
                extraction_status='explicit_table_from_primary_pdf_search_index; full_pdf_unavailable')
            panel.append(row)
with (OUT / 'employment_wage_panel.csv').open('w') as f:
    writer = csv.DictWriter(f, lineterminator='\n', fieldnames=list(panel[0]))
    writer.writeheader(); writer.writerows(panel)
changes = []
for city in CITIES:
    for indicator in ['employees_excl_sme', 'nominal_monthly_wage_rub']:
        for start, end in [(2017, 2022), (2022, 2023), (2023, 2024), (2017, 2024)]:
            a, b = unique[(city, start, indicator)]['value'], unique[(city, end, indicator)]['value']
            changes.append(dict(city=city, indicator=indicator, start=start, end=end,
                start_value=a, end_value=b, change=b-a, change_pct=100*(b/a-1),
                interpretation='descriptive_only; no treatment or control assigned'))
with (OUT / 'changes.csv').open('w') as f:
    writer = csv.DictWriter(f, lineterminator='\n', fieldnames=list(changes[0]))
    writer.writeheader(); writer.writerows(changes)
print(json.dumps({'panel_rows': len(panel), 'edition_observations': len(observations),
    'overlapping_observations_matching': len(observations)-len(unique),
    'cities': CITIES, 'years': [2017, 2024]}, ensure_ascii=False))

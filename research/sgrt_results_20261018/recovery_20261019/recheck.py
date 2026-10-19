"""Recheck preserved inputs and RFSD archive after the workspace restart."""
import hashlib
import json
from pathlib import Path
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
ARCHIVE = ROOT / 'SGRT_RFSD_RECOVERED.zip'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

panel = pd.read_csv(SOURCE, low_memory=False)
assert sha(SOURCE) == 'd40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c'
assert panel.shape == (142570, 135)
assert panel.entity_uid.is_unique
population = []
for year in (2002, 2010, 2021):
    values = pd.to_numeric(panel[f'population_{year}'], errors='raise')
    assert values.notna().all() and (values >= 0).all()
    population.append(dict(year=year, rows=len(values), population=int(values.sum()), zeros=int(values.eq(0).sum())))
pd.DataFrame(population).to_csv(ROOT/'population_rechecked.csv', index=False)
assert sha(ARCHIVE) == 'a1f4cf310b3fac8d0fd5cf2375e203ed7c589fbef7cabe05a52e7ab2fb33a6ef'
with zipfile.ZipFile(ARCHIVE) as z:
    assert z.testzip() is None
    provenance = json.loads(z.read('coverage_provenance.json'))
    years = []
    for row in provenance:
        assert row['status'] == 'ok'
        assert row['source_sha256'] == row['source_expected_sha256']
        assert row['bytes_transferred'] == row['source_expected_bytes']
        years.append({'year':row['year'], **row['coverage'], 'source_sha256':row['source_sha256']})
    assert sorted(r['year'] for r in years) == [2017,2018,2019,2020,2022,2023,2024,2025]
    pd.DataFrame(years).to_csv(ROOT/'rfsd_recovered_years.csv', index=False)
result = dict(status='PASS', source_sha256=sha(SOURCE), source_shape=list(panel.shape), population=population,
              rfsd_archive_sha256=sha(ARCHIVE), rfsd_archive_bytes=ARCHIVE.stat().st_size,
              rfsd_years=[r['year'] for r in years], organization_year_rows=sum(r['rows'] for r in years),
              scope='Recovered partial outputs only; final report, final membership and final typology have not been recovered.')
(ROOT/'RECHECK.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))

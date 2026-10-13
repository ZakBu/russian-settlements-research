#!/usr/bin/env python3
"""Read-only census inventory: no accepted direct point, distinct from scope coverage."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import duckdb

from build_long_table import ACCEPTED_COORDINATE_STATUSES

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / 'research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/graph29_ozherele_historical_points_20261005/config_graph29.json'


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def rows(con, sql):
    result = con.execute(sql)
    return [dict(zip([d[0] for d in result.description], r)) for r in result.fetchall()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    out = parser.parse_args().out
    if out.exists():
        raise FileExistsError('Use a new output directory')
    cfg = json.loads(CONFIG.read_text())
    inputs = {'selected': cfg['selected_observations'], 'points': cfg['working_point_uses'], 'scope_residual': cfg['residual']}
    hashes = {'selected': cfg['sha256']['selected_observations'], 'points': cfg['sha256']['point_uses'], 'scope_residual': cfg['sha256']['residual']}
    for k, p in inputs.items():
        assert sha(p) == hashes[k], k
    con = duckdb.connect()
    for k, p in inputs.items():
        con.read_parquet(p).create_view(k)
    allow = ','.join("'" + x + "'" for x in sorted(ACCEPTED_COORDINATE_STATUSES))
    con.execute(f'CREATE VIEW accepted_points AS SELECT * FROM points WHERE coordinate_admission_status IN ({allow})')
    assert con.execute('SELECT count(*),count(distinct target_source_record_id) FROM accepted_points').fetchone() == (428182,428182)
    assert con.execute('SELECT count(*) FROM accepted_points p ANTI JOIN selected s ON p.target_source_record_id=s.source_record_id').fetchone()[0] == 0
    assert con.execute('SELECT count(*) FROM accepted_points WHERE latitude IS NULL OR longitude IS NULL OR NOT(latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)').fetchone()[0] == 0
    con.execute('''CREATE TEMP TABLE unpointed AS SELECT s.*,
        coalesce(s.population_scope='federal_city_region',false)
        OR (s.region_norm=s.name_norm AND s.name_norm IN ('москва','санкт петербург','севастополь')) AS federal_aggregate,
        r.source_record_id IS NOT NULL AS in_frozen_scope_residual
        FROM selected s ANTI JOIN accepted_points p ON s.source_record_id=p.target_source_record_id
        LEFT JOIN scope_residual r USING(source_record_id)''')
    summary = rows(con, '''SELECT census_year,count(*) all_selected_rows_without_direct_point,
        sum(population) all_selected_population_without_direct_point,
        count(*) FILTER(WHERE NOT federal_aggregate) np_rows_without_direct_point,
        sum(population) FILTER(WHERE NOT federal_aggregate) np_population_without_direct_point,
        count(*) FILTER(WHERE NOT federal_aggregate AND in_frozen_scope_residual) np_unpointed_rows_in_scope_residual,
        sum(population) FILTER(WHERE NOT federal_aggregate AND in_frozen_scope_residual) np_unpointed_population_in_scope_residual,
        count(*) FILTER(WHERE NOT federal_aggregate AND population>=10000) np_unpointed_rows_ge10000,
        count(*) FILTER(WHERE NOT federal_aggregate AND population>=2000) np_unpointed_rows_ge2000,
        count(*) FILTER(WHERE NOT federal_aggregate AND population=0) np_unpointed_zero_population_rows,
        count(*) FILTER(WHERE NOT federal_aggregate AND population IS NULL) np_unpointed_unknown_population_rows
        FROM unpointed GROUP BY 1 ORDER BY 1''')
    fields = '''source_record_id,census_year,settlement_name,settlement_type,region_raw,district_raw,
        municipality_raw,population,population_value_quality,source_native_id,okato,oktmo,
        population_scope,entity_grain_status,in_frozen_scope_residual,source_file,source_sheet,source_row,
        latitude,longitude,coordinate_source'''
    out.mkdir(parents=True)
    for year in (2002,2010,2021):
        for cohort,extra in [('direct_point_missing',''),('scope_residual_direct_point_missing',' AND in_frozen_scope_residual')]:
            top = rows(con, f'SELECT {fields} FROM unpointed WHERE census_year={year} AND NOT federal_aggregate{extra} ORDER BY population DESC NULLS LAST,source_record_id LIMIT 20')
            with (out / f'top20_{year}_{cohort}.csv').open('w',encoding='utf-8',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(top[0]),lineterminator='\n')
                writer.writeheader();writer.writerows(top)
    federal=rows(con,f'SELECT {fields} FROM unpointed WHERE federal_aggregate ORDER BY census_year,population DESC')
    with (out/'federal_aggregate_rows_without_direct_point.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(federal[0]),lineterminator='\n');writer.writeheader();writer.writerows(federal)
    missing_year=rows(con,'''SELECT s.source_record_id,s.census_year,s.settlement_name,s.population,p.target_year
        FROM accepted_points p JOIN selected s ON p.target_source_record_id=s.source_record_id
        WHERE try_cast(p.target_year AS INT) IS DISTINCT FROM s.census_year ORDER BY s.census_year,s.source_record_id''')
    for k,p in inputs.items():
        assert sha(p)==hashes[k],k
    receipt={'status':'read_only_no_admissions','script_sha256':sha(__file__),
        'config_sha256':sha(CONFIG),'inputs':{k:{'path':p,'sha256':hashes[k]} for k,p in inputs.items()},
        'accepted_point_status_allowlist':sorted(ACCEPTED_COORDINATE_STATUSES),'accepted_point_uses':428182,
        'summary':summary,'accepted_point_target_year_missing_or_conflicting':missing_year,
        'all_inputs_unchanged':True,
        'definition':'Absence of a canonical accepted direct point use on the exact selected census source-record ID. Source year comes from selected, not optional point target_year. Federal subject/city totals are reported separately; 2010 totals identified by matching federal city name and region because their scope tag is settlement.',
        'limitations':['Counts are source observations, not unique settlements across years.',
            'No direct point does not mean no candidate, no point in another source, or no separate accepted territorial/event/partition representation.',
            'Frozen scope residual membership profiles the quoted broad metric, not independently established coordinate correctness.',
            '2010 source population quality is retained, including protected secondary values.',
            'Source names and numbered parts are retained literally, not silently merged or repaired.'],
        'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.glob('*.csv'))}}
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()

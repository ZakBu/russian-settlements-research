"""Verify restored research inputs; build an assignment-free settlement axis.

All inputs remain read-only. No old zones, centers, radii or nearest assignments
are used. Municipal name matches are hypotheses, never administrative evidence.
"""
from pathlib import Path
import argparse, hashlib, json, re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def norm(value):
    return re.sub(r'\s+', ' ', str(value).lower().replace('ё', 'е').strip().strip('"«»')).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--restored', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    a = ap.parse_args()
    root, out = a.restored.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    checks = []

    def check(name, ok, detail=None):
        checks.append(dict(test=name, passed=bool(ok), details=detail))
        if not ok:
            raise AssertionError((name, detail))

    manifest = json.loads((root/'PACKAGE_MANIFEST.json').read_text())
    audit = []
    for entry in manifest['files']:
        q = root / entry['path']
        actual = sha(q) if q.is_file() else None
        audit.append(dict(path=entry['path'], expected_sha256=entry['sha256'],
                          actual_sha256=actual, bytes=q.stat().st_size if q.exists() else None,
                          passed=actual == entry['sha256'] and q.stat().st_size == entry['bytes']))
    check('every_package_member_SHA_and_size', all(x['passed'] for x in audit), len(audit))
    pd.DataFrame(audit).to_csv(out/'package_member_audit.csv', index=False)
    old = root/'research/sgrt_recovered_20261019'
    source_path = root/'inputs/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
    source = pd.read_csv(source_path, low_memory=False)
    axis = pd.read_parquet(old/'data/panel.parquet')
    check('source_shape', source.shape == (142570, 135), list(source.shape))
    check('stage71_SHA', sha(source_path) == 'd40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c')
    check('axis_unique_and_full', len(axis) == 142570 and axis.id.is_unique)
    check('same_source_order', axis.id.equals(source.entity_uid.rename('id')))
    check('no_prior_assignment_columns', not any(re.search(r'nearest|center_id|centre_id|zone_id|basin|parent_id|root_id', c) for c in axis.columns))
    for year in [2002, 2010, 2021]:
        col = f'population_{year}'
        check(f'exact_raw_{year}_population', np.array_equal(axis[col].to_numpy(), source[col].to_numpy(), equal_nan=True))
        check(f'zeros_{year}_retained', axis[col].eq(0).sum() == source[col].eq(0).sum(), int(axis[col].eq(0).sum()))
        check(f'nonnegative_{year}', axis[col].ge(0).all())
    check('coordinates_reference2021_only', axis.coordinate_reference_year.eq(2021).all() and not axis.historical_coordinate_measurement_asserted.any())
    check('coordinate_bounds', axis.lat.between(-90,90).all() and axis.lon.between(-180,180).all())
    check('partial_1989_not_filled', axis.population_1989.notna().sum() == 19863)
    axis.to_parquet(out/'point_axis.parquet', compression='zstd', index=False)
    check('axis_readback_exact', pd.read_parquet(out/'point_axis.parquet').equals(axis))

    bridge_path = root/'inputs/research_rebuild/native_np_municipality_bridge.csv.gz'
    bridge = pd.read_csv(bridge_path, dtype='string')
    check('no_explicit_admin_center_field', not any(re.search(r'admin.*cent|center|centre|столиц|райцентр', c, re.I) for c in bridge.columns))
    # Exact literal municipal naming is weak naming evidence, not proof of center.
    candidates = []
    axis_name = axis.assign(name_key=axis.name.map(norm))
    municipal = axis[['region','municipality_oktmo8_2021','municipality_upper_2021']].drop_duplicates()
    for row in municipal.itertuples(index=False):
        label = norm(row.municipality_upper_2021)
        labels = [label]
        for pattern in [r'^городской округ город (.+)$', r'^городской округ (.+)$', r'^город (.+)$', r'^муниципальное образование город (.+)$', r'^муниципальный округ (.+)$']:
            m = re.fullmatch(pattern, label)
            if m:
                labels.append(m.group(1))
        matched = axis_name[(axis_name.region == row.region) & axis_name.name_key.isin(labels)]
        for r in matched.itertuples(index=False):
            candidates.append(dict(id=r.id, name=r.name, region=r.region, type=r.type,
                municipality_oktmo8_2021=row.municipality_oktmo8_2021,
                municipality_label=row.municipality_upper_2021,
                belongs_to_named_municipality=r.municipality_oktmo8_2021 == row.municipality_oktmo8_2021,
                regional_name_match_count=len(matched), method='literal_name_after_explicit_municipal_prefix',
                evidence='name_hypothesis_only_admin_status_unverified',
                used_for_center_selection=False))
    pd.DataFrame(candidates).to_csv(out/'municipal_literal_name_candidates.csv', index=False)

    coverage = []
    for region, g in axis.groupby('region', dropna=False):
        row = dict(region=region, settlements=len(g), municipality_code_observed=int(g.municipality_oktmo8_2021.notna().sum()))
        for year in [1989,2002,2010,2021]:
            row[f'observed_{year}'] = int(g[f'population_{year}'].notna().sum())
            row[f'zero_{year}'] = int(g[f'population_{year}'].eq(0).sum())
            row[f'population_sum_{year}'] = float(g[f'population_{year}'].sum())
        coverage.append(row)
    pd.DataFrame(coverage).to_csv(out/'regional_coverage.csv', index=False)
    functional = []
    for year in [2016, 2021]:
        q = root/f'inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet'
        pf = pq.ParquetFile(q)
        functional.append(dict(path=str(q), year=year, rows=pf.metadata.num_rows,
            columns=pf.schema_arrow.names, sha256=sha(q), geography='legal_address_geocode_not_activity_or_branches',
            spatial_assignment='none_in_input', known_limit='commercial_accounts_exclude_many_public_services'))
    # Retain external federal territories separately: not added population rows.
    federal_path = root/'inputs/publication/stage71/accepted_common_federal_territory_axis.csv'
    pd.read_csv(federal_path).to_csv(out/'external_federal_axis.csv', index=False)
    important = [source_path, old/'data/panel.parquet', bridge_path,
        root/'inputs/research_rebuild/population_1989_selected_long.parquet', federal_path,
        root/'inputs/recovery_inputs/columnar/agriculture.parquet']
    important += [root/f'inputs/recovery_inputs/enrichment/rfsd_{y}_selected.parquet' for y in [2016,2021]]
    immutable = {str(q.relative_to(root)): dict(sha256=sha(q), bytes=q.stat().st_size) for q in important}
    result = dict(status='PASS', package_members_verified=len(audit), axis_rows=len(axis), axis_columns=len(axis.columns),
        author='anchor_data; original restored demographic panel also authored by this role; independent only of later functional/GIS calculations',
        checks=checks, checks_passed=sum(c['passed'] for c in checks),
        all2010_observed_and_retained=True, no_2010_quality_metadata_exclusion=True,
        population_2010_zero=int(axis.population_2010.eq(0).sum()),
        population_sums={str(y): int(axis[f'population_{y}'].sum()) for y in [2002,2010,2021]},
        historically_complete_1989=False, historical_boundary_comparability='not_established',
        coordinate_reference_year=2021, municipal_context_year=2021, municipal_dataset_version='v20251217',
        current_2026_administrative_membership_asserted=False,
        explicit_administrative_center_field_available=False,
        literal_name_candidates=len(candidates), literal_name_candidates_are_confirmed_centers=False,
        functional_inputs=functional,
        commercial_input_not_comprehensive_service_inventory=True,
        immutable_inputs=immutable,
        outputs={q.name:dict(sha256=sha(q), bytes=q.stat().st_size) for q in out.iterdir() if q.is_file() and q.suffix in ['.parquet','.csv']})
    (out/'immutable_input_manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k:result[k] for k in ['status','package_members_verified','axis_rows','axis_columns','checks_passed','population_2010_zero','population_sums','literal_name_candidates']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

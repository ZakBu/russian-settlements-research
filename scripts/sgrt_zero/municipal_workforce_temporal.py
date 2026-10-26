#!/usr/bin/env python3
"""Annual workforce comparability and resident-employment denominator audit.

Matching an OKTMO code does not certify unchanged boundaries. Payroll staff
excluding small businesses and census employed residents are different sets;
their difference is never used as net commuting or as calibrated trip demand.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
try:
    from .municipal_workforce_source import classify_territory
except ImportError:
    from municipal_workforce_source import classify_territory

TOTAL = 'Всего по обследуемым видам экономической деятельности'
PERIOD = 'Январь-декабрь'
UPPER = 'Муниципальное образование верхнего уровня'
SUBJECT = 'Субъект РФ'
WARD = 'Внутригородская территория города федерального значения'
CITIES = {
    '45000000': ('Москва', 'г. Москва', True),
    '40000000': ('Санкт-Петербург', 'г. Санкт-Петербург', True),
    '63701000': ('Саратов', 'Саратовская область', False),
    '65701000': ('Екатеринбург', 'Свердловская область', False),
    '75701000': ('Челябинск', 'Челябинская область', False),
    '92701000': ('Казань', 'Республика Татарстан', False),
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def annual_rows(source, year):
    rows = source.loc[source.indicator_code.eq('Y48423005') & source.year.eq(year)
                      & source.indicator_period.eq(PERIOD) & source.okved2.eq(TOTAL)].copy()
    if rows.duplicated('oktmo').any():
        raise ValueError('Duplicate territory/annual/year/all-industry total')
    if not rows.indicator_unit.eq('Человек').all():
        raise ValueError('Unexpected annual workforce unit')
    if rows.empty:
        rows['source_territory_class'] = pd.Series(dtype='string')
        return rows, {'year': year, 'source_annual_rows': 0, 'selected_scope_rows': 0,
                      'unknown_annual_not_zero_workforce': True}
    rows['source_territory_class'] = rows.apply(classify_territory, axis=1)
    keep = rows.source_territory_class.isin(['municipal_territory_record', 'reported_federal_city_subject_total'])
    keep &= ((rows.mun_level.eq(UPPER) & ~rows.mun_type.eq(WARD))
             | rows.source_territory_class.eq('reported_federal_city_subject_total'))
    federal_prefix = rows.oktmo.astype(str).str[:2].isin(['40', '45'])
    keep &= ~federal_prefix | rows.source_territory_class.eq('reported_federal_city_subject_total')
    selected = rows.loc[keep].copy()
    selected['workforce_numeric'] = pd.to_numeric(selected.indicator_value, errors='coerce')
    if selected.workforce_numeric.dropna().lt(0).any():
        raise ValueError('Negative observed annual-average workforce')
    selected['history_from_numeric'] = pd.to_numeric(selected.oktmo_year_from, errors='coerce')
    selected['history_to_numeric'] = pd.to_numeric(selected.oktmo_year_to, errors='coerce')
    selected['code_history_interval_contains_year'] = (
        selected.history_from_numeric.le(year) & selected.history_to_numeric.ge(year))
    selected['code_history_interval_unknown'] = selected.history_from_numeric.isna() | selected.history_to_numeric.isna()
    facts = {'year': year, 'source_annual_rows': len(rows), 'selected_scope_rows': len(selected),
             'observed_numeric_rows': int(selected.workforce_numeric.notna().sum()),
             'group_aggregate_rows_excluded': int((rows.source_territory_class.eq('group_of_municipalities_aggregate') & ~keep).sum()),
             'source_ward_type_rows': int(rows.mun_type.eq(WARD).sum()),
             'actual_ward_type_rows_excluded': int((rows.mun_type.eq(WARD) & ~keep).sum()),
             'retained_federal_totals_with_ward_type': int((rows.mun_type.eq(WARD) & keep).sum()),
             'federal_total_rows': int(selected.source_territory_class.eq('reported_federal_city_subject_total').sum()),
             'code_interval_outside_source_year': int((~selected.code_history_interval_contains_year & ~selected.code_history_interval_unknown).sum()),
             'annual_absence_is_not_zero_workforce': True}
    return selected, facts


def compare_years(source, first=2021, last=2025):
    a, fa = annual_rows(source, first); b, fb = annual_rows(source, last)
    fields = ['oktmo', 'municipality', 'region_name', 'mun_level', 'mun_type_oktmo',
              'source_territory_class', 'workforce_numeric', 'oktmo_history',
              'history_from_numeric', 'history_to_numeric', 'code_history_interval_contains_year',
              'code_history_interval_unknown']
    joined = a[fields].merge(b[fields], on='oktmo', how='outer', suffixes=('_first', '_last'), indicator=True)
    joined['observation_first_year'] = first; joined['observation_last_year'] = last
    joined['both_numeric'] = joined.workforce_numeric_first.notna() & joined.workforce_numeric_last.notna()
    joined['same_name_and_type_labels'] = (joined.municipality_first.eq(joined.municipality_last)
        & joined.mun_type_oktmo_first.eq(joined.mun_type_oktmo_last))
    joined['source_reports_no_change_both'] = joined.oktmo_history_first.eq('Без изменений') & joined.oktmo_history_last.eq('Без изменений')
    joined['source_reports_union_or_split'] = joined[['oktmo_history_first','oktmo_history_last']].fillna('').apply(
        lambda c: c.astype(str).str.contains('Объедин|Раздел', case=False, regex=True)).any(axis=1)
    interval = joined.history_from_numeric_first.le(first) & joined.history_to_numeric_first.ge(last)
    interval &= joined.history_from_numeric_last.le(first) & joined.history_to_numeric_last.ge(last)
    joined['source_code_interval_spans_both_years'] = interval.fillna(False)
    joined['relative_change_of_reported_partial_count'] = (joined.workforce_numeric_last /
        joined.workforce_numeric_first - 1).where(joined.both_numeric & joined.workforce_numeric_first.gt(0))
    joined['territorial_boundary_equivalence_verified'] = False
    joined['difference_is_net_commuting'] = False
    joined['change_is_pure_employment_growth'] = False
    summary = {'first_year': first, 'last_year': last, 'first_source': fa, 'last_source': fb,
               'same_code_observed_both': int(joined.both_numeric.sum()),
               'first_only': int(joined._merge.eq('left_only').sum()),
               'last_only': int(joined._merge.eq('right_only').sum()),
               'both_with_same_name_and_type': int((joined.both_numeric & joined.same_name_and_type_labels).sum()),
               'both_source_no_change_labels': int((joined.both_numeric & joined.source_reports_no_change_both).sum()),
               'both_union_or_split_metadata': int((joined.both_numeric & joined.source_reports_union_or_split).sum()),
               'both_code_interval_spans_2021_2025': int((joined.both_numeric & joined.source_code_interval_spans_both_years).sum()),
               'same_code_or_source_no_change_is_not_independent_boundary_verification': True}
    stability = {}
    for label, mask in [('same_code_numeric_both', joined.both_numeric),
                        ('same_code_source_no_change', joined.both_numeric & joined.source_reports_no_change_both)]:
        subset = joined.loc[mask]
        changes = subset.relative_change_of_reported_partial_count.dropna()
        stability[label] = {'rows': len(subset),
            'spearman_recorded_partial_workforce_2021_2025': float(subset.workforce_numeric_first.corr(
                subset.workforce_numeric_last, method='spearman')),
            'reported_partial_count_relative_change_median': float(changes.median()),
            'reported_partial_count_relative_change_p10': float(changes.quantile(.1)),
            'reported_partial_count_relative_change_p90': float(changes.quantile(.9)),
            'not_boundary_verified_growth_or_hierarchy_stability': True}
    summary['recorded_partial_workforce_stability'] = stability
    return joined, summary


def city_denominator_audit(source, census):
    first, _ = annual_rows(source, 2021); last, _ = annual_rows(source, 2025)
    rows = []
    census = pd.DataFrame(census)
    for code, (name, region, federal_same_geography) in CITIES.items():
        one = first[first.oktmo.eq(code)]; recent = last[last.oktmo.eq(code)]
        resident = census[census.region.eq(region) & census.geography_type.eq('federal_subject')]
        total = resident[resident.population_category.eq('Городское и сельское население')]
        if len(total): resident = total
        else: resident = resident[resident.population_category.eq('Городское население')]
        if len(resident) != 1: raise ValueError('Ambiguous resident employed geography: ' + region)
        r = resident.iloc[0]
        y2021 = float(one.workforce_numeric.iloc[0]) if len(one) else np.nan
        y2025 = float(recent.workforce_numeric.iloc[0]) if len(recent) else np.nan
        same_year_and_territory = federal_same_geography and np.isfinite(y2021)
        rows.append({'city_reading_label':name,'workforce_oktmo':code,
            'workforce_geography':recent.municipality.iloc[0] if len(recent) else None,
            'partial_organisation_workforce_2021':y2021,'partial_organisation_workforce_2025':y2025,
            'census_employed_residents_age15plus_2021':int(r.employed_age15plus),
            'census_geography':region,'census_population_category':r.population_category,
            'same_reported_territory_grain':federal_same_geography,
            'same_reported_territory_and_year':same_year_and_territory,
            'raw_ratio_of_different_person_sets_not_coverage':y2021 / r.employed_age15plus if same_year_and_territory else np.nan,
            'ratio_is_net_commuting_or_resident_coverage':False,
            'source_person_sets_and_time_reference_comparable':False,
            'census_outside_np_observed':int(r.outside_np) if federal_same_geography else pd.NA,
            'census_daily_outside_np_observed':int(r.outside_daily) if federal_same_geography else pd.NA,
            'can_infer_destination_specific_level1_attachment':False,
            'reason':('same_reported_subject_2021_but_payroll_excludes_SMB_and_annual_worksites_differ_from_census_residents'
                      if same_year_and_territory else
                      'annual_2021_subject_total_absent_no_ward_sum_or_2025_substitution' if federal_same_geography else
                      'municipal_workforce_city_vs_census_whole_region_not_compatible_geography')})
    return pd.DataFrame(rows)


def observed_external_screen(census, threshold=.15):
    out = []
    for row in census:
        if row['region'] not in ['г. Москва','г. Санкт-Петербург']: continue
        employed, external, unknown = (int(row[k]) for k in ['employed_age15plus','outside_np','unresolved_np_location'])
        low, high = external/employed, (external+unknown)/employed
        out.append({'region':row['region'],'geography':'reported_federal_city_subject_not_a_NP_OD_matrix',
                    'census_year':2021,'employed_residents':employed,'observed_outside_any_np':external,
                    'unresolved_np_location':unknown,'outside_any_np_fraction_lower':low,
                    'outside_any_np_fraction_upper_if_all_unknown_outside':high,
                    'illustrative_destination_specific_threshold':threshold,
                    'upper_outside_any_np_below_illustrative_threshold':high<threshold,
                    'known_destination_core':False,'incoming_catchment_identifiable':False,
                    'source_method_reference_id':'DIJKSTRA2019_FUA',
                    'threshold_screen_is_not_observed_FUA_or_SGRT_delineation':True})
    return pd.DataFrame(out)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['workforce','census','output']:p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();source=pd.read_parquet(args.workforce);census=json.loads(args.census.read_text())
    yearly=[]
    for year in range(2017,2027): yearly.append(annual_rows(source,year)[1])
    matched,summary=compare_years(source);cities=city_denominator_audit(source,census)
    screen=observed_external_screen(census)
    args.output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(yearly).to_parquet(args.output/'annual_scope_coverage.parquet',index=False)
    matched.to_parquet(args.output/'workforce_2021_2025_code_comparison.parquet',index=False)
    cities.to_parquet(args.output/'six_city_denominator_audit.parquet',index=False)
    screen.to_parquet(args.output/'external_work_dependency_screen.parquet',index=False)
    cities.to_csv(args.output/'six_city_denominator_audit.csv',index=False)
    summary.update(annual_scope_coverage=yearly,input_sha256={'workforce':sha(args.workforce),'census':sha(args.census)},
                   code_sha256=sha(Path(__file__)),inferred_net_commuting=False,
                   observed_destination_specific_urban_hierarchy=False)
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()

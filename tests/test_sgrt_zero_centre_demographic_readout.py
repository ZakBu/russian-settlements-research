import pandas as pd
from scripts.sgrt_zero.centre_demographic_readout import analyse_component, build_readout


def record(sid, start, end, kind='село'):
    r = {'source_record_id': sid, 'name': sid, 'settlement_type_2021': kind,
         'budget_population_credit': True}
    for year, value in [(2002, start), (2010, start), (2021, end)]:
        r.update({f'population_{year}': value, f'credit_{year}': True,
                  f'source_record_id_{year}': f'{year}:{sid}',
                  f'population_value_quality_{year}': 'direct_published_census_value'})
    return r


def test_missing_year_preserves_partial_sum_but_blocks_whole_direction():
    a, b = record('a', 10, 20), record('b', None, 30)
    x = analyse_component([a, b], 2002)
    assert not x['complete'] and x['direction'] == 'unknown'
    assert x['start_observed_known_sum'] == 10 and x['end_observed_known_sum'] == 50
    assert x['comparable_records'] == 1
    assert 'missing_or_invalid_population_2002' in x['unknown_reasons_json']


def test_secondary_protected_2010_not_observed_despite_numeric_value():
    r = record('a', 100, 150)
    r['population_value_quality_2010'] = 'secondary_confidentiality_protected_value_exact_scope_unverified'
    x = analyse_component([r], 2010)
    assert x['direction'] == 'unknown' and x['start_observed_known_sum'] is None
    assert x['start_accepted_credited_numeric_sum'] == 100
    assert analyse_component([r], 2002)['direction'] == 'growth'
    assert 'scope_unverified_2010' in x['unknown_reasons_json']
    assert analyse_component([r], 2010, evidence_mode='accepted_values')['direction'] == 'growth'


def test_centre_excluded_from_external_and_urban_excluded_from_rural():
    ref = pd.DataFrame([record('c', 100, 200, 'город'), record('r', 10, 5), record('u', 20, 40, 'город')])
    centres = pd.DataFrame([{'star_id': 's', 'centre_settlement_id': 'c'}])
    members = pd.DataFrame({'star_id': ['s']*3, 'origin_id': ['c', 'r', 'u']})
    parts, classes = build_readout(centres, members, ref)
    p = parts[parts.start_year.eq(2002)].set_index('scope')
    assert p.loc['external', 'records'] == 2 and p.loc['external', 'start_paired_cohort_sum'] == 30
    assert p.loc['rural_external', 'records'] == 1
    assert classes.iloc[0].joint_centre_external_2002_2021 == 'growth__growth'
    assert classes.iloc[0].joint_centre_rural_external_2002_2021 == 'growth__decline'


def test_uncredited_member_blocks_whole_without_double_counting():
    a, b = record('a', 10, 20), record('b', 100, 200)
    b['credit_2002'] = False
    x = analyse_component([a, b], 2002)
    assert x['direction'] == 'unknown' and x['start_observed_known_sum'] == 10
    b['credit_2002'] = True
    b['budget_population_credit'] = False
    x = analyse_component([a, b], 2002)
    assert x['end_observed_known_sum'] == 20 and x['comparable_records'] == 1

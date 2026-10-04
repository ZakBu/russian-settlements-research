from research_rebuild.mass_linkage.apply_reviewed_combined_temporal_scope_20261004 import qualifying_date


def stamp(time, precision, **extra):
    return {'time': time, 'precision': precision, 'calendarmodel': 'http://www.wikidata.org/entity/Q1985727', 'before': 0, 'after': 0, **extra}


def test_actual_census_date_is_eligible_without_rewriting_precision():
    assert qualifying_date(stamp('+2002-10-09T00:00:00Z', 11), 2002)
    assert qualifying_date(stamp('+2010-10-14T00:00:00Z', 11), 2010)
    assert qualifying_date(stamp('+2002-00-00T00:00:00Z', 9), 2002)


def test_annual_dates_and_uncertainty_do_not_become_census_observations():
    assert not qualifying_date(stamp('+2010-01-01T00:00:00Z', 11), 2010)
    assert not qualifying_date(stamp('+2002-10-14T00:00:00Z', 11), 2002)
    assert not qualifying_date(stamp('+2010-10-14T00:00:00Z', 11, after=1), 2010)
    assert not qualifying_date(stamp('+2010-10-14T00:00:00Z', 11, calendarmodel='http://www.wikidata.org/entity/Q1985786'), 2010)

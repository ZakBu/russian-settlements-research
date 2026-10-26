import sys
from pathlib import Path
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from municipal_workforce_source import INDICATOR, TOTAL, PERIOD, UPPER, select_2025


def record(**changes):
    row = dict(indicator_code=INDICATOR, oktmo='65701000', year=2025,
        indicator_period=PERIOD, okved2=TOTAL, region_id='65',
        region_name='Свердловская область', municipality='город Екатеринбург',
        mun_level=UPPER, mun_type_oktmo='Городской округ, городской округ с внутригородским делением',
        indicator_unit='Человек', indicator_value=478059., oktmo_year_from='2010', oktmo_year_to='2025')
    return {**row, **changes}


class MunicipalWorkforceSourceTests(unittest.TestCase):
    def test_upper_level_label_does_not_turn_a_regional_group_into_a_city(self):
        source = pd.DataFrame([record(), record(oktmo='50700000',
            municipality='Городские округа Новосибирской области', region_id='50',
            region_name='Новосибирская область', indicator_value=451574.)])
        out = select_2025(source)
        group = out[out.oktmo.eq('50700000')].iloc[0]
        self.assertEqual(group.source_territory_class, 'group_of_municipalities_aggregate')
        self.assertFalse(group.eligible_as_individual_municipal_context)
        self.assertEqual(len(out), 2)  # Retained as evidence, not silently removed.

    def test_only_exact_year_full_period_and_total_are_admitted(self):
        out = select_2025(pd.DataFrame([record(), record(year=2024),
            record(indicator_period='Январь-март'), record(okved2='Раздел C Обрабатывающие производства')]))
        self.assertEqual(len(out), 1)
        self.assertEqual(out.workforce_numeric_value.iloc[0], 478059.)
        self.assertFalse(out.geography_automatically_equal_to_census_settlement.any())
        self.assertFalse(out.workers_allocated_to_settlements.any())

    def test_duplicates_fail_and_unknown_is_not_imputed_as_zero(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            select_2025(pd.DataFrame([record(), record()]))
        out = select_2025(pd.DataFrame([record(indicator_value=None)]))
        self.assertTrue(pd.isna(out.workforce_numeric_value.iloc[0]))
        self.assertEqual(out.workforce_observation_status.iloc[0], 'unknown_or_nonnumeric_not_zero')

    def test_city_subject_total_is_direct_not_added_to_wards(self):
        out = select_2025(pd.DataFrame([record(oktmo='45000000', municipality='Муниципальные образования города Москвы',
            region_id='45', region_name='Москва', mun_level='Субъект РФ',
            mun_type_oktmo='Субъект РФ', indicator_value=4211363.)]))
        self.assertEqual(out.source_territory_class.iloc[0], 'reported_federal_city_subject_total')
        self.assertFalse(out.municipal_components_summed.any())


if __name__ == '__main__':
    unittest.main()

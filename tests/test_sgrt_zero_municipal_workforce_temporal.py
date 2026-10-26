import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from municipal_workforce_temporal import annual_rows,compare_years,observed_external_screen,TOTAL,PERIOD,UPPER


def source():
    return pd.DataFrame(dict(indicator_code='Y48423005',year=[2021,2025],indicator_period=PERIOD,
        okved2=TOTAL,oktmo='63701000',indicator_unit='Человек',indicator_value=[100.,120.],
        municipality='город Саратов',region_name='Саратовская область',region_id='63',mun_level=UPPER,
        mun_type_oktmo='Городской округ, городской округ с внутригородским делением',
        mun_type='Городской округ',oktmo_history='Объединение',oktmo_year_from='2010',oktmo_year_to='2025'))


class TemporalWorkforceTests(unittest.TestCase):
    def test_same_code_with_union_metadata_is_not_verified_growth(self):
        out,summary=compare_years(source())
        self.assertEqual(summary['same_code_observed_both'],1)
        self.assertTrue(out.source_reports_union_or_split.iloc[0])
        self.assertFalse(out.territorial_boundary_equivalence_verified.iloc[0])
        self.assertFalse(out.change_is_pure_employment_growth.iloc[0])

    def test_missing_annual_does_not_substitute_quarterly_total(self):
        frame=source();frame.loc[0,'indicator_period']='Январь-сентябрь'
        out,facts=annual_rows(frame,2021)
        self.assertEqual(len(out),0)
        self.assertTrue(facts['unknown_annual_not_zero_workforce'])

    def test_ward_and_positive_group_are_excluded_even_if_labeled_upper(self):
        frame=source().iloc[[1]].copy()
        ward=frame.copy();ward['oktmo']='67701000';ward['mun_type']='Внутригородская территория города федерального значения'
        group=frame.copy();group['oktmo']='63500000';group['municipality']='Городские округа Саратовской области'
        out,facts=annual_rows(pd.concat([frame,ward,group],ignore_index=True),2025)
        self.assertEqual(out.oktmo.tolist(),['63701000'])
        self.assertEqual(facts['group_aggregate_rows_excluded'],1)
        self.assertEqual(facts['actual_ward_type_rows_excluded'],1)

    def test_unknown_destination_cannot_be_allocated_to_a_named_city(self):
        rows=[dict(region='г. Москва',employed_age15plus=1000,outside_np=20,unresolved_np_location=30)]
        out=observed_external_screen(rows)
        self.assertEqual(out.outside_any_np_fraction_upper_if_all_unknown_outside.iloc[0],.05)
        self.assertFalse(out.known_destination_core.iloc[0])
        self.assertFalse(out.incoming_catchment_identifiable.iloc[0])


if __name__=='__main__':unittest.main()

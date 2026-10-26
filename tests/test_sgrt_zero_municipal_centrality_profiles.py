import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from municipal_centrality_profiles import dominance_rank_bounds, select_workforce, federal_medical_stock, TOTAL, UPPER, SUBJECT, WARD


class MunicipalComparisonTests(unittest.TestCase):
    def test_complete_dominance_does_not_need_a_chosen_weight(self):
        lower, upper = dominance_rank_bounds([[10,10,10],[5,5,5],[1,1,1]])
        np.testing.assert_array_equal(lower,[1,2,3]);np.testing.assert_array_equal(upper,[1,2,3])

    def test_crossing_components_remain_partially_ordered(self):
        lower,upper=dominance_rank_bounds([[10,5],[5,10],[1,1]])
        np.testing.assert_array_equal(lower,[1,1,3]);np.testing.assert_array_equal(upper,[2,2,3])

    def test_equal_vectors_are_not_spuriously_ordered(self):
        lower,upper=dominance_rank_bounds([[2,2],[2,2]])
        np.testing.assert_array_equal(lower,[1,1]);np.testing.assert_array_equal(upper,[2,2])

    def test_federal_total_and_wards_are_not_both_ranked(self):
        frame=pd.DataFrame(dict(year=[2025]*3,indicator_period='Январь-декабрь',okved2=TOTAL,
            oktmo=['45000000','45901000','65701000'],mun_level=[SUBJECT,UPPER,UPPER],
            mun_type=['city',WARD,'Городской округ, городской округ с внутригородским делением'],indicator_code='Y48423005',indicator_unit='Человек',
            indicator_value=[100.,40.,20.],municipality=['M','ward','E'],region_name=['Москва','Москва','Свердловская область'],
            region_id=['45','45','65'],indicator_name='workers'))
        frame['mun_type_oktmo']=frame.mun_type
        out,_=select_workforce(frame)
        self.assertEqual(set(out.oktmo),{'45000000','65701000'})
        self.assertEqual(len(frame),3)

    def test_federal_subject_with_ward_type_is_not_counted_as_excluded(self):
        # Real source labels Moscow/SPB subject totals with the same mun_type
        # as their wards; mun_level and exact actor identity distinguish them.
        frame = pd.DataFrame(dict(year=[2025]*4, indicator_period='Январь-декабрь', okved2=TOTAL,
            oktmo=['45000000','45901000','82701365','50700000'],
            mun_level=[SUBJECT,UPPER,'Муниципальное образование нижнего уровня',UPPER],
            mun_type=[WARD,WARD,'Городской округ, городской округ с внутригородским делением',
                      'Городской округ, городской округ с внутригородским делением'],
            indicator_code='Y48423005', indicator_unit='Человек', indicator_value=[100.,40.,5.,999.],
            municipality=['Москва','ward','Ленинский район','Городские округа Новосибирской области'],
            region_name=['Москва','Москва','Республика Дагестан','Новосибирская область'],
            region_id=['45','45','82','50'], indicator_name='workers'))
        out, audit = select_workforce(frame)
        self.assertEqual(list(out.oktmo), ['45000000'])
        self.assertEqual(audit['source_rows_with_federal_ward_type'], 2)
        self.assertEqual(audit['retained_subject_rows_with_federal_ward_type'], 1)
        self.assertEqual(audit['excluded_federal_ward_rows'], 1)
        self.assertEqual(audit['excluded_group_aggregate_rows'], 1)
        self.assertEqual(audit['excluded_other_scope_rows'], 1)
        self.assertEqual(audit['annual_total_source_rows'], len(out) + sum(
            audit[k] for k in ['excluded_federal_ward_rows','excluded_group_aggregate_rows','excluded_other_scope_rows']))

    def test_conflicting_worker_total_is_rejected(self):
        frame=pd.DataFrame(dict(year=[2025]*2,indicator_period='Январь-декабрь',okved2=TOTAL,
            oktmo=['65701000']*2,mun_level=UPPER,mun_type='city',indicator_code='Y48423005',indicator_unit='Человек',
            indicator_value=[100.,200.],municipality='E',region_name='r',indicator_name='workers'))
        with self.assertRaises(ValueError):select_workforce(frame)

    def test_federal_child_with_generic_municipal_type_is_not_double_counted(self):
        frame=pd.DataFrame(dict(year=[2025]*2,indicator_period='Январь-декабрь',okved2=TOTAL,
            oktmo=['45000000','45901000'],mun_level=[SUBJECT,UPPER],
            mun_type=['city','Муниципальный округ'],indicator_code='Y48423005',indicator_unit='Человек',
            indicator_value=[100.,40.],municipality=['M','ward'],region_name='Москва',region_id='45',indicator_name='workers'))
        frame['mun_type_oktmo']=frame.mun_type
        out,_=select_workforce(frame)
        self.assertEqual(list(out.oktmo),['45000000'])

    def test_group_with_upper_level_label_is_not_a_territorial_node(self):
        frame=pd.DataFrame(dict(year=[2025]*2,indicator_period='Январь-декабрь',okved2=TOTAL,
            oktmo=['50500000','50701000'],mun_level=UPPER,
            mun_type='Городской округ, городской округ с внутригородским делением',
            indicator_code='Y48423005',indicator_unit='Человек',indicator_value=[999999999.,100.],
            municipality=['Городские округа Новосибирской области','город Новосибирск'],
            region_name='Новосибирская область',region_id='50',indicator_name='workers'))
        frame['mun_type_oktmo']=frame.mun_type
        out,audit=select_workforce(frame)
        self.assertEqual(list(out.oktmo),['50701000'])
        self.assertEqual(audit['excluded_group_aggregate_rows'],1)

    def test_federal_medical_region_keeps_unknown_NP_without_multiplying_profiles(self):
        evidence=pd.DataFrame({'UIDSPMO':['d1','d1','d2'],'IDADDRESS':['a1','a1','a2']})
        address=pd.DataFrame({'UIDSPMO':['d1','d2'],'IDADDRESS':['a1','a2'],
                              'address_region_normalized':['санкт петербург']*2,'source_record_id':['spb',None]})
        out=federal_medical_stock(evidence,address)
        self.assertEqual(out.loc['40000000','federal_medical_address_ids_known'],2)
        self.assertEqual(out.loc['40000000','federal_medical_address_ids_without_np_identity'],1)
        self.assertTrue(pd.isna(out.loc['45000000','federal_medical_address_ids_known']))


if __name__=='__main__':unittest.main()

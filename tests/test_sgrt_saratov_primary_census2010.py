import unittest
import pandas as pd
from scripts.sgrt_saratov.primary_census2010 import compare_legacy,parse_reader


class Primary2010Parsing(unittest.TestCase):
    def test_population_table_separates_actual_np_and_municipal_aggregate(self):
        text='''Численность населения по городским и сельским населенным пунктам на 14 октября 2010 г.
Городские округа
Городской округ город Саратов г. Саратов 100 40 60 40,0 60,0
Питерский район
Всего по району Сельское население 15 7 8 46,7 53,3
Питерское сельское поселение 15 7 8 46,7 53,3 село Питерка 10 5 5 50,0 50,0 посѐлок Опытная Станция 5 2 3 40,0 60,0 хутор Пустой - - - - -
Методологические пояснения
'''
        rows,controls=parse_reader(text)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows.primary_population_2010.tolist(),[100,10,5,0])
        self.assertEqual(rows.primary_name_literal.tolist(),['Саратов','Питерка','Опытная Станция','Пустой'])
        self.assertTrue(rows.male_plus_female_equals_total.all())
        self.assertTrue(controls.district_context_reconciled.all())

    def test_name_homonyms_are_not_resolved_using_population_equality(self):
        primary=pd.DataFrame([
            {'kind_key':'село','name_key':'питерка','primary_population_2010':12,'male_plus_female_equals_total':True},
            {'kind_key':'деревня','name_key':'ивановка','primary_population_2010':10,'male_plus_female_equals_total':True},
            {'kind_key':'деревня','name_key':'ивановка','primary_population_2010':20,'male_plus_female_equals_total':True}])
        legacy=pd.DataFrame([
            {'source_record_id':'old:village','census_year':2010,'region_norm':'саратовская','settlement_name':'Питерка','settlement_type':'село','population':10,'effective_population':10},
            {'source_record_id':'old:homonym','census_year':2010,'region_norm':'саратовская','settlement_name':'Ивановка','settlement_type':'деревня','population':20,'effective_population':20}])
        out=compare_legacy(primary,legacy).set_index('source_record_id_2010')
        self.assertTrue(out.loc['old:village','primary_value_admissible_in_separate_derived_variant'])
        self.assertEqual(out.loc['old:village','primary_minus_legacy'],2.)
        self.assertFalse(out.loc['old:homonym','primary_value_admissible_in_separate_derived_variant'])
        self.assertFalse(out.population_value_used_as_identity_key.any())
        self.assertFalse(out.matched_using_2021_name_or_district.any())

    def test_piterka_village_and_station_original_types_remain_distinct(self):
        primary=pd.DataFrame([
            {'kind_key':'село','name_key':'питерка','primary_population_2010':5439,'male_plus_female_equals_total':True},
            {'kind_key':'поселок','name_key':'железнодорожной станции питерка','primary_population_2010':542,'male_plus_female_equals_total':True}])
        legacy=pd.DataFrame([
            {'source_record_id':'old:v','census_year':2010,'region_norm':'саратовская','settlement_name':'Питерка','settlement_type':'село','effective_population':5439},
            {'source_record_id':'old:s','census_year':2010,'region_norm':'саратовская','settlement_name':'железнодорожной станции Питерка','settlement_type':'посёлок','effective_population':540}])
        out=compare_legacy(primary,legacy).set_index('source_record_id_2010')
        self.assertEqual(out.loc['old:v','primary_population_2010'],5439)
        self.assertEqual(out.loc['old:s','primary_population_2010'],542)
        self.assertTrue(out.loc['old:v','primary_equals_legacy'])
        self.assertFalse(out.loc['old:s','primary_equals_legacy'])


if __name__=='__main__':unittest.main()

import unittest
import pandas as pd
from scripts.sgrt_saratov.historical_school_inventory import parse_layout,school_scope,explicit_locality_candidates,link_records,inferred_grades

class HistoricalSchoolTests(unittest.TestCase):
    def roster(self):
        return pd.DataFrame([
            {'source_record_id':'village','name':'Питерка','settlement_type_2021':'село','district':'Питерский муниципальный район'},
            {'source_record_id':'station','name':'Питерка','settlement_type_2021':'железнодорожный объект','district':'Питерский муниципальный район'},
            {'source_record_id':'branch','name':'Агафоновка','settlement_type_2021':'село','district':'Питерский муниципальный район'},
            {'source_record_id':'saratov','name':'Саратов','settlement_type_2021':'город','district':'Городской округ город Саратов'},
            {'source_record_id':'rural','name':'Новое','settlement_type_2021':'село','district':'Саратовский муниципальный район'},
            {'source_record_id':'zato','name':'Шиханы','settlement_type_2021':'город','district':'Городской округ город Шиханы'},
        ])
    def test_village_station_not_conflated(self):
        self.assertEqual(explicit_locality_candidates('Средняя школа с. Питерка',self.roster()),['village'])
    def test_parent_locality_not_used_for_branch(self):
        self.assertEqual(explicit_locality_candidates('Школа с. Питерка филиал в с. Агафоновка',self.roster()),['branch'])
    def test_school_kindergarten_primary_is_not_discarded(self):
        s='Учреждение для детей дошкольного и младшего школьного возраста Начальная школа - детский сад с. Новое'
        self.assertEqual(school_scope(s),'ordinary_general_school_named_organisation')
        self.assertEqual(inferred_grades(s),'1–4')
        self.assertEqual(school_scope('Дошкольное образовательное учреждение детский сад'),'not_general_school')
    def test_arts_and_vocational_are_not_general_school(self):
        self.assertEqual(school_scope('Детская школа искусств'),'not_general_school')
        self.assertEqual(school_scope('Профессиональный лицей'),'not_general_school')
    def test_saratov_region_is_not_saratov_municipality(self):
        records=pd.DataFrame([{'ate':'239','organisation_code':'239000','name':'Управление образования ЗАТО Шиханы Саратовской области','source_pdf_page':1},
            {'ate':'239','organisation_code':'239003','name':'Средняя общеобразовательная школа г. Шиханы','source_pdf_page':1}])
        d,m=link_records(records,self.roster());self.assertEqual(m['239'],'Городской округ город Шиханы')
        self.assertEqual(d.iloc[0].source_record_id,'zato');self.assertTrue(d.iloc[0].historical_only)
        self.assertFalse(d.iloc[0].operation2026_verified);self.assertFalse(d.iloc[0].grades_verified)
    def test_layout_keeps_literal_multiline_and_page_locator(self):
        s='226 226003 Средняя общеобразовательная школа\n с. Питерка\n\f226 226004 Основная школа с. Агафоновка\n'
        d=parse_layout(s);self.assertEqual(len(d),2);self.assertIn('с. Питерка',d.iloc[0]['name']);self.assertEqual(d.iloc[1].source_pdf_page,2)

if __name__=='__main__':unittest.main()

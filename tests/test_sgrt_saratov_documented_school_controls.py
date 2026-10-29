import unittest

import pandas as pd

from scripts.sgrt_saratov.documented_school_controls import ANNEX, find_literal


class DocumentedSchoolIdentityTests(unittest.TestCase):
    def test_station_and_village_are_distinct(self):
        r=pd.DataFrame([
            {'name':'Питерка','settlement_type_2021':'село','source_record_id':'village'},
            {'name':'Питерка','settlement_type_2021':'железнодорожный объект','source_record_id':'station'},
        ])
        self.assertEqual(find_literal(r,'Питерка','село')[0],'village')
        self.assertEqual(find_literal(r,'Питерка','железнодорожный объект')[0],'station')
        self.assertIsNone(find_literal(r,'Питерка')[0])

    def test_kind_conflict_does_not_become_accepted(self):
        r=pd.DataFrame([{'name':'Верный','settlement_type_2021':'посёлок','source_record_id':'candidate'}])
        accepted,candidate,status=find_literal(r,'Верный','хутор')
        self.assertIsNone(accepted)
        self.assertEqual(candidate,'candidate')
        self.assertEqual(status,'literal_kind_conflict_held')

    def test_branch_is_not_legal_parent_destination(self):
        row=next(x for x in ANNEX if ('железнодорожный объект','Питерка') in x[3])
        self.assertEqual(row[1],'Агафоновка')
        self.assertEqual(row[2],'Питерка')
        self.assertNotEqual(row[1],row[2])
        morshanka=next(x for x in ANNEX if ('село','Моршанка') in x[3])
        self.assertEqual(morshanka[1],'Мироновка')


if __name__=='__main__':unittest.main()

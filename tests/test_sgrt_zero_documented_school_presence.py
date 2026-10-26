import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from scripts.sgrt_zero.documented_school_presence import add_documented_school_presence


class DocumentedPresenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);payload=b'<html>dated school address</html>'
        (self.root/'source.html').write_bytes(payload)
        self.ref=pd.DataFrame([{'source_record_id':'np','name':'Сосново-Озерское',
            'settlement_type_2021':'село','region':'бурятия','district':'Еравнинский район',
            'population_2021':1000.,'analysis_origin':True,'budget_population_credit':False,
            'population_role':'ordinary_settlement_record','ordinary_spatial_2021':True}])
        self.card={'card_id':'documented:school','eligible_as_dated_documented_presence':True,
            'source_record_id':'np','settlement_name':'Сосново-Озерское','settlement_type':'село',
            'region':'Республика Бурятия','district':'Еравнинский муниципальный район',
            'service_code':'school_general','external_seed':False,'site_lat':None,'site_lon':None,
            'coordinates_inferred':False,'historical_supply_needs_current_confirmation':True,
            'historical_source_only':True,'source_year':None,'observation_year':None,
            'source_snapshot':'2026-10-26','official_page_content_latest_visible_date':'2013-05-14',
            'institution_name':'Школа №1','evidence':[{'http_status':200,'path':'source.html',
            'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload),
            'content_type':'text/html','retrieved_utc':'2026-10-26T12:00:00+00:00'}]}

    def run_card(self, card=None, ref=None, offers=None):
        path=self.root/'cards.json';path.write_text(json.dumps({'school_cards':[card or self.card]}))
        return add_documented_school_presence(pd.DataFrame() if offers is None else offers,
                                             self.ref if ref is None else ref,path)

    def test_positive_uncredited_np_is_accepted_as_proxy_without_external_seed(self):
        row=self.run_card().iloc[0]
        self.assertEqual(row.supply_status,'proxy');self.assertTrue(row.eligible)
        self.assertTrue(row.route_eligible);self.assertFalse(row.default_external_seed_eligible)
        self.assertTrue(pd.isna(row.site_lat));self.assertTrue(pd.isna(row.site_lon))
        self.assertTrue(pd.isna(row.source_year));self.assertTrue(pd.isna(row.observation_year))
        self.assertEqual(row.source_page_latest_visible_dated_content,'2013-05-14')
        self.assertFalse(row.actual_operational_status_verified)

    def test_wrong_literal_identity_fields_fail(self):
        for key,value in [('source_record_id','wrong'),('settlement_name','Другое'),
                          ('settlement_type','город'),('region','саратовская'),('district','Другой район')]:
            with self.subTest(key=key):
                card=copy.deepcopy(self.card);card[key]=value
                with self.assertRaises(ValueError):self.run_card(card)

    def test_wrong_sha_or_non200_source_fails(self):
        for key,value in [('sha256','0'*64),('http_status',503),('bytes',1)]:
            with self.subTest(key=key):
                card=copy.deepcopy(self.card);card['evidence'][0][key]=value
                with self.assertRaises(ValueError):self.run_card(card)

    def test_missing_snapshot_fails(self):
        (self.root/'source.html').unlink()
        with self.assertRaises(FileNotFoundError):self.run_card()

    def test_external_or_inferred_coordinates_fail(self):
        for key,value in [('external_seed',True),('site_lat',55.),('coordinates_inferred',True)]:
            card=copy.deepcopy(self.card);card[key]=value
            with self.assertRaises(ValueError):self.run_card(card)

    def test_duplicate_card_or_existing_provider_fails(self):
        path=self.root/'cards.json';path.write_text(json.dumps({'school_cards':[self.card,self.card]}))
        with self.assertRaises(ValueError):add_documented_school_presence(pd.DataFrame(),self.ref,path)
        with self.assertRaises(ValueError):self.run_card(offers=pd.DataFrame({'provider_id':['documented:school']}))

    def test_zero_population_or_inactive_record_fails(self):
        for column,value in [('population_2021',0),('analysis_origin',False)]:
            ref=self.ref.copy();ref[column]=value
            with self.assertRaises(ValueError):self.run_card(ref=ref)

    def test_ineligible_card_does_not_create_an_offer(self):
        card=copy.deepcopy(self.card);card['eligible_as_dated_documented_presence']=False
        self.assertEqual(len(self.run_card(card)),0)

    def test_schema_extension_preserves_existing_implicit_admission(self):
        offers=pd.DataFrame({'provider_id':['old'],'supply_status':['observed'],'source_year':[2026]})
        result=self.run_card(offers=offers);old=result[result.provider_id.eq('old')].iloc[0]
        self.assertTrue(old.eligible);self.assertTrue(old.route_eligible)
        self.assertEqual(old.source_year,2026)
        self.assertEqual(offers.columns.tolist(),['provider_id','supply_status','source_year'])


if __name__=='__main__':unittest.main()

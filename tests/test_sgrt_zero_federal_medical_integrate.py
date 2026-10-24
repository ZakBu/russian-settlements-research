import importlib.util
from pathlib import Path
import unittest
import pandas as pd
P=Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/federal_medical_integrate.py';s=importlib.util.spec_from_file_location('integrate',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class TemporalEvidenceTests(unittest.TestCase):
 def historical(self):return pd.DataFrame([dict(object_id='oldclosedsource',subdivision_oid='org.0.1',activity_address='село Питерка, Советская42',activity_address_id='gar1'),dict(object_id='otherfacility_same_np',subdivision_oid='org.0.2',activity_address='село Питерка, Советская43',activity_address_id='gar2')])
 def current(self):return pd.DataFrame([dict(OID_SPMO='org.0.1',ADDR='село Питерка, Советская42',ADDR_GAR='gar1',organization_oms_participation_ended_asof=True)])
 def test_exact_ended_source_does_not_ban_whole_np(self):
  d=m.historical_time_audit(self.historical(),self.current()).set_index('object_id')
  self.assertTrue(d.loc['oldclosedsource','historical_offer_held_by_exact_current_evidence']);self.assertFalse(d.loc['otherfacility_same_np','historical_offer_held_by_exact_current_evidence']);self.assertFalse(d.physical_closure_inferred.any())
 def test_active_support_same_unit_address_prevents_blanket_hold(self):
  c=self.current();active=c.iloc[0].to_dict();active['organization_oms_participation_ended_asof']=False;c=pd.concat([c,pd.DataFrame([active])],ignore_index=True)
  d=m.historical_time_audit(self.historical(),c);self.assertFalse(d.historical_offer_held_by_exact_current_evidence.any())
 def test_changed_address_is_uncertain_not_exact_temporal_ban(self):
  c=self.current();c.loc[0,'ADDR']='другой адрес';c.loc[0,'ADDR_GAR']='other'
  d=m.historical_time_audit(self.historical(),c)
  self.assertFalse(d.iloc[0].historical_offer_held_by_exact_current_evidence);self.assertIn('uncertain',d.iloc[0].source_time_relation)
 def test_reused_gar_uuid_does_not_prove_same_care_address(self):
  c=self.current();c.loc[0,'ADDR']='Адрес А';other=c.iloc[0].to_dict();other['ADDR']='Адрес Б';c=pd.concat([c,pd.DataFrame([other])],ignore_index=True)
  result=m.historical_time_audit(self.historical(),c)
  self.assertFalse(result.iloc[0].historical_offer_held_by_exact_current_evidence)
 def test_known_np_without_coordinates_keeps_presence_but_no_external_seed(self):
  row=dict(source_record_id='np1',service_code='medical_basic_primary',source_id='["FEDERAL_F034_F038_20261023"]',source_year='["2026"]',service_basis='["explicit"]',supply_status='observed',source_records=1,has_official_registry=True,has_mapped_OSM=False,site_lat=float('nan'),site_lon=float('nan'),local_supply_eligible=True,default_external_seed_eligible=True,location_precision='settlement_point')
  d=m.combine_np_sources([pd.DataFrame([row])])
  self.assertTrue(d.iloc[0].local_supply_eligible);self.assertFalse(d.iloc[0].default_external_seed_eligible);self.assertEqual(d.iloc[0].location_precision,'settlement_identity_coordinate_unavailable')
if __name__=='__main__':unittest.main()

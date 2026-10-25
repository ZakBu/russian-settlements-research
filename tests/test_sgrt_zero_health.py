import importlib.util
from pathlib import Path
import unittest
import tempfile
import pandas as pd

P=Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/health.py'
spec=importlib.util.spec_from_file_location('zero_health',P);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


class HealthSourceTests(unittest.TestCase):
 def test_explicit_registry_site_path_works_with_portable_renamed_inputs(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);sites=root/'licensed_sites.parquet';sites.write_bytes(b'sites')
   self.assertEqual(h.registry_sites_path(root/'licensed_supply.parquet',sites),sites)
   with self.assertRaisesRegex(FileNotFoundError,'--official-sites'):
    h.registry_sites_path(root/'licensed_supply.parquet')
 def test_original_companion_filename_remains_supported(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);sites=root/'sites_matched.parquet';sites.write_bytes(b'sites')
   self.assertEqual(h.registry_sites_path(root/'supply.parquet'),sites)
 def row(self,**kwargs):
  return dict(broad_function='healthcare',medical_class='doctor_source_tag',name='',**kwargs)
 def test_unspecified_doctor_not_general_practitioner(self):
  s=h.classify_osm(self.row());self.assertEqual([r[0] for r in s],[h.UNSPECIFIED])
 def test_hospital_does_not_become_fap_or_primary_physician(self):
  s=h.classify_osm(dict(broad_function='healthcare',medical_class='hospital_source_tag',name='Больница'))
  self.assertEqual({r[0] for r in s},{h.UNSPECIFIED,'mapped_hospital_service_unknown_level'})
 def test_named_fap_stays_basic_not_physician(self):
  s=h.classify_osm(dict(broad_function='healthcare',medical_class='fap_name_assertion',name='Азоматовский ФАП'))
  self.assertEqual([r[0] for r in s],[h.BASIC])
 def test_lab_and_child_polyclinic_not_universal_primary(self):
  for name in ['Детская поликлиника','Поликлиника Инвитро','Стоматологическая поликлиника']:
   s=h.classify_osm(dict(broad_function='healthcare',medical_class='polyclinic_name_assertion',name=name))
   self.assertEqual([r[0] for r in s],[h.UNSPECIFIED])
 def test_explicit_general_practice_is_labelled_proxy_evidence(self):
  s=h.classify_osm(self.row(healthcare_speciality='general;family_medicine'))
  self.assertEqual({r[0] for r in s},{h.BASIC,h.PHYSICIAN})
  self.assertTrue(all(r[1]=='mapped_explicit_general_practice' for r in s))
 def test_school_cabinet_is_not_public_healthcare(self):
  s=h.classify_osm(dict(broad_function='healthcare',medical_class='clinic_source_tag',name='Медкабинет МБОУ СОШ №1'))
  self.assertEqual(s,[])
 def test_lifecycle_removal_and_na(self):
  self.assertIn('demolished:healthcare',h.lifecycle_reason({'tags_json':'{"demolished:healthcare":"clinic"}'}))
  self.assertEqual(h.lifecycle_reason({'inactive_source_assertion':float('nan')}),'')
 def test_np_union_does_not_count_multiple_sites_as_mass(self):
  official=pd.DataFrame([dict(provider_id='registry:a',source_record_id='a',service_code=h.BASIC,source_id='registry',source_year='2026',service_basis='licensed')])
  physical=pd.DataFrame([dict(provider_id='map:1',source_record_id='a',service_code=h.BASIC,supply_status='proxy',source_id='map',source_year=2026,evidence_quality='mapped_named_fap',service_basis='name',source_object_id='OSM:node:1')])
  reference=pd.DataFrame([dict(source_record_id='a',name='A',region='r',lat=1.,lon=2.,population_role='ordinary_settlement_record',ordinary_spatial_2021=True)])
  result,evidence=h.combined_np_supply(official,physical,reference)
  self.assertEqual(len(result),1);self.assertEqual(len(evidence),2)
  self.assertEqual(result.supply_status.iloc[0],'observed');self.assertFalse(result.default_external_seed_eligible.iloc[0])
  self.assertTrue(result.local_supply_eligible.iloc[0])
 def test_hightech_needs_literal_and_active_licence(self):
  base=dict(source_record_id='a',object_id='obj',source_id='registry',source_year='2026',source_part='x',source_row=1,subdivision_name='Больница',activity_address='село A',care_conditions_literal='Стационарно',care_profile_literal='хирургия',service_codes='medical_specialized',registered_exclusion_present=False,source_year_conflict_with_inventory=False)
  records=[dict(base,care_type_literal='специализированная медицинская помощь'),dict(base,object_id='high',care_type_literal='высокотехнологичная медицинская помощь'),dict(base,object_id='closed',source_record_id='b',registered_exclusion_present=True,care_type_literal='высокотехнологичная медицинская помощь')]
  source=pd.DataFrame(records)
  official=pd.DataFrame(columns=['provider_id','source_record_id','service_code','supply_status','source_id','source_year','service_basis'])
  result,evidence=h.higher_official_evidence(official,source)
  self.assertEqual(result.source_record_id.tolist(),['a'])
  self.assertEqual(result.service_code.tolist(),['medical_hightech_licensed'])
  self.assertEqual(evidence.literal_hightech_licensed_profile.sum(),1)
 def test_named_hospital_alias_is_not_independent_verified_service(self):
  original=pd.DataFrame([dict(source_medical_class='regional_hospital_name_assertion',service_code='mapped_hospital_service_unknown_level',source_object_id='OSM:way:4')])
  extra=h.higher_mapped_offers(original)
  self.assertEqual(extra.service_code.tolist(),['mapped_regional_hospital_named'])
  self.assertFalse(extra.counts_as_independent_service_channel.any())
 def test_fsins_access_comes_from_operator_or_org_not_street(self):
  self.assertTrue(h.explicit_restricted_scope('Поликлиника МСЧ-43','ФСИН России'))
  self.assertTrue(h.explicit_restricted_scope('Центр реабилитации','Медико-санитарная часть Федеральной службы исполнения наказаний'))
  self.assertFalse(h.explicit_restricted_scope('Меркульево воинская часть фельдшерско-акушерский пункт','ГБУЗ Брянская ЦРБ'))
 def test_federal_explicit_address_without_census_coordinate(self):
  reference=pd.DataFrame([dict(root='r',source_record_id='spb',name='Санкт-Петербург',region='санкт петербург',lat=float('nan'),lon=float('nan')),dict(root='other',source_record_id='o',name='Деревня',region='ленинградская',lat=59.9,lon=30.2)])
  legacy=pd.DataFrame([dict(id='legacy',root='other',source_record_id_2021='o',name='Деревня',region='ленинградская',lat=59.9,lon=30.2)])
  objects=pd.DataFrame([dict(object_id='OSM:node:1',baseline_uid=None,source_address_locality='Санкт-Петербург',link_status='coordinate_candidate_le10km_not_identity_accepted',lat=59.95,lon=30.3,start_date=None,end_date=None,source_snapshot_date='2026-10-19',addr_city='Санкт-Петербург',addr_region=None,tags_json='{}',inactive_source_assertion=False)])
  r=h.attach_osm(objects,reference,legacy)
  self.assertEqual(r.source_record_id.iloc[0],'spb');self.assertIn('not_proximity',r.np_identity_basis.iloc[0])
  self.assertTrue(pd.isna(reference.loc[0,'lat']))


if __name__=='__main__':unittest.main()

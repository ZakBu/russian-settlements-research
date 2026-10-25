import unittest
import pandas as pd
from scripts.sgrt_zero.health import primary_unit_scope_flags, classify_osm, BASIC, PHYSICIAN, UNSPECIFIED
from scripts.sgrt_zero.medical_scope import federal_child_unit_witnesses
from scripts.sgrt_zero.federal_medical_functions import classify_row
E={'V008':{'12':'первичная врачебная медико-санитарная помощь'},'V006':{'3':'Поликлиника'},'V002':{'97':'терапии'}}
class LiteralUnitSemanticsTests(unittest.TestCase):
 def test_womens_therapist_cannot_become_universal_general(self):
  for name,kind in [('Женская консультация 3 Поликлинического отделения 2','Женские консультации'),('Кабинет врача-терапевта женской консультации','Терапевтические'),('Поликлиника','Женские консультации')]:
   with self.subTest(name=name):
    r=classify_row(dict(NAM_SPMO=name,VID_SPMO=kind,organization_name='Городская больница',MPVID='12',MPUSL='3',MPROF='97'),E)
    self.assertNotIn(PHYSICIAN,r['service_codes'])
 def test_direct_psychiatric_tag_overrides_generic_polyclinic(self):
  row=dict(broad_function='healthcare',medical_class='polyclinic_name_assertion',name='Республиканская психотерапевтическая поликлиника',healthcare_speciality='psychiatry')
  self.assertEqual([s[0] for s in classify_osm(row)],[UNSPECIFIED])
 def test_mixed_explicit_general_specialty_survives(self):
  row=dict(broad_function='healthcare',medical_class='polyclinic_name_assertion',name='Поликлиника',healthcare_speciality='general;psychiatry')
  self.assertEqual({s[0] for s in classify_osm(row)},{BASIC,PHYSICIAN})
 def test_named_psychoneurologic_unit_correct_spelling_and_typo(self):
  for name in ['Психоневрологическая поликлиника','Психоневроогическая поликлиника']:
   with self.subTest(name=name):
    r=primary_unit_scope_flags(dict(subdivision_name=name))
    self.assertTrue(r['literal_narrow_primary_unit_scope'])
 def test_psych_hospital_parent_is_not_direct_polyclinic_specialty(self):
  # The parent's title alone does not turn a real general/GP subunit into
  # psychiatric care. This guards the new own-unit predicate, independently
  # of pre-existing conservative domain flags on a whole mixed label.
  from scripts.sgrt_zero.health import explicit_nongeneral_primary_unit
  for name in ['Поликлиника психоневроогического госпиталя ветеранов войн','Кабинет врача общей практики психоневрологической больницы']:
   self.assertFalse(explicit_nongeneral_primary_unit(name))
  r=classify_row(dict(NAM_SPMO='Кабинет врача общей практики психоневрологической больницы',VID_SPMO='Терапевтические',organization_name='Психиатрическая больница',MPVID='12',MPUSL='3',MPROF='97'),E)
  self.assertIn(PHYSICIAN,r['service_codes'])
 def test_fap_not_confused_with_womens_consultation(self):
  r=primary_unit_scope_flags(dict(subdivision_name='Фельдшерско-акушерский пункт села Преображенское'))
  self.assertFalse(r['literal_narrow_primary_unit_scope'])
  self.assertTrue(r['positive_general_primary_unit_literal'])
 def test_parent_alone_does_not_exclude_true_general_unit(self):
  r=classify_row(dict(NAM_SPMO='Взрослая поликлиника',VID_SPMO='Поликлиники',organization_name='Психиатрическая больница',MPVID='12',MPUSL='3',MPROF='97'),E)
  self.assertIn(PHYSICIAN,r['service_codes'])
 def test_exact_child_type_witness_needs_oid_address_and_coherent_types(self):
  active=pd.DataFrame([dict(object_id='hit',subdivision_oid='oid1',activity_address='Город, ул. А, 1',source_year=2026),dict(object_id='other-address',subdivision_oid='oid1',activity_address='Город, ул. А, 2',source_year=2026),dict(object_id='mixed',subdivision_oid='oid2',activity_address='Город, ул. А, 1',source_year=2026),dict(object_id='historical',subdivision_oid='oid1',activity_address='Город, ул. А, 1',source_year=2021)])
  base=dict(source_snapshot_date='23.10.2026',record_validity_status='valid_at_snapshot',subdivision_exact_join=True,care_address_exact_pair_join=True,NAM_SPMO='Поликлиника',VID_SPMO='Детские поликлиники (отделения, кабинеты)',ADDR='Город, ул. А, 1',source_record_row='1')
  care=pd.DataFrame([dict(base,OID_SPMO='oid1'),dict(base,OID_SPMO='oid2'),dict(base,OID_SPMO='oid2',VID_SPMO='Взрослая поликлиника')])
  self.assertEqual(set(federal_child_unit_witnesses(active,care).object_id),{'hit'})
if __name__=='__main__':unittest.main()

import importlib.util
from pathlib import Path
import unittest
P=Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/federal_medical_functions.py';spec=importlib.util.spec_from_file_location('federal',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
E={'V008':{'11':'первичная доврачебная медико-санитарная помощь','12':'первичная врачебная медико-санитарная помощь','13':'первичная специализированная медико-санитарная помощь','3':'специализированная, в том числе высокотехнологичная, медицинская помощь','31':'специализированная медицинская помощь','32':'высокотехнологичная специализированная медицинская помощь','33':'телемедицинская специализированная помощь'},'V006':{'1':'Стационар','2':'Дневной стационар','3':'Поликлиника'},'V002':{'42':'лечебному делу','57':'общей врачебной практике','97':'терапии','68':'педиатрии'}}
class FunctionalTests(unittest.TestCase):
 def row(self,**kw):return dict(MPVID='12',MPUSL='3',MPROF='97',NAM_SPMO='Поликлиника',VID_SPMO='',organization_name='Гражданская РБ')|kw
 def codes(self,**kw):return m.classify_row(self.row(**kw),E)['service_codes'].split('|')
 def test_primary_specialized_is_not_rare_hospital(self):self.assertNotIn('medical_specialized',self.codes(MPVID='13'))
 def test_general_physician_needs_explicit12(self):
  self.assertIn('medical_physician_primary',self.codes());self.assertNotIn('medical_physician_primary',self.codes(MPVID='11',MPROF='42'))
 def test_aggregate_including_hightech_does_not_prove_hightech(self):
  self.assertNotIn('medical_hightech_licensed',self.codes(MPVID='3',MPUSL='1'));self.assertIn('medical_hightech_licensed',self.codes(MPVID='32',MPUSL='1'))
 def test_named_child_scope_survives_aggregate_family_profile(self):self.assertNotIn('medical_physician_primary',self.codes(NAM_SPMO='Детская поликлиника',MPROF='57'))
 def test_fsins_operator_removed_from_all_public_roles(self):self.assertEqual(self.codes(organization_name='МСЧ ФСИН',MPVID='32',MPUSL='1'),[''])
 def test_telemedicine_not_physical_stationary_offer(self):self.assertEqual(self.codes(MPVID='33',MPUSL='1'),[''])
 def test_explicit_inpatient_survives_unknown_profile(self):self.assertIn('medical_inpatient',self.codes(MPROF='unknown',MPUSL='1',MPVID='31'))
 def test_unknown_code_is_held(self):self.assertEqual(self.codes(MPROF='unknown'),[''])
 def test_ended_oms_participation_not_current_offer(self):self.assertEqual(self.codes(organization_oms_participation_ended_asof=True),[''])
 def test_child_inpatient_condition_is_not_universal_hospital(self):
  r=m.classify_row(self.row(MPVID='31',MPUSL='1',MPROF='68',NAM_SPMO='Детский стационар'),E)
  self.assertIn('medical_inpatient',r['service_codes']);self.assertTrue(r['named_child_only_contingent']);self.assertFalse(r['universal_hospital_suitability_verified']);self.assertFalse(r['general_adult_profile_evidence'])
 def test_generic_including_children_type_is_not_child_only(self):
  codes=self.codes(NAM_SPMO='Кабинет врача общей практики',VID_SPMO='Лечебно-профилактические медицинские организации. Поликлиники (в том числе детские), а также поликлиники государственной системы здравоохранения',MPROF='57')
  self.assertIn('medical_physician_primary',codes)
 def test_adult_unit_not_overruled_by_child_organization_title(self):self.assertIn('medical_physician_primary',self.codes(NAM_SPMO='Взрослая поликлиника',organization_name='Детская областная больница'))
 def test_geographic_detskoe_is_not_child_contingent(self):self.assertIn('medical_physician_primary',self.codes(NAM_SPMO='Амбулатория с. Детское',MPROF='57'))
 def test_child_adolescent_declensions_are_not_general_primary(self):
  for name in ['Центр восстановительного лечения детей','Кабинет помощи детям','Подростковый кабинет','Кабинет для несовершеннолетних','Отделение медицинской помощи детскому населению на дому','Консультативно-диагностическое отделение №1Детская поликлиника','БУГУЛЬМИНСКАЯ ДЕТ.БОЛЬНИЦА','Дет. поликлиника № 4','дет поликлиника','Поликлиника Детство','Школы и детсады','лечебный кабинет (дет сад) МОБУ Муринский ДСКВ']:
   with self.subTest(name=name):self.assertNotIn('medical_physician_primary',self.codes(NAM_SPMO=name))
 def test_unrelated_letter_sequence_is_not_child_scope(self):
  self.assertIn('medical_physician_primary',self.codes(NAM_SPMO='Поликлиника частных охранников и детективов'))
 def test_narrow_or_school_unit_cannot_inherit_whole_licence_primary(self):
  for name in ['Кабинет врача-хирурга','Кардиологическое отделение','Кабинет гастроэнтеролога','Отделение медицинской реабилитации','Диагностическое отделение','Центр амбулаторной онкологической помощи','Центр здоровья','Школа для больных сахарным диабетом','Кабинет Школы №1','Школа Черга','Отделение новорожденных','Кабинет школьного фельдшера №2','Эндокринологический центр','Инфекционный госпиталь','Хирургический корпус','Наркологический диспансер','Онкодиспансер филиал','Гинекология','Эндоскопический кабинет','Санаторий-профилакторий','Кабинет вакцинации']:
   with self.subTest(name=name):self.assertNotIn('medical_physician_primary',self.codes(NAM_SPMO=name))
 def test_general_units_and_geography_survive_unit_scope_check(self):
  for name in ['Фельдшерско-акушерский пункт','Терапевтическое отделение','Кабинет врача общей практики','Амбулатория ул. Школьная','Центр общей врачебной практики и диагностическое отделение','ОВП с. Питерка','СВА','Кабинет врача-терапевта','Участковый терапевт']:
   with self.subTest(name=name):self.assertIn('medical_physician_primary',self.codes(NAM_SPMO=name))
 def test_broad_profile_does_not_identify_unknown_unit_function(self):
  self.assertNotIn('medical_physician_primary',self.codes(NAM_SPMO='Подразделение №7',MPROF='97'))
 def test_care_type_checked_separately_after_address(self):
  self.assertNotIn('medical_physician_primary',self.codes(NAM_SPMO='Поликлиника (г. Александров, ул. Кубасова, д. 2)',VID_SPMO='Детские поликлиники (отделения, кабинеты)'))
 def test_specialist_unit_type_cannot_inherit_general_profile(self):
  self.assertNotIn('medical_physician_primary',self.codes(NAM_SPMO='Поликлиника',VID_SPMO='Офтальмологические',MPROF='97'))
 def test_explicit_general_type_can_identify_unnamed_unit(self):
  self.assertIn('medical_physician_primary',self.codes(NAM_SPMO='Подразделение №7',VID_SPMO='Врачебная амбулатория',MPROF='97'))
if __name__=='__main__':unittest.main()

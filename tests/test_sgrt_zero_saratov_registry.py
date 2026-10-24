import importlib.util
from pathlib import Path
import unittest
import pandas as pd
P=Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/saratov_registry.py'
spec=importlib.util.spec_from_file_location('saratov_registry',P);a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class SaratovTests(unittest.TestCase):
 def test_wrapped_clinical_compound_keeps_literal(self):
  self.assertEqual(a.clean('медико-\nсанитарная  помощь'),'медико-санитарная помощь')
 def test_parent_oid_repairs_carried_wrong_organization(self):
  def row(org,oid,sub):return {k:'' for k in a.FIELDS}|{'organization_name':org,'organization_oid':oid,'subdivision_oid':sub,'subdivision_name':'Поликлиника','organization_oid_consistent_with_subdivision':False}
  d=pd.DataFrame([row('РБ1','1','1.0.10'),row('РБ2','2','2.0.20'),row('РБ2','2','1.0.11'),row('РБ2','2','3.0.30')])
  r=a.repair_organizations(d)
  self.assertEqual(r.loc[2,'organization_name'],'РБ1');self.assertEqual(r.loc[3,'organization_name'],'')
  self.assertEqual(r.loc[3,'organization_identity_basis'],'parent_oid_known_organization_text_unresolved')
 def test_literal_selo_disambiguates_station_without_distance(self):
  ref=pd.DataFrame({'source_record_id':['selo','station'],'name':['Питерка']*2,'region':['саратовская']*2,'district':['Питерский муниципальный район']*2,'settlement_type_2021':['село','железнодорожный объект']})
  m=pd.DataFrame({'source_record_id':[None],'activity_address':['Саратовская область, Питерский район, с. Питерка, ул. Советская,42'],'source_region_literal':['Саратовская область'],'match_status':['ambiguous']})
  result=a.refine_typed_addresses(m,ref)
  self.assertEqual(result.iloc[0].source_record_id,'selo')
  m.loc[0,'activity_address']='Саратовская область, Питерский район, ж/д ст Питерка, ул. Вокзальная,1'
  self.assertEqual(a.refine_typed_addresses(m,ref).iloc[0].source_record_id,'station')
 def test_same_type_ambiguity_is_not_forced(self):
  ref=pd.DataFrame({'source_record_id':['a','b'],'name':['Ивановка']*2,'region':['саратовская']*2,'district':['Питерский район']*2,'settlement_type_2021':['село']*2})
  m=pd.DataFrame({'source_record_id':[None],'activity_address':['Саратовская область, Питерский район, с. Ивановка, д.1'],'source_region_literal':['Саратовская область'],'match_status':['ambiguous']})
  self.assertIsNone(a.refine_typed_addresses(m,ref).iloc[0].source_record_id)
 def test_house_does_not_define_village_type(self):
  self.assertEqual(a.literal_type_name('Саратовская область, ул. Центральная, д.42'),(None,None))
 def test_repair_reclassifies_and_drops_wrong_carried_fsins_scope(self):
  def row(org,oid,sub):return {k:'' for k in a.FIELDS}|{'organization_name':org,'organization_oid':oid,'subdivision_oid':sub,'subdivision_name':'Поликлиника','care_type_literal':'первичная врачебная медико-санитарная помощь','care_conditions_literal':'Амбулаторно','care_profile_literal':'терапии','service_codes':'medical_specialized'}
  d=pd.DataFrame([row('Гражданская РБ','1','1.0.1'),row('ФСИН','2','2.0.1'),row('ФСИН','2','1.0.2')])
  r=a.repair_organizations(d)
  self.assertFalse(r.iloc[2].explicit_restricted_scope)
  self.assertEqual(r.iloc[2].service_codes,'medical_basic_primary|medical_physician_primary')
  self.assertTrue(r.iloc[1].explicit_restricted_scope)
 def test_inherited_address_from_other_org_is_held(self):
  d=pd.DataFrame({'subdivision_oid':['1.0.1','2.0.2'],'activity_address_inherited':[False,True]})
  self.assertEqual(a.audit_subdivision_fields(d).address_inheritance_parent_oid_conflict.tolist(),[False,True])
 def test_named_child_polyclinic_with_lechebnoe_is_not_adult_offer(self):
  row={k:'' for k in a.FIELDS}|{'organization_name':'Гражданская РБ','organization_oid':'1','subdivision_oid':'1.0.1','subdivision_name':'Детское поликлиническое отделение №4','care_type_literal':'первичная врачебная медико-санитарная помощь','care_conditions_literal':'Амбулаторно','care_profile_literal':'педиатрии, лечебному делу'}
  result=a.repair_organizations(pd.DataFrame([row]))
  self.assertTrue(result.iloc[0].pediatric_only_signal)
  row['care_profile_literal']='педиатрии, терапии'
  self.assertTrue(a.repair_organizations(pd.DataFrame([row])).iloc[0].named_child_only_without_adult_profile)
  row['subdivision_name']='Взрослое и детское поликлиническое отделение'
  self.assertFalse(a.repair_organizations(pd.DataFrame([row])).iloc[0].named_child_only_without_adult_profile)
if __name__=='__main__':unittest.main()

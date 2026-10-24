import unittest,tempfile,contextlib,io
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.federal_medical_addresses import AddressMatcher,locality_components,run,compare_mirrors,type_agrees,identity_diagnostics

class FederalActualAddressTests(unittest.TestCase):
 def setUp(self):
  self.matcher=AddressMatcher(pd.DataFrame([
   dict(source_record_id='v1',name='Березовка',region='саратовская',district='Первый район',oktmo='12345678901',settlement_type_2021='село'),
   dict(source_record_id='v2',name='Березовка',region='саратовская',district='Второй район',oktmo='12345678902',settlement_type_2021='село'),
   dict(source_record_id='city',name='Саратов',region='саратовская',district='Саратов',oktmo='12345678903',settlement_type_2021='город'),
   dict(source_record_id='sal',name='Салехард',region='ямало ненецкий',district='Салехард',oktmo='12345678905',settlement_type_2021='город'),
   dict(source_record_id='nen',name='Нарьян-Мар',region='ненецкий',district='Нарьян-Мар',oktmo='12345678906',settlement_type_2021='город'),
   dict(source_record_id='kom',name='Коммунарка',region='москва',district='Москва',oktmo='12345678907',settlement_type_2021='поселок'),
   dict(source_record_id='mos',name='Москва',region='москва',district='Москва',oktmo='12345678904',settlement_type_2021='город')]))
 def test_homonym_requires_district(self):
  self.assertIsNone(self.matcher.one('Саратовская область, с. Березовка, ул. Лесная, д. 4')['source_record_id'])
  self.assertEqual(self.matcher.one('Саратовская область, Первый район, с. Березовка, ул. Лесная, д. 4')['source_record_id'],'v1')
 def test_dot_without_space_is_valid_locality(self):
  self.assertEqual(self.matcher.one('Саратовская область, г.Саратов, ул.Лесная, д.4')['source_record_id'],'city')
 def test_street_name_is_not_locality(self):
  self.assertIsNone(self.matcher.one('Саратовская область, ул. Саратов, д. 4')['source_record_id'])
 def test_city_type_mismatch_is_not_match(self):
  self.assertIsNone(self.matcher.one('Саратовская область, с. Саратов, ул. Лесная, д. 4')['source_record_id'])
 def test_no_region_is_not_assigned_from_jurisdiction(self):
  self.assertIsNone(self.matcher.one('с. Березовка, Первый район')['source_record_id'])
 def test_moscow_context_is_literal(self):
  self.assertEqual(self.matcher.one('г. Москва, ул. Лесная, д. 4')['source_record_id'],'mos')
 def test_yamal_is_not_additionally_nenets_region(self):
  self.assertEqual(self.matcher.one('Ямало-Ненецкий автономный округ, г. Салехард, ул. Лесная, д.4')['source_record_id'],'sal')
 def test_rural_types_must_agree(self):
  self.assertIsNone(self.matcher.one('Саратовская область, Первый район, д. Березовка')['source_record_id'])
 def test_federal_context_does_not_override_explicit_locality(self):
  self.assertEqual(self.matcher.one('г.Москва, п.Коммунарка, ул. Лесная, д.4')['source_record_id'],'kom')
 def test_ambiguous_st_abbreviation_not_forced_to_one_type(self):
  self.assertTrue(type_agrees('ст','станция'))
  self.assertTrue(type_agrees('ст','станица'))
  self.assertFalse(type_agrees('ст','село'))
 def test_house_number_not_village(self):
  self.assertEqual(locality_components('Саратовская область, д. 4'),[])
 def test_parent_institution_name_not_locality(self):
  self.assertIsNone(self.matcher.one('Саратовская область, ГБУЗ Саратовская районная больница')['source_record_id'])

 def test_identifier_leading_zeros_and_centroid_not_geocoded(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.parquet';reference=root/'ref.parquet'
   pd.DataFrame({'IDADDRESS':['000007'],'UIDMO':['01202600100'],'UIDSPMO':['01202600100001005'],'ADDR':['Саратовская область, г.Саратов, ул. Лесная, д.4']}).to_parquet(source)
   self.matcher.ref.to_parquet(reference)
   with contextlib.redirect_stdout(io.StringIO()):result=run(source,reference,root/'out')
   self.assertEqual(result.IDADDRESS.iloc[0],'000007')
   self.assertEqual(result.UIDSPMO.iloc[0],'01202600100001005')
   self.assertFalse(result.physical_coordinates_observed.iloc[0])
   self.assertFalse(result.default_external_seed_eligible.iloc[0])
 def test_legal_only_input_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.parquet';reference=root/'ref.parquet'
   pd.DataFrame({'JURADDRESS_ADDRESS':['Саратовская область, г.Саратов']}).to_parquet(source)
   self.matcher.ref.to_parquet(reference)
   with self.assertRaisesRegex(ValueError,'legal address'):
    run(source,reference,root/'out')

 def test_mirror_comparison_preserves_exact_compound_ids(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   a=pd.DataFrame({'UIDSPMO':['001','002'],'IDADDRESS':['0001','0002'],'ADDR':['A','B'],'ADDR_GAR':['g1','g2']})
   b=a.iloc[:1].copy();b['ADDR']='different'
   a.to_parquet(root/'a.parquet');b.to_parquet(root/'b.parquet')
   with contextlib.redirect_stdout(io.StringIO()):result=compare_mirrors(root/'a.parquet',root/'b.parquet',root/'out')
   self.assertEqual(result['pair_counts']['left_only'],1)
   self.assertEqual(result['pair_counts']['both'],1)
   self.assertEqual(result['common_address_literal_disagreement'],1)
   self.assertEqual(result['common_gar_disagreement'],0)

 def test_conflicting_gar_does_not_override_literal_np(self):
  frame=pd.DataFrame({'ADDR_GAR':['same','same',''],'source_record_id':['np1','np2',None]})
  out=identity_diagnostics(frame)
  self.assertEqual(out.source_record_id.tolist(),['np1','np2',None])
  self.assertEqual(out.gar_multiple_literal_np_conflict.tolist(),[True,True,False])
  self.assertEqual(out.provider_settlement_id.tolist(),['np1','np2',None])

if __name__=='__main__':unittest.main()

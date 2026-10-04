"""Finite checks for secondary-reported inclusion and no parent transfer."""
import csv, json, pathlib, unittest
import pyarrow.parquet as pq

OUT=pathlib.Path(__file__).parent
class KrasnodarInclusionScopeGuards(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.obs=pq.read_table(OUT/'scoped_primary_observations.parquet').to_pylist()
  cls.points=pq.read_table(OUT/'scoped_point_uses.parquet').to_pylist()
  cls.edges=pq.read_table(OUT/'accepted_typed_scope_edges.parquet').to_pylist()
  cls.schema=json.loads((OUT/'loader_schema.json').read_text())
  with (OUT/'current_parent_context_references.csv').open(encoding='utf-8',newline='') as f:cls.parents=list(csv.DictReader(f))
  cls.articles=json.loads((OUT/'secondary_article_evidence.json').read_text())
  cls.receipt=json.loads((OUT/'application_receipt.json').read_text())
 def test_parquet_schema_matches_accepted_talnakh_loader(self):
  tal=pathlib.Path('/workspace/settlements-work/continuation_20261004/root/accepted_talnakh_typed_scope')
  for f in ['scoped_primary_observations.parquet','scoped_point_uses.parquet','accepted_typed_scope_edges.parquet']:
   self.assertEqual(pq.read_schema(OUT/f).remove_metadata(),pq.read_schema(tal/f).remove_metadata())
 def test_exact_old_source_rows_and_statement_provenance(self):
  self.assertEqual(len(self.obs),2)
  byname={x['source_name_raw']:x for x in self.obs}
  self.assertEqual(byname['пгт Калинино']['source_record_id'],'2002:1_TOM_01_04.xls:0:4119')
  self.assertEqual(byname['пгт Калинино']['population'],34152)
  self.assertEqual(byname['пгт Пашковский']['source_record_id'],'2002:1_TOM_01_04.xls:0:4120')
  self.assertEqual(byname['пгт Пашковский']['population'],43077)
  for o in self.obs:
   self.assertEqual(o['observation_year'],2002)
   self.assertEqual(o['wikidata_P585_precision'],9)
   claim=json.loads(o['wikidata_P1082_raw_statement_json'])
   self.assertEqual(claim['id'],o['wikidata_claim_guid'])
   self.assertEqual(int(claim['mainsnak']['datavalue']['value']['amount']),o['population'])
   self.assertTrue(claim.get('references'))
   self.assertFalse(o['ordinary_NP_same_grain_identity'])
   self.assertFalse(o['current_native_code_binding'])
   self.assertFalse(o['national_additive'])
 def test_points_keep_different_provider_strength_and_no_current_binding(self):
  self.assertEqual(len(self.points),2)
  byqid={x['subject_physical_place_qid']:x for x in self.points}
  self.assertEqual(byqid['Q4347629']['provider_id'],'512382')
  self.assertTrue(byqid['Q4347629']['provider_identifier_binding_asserted'])
  self.assertEqual(byqid['Q4209579']['point_provider'],'Wikidata P625')
  self.assertFalse(byqid['Q4209579']['provider_identifier_binding_asserted'])
  self.assertTrue(all(not x['direct_historical_coordinate_measurement'] for x in self.points))
  self.assertTrue(all(not x['native_current_settlement_id_binding'] for x in self.points))
 def test_links_only_secondary_reported_scope_and_current_parent_is_context(self):
  self.assertEqual(len(self.edges),2)
  self.assertTrue(all(x['decision_status']=='accepted_secondary_reported_inclusion_scope' for x in self.edges))
  self.assertTrue(all(x['root_approval_basis_receipt_sha256']=='f9740680d1a26dbe0d1eea2537d785a6620b29947955e6a93c854c8a37b5b1c1' for x in self.edges))
  self.assertTrue(all(not x['ordinary_NP_same_grain_identity'] and not x['population_comparability_asserted'] and not x['parent_population_transfer'] for x in self.edges))
  self.assertEqual(len(self.parents),2)
  old=next(x for x in self.parents if x['context_role']=='separate_selected_Krasnodar_city_source_row')
  self.assertEqual(old['source_record_id'],'2002:1_TOM_01_04.xls:0:4113')
  self.assertEqual(int(old['population']),646175)
  current=next(x for x in self.parents if x['context_role']=='current_receiving_city_parent_reference_only')
  self.assertEqual(current['source_record_id'],'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46712')
  self.assertEqual(int(current['population']),1099344)
  self.assertTrue(all('No 2021' in self.articles[k]['verification'] or 'no legal' in self.articles[k]['verification'].lower() for k in self.articles))
  self.assertIn('never assign parent value',self.schema['current_parent_context']['action'])
if __name__=='__main__':unittest.main()

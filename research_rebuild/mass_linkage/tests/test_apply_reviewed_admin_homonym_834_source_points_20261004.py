import csv
import json
import unittest
from pathlib import Path

import pyarrow.parquet as pq

from research_rebuild.mass_linkage.apply_reviewed_admin_homonym_834_source_points_20261004 import old_scope_gate

OUT=Path('/workspace/settlements-work/continuation_20261004/root/accepted_admin_homonym_834_source_points_scope_reconciled')
BASE=Path('/workspace/settlements-work/continuation_20261004/root/accepted_type_false_zero_177_source_points/accepted_point_uses.parquet')
SEEDS=Path('/workspace/settlements-work/continuation_20261004/independent_review/admin_homonym_834_point_review/eligible_point_seedlist.csv')

class AdminHomonym834ApplicationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.receipt=json.loads((OUT/'receipt.json').read_text())
  cls.out=pq.ParquetFile(OUT/'accepted_point_uses.parquet')
  with SEEDS.open(encoding='utf-8-sig',newline='') as f:cls.seeds={r['target_source_record_id']:r for r in csv.DictReader(f)}

 def test_append_preserves_baseline_and_reports_nonoverlap(self):
  base=pq.ParquetFile(BASE)
  self.assertEqual(base.metadata.num_rows,415248)
  self.assertEqual(self.out.metadata.num_rows,417750)
  self.assertEqual(self.receipt['baseline_prefix_rows_verified'],415248)
  self.assertTrue(self.receipt['baseline_prefix_all_columns_equal'])
  self.assertEqual(self.receipt['baseline_seed_targets_already_pointed'],0)
  self.assertEqual(self.receipt['appended_direct_source_point_rows'],834)
  self.assertEqual(self.receipt['appended_retrospective_transfer_rows'],1668)
  self.assertEqual(self.receipt['transfer_holds'],0)

 def test_raw_source_point_is_chosen_and_gn_is_only_witness(self):
  add=pq.read_table(OUT/'accepted_point_uses.parquet',columns=[
   'target_source_record_id','target_year','latitude','longitude','coordinate_source_file',
   'coordinate_source_sha256','coordinate_source_locator','point_origin_file','point_origin_sha256',
   'point_origin_locator','application_inference_kind','coordinate_provenance','coordinate_provider_id',
  ]).slice(415248).to_pylist()
  direct=[r for r in add if r['application_inference_kind']=='direct_reviewed_current_point_seed']
  self.assertEqual(len(direct),834)
  mismatch_to_gn=0
  for r in direct:
   seed=self.seeds[r['target_source_record_id']]
   self.assertEqual(float(r['latitude']),float(seed['source_raw_latitude']))
   self.assertEqual(float(r['longitude']),float(seed['source_raw_longitude']))
   self.assertEqual(float(r['latitude']),float(seed['proposed_coordinate_latitude']))
   self.assertTrue(r['point_origin_file'].endswith('data_allsettlements_anon_156_v20251217.parquet'))
   self.assertEqual(r['point_origin_sha256'],'86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14')
   self.assertIn('parquet_row_1based=',r['point_origin_locator'])
   self.assertEqual(r['coordinate_source_file'],r['point_origin_file'])
   self.assertEqual(r['coordinate_source_sha256'],r['point_origin_sha256'])
   self.assertIsNone(r['coordinate_provider_id'])
   self.assertIn('GeoNames witness ID',r['coordinate_provenance'])
   self.assertIn('is corroborating evidence only',r['coordinate_provenance'])
   mismatch_to_gn += int(float(r['latitude'])!=float(seed['geonames_latitude']) or float(r['longitude'])!=float(seed['geonames_longitude']))
  self.assertGreater(mismatch_to_gn,0)

 def test_2002_optional_scope_reconciliation_is_narrow_and_keeps_unknown(self):
  ev={'is_additive_settlement_record':True,'is_federal_aggregate':False,'legacy_same_year_collision':False,'legacy_verified_successor_settlement_id':None,'population_scope':None,'entity_grain_status':None}
  selected={'is_additive_settlement_record':True,'population_scope':None,'census_year':2002}
  proof={'historical_raw_row_checks_json':json.dumps([{'status':'raw_row_replayed','source_file':'/data/raw/2002/region.xls','raw_row_name_match':True,'raw_row_type_match':True,'raw_row_population_match':True}])}
  holds,basis=old_scope_gate(ev,selected,proof,2002)
  self.assertEqual(holds,[])
  self.assertIn('original unknown scope flag retained',basis)
  for altered in (
   {**ev,'is_additive_settlement_record':False},
   {**ev,'is_federal_aggregate':True},
   {**ev,'legacy_same_year_collision':True},
   {**ev,'legacy_verified_successor_settlement_id':'successor'},
   {**ev,'entity_grain_status':'municipal_total'},
  ):
   blocked,_=old_scope_gate(altered,selected,proof,2002)
   self.assertTrue(blocked)
  badproof={'historical_raw_row_checks_json':json.dumps([{'status':'raw_row_replayed','source_file':'/data/raw/2002/region.xls','raw_row_name_match':False,'raw_row_type_match':True,'raw_row_population_match':True}])}
  with self.assertRaises(ValueError):old_scope_gate(ev,selected,badproof,2002)

 def test_history_is_transfer_only_and_no_grain_or_boundary_claim_is_added(self):
  add=pq.read_table(OUT/'accepted_point_uses.parquet',columns=[
   'target_year','application_inference_kind','coordinate_provider_id','historical_measurement_claimed',
   'boundary_comparability_asserted','coordinate_admission_status','coordinate_uncertainty_flags_json',
  ]).slice(415248).to_pylist()
  old=[r for r in add if r['application_inference_kind']=='current_raw_source_point_retrospective_graph_continuity_inference']
  self.assertEqual(len(old),1668)
  self.assertEqual(sum(int(r['target_year'])==2002 for r in old),834)
  self.assertEqual(sum(int(r['target_year'])==2010 for r in old),834)
  for r in old:
   self.assertIsNone(r['coordinate_provider_id'])
   self.assertFalse(r['historical_measurement_claimed'])
   self.assertFalse(r['boundary_comparability_asserted'])
   self.assertEqual(r['coordinate_admission_status'],'reviewed_extension_rule_accepted')
  self.assertEqual(self.receipt['added_point_rows_and_population_by_year'],{
   '2002':{'rows':834,'population':120253.0},
   '2010':{'rows':834,'population':110553.0},
   '2021':{'rows':834,'population':100507.0},
  })

if __name__=='__main__':unittest.main()

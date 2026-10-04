import csv
import hashlib
import json
import unittest
from pathlib import Path

LAYER = Path(__file__).parent
REV = LAYER.parent / 'ukraine2001_to_2014_temporal_rule_independent_review'

def read_csv(name):
    with open(LAYER / name, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

class AcceptedUkraine2001ScopeLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads((LAYER / 'receipt.json').read_text(encoding='utf-8'))
        cls.obs = read_csv('accepted_2001_primary_observations.csv')
        cls.edges = read_csv('accepted_scoped_identity_edges.csv')
        cls.points = read_csv('accepted_retrospective_point_uses.csv')
        cls.paths = read_csv('accepted_available_year_paths.csv')
        cls.wd = read_csv('preserved_wikidata_secondary_alternatives.csv')

    def test_source_population_date_and_grain_are_preserved(self):
        self.assertEqual(len(self.obs), 27)
        self.assertEqual(sum(int(x['population_value']) for x in self.obs), 845627)
        self.assertTrue(all(x['reference_date'] == '2001-12-05' for x in self.obs))
        self.assertTrue(all(x['population_measure'] == 'present_population' for x in self.obs))
        self.assertTrue(all('Table 5' in x['source_locator'] for x in self.obs))
        self.assertTrue(all(x['source_has_native_locality_code'] == 'False' for x in self.obs))
        self.assertTrue(all(x['native_2001_code_binding_asserted'] == 'False' for x in self.obs))
        self.assertTrue(all(x['population_boundary_comparability_asserted'] == 'False' for x in self.obs))

    def test_each_observation_has_a_scoped_path_and_real_current_entity(self):
        self.assertEqual(len(self.edges), 27)
        self.assertEqual(len(self.paths), 27)
        self.assertEqual(len({x['entity_id'] for x in self.obs}), 27)
        self.assertEqual(len({x['source_record_id'] for x in self.obs}), 27)
        self.assertTrue(all(x['decision_status'] == 'accepted_root_approved_independent_review' for x in self.edges))
        obs_by_source = {x['source_record_id']: x for x in self.obs}
        self.assertTrue(all(x['current_entity_id'] == obs_by_source[x['source_record_id_2001']]['entity_id'] for x in self.paths))
        self.assertTrue(all(x['mapping_status'] == 'already_present_in_frozen_long_baseline_not_newly_admitted' for x in self.paths))
        self.assertTrue(all(x['strict_Russian_2002_2010_2021_chain'] == 'False' for x in self.paths))
        with open(REV / 'independently_eligible_edge_recommendations.csv', encoding='utf-8', newline='') as f:
            independent = list(csv.DictReader(f))
        got = {(x['from_source_record_id'], x['to_source_record_id']) for x in self.edges}
        want = {(x['source_record_id_2001'], x['source_record_id_2014']) for x in independent}
        self.assertEqual(got, want)

    def test_retrospective_points_never_claim_a_2001_measurement(self):
        self.assertEqual(len(self.points), 27)
        self.assertTrue(all(x['point_use_status'] == 'accepted_retrospective_current_representative_point_context' for x in self.points))
        self.assertTrue(all(x['coordinate_measurement_date_unknown'] == 'True' for x in self.points))
        self.assertTrue(all(x['historical_2001_coordinate_measurement'] == 'False' for x in self.points))
        self.assertTrue(all(x['point_coordinates_claimed_as_census_date_measurement'] == 'False' for x in self.points))
        self.assertTrue(all(x['boundary_comparability_asserted'] == 'False' for x in self.points))
        self.assertTrue(all(x['point_use_admission_changed_current_coordinate_record'] == 'False' for x in self.points))
        with open(REV / 'retrospective_current_point_use_recommendations.csv', encoding='utf-8', newline='') as f:
            candidates = list(csv.DictReader(f))
        self.assertEqual(len(candidates), 27)
        self.assertEqual({x['point_origin_sha256'] for x in self.points}, {x['point_origin_sha256'] for x in candidates})

    def test_secondary_wikidata_assertions_are_referenced_as_alternatives(self):
        self.assertEqual(len(self.wd), 27)
        obs_by_id = {x['source_record_id']: x for x in self.obs}
        for row in self.wd:
            accepted = obs_by_id[row['source_record_id_2001']]
            self.assertEqual(row['statement_guid'], accepted['source_secondary_WD_P1082_statement_guid'])
            self.assertEqual(row['population_raw'], accepted['source_secondary_WD_P1082_raw'])
            self.assertEqual(accepted['source_secondary_WD_claim_is_alternative_not_replacement'], 'True')
            self.assertEqual(accepted['source_secondary_WD_population_value_overwrote_primary'], 'False')

    def test_ninth_current_ids_are_not_mistaken_for_russian_2002_2010_links(self):
        c = self.receipt['counts']
        self.assertEqual(c['current_entity_ids_unchanged_in_ninth_core'], 27)
        self.assertEqual(c['ninth_graph_edges_touching_these_2021_ids'], 0)
        self.assertEqual(c['ninth_graph_edges_touching_these_current_ids_and_2002_or_2010'], 0)
        self.assertEqual(c['strict_Russian_2002_2010_2021_gains'], 0)
        self.assertEqual(c['canonical_graph_or_point_ledgers_modified'], False)

    def test_receipt_hashes_match_outputs(self):
        for filename, meta in self.receipt['outputs'].items():
            self.assertEqual(digest(LAYER / filename), meta['sha256'], filename)
        # Accepted source IDs and point recommendations remain pinned to the reviewed candidate packet.
        self.assertEqual(self.receipt['inputs'][str(REV / 'independent_review_receipt.json')], 'dba3dac13b73bee3b8de3389eabdc51d32fea67d9bade69dbe57791f25f3ac89')

if __name__ == '__main__':
    unittest.main()

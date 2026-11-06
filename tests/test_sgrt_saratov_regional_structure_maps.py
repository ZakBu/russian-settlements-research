import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd
import shapely
from shapely.geometry import box

from scripts.sgrt_saratov.regional_structure_maps import (
    common_supported_cohort, core_attributes, export_scenario, site_membership, voronoi_base,
)


class NodalCartograms(unittest.TestCase):
    def test_coincident_different_basins_are_mixed_not_lexical_winner(self):
        rows = pd.DataFrame([
            {'source_record_id': 'A', 'basin_id': 'one', 'core_id': 'A',
             'status': 'resolved_regional_peak', 'assignment_unique': True},
            {'source_record_id': 'B', 'basin_id': 'two', 'core_id': 'B',
             'status': 'resolved_regional_peak', 'assignment_unique': True},
        ])
        basin, core, status, selected = site_membership(['A', 'B'], rows)
        self.assertIsNone(basin)
        self.assertIsNone(core)
        self.assertIn('ambiguous', status)
        self.assertEqual(set(selected.source_record_id), {'A', 'B'})

    def test_unknown_and_halo_sites_remain_individual_and_geometry_keeps_points(self):
        roster = pd.DataFrame([
            {'source_record_id': i, 'name': i, 'lon': x, 'lat': y,
             'population_2021': 100, 'settlement_type_2021': 'село'}
            for i, x, y in [('A',45.1,51.1),('B',45.9,51.1),
                            ('C',45.1,51.9),('D',45.9,51.9)]])
        base = voronoi_base(roster, box(45,51,46,52))
        rows = pd.DataFrame([
            {'scenario_id': 'test', 'source_record_id': i,
             'basin_id': 'one' if i in {'A','B'} else None,
             'core_id': 'A' if i in {'A','B'} else None,
             'status': 'resolved_regional_peak' if i in {'A','B'} else
                       'external_halo_exit' if i=='C' else 'unknown_field',
             'assignment_unique': True}
            for i in ['A','B','C','D']])
        with tempfile.TemporaryDirectory() as tmp:
            summary = export_scenario(rows, base, {'A': {'class_index': 4,
                'core_name':'A'}}, tmp, tolerance_m=2000)
            features = json.loads((Path(tmp)/'test.geojson').read_text())['features']
        self.assertEqual(summary['resolved_display_basins'], 1)
        self.assertEqual(summary['neutral_individual_cells'], 2)
        self.assertEqual(len(features), 3)
        self.assertEqual(summary['attempts'][-1]['displaced_sampled_sites'], 0)
        self.assertTrue(all(base['region'].covers(shapely.from_geojson(json.dumps(f['geometry'])))
                            for f in features))
        self.assertTrue(all(not f['properties']['geometry_is_transport_isochrone'] for f in features))

    def test_zero_known_functions_is_separate_from_missing_evidence_rows(self):
        roster = pd.DataFrame([
            {'source_record_id':'A','name':'A','population_2021':20,'settlement_type_2021':'село'},
            {'source_record_id':'B','name':'B','population_2021':30,'settlement_type_2021':'село'}])
        links = pd.DataFrame([{'origin_id':'A','family':f,'evidence_scenario':'all_dated_known',
                               'known_local_supply':False}
                              for f in ['school','medical_basic','grocery']])
        result = core_attributes(roster, links)
        self.assertEqual(result['A']['class_index'], 4)
        self.assertFalse(result['A']['zero_known_functions_is_absence'])
        self.assertIsNone(result['B']['class_index'])

    def test_sampled_peak_without_comparators_is_assigned_but_not_supported(self):
        rows = pd.DataFrame([{'source_record_id': 'A', 'basin_id': 'one', 'core_id': 'A',
            'status': 'sampled_peak_without_nonself_comparators', 'assignment_unique': True,
            'terminal_has_nonself_comparison_support': False}])
        basin, core, status, selected = site_membership(['A'], rows)
        self.assertEqual((basin, core), ('one', 'A'))
        self.assertEqual(status, 'sampled_peak_without_nonself_comparators')
        self.assertFalse(selected.terminal_has_nonself_comparison_support.iloc[0])

    def test_paired_drawings_exclude_unsupported_points_on_both_sides(self):
        original = pd.DataFrame([
            {'scenario_id':'ascent','source_record_id':'A','assignment_unique':True,
             'status':'resolved_regional_peak'},
            {'scenario_id':'ascent','source_record_id':'B','assignment_unique':True,
             'status':'sampled_peak_without_nonself_comparators'}])
        control = pd.DataFrame([
            {'scenario_id':'nearest','source_record_id':'A','assignment_unique':True,
             'status':'resolved_regional_peak'},
            {'scenario_id':'nearest','source_record_id':'B','assignment_unique':True,
             'status':'resolved_regional_peak'}])
        before = original.copy(deep=True)
        self.assertEqual(common_supported_cohort(original, control, 'ascent', 'nearest'), {'A'})
        pd.testing.assert_frame_equal(original, before)


if __name__ == '__main__':
    unittest.main()

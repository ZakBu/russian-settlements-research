import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from scripts.sgrt_saratov.coordinate_cost_correction import (
    run, sha, origins, corrected_costs, check_derived_overlay, GRAPH_SHA256,
)


class CoordinateCostCorrectionTests(unittest.TestCase):
    def fixtures(self):
        # All directed arcs exist, with deliberately asymmetric costs.
        weights = np.arange(36, dtype=float).reshape(6, 6) + 1.
        np.fill_diagonal(weights, 0.)
        graph = csr_matrix(weights)
        before = pd.DataFrame({'source_record_id': ['a', 'b', 'c', 'd', 'u'],
            'population_2021': [100., 200., 30., 10., 4.],
            'credit_2021': [True]*5, 'base_lat': [50.]*5, 'base_lon': [45.]*5,
            'lat': [50.]*5, 'lon': [45.]*5,
            'road_node_index': [0., 1., 2., 5., np.nan],
            'snap_km': [.1, .2, .3, .4, np.nan],
            'accepted_source_endpoint': [True]*4+[False]})
        after = before.copy()
        after.loc[0, ['road_node_index', 'lat', 'lon', 'snap_km']] = [3., 51., 46., .05]
        after.loc[1, ['road_node_index', 'lat', 'lon', 'snap_km']] = [4., 52., 47., .07]
        after['pilot_geography_correction_applied'] = [True, True, False, False, False]
        return graph, before, after

    def test_population_and_other_points_cannot_change_under_point_overlay(self):
        _, before, after = self.fixtures()
        check_derived_overlay(before, after, {'a', 'b'}, 'test')
        bad = after.copy()
        bad.loc[0, 'population_2021'] = 999.
        with self.assertRaisesRegex(ValueError, 'population_2021'):
            check_derived_overlay(before, bad, {'a', 'b'}, 'test')
        bad = after.copy()
        bad.loc[2, 'lat'] += .1
        with self.assertRaisesRegex(ValueError, '.lat'):
            check_derived_overlay(before, bad, {'a', 'b'}, 'test')
        bad = after.iloc[::-1].reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, 'axis changed'):
            check_derived_overlay(before, bad, {'a', 'b'}, 'test')

    def test_two_changed_points_intersections_direction_connectors_and_unknown(self):
        graph, _, after = self.fixtures()
        origin = after.iloc[[0, 1, 2, 4]].reset_index(drop=True)
        dest = after.iloc[:4].copy()
        dest['destination_connector_minutes'] = 4*dest.snap_km
        rows, columns = corrected_costs(graph, origin, dest, {'a', 'b'})
        self.assertEqual(set(rows), {0, 1})
        self.assertEqual(set(columns), {0, 1})
        self.assertTrue(all(np.isnan(c[3]) for c in columns.values()))
        self.assertEqual(rows[0][0], 0.)
        self.assertEqual(rows[1][1], 0.)
        expected = dijkstra(graph, directed=True, indices=3)[4]+4*.07+4*.05
        self.assertAlmostEqual(rows[0][1], expected)
        self.assertAlmostEqual(columns[1][0], expected)
        self.assertNotEqual(rows[0][1], rows[1][0])

    def test_complete_patch_adds_halo_preserves_all_unrelated_costs_and_old_cache(self):
        graph, before, after = self.fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, new, cache, out = [root/name for name in ('old', 'new', 'cache', 'out')]
            for folder in (old, new, cache):
                folder.mkdir()
            for folder, table, halo_indices in ((old, before, [2]), (new, after, [2, 3])):
                table.to_parquet(folder/'national_reference_with_endpoints.parquet', index=False)
                table.iloc[[0, 1, 4]].to_parquet(folder/'regional_roster.parquet', index=False)
                halo = table.iloc[halo_indices].copy()
                halo['row_index'] = np.arange(len(halo))
                halo.to_parquet(folder/'halo_roster.parquet', index=False)
                dest = table.iloc[:4].copy()
                dest['destination_index'] = np.arange(4)
                dest['destination_connector_minutes'] = 4*dest.snap_km
                dest.to_parquet(folder/'destinations.parquet', index=False)
            old_origins = origins(old)
            old_dest = pd.read_parquet(old/'destinations.parquet')
            matrix = np.full((4, 4), np.nan)
            for i, row in old_origins.iterrows():
                if row.accepted_source_endpoint:
                    matrix[i] = (dijkstra(graph, directed=True, indices=int(row.road_node_index))[
                        old_dest.road_node_index.to_numpy(int)]+old_dest.destination_connector_minutes.to_numpy()+4*row.snap_km)
                    matrix[i, old_dest.source_record_id.eq(row.source_record_id)] = 0.
            np.save(cache/'full_destination_costs.npy', matrix)
            old_origins[['full_row_index', 'source_record_id', 'origin_scope', 'accepted_source_endpoint']].to_parquet(cache/'origin_axis.parquet', index=False)
            old_dest[['destination_index', 'source_record_id']].to_parquet(cache/'destination_axis.parquet', index=False)
            contract = {'graph_sha256': GRAPH_SHA256, 'shape': [4, 4],
                'producer_module_sha256': 'original-cost-producer',
                'reference_sha256': sha(old/'national_reference_with_endpoints.parquet'),
                'regional_roster_sha256': sha(old/'regional_roster.parquet'),
                'halo_roster_sha256': sha(old/'halo_roster.parquet'),
                'destinations_sha256': sha(old/'destinations.parquet')}
            (cache/'contract.json').write_text(json.dumps(contract))
            (cache/'complete.json').write_text(json.dumps({'complete': True}))
            pd.DataFrame({'source_record_id': ['a', 'b'], 'expected_lat': [50., 50.],
                'expected_lon': [45., 45.], 'corrected_lat': [51., 52.],
                'corrected_lon': [46., 47.]}).to_csv(root/'overlay.csv', index=False)
            with patch('scripts.sgrt_saratov.coordinate_cost_correction.load_graph', return_value=graph):
                result = run(old, new, cache, root, root/'overlay.csv', out)
            fixed = np.load(cache/'full_destination_costs.npy')
            self.assertEqual(fixed.shape, (5, 4))
            self.assertTrue(result['unrelated_shared_costs_exactly_unchanged'])
            self.assertEqual(result['corrected_forward_rows'], 3)
            self.assertEqual(result['corrected_reverse_columns'], 2)
            self.assertEqual(result['new_halo_origin_ids'], ['d'])
            np.testing.assert_array_equal(np.load(cache/'full_destination_costs_before_coordinate_overlay.npy'), matrix)
            new_origins = origins(new)
            dest = pd.read_parquet(new/'destinations.parquet')
            for i, row in new_origins.iterrows():
                if not row.accepted_source_endpoint:
                    self.assertTrue(np.isnan(fixed[i]).all())
                    continue
                expected = (dijkstra(graph, directed=True, indices=int(row.road_node_index))[
                    dest.road_node_index.to_numpy(int)]+dest.destination_connector_minutes.to_numpy()+4*row.snap_km)
                expected[dest.source_record_id.eq(row.source_record_id)] = 0.
                np.testing.assert_allclose(fixed[i], expected, rtol=1e-11, atol=1e-7)
            self.assertEqual(json.loads((cache/'contract.json').read_text())['shape'], [5, 4])
            with self.assertRaisesRegex(ValueError, 'existing proof'):
                run(old, new, cache, root, root/'overlay.csv', out)


if __name__ == '__main__':
    unittest.main()

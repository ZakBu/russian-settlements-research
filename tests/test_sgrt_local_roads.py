"""Scientific regressions: identity, directed costs and unreachable endpoints."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

spec = importlib.util.spec_from_file_location(
    'local_roads', Path(__file__).resolve().parents[1]/'scripts/sgrt_local/roads.py')
roads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roads)


class RoadRegression(unittest.TestCase):
    def test_names_do_not_override_wrong_census_root_or_coordinates(self):
        frame = pd.DataFrame({
            'root': ['right-root', 'different-root', 'moved-root'],
            'source_record_id_2021': ['a', 'b', 'c'],
            'accepted_point_present_2021': [True]*3,
            'accepted_latitude_2021': [54., 54., 54.1],
            'accepted_longitude_2021': [59., 59., 59.],
        })
        legacy = pd.DataFrame({
            'root': ['right-root', 'old-root', 'moved-root'],
            'source_record_id_2021': ['a', 'b', 'c'],
            'id': ['old-a', 'old-b', 'old-c'],
            'lat': [54.]*3, 'lon': [59.]*3,
        })
        origin = pd.DataFrame({
            'id': ['old-a', 'old-b', 'old-c'],
            'road_node_index': [0, 1, 2], 'snap_km': [.01]*3,
            'weak_component': [0]*3, 'accepted_snap': [True]*3,
            'road_snap_lat': [54.]*3, 'road_snap_lon': [59.]*3,
            'network_source_timestamp_utc': [roads.SNAPSHOT]*3,
            'connector_scenario_kmh': [15]*3,
        })
        result = roads.bridge(frame, legacy, origin).set_index('source_record_id_2021')
        self.assertTrue(result.loc['a', 'road_endpoint_accepted'])
        self.assertFalse(result.loc['b', 'road_endpoint_accepted'])
        self.assertEqual(result.loc['b', 'road_endpoint_status'], 'no_exact_road_identity')
        self.assertFalse(result.loc['c', 'road_endpoint_accepted'])
        self.assertEqual(result.loc['c', 'road_endpoint_status'], 'census_coordinate_not_exact_road_point')

    def test_directed_network_connectors_and_missing_are_not_zero(self):
        frame = pd.DataFrame({
            'source_record_id': ['a', 'b', 'c'],
            'settlement_name_2021': ['A', 'B', 'C'],
            'requested_destination': [True]*3,
            'road_endpoint_accepted': [True]*3,
            'road_node_index': [0, 1, 2],
            'snap_km': [.1, .2, 0],
            'weak_component': [0, 0, 1],
            'connector_over_2km': [False]*3,
        })
        graph = csr_matrix(np.array([[0., 10., 0.], [20., 0., 0.], [0., 0., 0.]]))
        costs = roads.route(frame, graph).set_index(['origin_id', 'provider_id'])
        self.assertAlmostEqual(costs.loc[('a', 'b'), 'network_minutes'], 10.)
        self.assertAlmostEqual(costs.loc[('b', 'a'), 'network_minutes'], 20.)
        self.assertAlmostEqual(costs.loc[('a', 'b'), 'connector_minutes'], 1.2)
        self.assertAlmostEqual(costs.loc[('a', 'b'), 'cost_minutes'], 11.2)
        self.assertEqual(costs.loc[('a', 'a'), 'cost_minutes'], 0.)
        self.assertTrue(np.isnan(costs.loc[('a', 'c'), 'cost_minutes']))
        self.assertEqual(costs.loc[('a', 'c'), 'route_status'], 'disconnected_weak_components')

    def test_context_distance_uses_anchors_not_external_destination(self):
        frame = pd.DataFrame({
            'source_record_id_2021': ['a', 'b', 'c'],
            'accepted_point_present_2021': [True]*3,
            'accepted_latitude_2021': [54., 55., 55.01],
            'accepted_longitude_2021': [59.]*3,
        })
        requested = pd.DataFrame({'source_record_id': ['a', 'b'],
                                  'context_anchor': [True, False]})
        result = roads.census_frame(requested, frame, context_km=5)
        self.assertEqual(set(result.source_record_id), {'a', 'b'})


if __name__ == '__main__':
    unittest.main()

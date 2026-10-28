import math
import json
import tempfile
from pathlib import Path
import unittest

from shapely.geometry import box
from scripts.sgrt_saratov.independent_checks import (
    inbound_oracle, inbound_edge_fraction, reachable_segment, polygon_checks, counterexamples, heap_shortest_path,
    audit_np_coverage,
    inbound_polyline_piece, audit_native_polylines,
)


class IndependentRoadTests(unittest.TestCase):
    def test_inbound_is_not_outbound_in_asymmetric_network(self):
        edges = [(0, 1, 10), (1, 2, 10), (2, 1, 30), (1, 0, 40)]
        self.assertEqual(inbound_oracle(3, edges, 2, 3), [23, 13, 3])
        reverse = [(v, u, cost) for u, v, cost in edges]
        self.assertEqual(inbound_oracle(3, reverse, 2, 3), [73, 33, 3])

    def test_partial_directed_edge_starts_near_head(self):
        fraction = inbound_edge_fraction(13, 10, 18)
        self.assertEqual(fraction, 0.5)
        self.assertEqual(reachable_segment((0, 0), (10, 0), fraction), ((5.0, 0.0), (10, 0)))

    def test_partial_arc_follows_real_bend_not_endpoint_chord(self):
        curve = [(0, 0), (0, 10), (10, 10)]
        self.assertEqual(inbound_polyline_piece(curve, 0.5), ((0, 10), (10, 10)))
        self.assertEqual(inbound_polyline_piece(curve, 0.25), ((5, 10), (10, 10)))
        self.assertEqual(inbound_polyline_piece(curve, 1), tuple(curve))
        self.assertEqual(inbound_polyline_piece(curve, 0), ((10, 10),))

    def test_connector_can_exhaust_the_budget(self):
        self.assertEqual(inbound_edge_fraction(13, 10, 12), 0)
        self.assertEqual(inbound_oracle(2, [(0, 1, 5)], 1, 20), [25, 20])

    def test_unknown_is_not_confirmed_unreachable_or_zero(self):
        self.assertIsNone(inbound_edge_fraction(None, 10, 15))
        self.assertIsNone(inbound_edge_fraction(math.nan, 10, 15))
        self.assertEqual(inbound_edge_fraction(math.inf, 10, 15), 0)
        self.assertEqual(inbound_edge_fraction(0, 10, 15), 1)

    def test_zero_time_edges_and_negative_rejection(self):
        self.assertEqual(inbound_edge_fraction(5, 0, 5), 1)
        self.assertEqual(inbound_edge_fraction(6, 0, 5), 0)
        with self.assertRaises(ValueError):
            inbound_oracle(2, [(0, 1, -1)], 1)

    def test_original_direction_heap_and_disconnected(self):
        from scipy.sparse import csr_matrix
        graph = csr_matrix(([10.0, 10.0, 30.0, 40.0], ([0, 1, 2, 1], [1, 2, 1, 0])), shape=(4, 4))
        self.assertEqual(heap_shortest_path(graph, 0, 2)[0], 20)
        self.assertEqual(heap_shortest_path(graph, 2, 0)[0], 70)
        self.assertEqual(heap_shortest_path(graph, 2, 2)[0], 0)
        self.assertTrue(math.isinf(heap_shortest_path(graph, 0, 3)[0]))

    def test_hull_fills_an_unreachable_water_gap(self):
        example = counterexamples()
        self.assertTrue(example["hull_river_witness_inside_hull"])
        self.assertFalse(example["hull_river_witness_inside_road_corridor"])

    def test_nested_cumulative_and_disjoint_bands(self):
        p1, p2 = box(0, 0, 1, 1), box(0, 0, 2, 2)
        props = [{"centre_id": "a", "minutes": x} for x in (10, 20)]
        rows = polygon_checks(list(zip(props, [p1, p2])), list(zip(props, [p1, p2.difference(p1)])))
        self.assertFalse(any(row["violation"] for row in rows))

    def test_polygon_audit_detects_shrinking_and_band_overlap(self):
        large, small = box(0, 0, 3, 3), box(0, 0, 1, 1)
        props = [{"centre_id": "a", "minutes": x} for x in (10, 20)]
        rows = polygon_checks(list(zip(props, [large, small])), list(zip(props, [large, small])), area_tolerance=0)
        self.assertEqual(rows[1]["nonnested_area_m2"], 8)
        self.assertEqual(rows[1]["overlap_previous_bands_m2"], 1)
        self.assertTrue(rows[1]["violation"])

    def test_display_band_does_not_replace_exact_or_unknown_np_times(self):
        import pandas as pd
        from shapely.geometry import mapping
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            pd.DataFrame({"source_record_id": ["a", "b", "c", "d"], "name": ["A", "B", "C", "D"],
                          "lon": [45, 45.001, 45.002, None], "lat": [51, 51, 51, None]}).to_parquet(root/"np.parquet")
            pd.DataFrame({"source_record_id": ["a"]}).to_csv(root/"centres.csv", index=False)
            frame = pd.DataFrame({"origin_id": ["a", "b", "c", "d"], "centre_id": ["a"]*4,
                                  "time_minutes_total": [0, 15, None, None],
                                  "network_minutes": [0, 14, None, None],
                                  "origin_connector_minutes": [0.1, 0.5, None, None],
                                  "destination_connector_minutes": [0.5]*4})
            for budget in (10, 20, 30, 60):
                frame[f"within_{budget}min_exact_cost"] = frame.time_minutes_total.le(budget).where(frame.time_minutes_total.notna())
            frame.to_parquet(root/"times.parquet")
            (root/"cumulative.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
                {"type": "Feature", "properties": {"centre_id": "a", "minutes": 10},
                 "geometry": mapping(box(44.999, 50.999, 45.003, 51.001))}]}))
            result = audit_np_coverage(root/"np.parquet", root/"centres.csv", root/"times.parquet", root/"cumulative.geojson")
            self.assertEqual(result["errors"], [])
            row = result["rows"][0]
            self.assertEqual(row["exact_time_reachable_records"], 1)
            self.assertEqual(row["finite_time_inside_but_above_budget"], 1)
            self.assertEqual(row["unknown_time_inside_display"], 1)
            self.assertEqual(row["records_without_finite_coordinates"], 1)
            self.assertEqual(row["unknown_or_infinite_time_records"], 2)
            self.assertEqual(row["maximum_known_excess_inside_display_minutes"], 5)
            frame = pd.read_parquet(root/"times.parquet").iloc[:2]
            frame.to_parquet(root/"times.parquet")
            result = audit_np_coverage(root/"np.parquet", root/"centres.csv", root/"times.parquet", root/"cumulative.geojson")
            self.assertEqual(result["violations"], 1)
            self.assertEqual(result["expected_np_time_rows"], 4)
            self.assertEqual(result["actual_np_time_rows"], 2)


class OriginalSourceShapeTests(unittest.TestCase):
    def fixture(self, root, coordinates):
        import pandas as pd
        import shapely
        pd.DataFrame({"way_id": [1], "refs": [[11, 12, 13]], "speed_kmh": [30.], "oneway": [1]}).to_parquet(root/"ways.parquet")
        pd.DataFrame({"osm_id": [11, 12, 13], "lon": [45., 45., 45.01], "lat": [51., 51.01, 51.01]}).to_parquet(root/"nodes.parquet")
        # Compute a fixture's spherical length with an independent atan2 form.
        length = 0.
        for (x, y), (xx, yy) in zip(coordinates[:-1], coordinates[1:]):
            y, yy, dx = math.radians(y), math.radians(yy), math.radians(xx-x)
            angle = math.atan2(math.sqrt((math.cos(yy)*math.sin(dx))**2 + (math.cos(y)*math.sin(yy)-math.sin(y)*math.cos(yy)*math.cos(dx))**2), math.sin(y)*math.sin(yy)+math.cos(y)*math.cos(yy)*math.cos(dx))
            length += 6371.0088*angle
        pd.DataFrame({"way_id": [1], "u_osm": [11], "v_osm": [13], "geometry_crs": ["EPSG:4326"],
                      "native_geometry_wkb": [shapely.to_wkb(shapely.LineString(coordinates))],
                      "source_polyline_vertices": [len(coordinates)], "native_length_km": [length],
                      "edge_minutes": [length/30*60], "oneway": [1], "speed_kmh": [30.]}).to_parquet(root/"edges.parquet")

    def test_original_bend_and_independent_length_match(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, [(45., 51.), (45., 51.01), (45.01, 51.01)])
            result = audit_native_polylines(root/"edges.parquet", root/"ways.parquet", root/"nodes.parquet")
            self.assertEqual(result["violations"], 0)
            self.assertEqual(result["segments_with_intermediate_vertices"], 1)

    def test_chord_with_correct_endpoints_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, [(45., 51.), (45.01, 51.01)])
            result = audit_native_polylines(root/"edges.parquet", root/"ways.parquet", root/"nodes.parquet")
            self.assertEqual(result["violations"], 1)
            self.assertIn("complete ordered source slice", result["examples"][0]["problem"])


if __name__ == "__main__":
    unittest.main()

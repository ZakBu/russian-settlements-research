import math
import sys
from pathlib import Path
import unittest
import json
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/sgrt_field_pilot"))
from independent_checks import (counterexamples, plateau_maxima,
                                scalar_potential_bounds, strict_local_peaks, audit_pilot_output)


class ScalarReferenceTests(unittest.TestCase):
    def test_more_smoothing_can_create_an_additional_sampled_peak_on_a_tree(self):
        example = counterexamples()["peak_birth_on_symmetric_tree"]
        self.assertEqual([r["strict_peak_indices"] for r in example["scales"]],
                         [[3], [0, 3], [0]])

    def test_omitted_external_source_reverses_the_order_of_inner_locations(self):
        r = counterexamples()["external_source_changes_inner_ordering"]
        self.assertLess(*r["inner_potential_clipped_sources"])
        self.assertGreater(*r["inner_potential_all_three_sources"])

    def test_settlement_samples_do_not_locate_a_gaussian_peak_between_sources(self):
        r = counterexamples()["settlement_sampling_misses_nonsettlement_peak"]
        self.assertGreater(r["at_unpopulated_midpoint"], r["at_either_settlement"])

    def test_complete_outgoing_neighbor_coverage_does_not_complete_union_graph(self):
        r = counterexamples()["outgoing_coverage_does_not_cover_incoming_union_edges"]
        self.assertEqual(r["sampled_peak_indices"], [1])
        self.assertEqual(r["global_union_peak_indices"], [2])
        for i in r["sampled_evaluation_indices"]:
            self.assertTrue(all(j in r["sampled_evaluation_indices"]
                                for j in r["global_outgoing_nearest_neighbors"][i]))

    def test_equal_adjacent_maxima_form_one_plateau_without_row_tie_break(self):
        values, graph = [3.0, 3.0, 1.0], [[1], [0, 2], [1]]
        self.assertEqual(strict_local_peaks(values, graph), [])
        self.assertEqual(plateau_maxima(values, graph), [[0, 1]])

    def test_reordering_preserves_plateau_membership(self):
        values = [3.0, 1.0, 3.0]
        graph = [[2], [2], [0, 1]]
        self.assertEqual(plateau_maxima(values, graph), [[0, 2]])

    def test_unknown_route_is_an_interval_not_a_zero_contribution(self):
        rows = scalar_potential_bounds([[0, None], [None, 0]], [10, 20], 3)
        self.assertEqual([(r["lower"], r["upper"]) for r in rows], [(10, 30), (20, 30)])
        self.assertTrue(all(not r["point_value_known"] for r in rows))

    def test_unknown_mass_is_not_imputed_to_zero(self):
        rows = scalar_potential_bounds([[0, 1], [1, 0]], [10, None], 3)
        self.assertTrue(all(math.isinf(r["upper"]) for r in rows))
        self.assertTrue(all(not r["point_value_known"] for r in rows))

    def test_directed_travel_times_are_retained(self):
        rows = scalar_potential_bounds([[0, 1], [10, 0]], [10, 10], 1)
        self.assertGreater(rows[0]["lower"], rows[1]["lower"])

    def test_self_exclusion_changes_the_object_not_the_source_population(self):
        times = [[0, 1], [1, 0]]
        masses = [100, 1]
        own = scalar_potential_bounds(times, masses, 1)
        external = scalar_potential_bounds(times, masses, 1, include_self=False)
        self.assertAlmostEqual(own[0]["lower"] - external[0]["lower"], 100)
        self.assertAlmostEqual(own[1]["lower"] - external[1]["lower"], 1)
        self.assertGreater(own[0]["lower"], own[1]["lower"])
        self.assertLess(external[0]["lower"], external[1]["lower"])
        self.assertEqual(masses, [100, 1])

    def test_disconnected_requires_explicit_infinity_and_is_not_unknown(self):
        rows = scalar_potential_bounds([[0, math.inf], [math.inf, 0]], [10, 20], 3)
        self.assertEqual([r["lower"] for r in rows], [10, 20])
        self.assertTrue(all(r["point_value_known"] for r in rows))

    def test_unknown_values_cannot_be_classified_as_peaks(self):
        with self.assertRaises(ValueError):
            plateau_maxima([1, math.nan], [[1], [0]])

    def test_bad_mass_and_scale_fail_instead_of_silent_repair(self):
        for masses in ([-1, 2], [math.nan, 2]):
            with self.assertRaises(ValueError):
                scalar_potential_bounds([[0, 1], [1, 0]], masses, 3)
        with self.assertRaises(ValueError):
            scalar_potential_bounds([[0]], [1], 0)


class SavedOutputCorruptionTests(unittest.TestCase):
    def fixture(self, path):
        import pandas as pd
        (path / "summary.json").write_text(json.dumps({"search_cutoff_minutes": 240,
            "known_positive_mass_without_accepted_endpoint": 0}))
        pd.DataFrame({"source_record_id": ["a", "b"], "source_mass_2021": [10, 20]}).to_parquet(path / "national_mass_sources.parquet")
        pd.DataFrame({"origin_id": ["a", "a", "b", "b"], "source_id": ["a", "b", "a", "b"],
                      "cost_minutes": [0., 1., 1., 0.], "source_population_2021": [10, 20, 10, 20]}).to_parquet(path / "routed_contributions.parquet")
        common = {"source_record_id": ["a", "b"], "pilot_id": ["p", "p"],
                  "kernel": ["exponential"] * 2, "half_time_minutes": [1.] * 2,
                  "include_self": [True] * 2}
        pd.DataFrame({**common, "known_routed_potential": [20., 25.],
                      "censored_routed_mass_potential_upper": [0., 0.],
                      "known_mass_potential_upper": [20., 25.],
                      "complete_population_field_upper": [math.nan, math.nan]}).to_parquet(path / "fields.parquet")
        pd.DataFrame({**common, "neighbor_count": [1, 1], "is_sampled_local_maximum": [False, True],
                      "is_certified_complete_field_peak": [False, False]}).to_parquet(path / "peaks.parquet")
        pd.DataFrame({"pilot_id": ["p"], "neighbor_count": [1], "source_id_a": ["a"],
                      "source_id_b": ["b"]}).to_parquet(path / "comparison_edges.parquet")
        pd.DataFrame({"origin_id": ["a", "a", "b", "b"], "destination_id": ["a", "b", "a", "b"],
                      "cost_minutes": [0., 1., 1., 0.]}).to_parquet(path / "evaluation_costs.parquet")

    def test_clean_saved_arithmetic_and_peaks_match_scalar_calculation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.fixture(path)
            result = audit_pilot_output(path)
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["field_rows_recomputed"], 2)
            self.assertEqual(result["peak_classification_disagreements"], 0)

    def test_mutated_potential_is_detected(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.fixture(path)
            fields = pd.read_parquet(path / "fields.parquet")
            fields.loc[0, "known_routed_potential"] += 1
            fields.to_parquet(path / "fields.parquet")
            self.assertIn("Scalar field differs from saved potential", audit_pilot_output(path)["errors"])

    def test_mutated_source_population_is_detected(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.fixture(path)
            routes = pd.read_parquet(path / "routed_contributions.parquet")
            routes.loc[0, "source_population_2021"] += 1
            routes.to_parquet(path / "routed_contributions.parquet")
            self.assertIn("Contribution population differs from source ledger", audit_pilot_output(path)["errors"])

    def test_mutated_peak_classification_is_detected(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.fixture(path)
            peaks = pd.read_parquet(path / "peaks.parquet")
            peaks.loc[0, "is_sampled_local_maximum"] = True
            peaks.to_parquet(path / "peaks.parquet")
            self.assertEqual(audit_pilot_output(path)["peak_classification_disagreements"], 1)


if __name__ == "__main__":
    unittest.main()

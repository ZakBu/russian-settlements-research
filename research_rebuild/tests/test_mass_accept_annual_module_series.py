import unittest

from research_rebuild.mass_linkage.accept_annual_module_series import (
    _accepted_graph_index,
    compare_module_assertion,
    official_comparison_class,
)


class AnnualModuleSeriesStagingTest(unittest.TestCase):
    def test_protected_2010_difference_is_not_called_wikipedia_error(self):
        status, note, difference = official_comparison_class(101, 96, "confidentiality_perturbed_within_ten")
        self.assertEqual(status, "numeric_values_differ_official_value_confidentiality_perturbed")
        self.assertIn("not_evidence", note)
        self.assertEqual(difference, 5)

    def test_direct_census_difference_keeps_quality_and_locator(self):
        selected = {
            "2021-id": {
                "source_record_id": "2021-id", "census_year": 2021, "population": 100,
                "population_value_quality": "direct_published_census_value",
                "population_scope": "settlement", "source_file": "source.parquet", "source_locator": "row:1",
            },
            "2010-id": {
                "source_record_id": "2010-id", "census_year": 2010, "population": 95,
                "population_value_quality": "confidentiality_perturbed_within_ten",
                "population_scope": "settlement", "source_file": "census2010.xls", "source_locator": "sheet1:7",
            },
        }
        edges = [{
            "relation": "same_place", "decision_status": "independent_case_review_accepted",
            "selection_projection_status": "active_endpoints_selected", "from_source_record_id": "2010-id",
            "from_year": "2010", "to_source_record_id": "2021-id", "to_year": "2021",
            "decision_id": "accepted-edge-1", "decision_rule": "reviewed", "evidence_sha256": "abc",
        }]
        adjacency, pair_edges, node_year = _accepted_graph_index(edges)
        candidate = {"current_source_record_id": "2021-id", "current_name_norm": "place",
                     "current_type_norm": "village", "current_region_norm": "region"}
        assertion = {"observation_year": 2010, "population_value": 101}
        result = compare_module_assertion(assertion, candidate, selected, {}, adjacency,
                                          pair_edges, node_year, {2002, 2010, 2021})
        self.assertEqual(result["census_comparison_status"], "numeric_values_differ_official_value_confidentiality_perturbed")
        self.assertEqual(result["census_comparison_basis"], "accepted_2021_identity_graph_same_place_endpoint")
        self.assertEqual(result["census_comparison_source_record_id"], "2010-id")
        self.assertEqual(result["census_comparison_locator"], "sheet1:7")
        self.assertIn("accepted-edge-1", result["census_comparison_graph_path_json"])
        self.assertFalse(result["census_comparison_identity_admission"])

    def test_diagnostic_exact_text_multiple_rows_remains_ambiguous(self):
        candidate = {"current_source_record_id": "2021-id", "current_name_norm": "place",
                     "current_type_norm": "village", "current_region_norm": "region"}
        key = (2002, "place", "village", "region")
        result = compare_module_assertion(
            {"observation_year": 2002, "population_value": 10}, candidate, {},
            {key: [{"source_record_id": "a"}, {"source_record_id": "b"}]}, {}, {}, {}, {2002},
        )
        self.assertEqual(result["census_comparison_status"], "diagnostic_name_type_region_has_multiple_rows")
        self.assertEqual(result["census_comparison_basis"], "diagnostic_only_ambiguous")
        self.assertFalse(result["census_comparison_identity_admission"])

    def test_no_1970_1989_official_endpoint_is_explicitly_unavailable(self):
        candidate = {"current_source_record_id": "2021-id", "current_name_norm": "place",
                     "current_type_norm": "village", "current_region_norm": "region"}
        result = compare_module_assertion({"observation_year": 1989, "population_value": 10}, candidate,
                                          {}, {}, {}, {}, {}, {2002, 2010, 2021})
        self.assertEqual(result["census_comparison_status"], "selected_official_source_has_no_rows_for_this_year")
        self.assertIsNone(result["census_comparison_population"])

    def test_annual_non_census_year_has_no_synthesized_nearby_comparison(self):
        candidate = {"current_source_record_id": "2021-id", "current_name_norm": "place",
                     "current_type_norm": "village", "current_region_norm": "region"}
        result = compare_module_assertion({"observation_year": 2019, "population_value": 10}, candidate,
                                          {}, {}, {}, {}, {}, {2002, 2010, 2021})
        self.assertEqual(result["census_comparison_status"], "selected_official_source_has_no_rows_for_this_year")
        self.assertIsNone(result["census_comparison_population"])


if __name__ == "__main__":
    unittest.main()

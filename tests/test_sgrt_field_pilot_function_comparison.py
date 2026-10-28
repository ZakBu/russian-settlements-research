import unittest

import pandas as pd

from scripts.sgrt_field_pilot.function_comparison import (
    attach_municipal_context, compare_functions, compare_peaks, municipal_sector_context, summarize,
)


def example():
    roster = pd.DataFrame({"source_record_id": ["village", "town", "unlisted"], "pilot": ["example"] * 3})
    edges = pd.DataFrame([
        {"origin_id": "village", "service_family": "school", "provider_settlement_id": "village", "known_local_supply": True, "l0_admitted": True},
        {"origin_id": "village", "service_family": "medical_basic", "provider_settlement_id": "town_outside_window", "known_local_supply": False, "l0_admitted": True},
        {"origin_id": "village", "service_family": "grocery", "provider_settlement_id": None, "known_local_supply": False, "l0_admitted": False},
    ])
    units = pd.DataFrame({"centre_settlement_id": ["village"], "is_registered_external_serving_centre": [True], "external_participant_count": [2]})
    return roster, edges, units


class FunctionalComparisonTests(unittest.TestCase):
    def test_local_school_preserved_when_not_a_population_peak(self):
        roster, edges, units = example()
        result = compare_functions(roster, edges, units)
        peaks = pd.DataFrame({"source_record_id": ["village", "town"], "pilot_id": ["example"] * 2, "is_local_maximum": [False, True]})
        joined = compare_peaks(result, peaks).set_index("source_record_id")
        self.assertTrue(joined.loc["village", "registered_centre_without_population_peak"])
        self.assertTrue(joined.loc["village", "school__local_function_known_present"])
        self.assertTrue(pd.isna(joined.loc["unlisted", "registered_centre_without_population_peak"]))
        self.assertTrue(joined.loc["town", "population_peak_without_recorded_local_basic_functions"])

    def test_missing_local_stock_is_unknown_and_external_target_is_not_clipped(self):
        roster, edges, units = example()
        result = compare_functions(roster, edges, units).set_index("source_record_id")
        self.assertEqual(result.loc["village", "medical_basic__provider_settlement_id"], "town_outside_window")
        self.assertEqual(result.loc["village", "medical_basic__comparison_status"], "model_external_admitted_local_stock_unknown")
        self.assertEqual(result.loc["unlisted", "school__comparison_status"], "missing_origin_row_unknown")
        self.assertEqual(result.loc["village", "grocery__comparison_status"], "direction_and_local_stock_unknown")
        self.assertEqual(result.loc["village", "known_local_basic_function_count"], 1)
        self.assertEqual(summarize(result.reset_index()).iloc[0].school_local_stock_unknown, 2)

    def test_duplicate_source_outcome_rejected(self):
        roster, edges, units = example()
        with self.assertRaises(ValueError):
            compare_functions(roster, pd.concat([edges, edges.iloc[:1]]), units)

    def test_known_school_site_with_unknown_np_identity_is_not_absent(self):
        roster, edges, units = example()
        edges.loc[0, "provider_settlement_id"] = None
        edges.loc[0, "provider_site_id"] = "mapped_school"
        edges.loc[0, "known_local_supply"] = False
        result = compare_functions(roster, edges, units).set_index("source_record_id")
        self.assertEqual(result.loc["village", "school__comparison_status"], "known_provider_site_np_identity_unknown_local_stock_unknown")
        self.assertEqual(result.loc["village", "school__provider_site_id"], "mapped_school")

    def test_known_local_cannot_be_relabelled_as_external(self):
        roster, edges, units = example()
        edges.loc[0, "provider_settlement_id"] = "town"
        with self.assertRaises(ValueError):
            compare_functions(roster, edges, units)

    def test_municipal_workers_remain_territorial_context(self):
        roster, _, _ = example()
        crosswalk = pd.DataFrame({"source_record_id": ["village", "town"], "matched_2021_parent_code": ["MO", "MO"], "parent_scope_basis": ["source_exact", "source_exact"]})
        municipal = pd.DataFrame({"oktmo": ["MO"], "municipality": ["Example district"], "year": [2025], "indicator_name": ["Partial workers"], "indicator_unit": ["people"], "partial_organisation_workers_2025_territorial": [1000.0], "territorial_boundary_2021_2025_equality_verified": [False]})
        result = attach_municipal_context(roster, crosswalk, municipal)
        self.assertEqual(result.partial_organisation_workers_2025_territorial.tolist()[:2], [1000.0, 1000.0])
        self.assertTrue(result.municipal_workers_are_not_settlement_jobs.all())
        self.assertTrue(pd.isna(result.iloc[2].partial_organisation_workers_2025_territorial))

    def test_sector_context_retains_unknown_and_never_allocates_workers(self):
        crosswalk = pd.DataFrame({"matched_2021_parent_code": ["MO", "MO"]})
        raw = pd.DataFrame({"oktmo": ["MO", "MO"], "indicator_code": ["Y48423005"] * 2,
                            "indicator_period": ["Январь-декабрь"] * 2, "year": [2025] * 2,
                            "okved2": ["Всего по обследуемым видам экономической деятельности", "Раздел A Сельское, лесное хозяйство, охота, рыболовство и рыбоводство"],
                            "indicator_unit": ["Человек"] * 2, "indicator_value": [1000.0, None]})
        result = municipal_sector_context(crosswalk, raw)
        self.assertEqual(len(result), 2)
        self.assertTrue(pd.isna(result.iloc[1].indicator_value))
        self.assertFalse(result.workers_allocated_to_np.any())


if __name__ == "__main__":
    unittest.main()

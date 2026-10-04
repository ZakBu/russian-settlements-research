import json
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import review_type_false_zero_177 as review


OUT = Path("/workspace/settlements-work/continuation_20261004/independent_review/type_false_zero_177_review")


class IndependentTypeFalseZeroReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads((OUT / "independent_review_receipt.json").read_text(encoding="utf-8"))
        cls.eligible = pd.read_csv(OUT / "independently_eligible_point_seed_list.csv", dtype=str, keep_default_na=False)
        cls.held = pd.read_csv(OUT / "held_point_candidates.csv", dtype=str, keep_default_na=False)
        cls.sample = pd.read_csv(OUT / "fixed_20_risk_sample.csv", dtype=str, keep_default_na=False)

    def test_literal_publisher_type_match_is_exact_and_preserves_subtypes(self):
        self.assertEqual(review.publisher_class("село Грибцово", "село")[0], "literal_object_name_type_prefix")
        self.assertEqual(review.publisher_class("г. Луза", "город")[0], "literal_publisher_city_abbreviation")
        self.assertEqual(review.publisher_class("железнодорожная станция Кабарга", "железнодорожный объект")[0],
                         "publisher_physical_railway_subtype_under_broad_class")
        self.assertIsNone(review.publisher_class("СНТ Березка", "село"))

    def test_helper_fields_remain_distinct_and_missing_is_unknown(self):
        self.assertEqual(review.helper_relation("село", "с", "село"),
                         "helper_semantically_agrees_after_documented_abbreviation")
        self.assertEqual(review.helper_relation("железнодорожный объект", "ж/д_ст", "железнодорожная станция"),
                         "detailed_railway_subtype_of_selected_broad_class")
        self.assertEqual(review.helper_relation("хутор", "с", "село"),
                         "helper_conflict_retained_publisher_type_replayed_separately")
        self.assertEqual(review.helper_relation("город", None, None), "helper_fields_missing_unknown")

    def test_independent_vector_has_only_point_seed_scope(self):
        self.assertEqual(len(self.eligible), 177)
        self.assertEqual(len(self.held), 0)
        self.assertEqual(self.eligible.target_source_record_id.nunique(), 177)
        self.assertEqual(self.receipt["independently_eligible_rows"], 177)
        self.assertEqual(self.receipt["eligible_source_population_sum_conditional_only"], 89733.0)
        self.assertEqual(self.receipt["conditional_fullchain_count_latest_graph"], 177)
        self.assertEqual(self.receipt["distinct_current_fullchain_components"], 177)
        self.assertEqual(self.receipt["candidate_overlaps_existing_ninth_point_ledger"], 0)
        self.assertEqual(self.receipt["global_blocked_candidate_count"], 0)
        self.assertEqual(self.receipt["admissions"], {
            "point_uses": 0, "identity_bindings": 0,
            "historical_provider_bindings": 0, "historical_coordinate_uses": 0})
        self.assertTrue(self.eligible.review_status.eq("independently_eligible_current_point_seed_pending_root_admission").all())
        self.assertTrue(self.eligible.point_origin_file.eq(str(review.RAW)).all())
        self.assertTrue(self.eligible.point_origin_sha256.eq(review.PINS["tochno_raw"][1]).all())
        self.assertTrue(self.eligible.point_origin_locator.str.contains("parquet_row_1based=").all())

    def test_full_vector_gates_and_fixed_risk_sample(self):
        for row in self.eligible.itertuples(index=False):
            checks = json.loads(row.rule_checks_json)
            self.assertTrue(all(checks.values()), row.target_source_record_id)
            self.assertEqual(str(row.measurement_date_precision_or_historical_claim).lower(), "false")
        self.assertEqual(len(self.sample), 20)
        self.assertEqual(set(self.sample.publisher_type_evidence_independent), {
            "literal_object_name_type_prefix", "literal_publisher_city_abbreviation",
            "publisher_physical_railway_subtype_under_broad_class"})
        self.assertEqual(self.receipt["original_screen_rounded_coordinate_lookup_zero_full_precision_unique_rows"], 20)
        self.assertEqual(int(self.eligible.screen_coordinate_lookup_zero_but_full_precision_coordinate_unique.astype(str).str.lower().eq("true").sum()), 20)


if __name__ == "__main__":
    unittest.main()

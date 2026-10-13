import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_rebuild.mass_linkage.apply_point_gap_five_reviewed_2021_seeds_20261004 import (
    BASE_DIR,
    BLOCKLIST,
    FROZEN_DIR,
    REVIEW_DIR,
    hard_source_flags,
    point_spread_conflicts,
    run,
    unique_three_year_component,
    validate_review,
)


class PointGapFiveApplyTests(unittest.TestCase):
    def test_exact_reviewed_packet_passes_and_mutated_packet_fails(self):
        _, rows = validate_review(REVIEW_DIR)
        self.assertEqual(len(rows), 5)
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "review"
            shutil.copytree(REVIEW_DIR, copy)
            target = copy / "eligible_point_seeds.csv"
            raw = target.read_text(encoding="utf-8")
            target.write_text(raw.replace("unique_alias_within_1km", "unique_alias_no_longer_1km", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixed reviewed point seed bytes"):
                validate_review(copy)

    def test_actual_source_hard_flags_block_but_route_only_identity_flag_is_retained(self):
        self.assertEqual(hard_source_flags({
            "is_additive_settlement_record": True,
            "legacy_identity_conflict": True,
            "legacy_identity_reasons": ["legacy_not_accepted", "text_similarity_only"],
            "settlement_name": "X", "settlement_type": "село",
        }), [])
        self.assertIn("source_federal_aggregate", hard_source_flags({"is_federal_aggregate": True, "is_additive_settlement_record": True, "settlement_name": "X", "settlement_type": "село"}))
        self.assertIn("source_verified_successor_event", hard_source_flags({"legacy_verified_successor_settlement_id": "RU-OKTMO-1", "is_additive_settlement_record": True, "settlement_name": "X", "settlement_type": "село"}))
        self.assertIn("source_same_year_collision", hard_source_flags({"legacy_same_year_collision": True, "is_additive_settlement_record": True, "settlement_name": "X", "settlement_type": "село"}))
        self.assertIn("source_not_additive_atomic_settlement", hard_source_flags({"is_additive_settlement_record": False, "settlement_name": "X", "settlement_type": "село"}))

    def test_component_requires_one_observation_in_each_census_year(self):
        self.assertTrue(unique_three_year_component({"a", "b", "c"}, {"a": 2002, "b": 2010, "c": 2021}))
        self.assertFalse(unique_three_year_component({"a", "b", "c"}, {"a": 2002, "b": 2002, "c": 2021}))
        self.assertFalse(unique_three_year_component({"a", "b"}, {"a": 2002, "b": 2021}))

    def test_existing_component_point_more_than_five_km_holds_continuity(self):
        near = {"target_source_record_id": "near", "latitude": 55.0, "longitude": 37.0}
        far = {"target_source_record_id": "far", "latitude": 56.0, "longitude": 37.0}
        self.assertEqual(point_spread_conflicts(55.0, 37.0, [near]), [])
        conflicts = point_spread_conflicts(55.0, 37.0, [far])
        self.assertEqual(conflicts[0][0], "far")
        self.assertGreater(conflicts[0][1], 5.0)

    def test_end_to_end_streamed_append_preserves_all_414875_baseline_rows(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = run(REVIEW_DIR, BASE_DIR, FROZEN_DIR, BLOCKLIST, Path(td) / "applied")
            self.assertEqual(receipt["direct_reviewed_seed_rows"], 5)
            self.assertEqual(receipt["point_use_rows_appended"], 15)
            self.assertEqual(receipt["historical_point_continuity_rows_appended"], 10)
            self.assertEqual(receipt["baseline_point_rows"], 414875)
            self.assertEqual(receipt["baseline_prefix_value_identical_rows"], 414875)
            self.assertEqual(receipt["final_point_rows"], 414890)
            self.assertEqual(receipt["existing_point_rows_changed"], 0)
            self.assertFalse(receipt["accepted_identity_graph_mutated"])
            self.assertFalse(receipt["selected_population_frame_mutated"])
            self.assertFalse(receipt["historical_provider_id_binding_claimed"])


if __name__ == "__main__":
    unittest.main()

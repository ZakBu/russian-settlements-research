import csv
import tempfile
import unittest
from pathlib import Path

from research_rebuild.mass_linkage.reconcile_point_gap_five_archive_origin_paths_20261004 import (
    APPLIED_DIR,
    BASE_POINTS,
    OUTPUT,
    REVIEW_DIR,
    ZIP_PATH,
    read_csv,
    rewrite_metadata,
    run,
    verify_archive_lines,
)


class PointGapFiveOriginReconciliationTests(unittest.TestCase):
    def test_exact_archive_member_lines_replay_from_pinned_zip(self):
        seeds = read_csv(REVIEW_DIR / "eligible_point_seeds.csv")
        rows = verify_archive_lines(ZIP_PATH, seeds)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r["archive_member"] == "RU.txt" for r in rows))
        self.assertTrue(all(r["origin_replay_status"] == "exact_raw_member_line_and_coordinate_verified" for r in rows))

    def test_archive_replay_rejects_changed_reviewed_coordinate(self):
        seeds = read_csv(REVIEW_DIR / "eligible_point_seeds.csv")
        seeds[0] = dict(seeds[0], proposed_point_latitude="0.0")
        with self.assertRaisesRegex(ValueError, "failed origin replay"):
            verify_archive_lines(ZIP_PATH, seeds)

    def test_metadata_rewrite_keeps_origin_label_and_does_not_change_science_fields(self):
        old = str(ZIP_PATH) + "!RU.txt"
        row = {
            "target_source_record_id": "record-1",
            "point_origin_file": old,
            "coordinate_source_file": old,
            "point_claim_artifact_file": old,
            "geonames_source_file": old,
            "point_origin_locator": "member=RU.txt;line=1;byte_start=0;byte_end=4;raw_line_sha256=abc",
            "coordinate_source_sha256": "9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4",
            "point_origin_sha256": "9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4",
            "coordinate_provenance": "reviewed point origin",
            "latitude": 55.5,
            "longitude": 37.5,
            "coordinate_admission_status": "reviewed_extension_rule_accepted",
        }
        updated = rewrite_metadata(row, old, ZIP_PATH)
        for field in ("point_origin_file", "coordinate_source_file", "point_claim_artifact_file", "geonames_source_file"):
            self.assertEqual(updated[field], str(ZIP_PATH))
        self.assertIn("review_packet_origin_label=" + old, updated["coordinate_provenance"])
        self.assertIn("member=RU.txt", updated["point_origin_locator"])
        for field in ("latitude", "longitude", "coordinate_admission_status", "point_origin_locator", "point_origin_sha256"):
            self.assertEqual(updated[field], row[field])

    def test_metadata_rewrite_rejects_unexpected_input_origin(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            rewrite_metadata({"point_origin_file": "/other.zip!RU.txt"}, str(ZIP_PATH) + "!RU.txt", ZIP_PATH)

    def test_end_to_end_metadata_only_projection_preserves_baseline_and_coordinates(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = run(APPLIED_DIR, BASE_POINTS, REVIEW_DIR, ZIP_PATH, Path(td) / "final")
            self.assertEqual(receipt["target_metadata_rows_reconciled"], 15)
            self.assertEqual(receipt["input_point_rows"], 414890)
            self.assertEqual(receipt["original_baseline_rows_verified_unchanged"], 414875)
            self.assertEqual(receipt["prior_ledger_rows_value_compared"], 414890)
            self.assertEqual(receipt["coordinate_values_changed"], 0)
            self.assertEqual(receipt["coordinate_status_values_changed"], 0)
            self.assertEqual(receipt["source_record_ids_changed"], 0)
            self.assertFalse(receipt["selected_population_or_identity_graph_changed"])
            self.assertTrue(receipt["review_packet_origin_label_preserved_in_coordinate_provenance"])
            self.assertGreaterEqual(receipt["elapsed_seconds_measured"], 0)


if __name__ == "__main__":
    unittest.main()

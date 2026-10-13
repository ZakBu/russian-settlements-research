import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from research_rebuild.mass_linkage.apply_reviewed_current_point_retrospective_20261004 import (
    BLOCK_BASIS,
    EXPECTED_ELIGIBLE_COUNT,
    EXPECTED_REVIEW_STATUS,
    assert_direct_targets_not_blocked,
    assert_baseline_prefix_exact,
    cast_addition_to_schema,
    make_addition,
    validate_direct_point_origin,
    validate_blocklist_scope,
    validate_review_receipt,
    validate_reviewed_candidate,
)


class RetrospectiveCurrentPointApplicationTests(unittest.TestCase):
    def setUp(self):
        self.target = "2010:test.xls:Sheet1:12"
        self.carrier_id = "2021:test.parquet:parquet:12"
        self.edge_id = "edge-1"
        self.flags = {
            "is_additive_settlement_record": True,
            "is_federal_aggregate": False,
            "legacy_identity_conflict": False,
            "legacy_same_year_collision": False,
            "legacy_verified_successor_settlement_id": None,
            "population_scope": "settlement",
        }
        self.candidate = {
            "historical_source_record_id": self.target,
            "historical_year": "2010",
            "historical_population": "1234",
            "historical_name": "Тестово",
            "historical_type": "село",
            "historical_region_norm": "тестовая",
            "current_source_record_id": self.carrier_id,
            "current_name": "Тестово",
            "current_type": "село",
            "current_region_norm": "тестовая",
            "latitude": "55.25",
            "longitude": "37.5",
            "coordinate_source": "wikidata_p625",
            "coordinate_provider": "wikidata_p625",
            "coordinate_provider_id": "Q123",
            "coordinate_admission_status": "reviewed_rule_accepted",
            "point_origin_file": "/tmp/origin.jsonl.gz",
            "point_origin_sha256": "origin-sha",
            "point_origin_locator": "line=1;entity=Q123;claim=P625",
            "point_origin_kind": "wikidata_truthy_p625_raw_claim",
            "accepted_identity_path_json": json.dumps([{
                "decision_id": self.edge_id,
                "from_source_record_id": self.target,
                "to_source_record_id": self.carrier_id,
                "relation": "same_place",
                "decision_status": "checked_rule_accepted",
            }]),
            "accepted_identity_path_edge_count": "1",
            "original_global_point_reuse_block_preserved": "False",
            "original_global_point_reuse_block_basis": "",
            "historical_source_evidence_flags_json": json.dumps(self.flags),
            "current_source_evidence_flags_json": json.dumps(self.flags),
        }
        self.selected = {
            self.target: {
                "source_record_id": self.target, "census_year": 2010,
                "settlement_name": "Тестово", "settlement_type": "село",
                "region_norm": "тестовая", "region_raw": "Тестовая",
                "source_file": "test.xls", "source_row": 12,
                "population": 1234.0, "population_scope": "settlement",
                "population_value_quality": "reviewed_primary_reported_value",
                "source_name_raw": "с Тестово", "source_sheet": "Sheet1",
                "source_sha256": "selected-sha", "source_locator": "Sheet1!A12",
                "oktmo": None, "okato": None,
            },
            self.carrier_id: {
                "source_record_id": self.carrier_id, "census_year": 2021,
                "settlement_name": "Тестово", "settlement_type": "село",
                "region_norm": "тестовая", "region_raw": "Тестовая область",
                "population": 1500.0, "population_scope": "settlement",
            },
        }
        self.evidence = {self.target: dict(self.flags), self.carrier_id: dict(self.flags)}
        self.carrier = {
            "target_source_record_id": self.carrier_id, "target_year": 2021.0,
            "latitude": 55.25, "longitude": 37.5,
            "coordinate_admission_status": "reviewed_rule_accepted",
            "coordinate_source": "wikidata_p625", "coordinate_source_record_id": self.carrier_id,
            "coordinate_provider": "wikidata_p625", "coordinate_provider_id": "Q123",
            "point_origin_file": "/tmp/origin.jsonl.gz", "point_origin_sha256": "origin-sha",
            "point_origin_locator": "line=1;entity=Q123;claim=P625",
            "point_origin_kind": "wikidata_truthy_p625_raw_claim",
            "coordinate_quality": "reviewed modern representative point",
            "admission_rule": "checked_point_rule", "coordinate_provenance": "point-provenance",
        }
        self.origin = {
            self.target: {
                "historical_source_record_id": self.target,
                "current_carrier_source_record_id": self.carrier_id,
                "source_file": "/tmp/origin.jsonl.gz", "source_file_sha256": "origin-sha",
                "source_locator": "line=1;entity=Q123;claim=P625",
                "latitude": "55.25", "longitude": "37.5", "external_point_id": "Q123",
            }
        }
        self.graph_edges = {self.edge_id: {
            "decision_id": self.edge_id, "from_source_record_id": self.target,
            "to_source_record_id": self.carrier_id, "from_year": "2010", "to_year": "2021",
            "relation": "same_place", "decision_status": "checked_rule_accepted",
        }}

    def validate(self, row=None, *, blocked=frozenset()):
        return validate_reviewed_candidate(
            row or self.candidate, selected=self.selected, evidence=self.evidence,
            carriers={self.carrier_id: self.carrier}, origins=self.origin,
            graph_edges=self.graph_edges, existing_target_ids=set(), blocked_targets=set(blocked),
        )

    def test_exact_reviewed_carrier_origin_coordinates_and_path_pass(self):
        result = self.validate()
        self.assertEqual(result["carrier_id"], self.carrier_id)
        self.assertEqual(result["decision_ids"], [self.edge_id])
        self.assertFalse(result["blocked_exception"])

    def test_wrong_carrier_fails(self):
        row = dict(self.candidate, current_source_record_id="2021:other.parquet:row:1")
        with self.assertRaisesRegex(ValueError, "carrier"):
            self.validate(row)

    def test_wrong_origin_fails(self):
        row = dict(self.candidate, point_origin_sha256="wrong-sha")
        with self.assertRaisesRegex(ValueError, "Carrier point point_origin_sha256 mismatch"):
            self.validate(row)

    def test_wrong_coordinate_fails(self):
        row = dict(self.candidate, latitude="55.251")
        with self.assertRaisesRegex(ValueError, "carrier latitude mismatch"):
            self.validate(row)

    def test_unreviewed_or_wrong_edge_fails(self):
        bad_graph = {self.edge_id: dict(self.graph_edges[self.edge_id], relation="same_place_candidate")}
        with self.assertRaisesRegex(ValueError, "nonaccepted/non-same-place"):
            validate_reviewed_candidate(
                self.candidate, selected=self.selected, evidence=self.evidence,
                carriers={self.carrier_id: self.carrier}, origins=self.origin,
                graph_edges=bad_graph, existing_target_ids=set(), blocked_targets=set(),
            )

    def test_hard_flag_is_never_waived_by_retro_route(self):
        self.evidence[self.target]["legacy_identity_conflict"] = True
        with self.assertRaisesRegex(ValueError, "legacy identity conflict"):
            self.validate()

    def test_existing_target_point_is_never_overwritten(self):
        with self.assertRaisesRegex(ValueError, "already has an accepted point"):
            validate_reviewed_candidate(
                self.candidate, selected=self.selected, evidence=self.evidence,
                carriers={self.carrier_id: self.carrier}, origins=self.origin,
                graph_edges=self.graph_edges, existing_target_ids={self.target}, blocked_targets=set(),
            )

    def test_blocklist_exception_is_exact_five_reviewed_targets_only(self):
        rows = []
        blocked_ids = set()
        for index in range(5):
            row = dict(self.candidate)
            row["historical_source_record_id"] = f"target-{index}"
            row["original_global_point_reuse_block_preserved"] = "True"
            row["original_global_point_reuse_block_basis"] = BLOCK_BASIS
            row["point_origin_file"] = "/tmp/origin.jsonl.gz"
            blocked_ids.add(row["historical_source_record_id"])
            rows.append(row)
        self.assertEqual(validate_blocklist_scope(rows, {"blocked_target_source_record_ids": sorted(blocked_ids)}), blocked_ids)
        # Adding a sixth blocked target to this packet must fail. The blocklist
        # itself stays unchanged; there is no generic blocked-target bypass.
        extra = dict(rows[0], historical_source_record_id="outside-packet-target")
        rows.append(extra)
        blocked_ids.add("outside-packet-target")
        with self.assertRaisesRegex(ValueError, "exact five-target exception"):
            validate_blocklist_scope(rows, {"blocked_target_source_record_ids": sorted(blocked_ids)})

    def test_addition_preserves_actual_origin_but_drops_historical_provider_binding(self):
        validated = self.validate()
        schema = pa.schema([
            ("target_source_record_id", pa.string()), ("target_year", pa.float64()),
            ("latitude", pa.float64()), ("longitude", pa.float64()),
            ("coordinate_source", pa.string()), ("coordinate_source_record_id", pa.string()),
            ("coordinate_provider", pa.string()), ("coordinate_provider_id", pa.string()),
            ("coordinate_admission_status", pa.string()), ("coordinate_quality", pa.string()),
            ("point_origin_file", pa.string()), ("point_origin_sha256", pa.string()),
            ("point_origin_locator", pa.string()), ("coordinate_measurement_date_unknown", pa.bool_()),
            ("boundary_comparability_asserted", pa.bool_()), ("coordinate_provider_id", pa.string()),
            ("provider_binding_status", pa.string()), ("coordinate_provenance", pa.string()),
            ("candidate_only", pa.bool_()), ("admission_allowed", pa.bool_()),
            ("coordinate_application_review_sha256", pa.string()),
            ("blocked_conflict_resolution_approved", pa.bool_()),
        ])
        addition = make_addition(validated, schema, "review-sha", {"path": "eligible.csv", "sha256": "eligible-sha"}, "base-points-sha")
        self.assertEqual(addition["target_source_record_id"], self.target)
        self.assertEqual(addition["coordinate_source_record_id"], self.carrier_id)
        self.assertEqual(addition["point_origin_sha256"], "origin-sha")
        self.assertIsNone(addition["coordinate_provider_id"])
        self.assertFalse(addition["boundary_comparability_asserted"])
        self.assertFalse(addition["candidate_only"])

    def test_direct_named_point_origin_is_exact_and_point_correctness_stays_separate(self):
        with tempfile.TemporaryDirectory() as td:
            origin_path = Path(td) / "okato.dbf"
            origin_path.write_bytes(b"raw DBF fixture")
            origin_sha = hashlib.sha256(origin_path.read_bytes()).hexdigest()
            row = {
                "point_use_disposition": "eligible_scoped_point_use_candidate_pending_root_application",
                "native_code_provider_binding": "not_claimed",
                "coordinate_measurement_date": "unknown/not asserted",
                "historical_boundary_equivalence": "unknown/not asserted",
                "population_value_changed": "False", "source_row_mutated": "False",
                "identity_graph_mutated": "False", "point_ledger_mutated": "False",
                "point_latitude": "61.743937", "point_longitude": "75.596928",
                "target_name": "Покачи", "source_population": "17017",
                "point_origin_evidence_json": json.dumps({
                    "origin_path": str(origin_path), "origin_sha256": origin_sha,
                    "source_kind": "raw_named_typed_GeoKLADR_2011_DBf",
                    "record_1based": 121362, "byte_offset_0based": 47938300,
                    "raw_record": {"LAT": "61.743937", "LONG": "75.596928", "NAME1": "Покачи", "SCOKATO": "г"},
                }),
            }
            self.assertEqual(validate_direct_point_origin(row)["origin_sha256"], origin_sha)
            row["point_longitude"] = "75.597"
            with self.assertRaisesRegex(ValueError, "GeoKLADR raw longitude mismatch"):
                validate_direct_point_origin(row)

    def test_direct_named_point_cannot_waive_global_block(self):
        rows = [{"source_record_id": self.target}]
        with self.assertRaisesRegex(ValueError, "cannot waive any global point blocklist"):
            assert_direct_targets_not_blocked(rows, {"blocked_target_source_record_ids": [self.target]})

    def test_schema_driven_cast_and_parquet_readback_preserve_mixed_baseline_types(self):
        schema = pa.schema([
            ("target_source_record_id", pa.string()), ("target_year", pa.string()),
            ("source_row", pa.float64()), ("source_population", pa.string()),
            ("latitude", pa.float64()), ("longitude", pa.float64()),
            ("coordinate_admission_status", pa.string()),
            ("coordinate_measurement_date_unknown", pa.bool_()),
        ])
        source = {"target_source_record_id": self.target, "target_year": 2010,
                  "source_row": 12.0, "source_population": 1234.0,
                  "latitude": 55.25, "longitude": 37.5,
                  "coordinate_admission_status": "reviewed_extension_rule_accepted",
                  "coordinate_measurement_date_unknown": True}
        cast = cast_addition_to_schema(source, schema)
        table = pa.Table.from_pylist([cast], schema=schema)
        self.assertEqual(table["target_year"].to_pylist(), ["2010"])
        self.assertEqual(table["source_population"].to_pylist(), ["1234.0"])
        with tempfile.TemporaryDirectory() as td:
            baseline_path = Path(td) / "baseline.parquet"
            output_path = Path(td) / "appended.parquet"
            baseline = pa.Table.from_pylist([{
                "target_source_record_id": "old-row", "target_year": "2021",
                "source_row": 7.0, "source_population": "900.0",
                "latitude": 55.0, "longitude": 37.0,
                "coordinate_admission_status": "reviewed_rule_accepted",
                "coordinate_measurement_date_unknown": False,
            }], schema=schema)
            pq.write_table(baseline, baseline_path)
            with pq.ParquetWriter(output_path, schema) as writer:
                writer.write_table(baseline)
                writer.write_table(table)
            self.assertEqual(assert_baseline_prefix_exact(baseline_path, output_path, 1), 1)
            readback = pq.read_table(output_path)
            self.assertEqual(readback.num_rows, 2)
            self.assertEqual(readback["target_source_record_id"].to_pylist(), ["old-row", self.target])

    def test_integer_schema_refuses_fractional_year_or_row(self):
        schema = pa.schema([("target_year", pa.int16()), ("latitude", pa.float64())])
        with self.assertRaisesRegex(ValueError, "non-integral target_year"):
            cast_addition_to_schema({"target_year": 2010.5, "latitude": 55.0}, schema)

    def test_bad_review_hash_fails_before_any_application(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            eligible = root / "eligible.csv"
            eligible.write_text("historical_source_record_id\nT\n", encoding="utf-8")
            origin = root / "origin.csv"
            origin.write_text("historical_source_record_id\nT\n", encoding="utf-8")
            pins = {
                str(root / "selected_observations.parquet"): "sel",
                str(root / "source_evidence.parquet"): "ev",
                str(root / "accepted_identity_edges.parquet"): "graph",
                str(root / "accepted_point_uses.parquet"): "points",
                str(root / "blocked_point_reuse_targets_v1.json"): "block",
            }
            receipt = {
                "status": EXPECTED_REVIEW_STATUS,
                "eligible_rows": EXPECTED_ELIGIBLE_COUNT,
                "outputs": {
                    "eligible_retrospective_point_uses.csv": {"path": str(eligible), "sha256": hashlib.sha256(eligible.read_bytes()).hexdigest(), "rows": 29},
                    "raw_point_origin_replay.csv": {"sha256": hashlib.sha256(origin.read_bytes()).hexdigest()},
                },
                "input_sha256": pins,
                "selected_source_mismatches": 0,
                "identity_path_edges_found_and_accepted": 33,
                "exact_current_point_coordinate_origin_matches": 29,
                "hard_source_flags_among_eligible": 0,
                "global_point_block_list_mutated": False,
                "old_global_point_block_targets_preserved": 5,
            }
            review_path = root / "review.json"
            review_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "review receipt SHA-256 mismatch"):
                validate_review_receipt(
                    eligible_path=eligible, eligible_sha=hashlib.sha256(eligible.read_bytes()).hexdigest(),
                    receipt_path=review_path, receipt_sha="wrong-review-sha", review_graph_sha="graph",
                    review_points_sha="points", selected_sha="sel", source_evidence_sha="ev",
                    blocklist_sha="block", origin_replay_sha=hashlib.sha256(origin.read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()

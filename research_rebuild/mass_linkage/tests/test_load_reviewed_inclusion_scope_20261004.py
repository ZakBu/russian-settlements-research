import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from research_rebuild.mass_linkage.load_reviewed_inclusion_scope_20261004 import (
    apply_scoped_inclusion_reference,
    load_scoped_inclusion_references,
)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resign(folder, relpath):
    receipt_path = folder / "handoff_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["main_scope_outputs_sha256"][relpath] = sha(folder / relpath)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


def replace_csv_row(path, key, value, updates):
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row[key] == value:
            row.update(updates)
    write_csv(path, rows)


class LoaderTest(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        folder = Path(temp.name)
        archive = folder / "geonames.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("RU.txt", "1001\tTest Settlement\t\t\t51.0\t39.0\tP\tPPL\tRU\n")
        line_hash = hashlib.sha256(b"1001\tTest Settlement\t\t\t51.0\t39.0\tP\tPPL\tRU\n").hexdigest()
        rows = {
            "scoped_inclusion_observations.csv": [{
                "observation_id": "obs:child", "source_record_id": "old:child",
                "source_year": "2002", "population": "17", "population_raw": "17", "selected_source_type": "пгт",
                "source_file": "src.xls", "source_sha256": "a" * 64,
                "source_locator": "sheet=0,row=3", "point_use_id": "point:child",
                "old_parent_city_proper_source_record_id": "old:parent",
                "old_parent_city_proper_population": "80",
                "current_receiver_source_record_id": "now:parent",
                "national_additive": "False", "ordinary_NP3_admission": "False",
                "same_place_graph_identity_claimed": "False", "current_child_population_asserted": "False",
                "parent_population_transfer_asserted": "False",
                "scope_status": "eligible_secondary_reported_inclusion_context_only",
            }],
            "old_source_union_hooks.csv": [{"source_record_id": "old:child",
                                             "source_row_already_present_in_primary": "True",
                                             "existing_primary_row_source_id": "old:child",
                                             "existing_primary_row_population": "17",
                                             "strict_no_double_count_status": "old source row already in primary; sidecar contributes zero national count"}],
            "secondary_inclusion_edges.csv": [{"from_observation_id": "obs:child",
                                                  "current_receiver_source_record_id": "now:parent"}],
            "scoped_point_uses.csv": [{"point_use_id": "point:child", "historical_place_qid": "Q1",
                                       "latitude": "51.0", "longitude": "39.0",
                                       "point_origin_file": str(archive), "point_origin_sha256": sha(archive),
                                       "point_origin_member": "RU.txt", "point_origin_line_sha256": line_hash,
                                       "point_origin_locator": "RU.txt:line=1;geonameid=1001",
                                       "provider_feature_id": "1001", "measurement_date": "unknown",
                                       "direct_historical_coordinate_measurement": "False"}],
            "current_receiver_contexts.csv": [{"source_record_id": "now:parent", "year": "2021",
                                                "population_context_only": "100", "type": "город",
                                                "population_is_child_value": "False"}],
        }
        # The loader verifies every pinned file, including files not selected.
        for name, data in rows.items():
            write_csv(folder / name, data)
        names = list(rows)
        pins = {name: sha(folder / name) for name in names}
        supplement = folder / "zheleznodorozhny_secondary_context_supplement"
        zrows = {
            "zheleznodorozhny_observations.csv": [{
                "source_record_id": "old:zhel", "year": "2002", "population": "12",
                "source_type": "город", "source_file_path": "zhel.xls", "source_file_sha256": "b" * 64,
                "source_locator": "row=9", "receiver_source_record_id": "now:parent",
                "current_receiver_population_context_only": "100", "secondary_reported_context_only": "True",
            }],
            "zheleznodorozhny_old_city_proper_union_hooks.csv": [{
                "old_child_source_record_id": "old:zhel", "old_city_proper_parent_source_record_id": "old:parent",
                "old_city_proper_population": "80",
            }],
            "zheleznodorozhny_existing_point_references.csv": [{
                "source_record_id": "old:zhel", "coordinate_admission_status": "reviewed_extension_rule_accepted",
                "latitude": "55.0", "longitude": "38.0",
                "point_origin_file": str(archive), "point_origin_sha256": sha(archive),
            }],
        }
        supplement_pins = {}
        for name, data in zrows.items():
            path = supplement / name
            write_csv(path, data)
            supplement_pins[f"zheleznodorozhny_secondary_context_supplement/{name}"] = sha(path)
        build_receipt = folder / "build_receipt.json"
        build_receipt.write_text("{}", encoding="utf-8")
        pins["build_receipt.json"] = sha(build_receipt)
        receipt = {"main_scope_receipt_sha256": pins["build_receipt.json"],
                   "main_scope_outputs_sha256": pins,
                   "zheleznodorozhny_supplement_files_sha256": supplement_pins}
        (folder / "handoff_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        selected = {
            "old:child": {"source_record_id": "old:child", "census_year": 2002, "population": 17, "type_raw": "пгт", "is_additive_settlement_record": True, "population_scope": "settlement", "is_federal_aggregate": False},
            "old:parent": {"source_record_id": "old:parent", "census_year": 2002, "population": 80, "type_raw": "город", "is_additive_settlement_record": True, "population_scope": "settlement", "is_federal_aggregate": False},
            "now:parent": {"source_record_id": "now:parent", "census_year": 2021, "population": 100, "type_raw": "город", "is_additive_settlement_record": True, "population_scope": "settlement", "is_federal_aggregate": False},
            "old:zhel": {"source_record_id": "old:zhel", "census_year": 2002, "population": 12, "type_raw": "город", "is_additive_settlement_record": True, "population_scope": "settlement", "is_federal_aggregate": False},
        }
        point_rows = {"old:child": {"target_source_record_id": "old:child", "coordinate_admission_status": "reviewed_rule_accepted", "latitude": 51.0, "longitude": 39.0},
                      "old:zhel": {"target_source_record_id": "old:zhel", "coordinate_admission_status": "reviewed_extension_rule_accepted", "latitude": 55.0, "longitude": 38.0}}
        return temp, folder, selected, point_rows

    def test_loads_secondary_reference_and_validates_exact_rows(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        rows = load_scoped_inclusion_references(folder, selected, points)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_record_id"], "old:child")
        self.assertFalse(rows[0]["population_additive"])
        self.assertEqual(rows[0]["point_origin_reference"]["historical_place_qid"], "Q1")

    def test_hash_mismatch_fails_before_selection(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        with (folder / "scoped_inclusion_observations.csv").open("a") as f:
            f.write("tampered\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_scoped_inclusion_references(folder, {}, {})

    def test_selected_population_and_point_origin_type_are_checked(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        selected["old:child"]["population"] = 18
        with self.assertRaisesRegex(ValueError, "tuple mismatch"):
            load_scoped_inclusion_references(folder, selected, points)

    def test_duplicate_source_reference_fails(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        path = folder / "scoped_inclusion_observations.csv"
        with path.open(newline="", encoding="utf-8") as f:
            records = list(csv.DictReader(f))
        write_csv(path, records + records)
        receipt_path = folder / "handoff_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["main_scope_outputs_sha256"][path.name] = sha(path)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate inclusion source ID"):
            load_scoped_inclusion_references(folder, selected, points)

    def test_duplicate_hook_key_is_rejected(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        path = folder / "old_source_union_hooks.csv"
        with path.open(newline="", encoding="utf-8") as f:
            records = list(csv.DictReader(f))
        write_csv(path, records + records)
        resign(folder, path.name)
        with self.assertRaisesRegex(ValueError, "duplicate old-source hook ID"):
            load_scoped_inclusion_references(folder, selected, points)

    def test_zheleznodorozhny_requires_explicit_opt_in_and_existing_point(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        rows = load_scoped_inclusion_references(folder, selected, points)
        self.assertEqual(len(rows), 1)
        rows = load_scoped_inclusion_references(folder, selected, points, include_zheleznodorozhny=True)
        self.assertEqual({r["source_record_id"] for r in rows}, {"old:child", "old:zhel"})
        del points["old:zhel"]
        with self.assertRaisesRegex(ValueError, "missing by exact source ID"):
            load_scoped_inclusion_references(folder, selected, points, include_zheleznodorozhny=True)

    def test_zheleznodorozhny_never_binds_by_coordinates_alone(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        del points["old:zhel"]
        points["different-place"] = {
            "target_source_record_id": "different-place",
            "coordinate_admission_status": "reviewed_extension_rule_accepted",
            "latitude": 55.0, "longitude": 38.0,
        }
        with self.assertRaisesRegex(ValueError, "missing by exact source ID"):
            load_scoped_inclusion_references(folder, selected, points, include_zheleznodorozhny=True)

    def test_zheleznodorozhny_uses_canonical_coordinate_status_set(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        points["old:zhel"]["coordinate_admission_status"] = "accepted"
        with self.assertRaisesRegex(ValueError, "not canonically accepted"):
            load_scoped_inclusion_references(folder, selected, points, include_zheleznodorozhny=True)

    def test_aggregate_parent_is_rejected_even_when_its_type_is_city(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        selected["old:parent"]["population_scope"] = "federal_city_region"
        selected["old:parent"]["is_federal_aggregate"] = True
        with self.assertRaisesRegex(ValueError, "not physical-settlement grain"):
            load_scoped_inclusion_references(folder, selected, points)

    def test_changed_geonames_coordinate_is_rejected_after_origin_repin(self):
        temp, folder, selected, points = self.fixture()
        self.addCleanup(temp.cleanup)
        archive = folder / "geonames.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("RU.txt", "1001\tTest Settlement\t\t\t52.0\t39.0\tP\tPPL\tRU\n")
        line_hash = hashlib.sha256(b"1001\tTest Settlement\t\t\t52.0\t39.0\tP\tPPL\tRU\n").hexdigest()
        path = folder / "scoped_point_uses.csv"
        replace_csv_row(path, "point_use_id", "point:child", {
            "point_origin_sha256": sha(archive), "point_origin_line_sha256": line_hash,
        })
        resign(folder, path.name)
        with self.assertRaisesRegex(ValueError, "source coordinates differ"):
            load_scoped_inclusion_references(folder, selected, points)

    def test_union_requires_receiver_and_parent_and_does_not_double_count(self):
        row = {"year": 2002, "population": 17, "source_record_id": "old:child",
               "old_same_year_city_proper_source_record_id": "old:parent",
               "current_2021_receiver_source_record_id": "now:parent"}
        base = {"old:parent": 80, "old:child": 17}
        once = apply_scoped_inclusion_reference(base, 2002, row,
                                                represented_current_receivers={"now:parent"})
        self.assertEqual(once, base)
        self.assertIsNot(once, base)
        with self.assertRaisesRegex(ValueError, "receiver"):
            apply_scoped_inclusion_reference(base, 2002, row, represented_current_receivers=set())
        with self.assertRaisesRegex(ValueError, "parent"):
            apply_scoped_inclusion_reference({"old:child": 17}, 2002, row,
                                             represented_current_receivers={"now:parent"})
        with self.assertRaisesRegex(ValueError, "differs"):
            apply_scoped_inclusion_reference({"old:parent": 80, "old:child": 18}, 2002, row,
                                             represented_current_receivers={"now:parent"})
        self.assertEqual(apply_scoped_inclusion_reference(base, 2010, row,
                                                          represented_current_receivers=set()), base)


if __name__ == "__main__":
    unittest.main()

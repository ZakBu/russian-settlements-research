import csv
import hashlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from research_rebuild.mass_linkage import recover_admin_context as recover


class FakeSheet:
    def __init__(self, rows):
        self.rows = rows
        self.nrows = len(rows)
        self.ncols = max(map(len, rows))

    def cell_value(self, row, col):
        return self.rows[row][col] if col < len(self.rows[row]) else ""


class FakeBook:
    def __init__(self, sheet):
        self.sheet = sheet

    def sheet_names(self):
        return ["NW"]

    def sheet_by_name(self, name):
        if name != "NW":
            raise KeyError(name)
        return self.sheet

    def unload_sheet(self, name):
        pass

    def release_resources(self):
        pass


def make_sheet():
    return FakeSheet([
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "Год переписи", "2010", "", ""],
        ["№", "субъ1", "субъ2", "район", "н.п.", "Всего"],
        ["", "", "", "", "", ""],
        [1, "Region A", "Region A", "District One", "village One", 10],
        [2, "", "Region A", "", "Village Two", 9],
        [3, "Region B", "Region B", "", "Village Three", 7],
        [4, "Region B", "Region B", "", "Village Four", 6],
    ])


class RecoverAdminContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raw_root = self.root / "raw"
        self.raw_root.mkdir()
        self.source = self.raw_root / recover.SOURCE_FILE
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"synthetic-xls-placeholder")
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.manifest = self.root / "manifest.csv"
        with self.manifest.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["path", "sha256"])
            writer.writeheader()
            writer.writerow({"path": recover.SOURCE_FILE, "sha256": self.sha})
        self.selection = self.root / "selected.parquet"
        conn = duckdb.connect()
        conn.execute("""
            CREATE TABLE selected (
                source_record_id VARCHAR, census_year INTEGER, source_file VARCHAR,
                source_sheet VARCHAR, source_row INTEGER, source_native_id VARCHAR,
                source_name_raw VARCHAR, settlement_name VARCHAR, district_raw VARCHAR, region_raw VARCHAR,
                population BIGINT, population_value_quality VARCHAR, settlement_id VARCHAR
            )
        """)
        conn.executemany("INSERT INTO selected VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            ("id-6", 2010, recover.SOURCE_FILE, "NW", 6, "1", "village One", "village One", "District One", "Region A", 10, recover.QUALITY, "candidate-A"),
            ("id-7", 2010, recover.SOURCE_FILE, "NW", 7, "2", "Village Two", "Village Two", None, "Region A", 9, recover.QUALITY, "candidate-B"),
            ("id-8", 2010, recover.SOURCE_FILE, "NW", 8, "3", "Village Three", "Village Three", None, "Region B", 7, recover.QUALITY, "candidate-C"),
            ("id-9", 2010, recover.SOURCE_FILE, "NW", 9, "4", "Village Four", "Village Four", "Wrong District", "Region B", 5, recover.QUALITY, "candidate-D"),
        ])
        conn.execute("COPY selected TO ? (FORMAT PARQUET)", [str(self.selection)])
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_inherits_only_inside_same_explicit_region_and_exact_source_rows(self):
        fake_module = types.SimpleNamespace(open_workbook=lambda *_args, **_kwargs: FakeBook(make_sheet()))
        with patch.dict(sys.modules, {"xlrd": fake_module}):
            result = recover.recover_admin_context(self.selection, self.raw_root, self.manifest)
        rows = result["assertions"]
        self.assertEqual([r["source_row_1based"] for r in rows], [6, 7])
        inherited = rows[1]
        self.assertEqual(inherited["recovered_district_raw"], "District One")
        self.assertEqual(inherited["recovered_district_from_row_1based"], 6)
        self.assertEqual(inherited["assertion_status"], "source_context_assertion_pending_review")
        self.assertEqual(inherited["identity_status"], "not_evaluated_not_admitted_by_context_recovery")
        self.assertIsNone(inherited["valid_from"])
        self.assertIsNone(inherited["valid_to"])
        self.assertIsNone(inherited["current_district_matches_source_context"])
        self.assertTrue(rows[0]["current_district_matches_source_context"])
        self.assertEqual(result["diagnostics"]["source_population_mismatch"], 1)
        self.assertEqual(result["diagnostics"]["source_label_mismatch"], 0)
        self.assertEqual(result["diagnostics"]["missing_context_district"], 2)
        self.assertEqual(result["diagnostics"]["current_district_matches_explicit"], 1)

    def test_source_hash_and_workbook_layout_are_mandatory(self):
        fake_module = types.SimpleNamespace(open_workbook=lambda *_args, **_kwargs: FakeBook(make_sheet()))
        with patch.dict(sys.modules, {"xlrd": fake_module}):
            self.source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "workbook hash mismatch"):
                recover.recover_admin_context(self.selection, self.raw_root, self.manifest)
            self.source.write_bytes(b"synthetic-xls-placeholder")
            bad = make_sheet()
            bad.rows[3][3] = "status"
            fake_module.open_workbook = lambda *_args, **_kwargs: FakeBook(bad)
            with self.assertRaisesRegex(ValueError, "does not match the audited NW layout"):
                recover.recover_admin_context(self.selection, self.raw_root, self.manifest)

    def test_context_normalization_does_not_pad_or_guess(self):
        self.assertEqual(recover._context_norm("Вельский район"), recover._context_norm("Вельский"))
        self.assertEqual(recover._norm("Ёлки  2"), "елки 2")
        self.assertEqual(recover._population_int(12.0), 12)
        self.assertIsNone(recover._population_int(12.5))
        self.assertIsNone(recover._population_int("12 тыс."))
        self.assertFalse(recover._usable_context("??"))
        self.assertFalse(recover._usable_context("!"))
        self.assertTrue(recover._usable_context("Вельский район"))

    def test_national_profile_requires_exact_row_label_population_and_region_boundaries(self):
        fake_module = types.SimpleNamespace(open_workbook=lambda *_args, **_kwargs: FakeBook(make_sheet()))
        with patch.dict(sys.modules, {"xlrd": fake_module}):
            result = recover.recover_national_admin_context(self.selection, self.raw_root, self.manifest)
        self.assertEqual(result["scope"]["profiled_protected_rows"], 4)
        rows = result["assertions"]
        self.assertEqual([r["source_row_1based"] for r in rows], [6, 7])
        self.assertEqual(rows[0]["source_context_kind"], "district_or_urban_administrative_parent_unclassified")
        self.assertEqual(rows[1]["recovered_district_raw"], "District One")
        self.assertEqual(rows[1]["recovered_district_from_row_1based"], 6)
        self.assertEqual(rows[1]["source_record_id"], "id-7")
        self.assertEqual(rows[1]["target_region_normalized"], "region a")
        self.assertEqual(rows[1]["normalization_version"], recover.NORMALIZATION_VERSION)
        self.assertTrue(rows[1]["source_region_matches_selected"])
        self.assertEqual(rows[1]["identity_status"], "not_evaluated_not_admitted_by_context_recovery")
        self.assertIsNone(rows[1]["valid_from"])
        self.assertIsNone(rows[1]["valid_to"])
        self.assertEqual(result["profiled_sheets"][recover.SOURCE_FILE]["population_mismatches"], 1)
        self.assertEqual(result["profiled_sheets"][recover.SOURCE_FILE]["unasserted_target_rows"], 2)


if __name__ == "__main__":
    unittest.main()

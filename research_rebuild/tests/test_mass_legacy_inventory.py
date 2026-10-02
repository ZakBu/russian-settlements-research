import tempfile
import unittest
from pathlib import Path

import duckdb

from research_rebuild.mass_linkage import legacy_inventory


class LegacyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.database = self.root / "legacy_fixture.duckdb"
        conn = duckdb.connect(str(self.database))
        conn.execute("""
            CREATE TABLE population_observations (
                observation_year INTEGER,
                population_raw VARCHAR,
                population BIGINT,
                quality_status VARCHAR,
                source_url VARCHAR,
                source_sha256 VARCHAR,
                row_locator VARCHAR,
                point_in_time DATE
            )
        """)
        conn.executemany(
            "INSERT INTO population_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (2002, "4", 4, "direct official exact", "https://example.test/t1", "a" * 64, "sheet=1;row=2", "2002-10-09"),
                (2010, "5", 6, "confidentiality perturbed within ten", "https://example.test/t2", "b" * 64, "sheet=2;row=3", "2010-10-14"),
                (2010, "~1000", 1000, "rounded to thousands", None, None, "PDF p.9", "2010-10-14"),
            ],
        )
        conn.execute("""
            CREATE TABLE code_history (
                oktmo VARCHAR,
                okato VARCHAR,
                effective_date DATE,
                statement_id VARCHAR,
                references_json VARCHAR,
                raw_value VARCHAR
            )
        """)
        conn.execute("INSERT INTO code_history VALUES ('001', '002', '2011-01-01', 'Q1$abc', '[{}]', '001')")
        conn.execute("CREATE TABLE dated_text_fixture (record_date VARCHAR)")
        conn.executemany("INSERT INTO dated_text_fixture VALUES (?)", [("2021-10-01T00:00:00Z",), ("archived 2010 workbook",), ("unknown",)])
        conn.close()
        self.database_sha = legacy_inventory.sha256_file(self.database)

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspects_schema_counts_years_and_provenance_without_mutation(self):
        report = legacy_inventory.inspect_legacy_database(self.database, self.database_sha)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["table_count"], 3)
        self.assertEqual(report["candidate_table_count"], 2)
        by_name = {row["table"]: row for row in report["tables"]}
        population = by_name["population_observations"]
        self.assertEqual(population["row_count"], 3)
        self.assertEqual(population["field_role_columns"]["population"], ["population_raw", "population"])
        years = {row["field"]: row for row in population["temporal_fields"]}
        self.assertEqual(years["observation_year"]["year_value_counts"], {"2002": 1, "2010": 2})
        self.assertEqual(years["point_in_time"]["year_value_counts"], {"2002": 1, "2010": 2})
        quality = population["quality_or_precision_value_counts"][0]["value_counts"]
        classifications = {row["value_raw"]: row["classification"] for row in quality}
        self.assertEqual(classifications["direct official exact"], "explicit_exact_or_official_label")
        self.assertEqual(classifications["confidentiality perturbed within ten"], "protected_or_perturbed")
        self.assertEqual(classifications["rounded to thousands"], "rounded_or_estimated")
        self.assertIn("source_sha256", population["evidence_field_presence"]["provenance"])
        self.assertEqual(legacy_inventory.sha256_file(self.database), self.database_sha)

    def test_date_text_requires_a_leading_iso_date(self):
        report = legacy_inventory.inspect_legacy_database(self.database, self.database_sha)
        dated = next(row for row in report["tables"] if row["table"] == "dated_text_fixture")
        self.assertEqual(dated["temporal_fields"][0]["year_value_counts"], {"2021": 1})

    def test_code_history_is_candidate_and_dates_are_not_identity_admissions(self):
        report = legacy_inventory.inspect_legacy_database(self.database, self.database_sha)
        codes = next(row for row in report["tables"] if row["table"] == "code_history")
        self.assertIn("oktmo", codes["field_role_columns"]["identifier_or_code"])
        self.assertIn("effective_date", codes["field_role_columns"]["temporal"])
        self.assertIn("statement_id", codes["field_role_columns"]["provenance"])
        self.assertIn("references_json", codes["field_role_columns"]["provenance"])
        self.assertIn("not certification", codes["read_only_inventory_caveat"])

    def test_hash_is_required_and_mismatch_fails_before_open(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            legacy_inventory.inspect_legacy_database(self.database, "0" * 64)
        with self.assertRaisesRegex(ValueError, "expected_sha256"):
            legacy_inventory.verify_database(self.database, "not-a-sha")

    def test_selected_export_preserves_raw_and_interpreted_values_outside_repo(self):
        original_export_root = legacy_inventory.REQUIRED_EXPORT_ROOT
        with tempfile.TemporaryDirectory() as external:
            legacy_inventory.REQUIRED_EXPORT_ROOT = Path(external) / "legacy_inventory"
            output = legacy_inventory.REQUIRED_EXPORT_ROOT / "protected_rows.parquet"
            receipt = legacy_inventory.export_selected_rows(
                self.database, self.database_sha, "main", "population_observations",
                ["observation_year", "population_raw", "population", "quality_status", "source_url", "row_locator"],
                output, equals={"quality_status": "confidentiality perturbed within ten"},
            )
            self.assertEqual(receipt["row_count"], 1)
            self.assertTrue(receipt["source_values_preserved_without_interpretation"])
            exported = duckdb.connect().execute("SELECT population_raw, population, source_url, row_locator FROM read_parquet(?)", [str(output)]).fetchone()
            self.assertEqual(exported, ("5", 6, "https://example.test/t2", "sheet=2;row=3"))
            with self.assertRaisesRegex(FileExistsError, "protected_rows.parquet"):
                legacy_inventory.export_selected_rows(
                    self.database, self.database_sha, "main", "population_observations",
                    ["population_raw"], output,
                )
        legacy_inventory.REQUIRED_EXPORT_ROOT = original_export_root

    def test_exports_reject_checkout_paths_and_implicit_columns(self):
        original_export_root = legacy_inventory.REQUIRED_EXPORT_ROOT
        with tempfile.TemporaryDirectory() as external:
            legacy_inventory.REQUIRED_EXPORT_ROOT = Path(external) / "legacy_inventory"
            with self.assertRaisesRegex(ValueError, "outside the Git checkout"):
                legacy_inventory._check_external_output(legacy_inventory.REPOSITORY_ROOT / "bad.parquet")
            with self.assertRaisesRegex(ValueError, "explicit column list"):
                legacy_inventory.export_selected_rows(
                    self.database, self.database_sha, "main", "population_observations", [],
                    legacy_inventory.REQUIRED_EXPORT_ROOT / "bad.parquet",
                )
        legacy_inventory.REQUIRED_EXPORT_ROOT = original_export_root


if __name__ == "__main__":
    unittest.main()

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_rebuild/ingestion"))
from build_karelia_2010_fresh_primary import DEFAULT_DOCX, DEFAULT_PDF, build, canonical_frame_sha256


class FreshPrimaryExtractionTests(unittest.TestCase):
    def test_empty_output_run_extracts_800_rows_from_primary_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "empty-output"
            out.mkdir()
            self.assertEqual(list(out.iterdir()), [])
            summary = build(DEFAULT_DOCX, DEFAULT_PDF, out)
            result = pd.read_parquet(out / "karelia_2010_fresh_primary_observations.parquet")
            self.assertTrue(summary["source_independent_of_generated_row_cache"])
            self.assertEqual(len(result), 800)
            self.assertEqual(result.source_record_id.nunique(), 800)
            self.assertEqual(int(result.population.sum()), 643548)
            self.assertEqual(int(result.men.sum() + result.women.sum()), 643548)
            self.assertEqual(int((result.population == 0).sum()), 109)
            self.assertEqual(
                result[result.source_role.eq("official_rosstat_volume_1_table_5_urban")].shape[0], 24
            )
            rural = result[result.source_role.eq("official_regional_census_rural")]
            self.assertEqual(len(rural), 776)
            self.assertEqual(int(rural.population.sum()), 141331)
            self.assertEqual(summary["table5_extraction_summary"]["urban_source_population"], 502217)
            facts = json.loads((out / "rural_source_extraction/karelia_2010_rural_docx_source_facts.json").read_text())
            self.assertEqual(facts["document_cell_text_difference_count_vs_python_docx"], 2)
            self.assertEqual(facts["document_cell_audit_count"], 36753)
            self.assertEqual(facts["source_path"], "evidence/ingestion/source/karelia_2010_rural_settlements.docx")
            receipt = json.loads((out / "run_receipt.json").read_text())
            self.assertEqual(receipt["output_row_count"], 800)
            self.assertEqual(receipt["output_population"], 643548)
            self.assertEqual(len(receipt["input_sources"]), 2)
            self.assertGreater(len(receipt["outputs"]), 8)
            self.assertTrue(receipt["canonical_parquet_content_sha256"])
            self.assertEqual(receipt["input_sources"][0]["logical_locator"],
                             "evidence/ingestion/source/karelia_2010_rural_settlements.docx")
            self.assertEqual(receipt["input_sources"][1]["logical_locator"],
                             "data/raw/2010_official_tom11/pub-11-1-4.pdf")
            self.assertEqual(set(result.source_path.unique()), {
                "evidence/ingestion/source/karelia_2010_rural_settlements.docx",
                "data/raw/2010_official_tom11/pub-11-1-4.pdf",
            })
            from hashlib import sha256
            listed = {item["path"]: item["sha256"] for item in receipt["outputs"]}
            summary_path = out / "karelia_2010_fresh_primary_summary.json"
            self.assertEqual(listed[summary_path.name], sha256(summary_path.read_bytes()).hexdigest())
            self.assertTrue((out / "run_receipt.json.sha256").is_file())

    def test_typed_content_hash_ignores_parquet_container_metadata(self):
        frame = pd.DataFrame({"id": ["a", "b"], "population": [0, 7], "context": [None, "x"]})
        self.assertEqual(canonical_frame_sha256(frame), canonical_frame_sha256(frame.copy()))


if __name__ == "__main__":
    unittest.main()

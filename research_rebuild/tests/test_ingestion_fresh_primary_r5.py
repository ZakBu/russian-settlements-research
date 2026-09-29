import json
import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research_rebuild/ingestion'))
from build_karelia_2010_fresh_primary_r5 import DEFAULT_DOCX, DEFAULT_PDF, build, EXTRACTION_VERSION

class FreshPrimaryR5Tests(unittest.TestCase):
    def test_wrong_pdf_hash_fails_before_parser_or_output(self):
        wrong=ROOT/'data/raw/2010_official_tom11/pub-11-1-4.pdf'
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';out.mkdir()
            with self.assertRaisesRegex(ValueError,'Source provenance mismatch before extraction'):
                build(DEFAULT_DOCX,wrong,out)
            self.assertEqual(list(out.iterdir()),[])

    def test_empty_run_uses_hashed_volume1_table5_and_preserves_controls(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';out.mkdir()
            summary=build(DEFAULT_DOCX,DEFAULT_PDF,out)
            data=pd.read_parquet(out/'karelia_2010_fresh_primary_observations.parquet')
            receipt=json.loads((out/'run_receipt.json').read_text())
            self.assertEqual(summary['extraction_version'],EXTRACTION_VERSION)
            self.assertEqual(len(data),800)
            self.assertEqual(data.source_record_id.nunique(),800)
            self.assertEqual(int(data.population.sum()),643548)
            self.assertEqual(int(data.men.sum()+data.women.sum()),643548)
            self.assertEqual(int((data.population==0).sum()),109)
            self.assertEqual(data.extraction_version.unique().tolist(),[EXTRACTION_VERSION])
            self.assertEqual(receipt['input_sources'][1]['logical_locator'],
              'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf')
            self.assertEqual(receipt['input_sources'][1]['sha256'],
              '42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3')
            self.assertEqual(data.loc[data.source_role.eq('official_rosstat_volume_1_table_5_urban'),'source_path'].unique().tolist(),
              ['data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf'])
            self.assertIn('source_locator_contract',receipt)
            self.assertTrue((out/'run_receipt.json.sha256').is_file())

if __name__=='__main__': unittest.main()

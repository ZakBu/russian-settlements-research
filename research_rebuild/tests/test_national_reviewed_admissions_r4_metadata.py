from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import pandas as pd
from research_rebuild.linkage.build_national_reviewed_admissions_r4_metadata import build, ROOT
R3=ROOT/"research_rebuild/evidence/releases/national_reviewed_admissions_r3_20260930"
R4=ROOT/"research_rebuild/evidence/releases/national_reviewed_admissions_r4_metadata_20260930"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
class R4MetadataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.m=json.loads((R4/"release_manifest.json").read_text())
  cls.d=pd.read_csv(R4/"tom11_bridge_decisions.csv")
 def test_locator_is_null_or_typed_and_table5_remains_distinct(self):
  self.assertEqual(len(self.d),965)
  for r in self.d.itertuples(index=False):
   ev=json.loads(r.evidence_json); selected=ev["selected_2010_endpoint"]; t5=ev["independent_2010_table5_binding"]
   self.assertEqual(selected["source_record_id"],r.to_source_record_id)
   self.assertTrue(t5["reference_id"].startswith("ROSSTAT2010:T5:"))
   self.assertIn("source_file",selected)
   self.assertNotEqual(selected.get("source_locator"),"None")
   self.assertNotEqual(selected.get("source_locator"),"nan")
   if selected["source_locator"] is None:
    self.assertTrue(selected["source_locator_null_reason"])
    self.assertTrue(selected["source_sheet"])
    self.assertIsNotNone(selected["source_row"])
   else:
    self.assertIsNone(selected["source_locator_null_reason"])
   self.assertEqual(t5["source_pdf"],"data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf")
   self.assertTrue(selected["source_sheet"])
 def test_scientific_outputs_unchanged(self):
  for name in ("identity_edges_accepted.csv","coordinate_admissions.csv","publication_bindings.csv","reviewed_case_axes.csv","selection_checks.csv","coverage_by_year.csv"):
   self.assertEqual(sha(R4/name),sha(R3/name),name)
  prior=pd.read_csv(R3/"tom11_bridge_decisions.csv")
  self.assertEqual(self.d.decision_id.tolist(),prior.decision_id.tolist())
  self.assertEqual(self.d.decision_action.tolist(),prior.decision_action.tolist())
 def test_manifest_hashes_and_fresh_build(self):
  for name,e in self.m["outputs"].items(): self.assertEqual(sha(R4/name),e["sha256"],name)
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/"fresh"; fresh=build(out)
   for name,e in self.m["outputs"].items(): self.assertEqual(sha(out/name),e["sha256"],name)
   self.assertEqual(fresh["decisions"],self.m["decisions"])
if __name__=="__main__": unittest.main()

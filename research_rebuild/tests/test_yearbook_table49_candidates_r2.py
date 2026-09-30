from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import pandas as pd
from research_rebuild.linkage.build_yearbook_table49_candidates_r2 import build, ROOT
OUT=ROOT/"research_rebuild/evidence/discovery/yearbook_table49_2010_2021_candidates_r2_20260930"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
class YearbookTable49Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.m=json.loads((OUT/"manifest.json").read_text())
  cls.rows=pd.read_csv(OUT/"table49_source_rows.csv",keep_default_na=False)
  cls.cand=pd.read_csv(OUT/"bridge_candidates_2010_2021.csv",keep_default_na=False)
  cls.byname=cls.rows.set_index("normalized_city_label")
 def test_table_source_reconciliation_and_edge_cases(self):
  self.assertEqual(len(self.rows),172)
  self.assertEqual(self.rows.row_id.nunique(),172)
  self.assertEqual(self.m["extraction"]["page_row_counts"],{"91":33,"92":77,"93":62})
  self.assertEqual(self.byname.loc["Волгоград","2010_raw"],"1 021")
  b=self.rows[self.rows.raw_russian_label.str.startswith("Благовещенск")].iloc[0]
  self.assertEqual(b.explicit_region_qualifier_raw,"Амурская область")
  self.assertEqual(b["2002_raw"],"219")
  self.assertEqual(self.rows[self.rows.normalized_city_label.eq("Балашиха")].footnote_markers.iloc[0],"2")
  self.assertEqual(self.rows[self.rows.normalized_city_label.eq("Москва")].footnote_markers.iloc[0],"3")
  for name in ("Зеленодольск","Ханты-Мансийск"):
   r=self.rows[self.rows.normalized_city_label.eq(name)].iloc[0]
   self.assertEqual(r["2002_missing_kind"],"blank"); self.assertEqual(r["2010_missing_kind"],"blank")
  self.assertEqual(self.rows[self.rows.normalized_city_label.eq("Евпатория")]["2002_missing_kind"].iloc[0],"ellipsis")
  notes=json.loads((OUT/"table49_method_notes.json").read_text())
  self.assertIn("Данные  приведены",notes["source_verbatim_russian_footnote_block"])
  collapsed=" ".join(notes["source_verbatim_russian_footnote_block"].split())
  self.assertIn("изменения его границы в 2015 году",collapsed)
  self.assertIn("с 1 июля 2012 года",collapsed)
 def test_candidate_only_unique_typed_and_rounded_endpoints(self):
  self.assertEqual(len(self.cand),172)
  self.assertEqual(int(self.m["candidate_metrics"]["candidate_rows"]),163)
  eligible=self.cand[self.cand.candidate_status_2010_2021.eq("candidate_for_independent_review")]
  self.assertEqual(len(eligible),163)
  self.assertFalse(eligible.is_identity_admission.astype(str).str.lower().eq("true").any())
  for y in (2010,2021):
   self.assertTrue(eligible[f"{y}_rounding_compatible"].astype(str).str.lower().eq("true").all())
   self.assertTrue(eligible[f"{y}_match_count"].astype(int).eq(1).all())
   self.assertTrue(eligible[f"{y}_settlement_type"].eq("город").all())
   self.assertFalse(eligible[f"{y}_source_record_id"].duplicated().any())
  self.assertEqual(len(self.cand[self.cand.candidate_status_2010_2021.str.contains("boundary_change_footnote_hold")]),2)
  self.assertEqual(len(self.cand[self.cand.candidate_status_2010_2021.str.contains("federal_city_scope_hold")]),3)
  self.assertTrue(self.cand.candidate_status_2010_2021.str.contains("yearbook_2010_value_ellipsis").sum()>=3)
  self.assertTrue((pd.to_numeric(eligible["2010_population"]).sum())>53_000_000)
  self.assertTrue((pd.to_numeric(eligible["2021_population"]).sum())>56_000_000)
 def test_exact_endpoint_source_receipts(self):
  eligible=self.cand[self.cand.candidate_status_2010_2021.eq("candidate_for_independent_review")]
  for y in (2010,2021):
   self.assertTrue(eligible[f"{y}_source_sha256"].str.fullmatch(r"[0-9a-f]{64}").all())
   self.assertTrue(eligible[f"{y}_source_file"].notna().all())
   self.assertTrue(eligible[f"{y}_source_sheet"].notna().all())
   self.assertTrue(eligible[f"{y}_source_row"].notna().all())
  self.assertEqual(set(self.m["endpoint_source_files"]),{
   "data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf",
   "data/raw/2010_official_tom11/pub-11-1-4.pdf",
   "data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet"})
 def test_hashes_and_fresh_rebuild(self):
  for name,e in self.m["outputs"].items(): self.assertEqual(sha(OUT/name),e["sha256"],name)
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/"release"; fresh=build(out)
   for name,e in self.m["outputs"].items(): self.assertEqual(sha(out/name),e["sha256"],name)
   self.assertEqual(fresh["candidate_metrics"],self.m["candidate_metrics"])
if __name__=="__main__": unittest.main()

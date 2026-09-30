from pathlib import Path
import csv,hashlib,json,unittest
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
REL=ROOT/'research_rebuild/evidence/releases/national_reviewed_admissions_r5b_yearbook_20260930'
BASE=ROOT/'research_rebuild/evidence/releases/national_reviewed_admissions_r4_metadata_20260930'
SEL=ROOT/'research_rebuild/evidence/releases/national_source_selection_r1_20260930/selected_observations.parquet'
CAND=ROOT/'research_rebuild/evidence/discovery/yearbook_table49_2010_2021_candidates_r2_20260930/bridge_candidates_2010_2021.csv'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class YearbookAdmissionTests(unittest.TestCase):
 def test_exact_decision_partition_and_endpoint_set(self):
  decisions=pd.read_csv(REL/'yearbook_bridge_decisions.csv')
  edges=pd.read_csv(REL/'yearbook_new_identity_edges.csv')
  pairs=pd.read_csv(REL/'accepted_and_deduplicated_yearbook_pairs.csv')
  self.assertEqual(len(decisions),163);self.assertEqual(len(edges),159);self.assertEqual(len(pairs),163)
  self.assertEqual(decisions.decision_action.value_counts().to_dict(),{'applied':159,'recorded_supporting_evidence_no_duplicate_edge':4})
  c=pd.read_csv(CAND);c=c[c.candidate_status_2010_2021.eq('candidate_for_independent_review')]
  self.assertEqual(set(zip(c['2010_source_record_id'],c['2021_source_record_id'])),set(zip(decisions.from_source_record_id,decisions.to_source_record_id)))
  self.assertEqual(edges.decision_id.nunique(),159)
 def test_selected_component_has_one_record_per_year_and_no_new_points(self):
  edges=pd.read_csv(REL/'identity_edges_accepted.csv')
  self.assertEqual(len(edges),1162);self.assertFalse(edges.decision_id.duplicated().any())
  selected=pd.read_parquet(SEL); selected.source_record_id=selected.source_record_id.astype(str)
  linked=set(edges.from_source_record_id.astype(str))|set(edges.to_source_record_id.astype(str))
  nodes=selected[selected.source_record_id.isin(linked)].copy()
  parent={}
  def find(x):
   parent.setdefault(x,x)
   if parent[x]!=x:parent[x]=find(parent[x])
   return parent[x]
  for r in edges.itertuples():
   a,b=find(str(r.from_source_record_id)),find(str(r.to_source_record_id))
   if a!=b:parent[b]=a
  nodes['component']=nodes.source_record_id.map(find)
  self.assertFalse((nodes.groupby(['component','census_year']).source_record_id.nunique()>1).any())
  self.assertEqual(sha(REL/'coordinate_admissions.csv'),sha(BASE/'coordinate_admissions.csv'))
 def test_certified_incremental_coverage_and_receipts(self):
  m=json.loads((REL/'release_manifest.json').read_text())
  self.assertEqual(m['decisions']['new_identity_edges'],159)
  self.assertEqual(m['decisions']['already_connected_supporting_decisions'],4)
  self.assertEqual(m['decisions']['newly_linked_coverage_by_year'],[
   {'year':2002,'newly_linked_selected_rows':0,'newly_linked_selected_population':0},
   {'year':2010,'newly_linked_selected_rows':6,'newly_linked_selected_population':1012219},
   {'year':2021,'newly_linked_selected_rows':159,'newly_linked_selected_population':52504994}])
  self.assertEqual(m['review_gate']['accepted'],24)
  self.assertEqual(m['limitations'][-1],'No coordinate or point-in-time geometry is admitted by Yearbook continuity.')
  for name,entry in m['outputs'].items():self.assertEqual(sha(REL/name),entry['sha256'])

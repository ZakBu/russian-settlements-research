#!/usr/bin/env python3
"""Read back the frozen 129 OKATO candidate pairs against full Graph28 ledgers."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd

CANDIDATES=Path('/workspace/russian-settlements-research/research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/historical_code_bridge_129_candidate_component_readback_20261005.csv')
EDGES=Path('/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet')
POINTS=Path('/tmp/graph28_three_code_bridge_20261005/accepted_point_uses.parquet')
OUT=Path('/tmp/historical_code_bridge_129_full_graph_readback_20261005.json')
EXPECTED={
 'candidates':'a5e3476269a5077dab7d43c715989d4ea4a440faf0171a3e3bb781d5d3dba8d8',
 'edges':'583364c80cddc4fbed00dd06527f734242b1983c268f83a78a38946a811ede1d',
 'points':'e4c8de5891a179057356d357e564e5928e0d0113519e8b9e8f1152df8ef479fb',
}
EDGE_STATUSES={
 'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect',
 'accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted',
 'case_review_accepted','independent_case_review_accepted','accepted_case_specific',
}
POINT_STATUSES={'reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted'}
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 paths={'candidates':CANDIDATES,'edges':EDGES,'points':POINTS}
 for key,path in paths.items():
  got=sha(path)
  if got!=EXPECTED[key]:raise ValueError(f'{key} SHA mismatch: {got}')
 c=pd.read_csv(CANDIDATES,dtype=str).fillna('')
 if len(c)!=129 or c[['source_record_id_02','source_record_id_10']].isna().any().any():raise ValueError('candidate cohort shape/IDs mismatch')
 e=pd.read_parquet(EDGES,columns=['from_source_record_id','to_source_record_id','relation','decision_status'])
 e=e[e.relation.eq('same_place')&e.decision_status.isin(EDGE_STATUSES)]
 parent={}
 def find(x):
  parent.setdefault(x,x)
  while parent[x]!=x:
   parent[x]=parent[parent[x]];x=parent[x]
  return x
 for a,b in e[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
  a,b=str(a),str(b);ra,rb=find(a),find(b)
  if ra!=rb:parent[rb]=ra
 connected=[]
 for row in c.itertuples(index=False):
  a,b=str(row.source_record_id_02),str(row.source_record_id_10)
  connected.append(a in parent and b in parent and find(a)==find(b))
 p=pd.read_parquet(POINTS,columns=['target_source_record_id','coordinate_admission_status'])
 p=set(p.loc[p.coordinate_admission_status.isin(POINT_STATUSES),'target_source_record_id'].astype(str))
 dual=[str(a) in p and str(b) in p for a,b in c[['source_record_id_02','source_record_id_10']].itertuples(index=False,name=None)]
 if not all(connected):raise ValueError(f'not all candidate pairs are connected: {sum(connected)}/129')
 result={'status':'full_graph_candidate_overlap_reproduced','candidate_pairs':len(c),'accepted_same_place_edges':len(e),'candidate_pairs_connected_in_full_graph':sum(connected),'pairs_with_accepted_points_on_both_endpoints':sum(dual),'point_gap_pair_names':c.loc[[not v for v in dual],'settlement_name'].astype(str).tolist(),'new_identity_edges_added':0,'gross_selected_population_observations_by_year':{'2002':int(pd.to_numeric(c.population_02).sum()),'2010':int(pd.to_numeric(c.population_10).sum())},'input_sha256':{k:sha(v) for k,v in paths.items()}}
 if result['point_gap_pair_names']!=['Ожерелье']:raise ValueError(f'unexpected point gaps: {result["point_gap_pair_names"]}')
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

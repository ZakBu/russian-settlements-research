#!/usr/bin/env python3
"""Independent readback guards for the narrowly scoped Graph19 Lokot increment."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd

ROOT = Path('/workspace/settlements-work/continuation_20261004')
GRAPH = ROOT / 'accepted_graph19_lokot_20261005/accepted_identity_edges.parquet'
POINTS = ROOT / 'accepted_graph19_lokot_20261005/accepted_point_uses.parquet'
APP = ROOT / 'accepted_graph19_lokot_20261005/receipt.json'
COVERAGE = ROOT / 'coverage_graph19_lokot_20261005/scoped_joint_coverage.json'
BASE_COVERAGE = ROOT / 'coverage_graph18_russky_only_20261005/scoped_joint_coverage.json'
LONG = ROOT / 'root/long_graph19_lokot_patch_20261005/settlements_long_refreshed.parquet'
LONG_RECEIPT = ROOT / 'root/long_graph19_lokot_patch_20261005/refresh_receipt.json'
IDS = [
 '2002:1_TOM_01_04.xls:0:133',
 'ROSSTAT2010:T5:p15:l48',
 '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:173506',
]
POP = {'2002': 12094, '2010': 10028, '2021': 8469}
CONTROLS = {'2002':145166731, '2010':142856536, '2021':147182123}

def sha(p: Path) -> str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def main():
 app=json.loads(APP.read_text()); cov=json.loads(COVERAGE.read_text()); base=json.loads(BASE_COVERAGE.read_text()); lr=json.loads(LONG_RECEIPT.read_text())
 assert app['status']=='applied_manifest_pinned_reviewed_mass_extensions'
 assert app['new_identity_rows']==2 and app['new_direct_point_uses']==1 and app['new_continuity_point_uses']==1
 edges=pd.read_parquet(GRAPH)
 selected_pairs={('2002:1_TOM_01_04.xls:0:133','ROSSTAT2010:T5:p15:l48'),('ROSSTAT2010:T5:p15:l48',IDS[2])}
 rows=edges[edges.from_source_record_id.astype(str).isin(IDS)&edges.to_source_record_id.astype(str).isin(IDS)]
 got={(str(r.from_source_record_id),str(r.to_source_record_id)) for r in rows.itertuples()}
 assert got==selected_pairs, got
 points=pd.read_parquet(POINTS)
 p=points[points.target_source_record_id.astype(str).isin(IDS)].set_index('target_source_record_id')
 assert set(p.index)==set(IDS)
 assert tuple(p.loc[IDS[0],['latitude','longitude']].astype(float))==(52.573368,34.568384)
 assert tuple(p.loc[IDS[1],['latitude','longitude']].astype(float))==(52.5609693,34.576992)
 assert tuple(p.loc[IDS[2],['latitude','longitude']].astype(float))==(52.5609693,34.576992)
 assert str(p.loc[IDS[1],'application_inference_kind'])=='sourced_representative_point_reuse_across_accepted_observed_years'
 assert str(p.loc[IDS[2],'coordinate_quality'])=='direct_current_settlement_record_FIAS6_OKATO_OKTMO'
 # All three selected values and identity-to-point joins survive in full long output.
 long=pd.read_parquet(LONG)
 l=long[long.observation_id.astype(str).isin('census:'+pd.Series(IDS))].set_index('observation_id')
 assert len(l)==3
 for year,sid in zip(['2002','2010','2021'],IDS):
  r=l.loc['census:'+sid]
  assert int(r.population_value)==POP[year]
  assert bool(r.census_full_chain)
  assert pd.notna(r.latitude) and pd.notna(r.longitude)
  assert str(r.entity_id).endswith(IDS[2])
 assert lr['status']=='full_long_exact_census_observation_patch_passed'
 assert lr['final_rows']==865395 and lr['census_rows']==465800 and int(lr['selected_census_population_sum'])==434700152
 assert lr['population_values_modified'] is False
 result={}
 for year,control in CONTROLS.items():
  now=cov['results'][year]; old=base['results'][year]
  assert now['available_scope_joint_population']-old['available_scope_joint_population']==POP[year]
  assert now['control_population']==control
  assert now['remaining_population_to_99']==max(0,(__import__('math').ceil(control*.99)-now['available_scope_joint_population']))
  result[year]={
   'available_scope_joint_population':now['available_scope_joint_population'],
   'official_control_fraction':now['available_scope_joint_percent']/100,
   'improvement_vs_graph18_people':POP[year],
   'remaining_to_99':now['remaining_population_to_99'],
   'strict_NP_joint_population':now['strict_NP_joint_population'],
   'strict_NP_joint_fraction':now['strict_NP_joint_population']/control,
  }
 out={
  'status':'independent_graph19_lokot_readback_passed',
  'selected_ids':IDS,
  'selected_population_values_retained':POP,
  'new_identity_edges':2,
  'direct_2021_point_uses':1,
  'continuity_2010_point_uses':1,
  'all_three_long_rows_have_coordinates_and_full_chain':True,
  'full_long_rows':lr['final_rows'],
  'full_long_census_rows':lr['census_rows'],
  'full_long_census_population_sum':int(lr['selected_census_population_sum']),
  'axes':result,
  'sha256':{str(p):sha(p) for p in [APP,GRAPH,POINTS,COVERAGE,LONG,LONG_RECEIPT]},
 }
 dest=Path(__file__).resolve().parents[1]/'evidence/mass_joint_20261004/graph19_lokot/independent_readback.json'
 dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

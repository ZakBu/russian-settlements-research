"""Disk replay of the additional exclusive whole-locality projection on frozen stage21."""
import sys,json
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from current_chain_state_20261007 import sha
r=json.loads((OUT/'application_receipt.json').read_text())
for path,digest in r['inputs'].items():assert sha(Path(path))==digest,path
for name,digest in r['outputs'].items():assert sha(OUT/name)==digest,name
s=load(stage=21);prior=set(pd.read_csv(PARTITION_MEMBERS).source_record_id);event=ROOT/'research_rebuild/evidence/event_aware_path_union_20261005/accepted_event_path_selected_rows.csv';prior.update(pd.read_csv(event,dtype=str).source_record_id)
projection=pd.read_csv(OUT/'accepted_exclusive_member_projection.csv');series=pd.read_csv(OUT/'accepted_three_census_whole_place_series.csv');assert not projection.source_record_id.duplicated().any();assert len(projection)==4 and len(series)==3
for year,g in projection.groupby('year'):
 whole=series[series.year.eq(year)].iloc[0];assert set(json.loads(whole.member_source_record_ids_json))==set(g.source_record_id);assert int(g.population.sum())==int(whole.population)
 for row in g.itertuples():assert int(s.by_id.loc[row.source_record_id,'population'])==int(row.population);assert int(s.by_id.loc[row.source_record_id,'census_year'])==int(year)
assert s.metrics(extra_covered_ids=prior)==r['before_ordinary_plus_prior_selected_member_union'];assert s.metrics(extra_covered_ids=prior|set(projection.source_record_id))==r['after_plus_new_complete_partition_union']
r['disk_replay_stage21_plus_exclusive_member_union_verified']=True;(OUT/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('Disk replay passed: four unique selected members, three actual census observations, no part identity/point mutation.')

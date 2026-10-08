"""Exercise real frozen100 inputs on a bounded two-row baseline, without State.load."""
from pathlib import Path
from types import SimpleNamespace
import sys,json,hashlib
import duckdb,pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from build_long_table import UnionFind
from add_source_observations import append_reviewed_source_observations,apply_reviewed_parent_grain,STANDARD_COLUMNS
plan=json.loads((HERE/'plan.json').read_text())['source_supplement'];ZONE=ROOT/plan['zone'];SELECTED='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
ids=['2002:038_218ac665d8_02c_Astraxanskaja.xls:Sheet1:456','2002:038_218ac665d8_02c_Astraxanskaja.xls:Sheet1:457']
c=duckdb.connect();obs=c.execute('SELECT '+','.join(STANDARD_COLUMNS)+' FROM read_parquet(?) WHERE source_record_id IN (?,?)',[SELECTED,*ids]).fetchdf();c.close();assert len(obs)==2
obs['root']=obs.source_record_id
make=lambda frame:SimpleNamespace(obs=frame.copy(deep=True),by_id=frame.set_index('source_record_id',drop=False),uf=UnionFind(frame.source_record_id),years={sid:{2002} for sid in frame.source_record_id},point_rows={},inputs=[])
state=make(obs);before=obs.copy(deep=True)
kwargs=dict(observation_sha256=plan['observation_sha256'],metadata_sha256=plan['metadata_sha256'],accepted_metadata_statuses=plan['accepted_metadata_statuses'])
a=append_reviewed_source_observations(state,ZONE/plan['observations'],ZONE/plan['metadata'],**kwargs)
g=apply_reviewed_parent_grain(state,ZONE/plan['grain_delta'],delta_sha256=plan['grain_delta_sha256'],accepted_statuses=plan['accepted_grain_statuses'],baseline_credited_IDs=set())
assert len(state.obs)==102 and len(state.by_id)==102 and state.obs.source_record_id.is_unique
assert state.by_id.loc[ids[0],'population']==before.set_index('source_record_id',drop=False).loc[ids[0],'population']==544
assert state.by_id.loc[ids[1],STANDARD_COLUMNS].equals(before.set_index('source_record_id',drop=False).loc[ids[1],STANDARD_COLUMNS])
assert state.obs.loc[state.obs.is_additive_settlement_record,'population'].sum()-before.population.sum()==9312
# Publication overlap must reject a renamed copy before any observation/UF mutation.
r=pd.read_csv(ZONE/plan['observations'],dtype=str,keep_default_na=False).iloc[0].to_dict();sid=r['source_record_id'];pieces=sid.split(':');pieces[1]='renamed_publication_copy.xls';r['source_record_id']=':'.join(pieces);r['root']=r['source_record_id']
f=pd.concat([obs,pd.DataFrame([r])],ignore_index=True);f.census_year=pd.to_numeric(f.census_year);bad=make(f);failed=False
try:append_reviewed_source_observations(bad,ZONE/plan['observations'],ZONE/plan['metadata'],**kwargs)
except AssertionError as e:failed=str(e)=='publication-row overlap'
assert failed and bad.obs.equals(f) and len(bad.uf.parent)==len(f)
addon=json.loads((HERE/'plan.json').read_text())['source_observation_addons'][0];az=ROOT/addon['zone']
t=append_reviewed_source_observations(state,az/addon['observations'],az/addon['metadata'],observation_sha256=addon['observation_sha256'],metadata_sha256=addon['metadata_sha256'],accepted_metadata_statuses=addon['accepted_metadata_statuses'],expected_rows=addon['rows'],expected_population=addon['raw_source_population'])
assert len(state.obs)==130 and len(state.supplemental_source_metadata)==128 and state.supplemental_source_metadata.source_record_id.is_unique
assert state.obs.loc[state.obs.is_additive_settlement_record,'population'].sum()-before.population.sum()==12483
result={'status':'bounded_helper_integration_checks_passed','scope':'real frozen100 plus Tver28 sourceinputs and two actual baseline parent/child rows; not a full State baseline replay','appended_rows':a['rows']+t['rows'],'net_additive_population_delta':12483,'source_control_signed_gap':-757,'raw_parent_and_child_population_unchanged':True,'same_publication_row_via_renamed_copy_rejected_before_mutation':True,'State_load_calls':0,'live_API_or_selected_bytes_modified':False,'helper_sha256':hashlib.sha256((HERE/'add_source_observations.py').read_bytes()).hexdigest()}
(HERE/'helper_check_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

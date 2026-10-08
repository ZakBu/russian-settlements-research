"""Reproduce the bounded native suffix/former-name application from frozen stage 26."""
import sys,json,math
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
O=Path(__file__).parent

def finite_metrics(state):
 d=state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])];d=d[~(d.census_year.eq(2021)&d.region_norm.eq('крым'))]
 roots={state.uf.find(x) for x in d.source_record_id};badroots={state.uf.find(x) for x in state.conflicting_point_targets};members={}
 for x in state.by_id.index:members.setdefault(state.uf.find(x),[]).append(x)
 good={r for r in roots if state.years[r]=={2002,2010,2021} and r not in badroots and all(x in state.point_rows and math.isfinite(float(state.by_id.loc[x].population)) for x in members[r])}
 full=d[d.source_record_id.map(state.uf.find).isin(good)]
 return {'histories':len(good),'populations_by_year':{str(int(y)):int(g.population.sum()) for y,g in full.groupby('census_year')}}

def apply(state):
 receipt=json.loads((O/'application_receipt.json').read_text())
 for n,h in receipt['output_pins'].items():assert sha(O/n)==h,n
 for p,h in receipt['input_pins'].items():assert sha(Path(p))==h,p
 assert state.metrics()==receipt['before'],'Frozen26 baseline differs'
 state.reject_point_uses(O/'accepted_point_rejection_delta.csv')
 state.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv'])
 assert state.metrics()==receipt['after']
 return state

if __name__=='__main__':
 s=load(26);before=finite_metrics(s);s=apply(s);after=finite_metrics(s)
 p=O/'application_receipt.json';r=json.loads(p.read_text());r.update(status='Applied in memory and ready for root loader integration; frozen26 State API replay and source/output pins passed',before_finite_all3_all_points=before,after_finite_all3_all_points=after,net_finite_all3_all_points={'histories':after['histories']-before['histories'],'populations_by_year':{y:after['populations_by_year'][y]-before['populations_by_year'][y] for y in before['populations_by_year']}},State_API_replay_passed=True);p.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:r[k] for k in ['status','net_population_by_year','net_finite_all3_all_points']},ensure_ascii=False))

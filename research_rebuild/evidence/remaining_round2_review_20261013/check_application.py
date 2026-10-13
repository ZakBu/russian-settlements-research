import hashlib,json,math
from pathlib import Path
import pandas as pd

ROOT=Path('/workspace/russian-settlements-research')
E=ROOT/'research_rebuild/evidence'
O=Path(__file__).resolve().parent
A=E/'remaining_round2_root_20261013/applied'
B=Path('/workspace/scratch/residual-20261013/final')
F=Path('/workspace/scratch/residual-round2-20261013/final')
pins={}
def pin(p):
 p=Path(p);pins[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();return p
def csv(p):return pd.read_csv(pin(p))
def parquet(p):return pd.read_parquet(pin(p))
receipt=json.load(open(pin(A/'application_receipt.json')))
for p,v in receipt['input_pins'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==v['sha256'],p
for name,h in receipt['full_output_hashes'].items():assert hashlib.sha256((F/name).read_bytes()).hexdigest()==h,name
old=parquet(B/'applied_state_observations.parquet').set_index('source_record_id').sort_index()
new=parquet(F/'applied_state_observations.parquet').set_index('source_record_id').sort_index()
actual=parquet(F/'integrated_spatial_temporal_records.parquet').set_index('source_record_id').sort_index()
assert old.index.is_unique and new.index.equals(old.index) and actual.index.equals(old.index)
assert old.drop(columns='root').equals(new.drop(columns='root'))
assert new.equals(actual[new.columns])
pold=parquet(B/'applied_core_point_snapshot.parquet').set_index('source_record_id').sort_index()
pnew=parquet(F/'applied_core_point_snapshot.parquet').set_index('source_record_id').sort_index()
pointdelta=csv(A/'applied_point_use_delta.csv').set_index('target_source_record_id')
repair=next(i for i in pointdelta.index if i.endswith(':!!!:12204'))
assert set(pnew.index)-set(pold.index)==set(pointdelta.index)-set(pold.index)
assert len(pnew)==447367 and len(pold)==447366 and set(pold.index)<=set(pnew.index)
assert pold.drop(index=repair).equals(pnew.loc[pold.index].drop(index=repair))
for sid,r in pointdelta.iterrows():
 assert math.isclose(pnew.loc[sid,'latitude'],r.latitude,abs_tol=1e-10)
 assert math.isclose(pnew.loc[sid,'longitude'],r.longitude,abs_tol=1e-10)
 assert pnew.loc[sid,'point_origin_sha256']==r.point_origin_sha256
assert (pold.loc[repair,'latitude'],pold.loc[repair,'longitude'])==(57.593341,52.522646)
assert math.isclose(pnew.loc[repair,'latitude'],56.91305555555555,abs_tol=1e-10)
overlay=csv(ROOT/'publication/stage71/applied_primary_population_source_overlay_2010.csv.gz').set_index('original_source_record_id')
expected=new.index.to_series().map(overlay.population).combine_first(new.population)
assert actual.effective_population.equals(expected)
scope=pd.concat([csv(ROOT/'publication/stage71/accepted_large_record_scope_classification_overlay.csv'),csv(E/'over500_route_audit_20261009/accepted_scope_overlay.csv')])
def complete(frame,points):
 a=frame[frame.is_additive_settlement_record.fillna(False)&~frame.region_norm.isin(['москва','санкт петербург','крым','севастополь'])&~frame.index.isin(scope.source_record_id)].copy()
 a['point']=a.index.isin(points.index);a['finite']=a.population.notna()
 grouped=a.groupby('root')
 g=pd.DataFrame({'n':grouped.size(),'years':grouped.census_year.nunique(),'point':grouped.point.sum(),'finite':grouped.finite.sum()})
 roots=set(g[(g.n==3)&(g.years==3)&(g.point==3)&(g.finite==3)].index)
 return set(a.index[a.root.isin(roots)]),roots
before,beforeroots=complete(old,pold);full,roots=complete(new,pnew)
assert len(beforeroots)==142735 and len(roots)==142759 and before<=full
assert set(actual.index[actual.finite_ordinary_full3_all_ownpoints])==full
seed=csv(E/'residual_root_20261013/applied/integrated_credited_UID_roster.csv.gz')
ledger=csv(A/'integrated_credited_UID_roster.csv.gz')
routes=csv(A/'applied_typed_native_credit_routes.csv')
ids=set(seed.source_record_id)|full|set(routes.source_record_id)
assert len(seed)==431869 and len(ids)==431932 and ledger.source_record_id.is_unique
assert ids==set(ledger.source_record_id)==set(actual.index[actual.working_credit_present])
gained=ids-set(seed.source_record_id)
assert len(gained)==63 and gained==set(csv(A/'new_credit_native_records.csv.gz').source_record_id)
assert gained==set(actual.index[actual.new_credit_this_application])
fed=csv(ROOT/'publication/stage71/accepted_common_federal_territory_axis.csv')
assert len(fed)==6 and fed.population_source_record_id.is_unique and not set(fed.population_source_record_id)&ids
coverage=csv(A/'coverage.csv').set_index('census_year')
previous=csv(E/'residual_root_20261013/applied/coverage.csv').set_index('census_year')
totals={}
for year,den in [(2002,145166731),(2010,142856536),(2021,144699673)]:
 n=int(actual.loc[actual.census_year.eq(year)&actual.index.isin(ids),'effective_population'].sum()+fed.loc[fed.census_year.eq(year),'territory_population'].sum())
 gain=int(actual.loc[actual.census_year.eq(year)&actual.index.isin(gained),'effective_population'].sum())
 assert n==coverage.loc[year,'credited_population'] and den==coverage.loc[year,'denominator']
 assert math.isclose(100*n/den,coverage.loc[year,'coverage_percent'],abs_tol=1e-12)
 assert gain==coverage.loc[year,'net_population_gain']==n-previous.loc[year,'credited_population']
 totals[year]=dict(credited_population=n,new_uid_population=gain,coverage_percent=100*n/den)
edges=csv(A/'applied_identity_edges.csv');assert len(edges)==26
for _,r in edges.iterrows():assert new.loc[r.from_source_record_id,'root']==new.loc[r.to_source_record_id,'root']
events=csv(A/'applied_typed_events.csv');statuses=csv(A/'typed_available_year_statuses.csv')
assert len(events)==4 and routes.source_record_id.nunique()==6 and not routes.graph_union_allowed.any()
ev=events[events.scope_id.eq('round2_oreshkovo_merged_successor')].iloc[0]
donors=json.loads(ev.predecessor_source_record_ids);successor=routes.loc[routes.scope_id.eq(ev.scope_id),'source_record_id'].iloc[0]
assert len(set(new.loc[donors,'root']))==3 and new.loc[successor,'root'] not in set(new.loc[donors,'root'])
assert (old.loc[donors,'root']==new.loc[donors,'root']).all()
credited_donors=set(donors)&set(seed.source_record_id)
assert len(credited_donors)==2 and (set(donors)&ids)==credited_donors and not set(donors)&gained
assert new.loc[donors].query('census_year==2010').population.sum()==729
assert set(routes.loc[routes.scope_id.eq(ev.scope_id),'source_record_id'])=={successor}
for name in ['Исаково','Марьино']:
 s=statuses[(statuses.scope_id=='round2_reinstated_'+name)&(statuses.census_year==2002)].iloc[0]
 assert s.status=='UNKNOWN_prior_entity_and_population' and pd.isna(s.own_population)
initial=csv(E/'residual_root_20261013/applied/remaining_initial_over500_residual.csv.gz')
remaining=csv(A/'remaining_initial_over500_residual.csv.gz')
assert len(initial)==306 and len(remaining)==254 and set(remaining.source_record_id)==set(initial.source_record_id)-ids
ratios=csv(A/'new_edge_population_ratio_screen.csv');assert len(ratios)==26 and not ratios.extreme_flag.any()
for _,r in ratios.iterrows():
 x=float(actual.loc[r.from_source_record_id,'effective_population']);y=float(actual.loc[r.to_source_record_id,'effective_population'])
 assert x==r.from_population and y==r.to_population
 assert not ((x==0 and y>0)or(y==0 and x>0)or(x>0 and y/x>21)or(y>0 and x/y>21))
result=dict(status='pass',native_observations_unchanged=465929,ordinary_components_before=len(beforeroots),ordinary_components_after=len(roots),credited_uid_seed=len(seed),credited_uid_union=len(ids),new_credited_uids=len(gained),point_replacements=1,point_additions=1,typed_scopes=4,typed_uids=6,oreshkovo_preserved_donor_roots=3,oreshkovo_previously_credited_donor_uids=2,federal_rows_counted_once=6,initial_residual_closed=52,remaining_residual=254,coverage=totals,input_output_pins=pins)
(O/'final_application_review_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='input_output_pins'},ensure_ascii=False,indent=2))

#!/usr/bin/env python3
"""Actual stage61 primary formation+direct residual, no admissions or allocation."""
from pathlib import Path
import sys,json,hashlib,time,math
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).resolve().parent
REPORT=ROOT/'research_rebuild/evidence/working_full_chain_20261007'
M=ROOT/'research_rebuild/mass_linkage';sys.path.insert(0,str(M))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
start=time.monotonic();pins={}
def pin(p):
 p=Path(p);pins[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size};return p
receipt=json.loads(pin(REPORT/'coverage_receipt.json').read_text());assert receipt['working_stage']==61
for p in [M/'working_state_20261007.py',M/'current_chain_state_20261007.py',REPORT/'build_report.py',REPORT/'direct_inclusion_paths.py']:pin(p)
state=load(stage=61)
for p in state.inputs:pin(p)
obs=state.obs.copy(); ordinary=obs[obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((obs.census_year==2021)&obs.region_norm.eq('крым'))].copy()
full={sid for sid in obs.source_record_id if state.years[state.uf.find(sid)]=={2002,2010,2021}}
allpointroots={r for r,y in state.years.items() if y=={2002,2010,2021}}
for sid in full-set(state.point_rows):allpointroots.discard(state.uf.find(sid))
blocked={state.uf.find(sid) for sid,p in obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(p) or not math.isfinite(float(p))}
finite={sid for sid in full if state.uf.find(sid) in allpointroots and state.uf.find(sid) not in blocked}
sets={'finite_ordinary_full3_all_ownpoints':finite}
for key,name in [('partition','complete_publisher_partition_members.csv'),('qualified','qualified_scope_source_id_credit_union.csv'),('named','named_merger_lineage_constituents.csv'),('territorial','complete_territorial_scope_constituents.csv'),('direct','direct_inclusion_transformation_path_native_credit_union.csv'),('formation','formation_path_native_credit_union.csv')]:
 f=pd.read_csv(pin(REPORT/name),keep_default_na=False,usecols=['source_record_id']);sets[key]=set(f.source_record_id)-{''}
credited=set().union(*sets.values());assert credited<=set(obs.source_record_id)
ordinary['has_own_point']=ordinary.source_record_id.isin(state.point_rows)
ordinary['component_years']=ordinary.source_record_id.map(lambda sid:','.join(map(str,sorted(state.years[state.uf.find(sid)]))))
ordinary['full3']=ordinary.source_record_id.isin(full)
ordinary['all_component_points']=ordinary.root.isin(allpointroots)
ordinary['component_has_unknown_population']=ordinary.root.isin(blocked)
component_ids=obs.groupby('root').source_record_id.agg(lambda v:'|'.join(v)).to_dict()
current=obs[obs.census_year.eq(2021)].set_index('root')
for field in ['source_record_id','settlement_name','settlement_type','oktmo','okato','district_raw']:
 ordinary['current_'+field]=ordinary.root.map(current[field].to_dict()).fillna('')
ordinary['component_source_ids']=ordinary.root.map(component_ids)
ordinary['accepted_own_latitude']=ordinary.source_record_id.map(lambda sid:state.point_rows.get(sid,{}).get('latitude',''))
ordinary['accepted_own_longitude']=ordinary.source_record_id.map(lambda sid:state.point_rows.get(sid,{}).get('longitude',''))
ordinary['point_origin_file']=ordinary.source_record_id.map(lambda sid:state.point_rows.get(sid,{}).get('point_origin_file',''))
residual=ordinary[~ordinary.source_record_id.isin(credited)].copy()
def cause(r):
 if r.component_has_unknown_population:return 'unknown_population_component'
 if r.full3 and not r.all_component_points:return 'full3_missing_component_ownpoint'
 if r.has_own_point:return 'ownpoint_missing_census_identity_or_lifecycle'
 return 'missing_ownpoint_and_census_identity_or_lifecycle'
residual['cause']=residual.apply(cause,axis=1)
residual['candidate_source_routes']=residual.cause.map({'unknown_population_component':'original_source_protected_unknown_control','full3_missing_component_ownpoint':'own_locality_article_coordinates;source_classifier_binding','ownpoint_missing_census_identity_or_lifecycle':'dated_own_article_census_history;printed_source_county;historical_alias;dated_inclusion_act','missing_ownpoint_and_census_identity_or_lifecycle':'printed_source_county;own_locality_article;classifier;complete_published_territorial_roster'})
residual=residual.sort_values(['population','census_year','source_record_id'],ascending=[False,True,True],na_position='last')
residual['population_priority_rank']=range(1,len(residual)+1)
# Low population and zero rows remain present; unknown never replaced by zero.
residual.to_csv(OUT/'primary_axis_remaining_source_records.csv.gz',index=False,compression={'method':'gzip','compresslevel':9,'mtime':0})
missing=ordinary[ordinary.census_year.eq(2021)&~ordinary.has_own_point].copy();missing['already_credited_primary_axis']=missing.source_record_id.isin(credited)
missing.to_csv(OUT/'current2021_missing_ownpoints.csv.gz',index=False,compression={'method':'gzip','compresslevel':9,'mtime':0})
controls={2002:145166731,2010:142856536,2021:144699673};federal={2002:15043973,2010:16383067,2021:18612023};proof={}
axis=receipt['separate_sourceyear_formation_plus_direct_lifecycle_axis']['by_year']
for year,g in ordinary.groupby('census_year'):
 year=int(year);taken=g[g.source_record_id.isin(credited)];left=g[~g.source_record_id.isin(credited)];covered=int(taken.population.sum())+federal[year]
 assert covered==axis[str(year)]['lifecycle_plus_formation_population'],(year,covered,axis[str(year)])
 external=controls[year]-int(g.population.sum())-federal[year]
 assert external=={2002:11726,2010:493512,2021:0}[year]
 assert covered+int(left.population.sum())+external==controls[year]
 proof[year]={'common_control':controls[year],'federal_territory_population':federal[year],'credited_selected_source_ids':len(taken),'credited_selected_population':int(taken.population.sum()),'primary_axis_population':covered,'remaining_selected_source_ids':len(left),'remaining_selected_population':int(left.population.sum()),'remaining_unknown_population_rows':int(left.population.isna().sum()),'external_selected_source_control_deficit_unallocated':external,'exact_union_conservation_passed':True,'component_set_reference_counts':{k:int(g.source_record_id.isin(v).sum()) for k,v in sets.items()}}
regional=residual.groupby(['census_year','region_norm','cause'],dropna=False).agg(source_rows=('source_record_id','size'),source_population=('population','sum'),unknown_population_rows=('population',lambda v:int(v.isna().sum()))).reset_index().sort_values('source_population',ascending=False)
regional.to_csv(OUT/'regional_cause_priority.csv',index=False)
# Readback verifies the complete IDs, not merely sums.
back=pd.read_csv(OUT/'primary_axis_remaining_source_records.csv.gz',keep_default_na=False);assert back.source_record_id.is_unique and set(back.source_record_id)==set(residual.source_record_id)
for y,g in back.groupby('census_year'):assert len(g)==proof[int(y)]['remaining_selected_source_ids']
outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file() and p.name!='receipt.json'}
assert sum(v['bytes'] for v in outputs.values())<8000000
result={'status':'actual_stage61_primary_formation_plus_direct_exclusive_UID_union_residual_verified','stage':61,'baseline_axis':'separate_sourceyear_formation_plus_direct_lifecycle_axis','by_year':proof,'current2021_missing_ownpoint_rows':len(missing),'candidate_generation_implies_admission':False,'unknown_population_imputed':False,'source_control_deficit_allocated':False,'readback_unique_remaining_UID_union_passed':True,'source_input_pins':pins,'output_pins':outputs,'wall_seconds':round(time.monotonic()-start,3)}
(OUT/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'by_year':proof,'missing2021':len(missing),'outputs':outputs,'wall_seconds':result['wall_seconds']},ensure_ascii=False))

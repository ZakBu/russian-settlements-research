#!/usr/bin/env python3
"""Apply finalized65 deltas to certified64 snapshots; no State.load replay."""
from pathlib import Path
import sys,json,hashlib,time,math,collections,base64
import pandas as pd
import duckdb
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];E=ROOT/'research_rebuild/evidence';M=ROOT/'research_rebuild/mass_linkage';BASE=E/'main_axis_residual_application64_20261008'
sys.path.insert(0,str(M))
from current_chain_state_20261007 import State,sha,distance_km
from build_long_table import UnionFind,ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES

START=time.monotonic();PINS={};YEARS={2002,2010,2021};COMMON={2002:145166731,2010:142856536,2021:144699673};FED={2002:15043973,2010:16383067,2021:18612023};EXTERNAL={2002:-757,2010:493512,2021:0}
def pin(p,expected=None):
 p=Path(p);k=str(p)
 if k not in PINS:PINS[k]={'sha256':sha(p),'bytes':p.stat().st_size}
 if expected is not None:assert PINS[k]['sha256']==expected,(k,expected,PINS[k])
 return p
def read(p):return pd.read_csv(pin(p),dtype=str,keep_default_na=False)
def receipt(p):
 p=Path(p);r=json.loads(pin(p).read_text())
 for q,h in {**r.get('source_pins',{}),**r.get('input_pins',{})}.items():pin(ROOT/q if not Path(q).is_absolute() and not Path(q).exists() else q,h['sha256'] if isinstance(h,dict) else h)
 for q,h in {**r.get('outputs',{}),**r.get('output_pins',{})}.items():pin(Path(q) if Path(q).is_absolute() else p.parent/q,h['sha256'] if isinstance(h,dict) else h)
 return r
pin(OUT/'RCSI44_scoped_positive_GN_rule.json');config=json.loads(pin(OUT/'finalized_packets.json').read_text());assert config['all_packets_finalized'] and config['capacity_authorized']
assert config['application_authorized_after_checkpoint64'] and config['baseline_commit']
base=json.loads(pin(BASE/'application_receipt.json','adac8a1b1204d1aa5e59e64f35ca078cc2a65d1d7b2375ed2dea6513c047768d').read_text());assert base['intended_working_stage']==64 and base['canonical_State_API_replay_passed']
api=pin(OUT/'frozen_State_API65.py',config['API_sha256']);pin(M/'current_chain_state_20261007.py',sha(api));pin(OUT/'frozen_stage64_loader.py',config['loader_sha256'])
for name in ['applied_state_observations.parquet','applied_component_snapshot.csv.gz','applied_point_snapshot.parquet','applied_primary_credited_UID_roster.csv.gz']:pin(BASE/name,base['output_pins'][name]['sha256'])

import pyarrow as pa
import pyarrow.parquet as pq
from stream_point_snapshot import textcell
partial={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file() and p.name in ['accepted_identity_edge_delta.csv.gz','accepted_point_use_delta.csv.gz','point_use_rejections.csv.gz','actual_newly_credited_primary_source_IDs.csv.gz','actual_lost_primary_source_IDs.csv.gz','applied_primary_credited_UID_roster.csv.gz','applied_remaining_primary.csv.gz','applied_component_snapshot.csv.gz']}
for spec in config['native_packets']:
 z=ROOT/spec['zone'];pin(z/spec['receipt'],spec['receipt_sha256']);receipt(z/spec['receipt'])
 for name in spec.get('point_files',[])+spec.get('edge_files',[])+spec.get('rejection_files',[]):pin(z/name)
cs=read(OUT/'applied_component_snapshot.csv.gz');assert cs.source_record_id.is_unique and len(cs)==465928
obs=pd.read_parquet(BASE/'applied_state_observations.parquet');oldobs=obs.copy();roots=dict(zip(cs.source_record_id,cs.root));assert set(roots)==set(obs.source_record_id);obs['root']=obs.source_record_id.map(roots);assert obs.drop(columns='root').equals(oldobs.drop(columns='root'))
pointout=OUT/'accepted_point_use_delta.csv.gz';delta=pd.read_csv(pointout,keep_default_na=False);assert len(delta)==219 and delta.target_source_record_id.is_unique
new={}
for row in delta.to_dict('records'):
 sid=str(row['target_source_record_id']);row.update(latitude=float(row['latitude']),longitude=float(row['longitude']),point_ledger_path=str(pointout));new[sid]=row
reject=read(OUT/'point_use_rejections.csv.gz');assert len(reject)==44 and set(reject.target_source_record_id)<=set(new)
basepf=pq.ParquetFile(BASE/'applied_point_snapshot.parquet');columns=list(basepf.schema_arrow.names)
for row in new.values():
 for c in row:
  if c not in columns:columns.append(c)
columns=[c for c in columns if c!='source_record_id']+['source_record_id'];schema=pa.schema([(c,pa.string()) for c in columns]);keys=set();basekeys=set();retained=0;newcount=0
writer=pq.ParquetWriter(str(OUT/'applied_point_snapshot.parquet'),schema,compression='zstd')
try:
 for batch in basepf.iter_batches(batch_size=8192):
  rows=[]
  for row in batch.to_pylist():
   sid=row['source_record_id'];assert sid and sid not in basekeys;basekeys.add(sid)
   if sid in new:continue
   assert sid not in keys;keys.add(sid);retained+=1
   rows.append({**{c:textcell(row.get(c,'')) for c in columns if c!='source_record_id'},'source_record_id':sid})
  if rows:writer.write_table(pa.Table.from_pylist(rows,schema=schema))
 rows=[]
 for sid,row in new.items():
  assert sid not in keys;keys.add(sid);newcount+=1;rows.append({**{c:textcell(row.get(c,'')) for c in columns if c!='source_record_id'},'source_record_id':sid})
 writer.write_table(pa.Table.from_pylist(rows,schema=schema))
finally:writer.close()
assert len(basekeys)==445145 and set(new)&basekeys==set(reject.target_source_record_id)
assert len(keys)==445320 and keys==set(cs.loc[cs.has_own_point.eq('True'),'source_record_id'])
# Narrow readback verifies complete authoritative keyset; batches preserve all optional fields.
readkeys=set()
for batch in pq.ParquetFile(OUT/'applied_point_snapshot.parquet').iter_batches(batch_size=8192,columns=['source_record_id','target_source_record_id']):
 for row in batch.to_pylist():
  sid=row['source_record_id'];assert sid and sid not in readkeys;readkeys.add(sid);assert not row['target_source_record_id'] or row['target_source_record_id']==sid
assert readkeys==keys
obs.to_parquet(OUT/'applied_state_observations.parquet',index=False,compression='zstd');assert pd.read_parquet(OUT/'applied_state_observations.parquet').equals(obs)
parent='2002:038_218ac665d8_02c_Astraxanskaja.xls:Sheet1:456';assert obs.loc[obs.source_record_id.eq(parent),'is_additive_settlement_record'].iloc[0]==False and obs.loc[obs.source_record_id.eq(parent),'population'].iloc[0]==544
baseline=read(BASE/'applied_primary_credited_UID_roster.csv.gz');baseids=set(baseline.source_record_id);basefinite=set(baseline.loc[baseline.finite_ordinary_full3_all_ownpoints.eq('True'),'source_record_id'])
appearance=set(baseline.loc[baseline.explicit_appearance_publication_absence_credit.eq('True'),'source_record_id']);inclusions=set(baseline.loc[baseline.explicit_inclusion_credit.eq('True'),'source_record_id']);round2=set(baseline.loc[baseline.explicit_available_year_lifecycle_round2_credit.eq('True'),'source_record_id']);mainextra=baseids-basefinite;coreextra=baseids-basefinite-appearance-inclusions-round2
g17ids=set(read(OUT/'g17_accepted_source_UID_credit.csv').source_record_id);assert len(g17ids)==1
sizes=obs.groupby('root').census_year.agg(['size','nunique']);assert sizes['size'].eq(sizes['nunique']).all() and sizes['size'].le(3).all();fullroots=set(sizes.index[sizes['size'].eq(3)])
missingroots=set(cs.loc[~cs.has_own_point.eq('True'),'root']);allroots=fullroots-missingroots;blocked=set(obs.loc[obs.population.isna()|~obs.population.map(lambda p:pd.isna(p) or math.isfinite(float(p))),'root']);allids=set(obs.loc[obs.root.isin(allroots),'source_record_id']);afinite=set(obs.loc[obs.root.isin(allroots-blocked),'source_record_id'])
ordinary=obs[obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((obs.census_year==2021)&obs.region_norm.eq('крым'))].copy()
def axes(extra):
 credit=afinite|set(extra);out={}
 for y,g in ordinary.groupby('census_year'):
  y=int(y);a=g[g.source_record_id.isin(allids)];f=g[g.source_record_id.isin(afinite)];taken=g[g.source_record_id.isin(credit)];left=g[~g.source_record_id.isin(credit)];total=int(taken.population.sum())+FED[y];assert total+int(left.population.sum())+EXTERNAL[y]==COMMON[y]
  out[str(y)]={'ordinary_all3_ownpoints_rows':len(a),'ordinary_all3_ownpoints_population':int(a.population.sum()),'ordinary_all3_ownpoints_unknown_rows':int(a.population.isna().sum()),'finite_all3_ownpoints_rows':len(f),'finite_all3_ownpoints_population':int(f.population.sum()),'primary_selected_UID_rows':len(taken),'primary_axis_population':total,'remaining_primary_UID_rows':len(left),'remaining_primary_population':int(left.population.sum()),'remaining_unknown_rows':int(left.population.isna().sum()),'external_control_deficit_unallocated':EXTERNAL[y],'common_control':COMMON[y],'percent_common_control':100*total/COMMON[y]}
 return out,credit
before=base['after'];before_core=base['after_core_formation_plus_direct_axis'];after_core,_=axes(coreextra);after_appearance,_=axes(coreextra|appearance);after_inclusion,_=axes(coreextra|appearance|inclusions);after_legacy,alegacy=axes(mainextra);after,acredit=axes(mainextra|g17ids)
actual=read(OUT/'applied_primary_credited_UID_roster.csv.gz');assert set(actual.source_record_id)==set(ordinary.loc[ordinary.source_record_id.isin(acredit),'source_record_id']);assert set(actual.loc[actual.finite_ordinary_full3_all_ownpoints.eq('True'),'source_record_id'])==set(ordinary.source_record_id)&afinite;assert set(actual.loc[actual.explicit_gorodok17_inclusion_credit.eq('True'),'source_record_id'])==g17ids
changed=ordinary[ordinary.source_record_id.isin(acredit-baseids)];lost=ordinary[ordinary.source_record_id.isin(baseids-acredit)];assert set(read(OUT/'actual_newly_credited_primary_source_IDs.csv.gz').source_record_id)==set(changed.source_record_id);assert set(read(OUT/'actual_lost_primary_source_IDs.csv.gz').source_record_id)==set(lost.source_record_id)
assert set(read(OUT/'applied_remaining_primary.csv.gz').source_record_id)==set(ordinary.source_record_id)-set(actual.source_record_id)
gains={y:{'newly_credited_source_IDs':int(changed.census_year.eq(int(y)).sum()),'lost_source_IDs':int(lost.census_year.eq(int(y)).sum()),'net_primary_population_gain':after[y]['primary_axis_population']-before[y]['primary_axis_population'],'net_core_formation_plus_direct_population_gain':after_core[y]['primary_axis_population']-before_core[y]['primary_axis_population'],'net_finite_all3_ownpoint_population_gain':after[y]['finite_all3_ownpoints_population']-before[y]['finite_all3_ownpoints_population'],'new_finite_all3_ownpoint_histories':after[y]['finite_all3_ownpoints_rows']-before[y]['finite_all3_ownpoints_rows']} for y in before}
for y,g in gains.items():assert g['net_primary_population_gain']==int(changed.loc[changed.census_year.eq(int(y)),'population'].sum())-int(lost.loc[lost.census_year.eq(int(y)),'population'].sum())
metrics={}
for y,g in ordinary.groupby('census_year'):
 covered=g.source_record_id.isin(keys)&g.root.isin(fullroots);denominator=int(g.population.sum());n=int(g.loc[covered,'population'].sum());metrics[str(int(y))]={'denominator_selected_ordinary_population':denominator,'covered_population':n,'coverage_percent':100*n/denominator,'covered_rows':int(covered.sum()),'residual_rows':int((~covered).sum()),'gap_to_99_percent':max(0,math.ceil(.99*denominator)-n)}
proof={'status':'passed_export_only_recovery_after_actual_API_application','failed_export_process_exit_code':137,'failure_stage':'bulk wide optional-metadata point snapshot DataFrame export','executed_recipe_sha256':sha(OUT/'executed_recipe65_before_streaming_export.py'),'canonical_API_application_already_completed':True,'actual_State_loads_during_recovery':0,'canonical_API_reapplications_during_recovery':0,'certified_post_API_partial_output_pins':partial,'baseline_active_points':len(basekeys),'accepted_point_delta_rows':len(new),'reviewed_current_replacements':len(reject),'retained_baseline_rows':retained,'new_delta_rows':newcount,'final_active_point_rows':len(keys),'all_active_metadata_fields_preserved':True,'authoritative_source_key_written_last':True,'batch_size':8192,'component_ownpoint_flag_keyset_equal':True,'source_observations_protected_except_actual_component_root':True,'raw_parent544_preserved_nonadditive':True}
(OUT/'export_only_recovery_receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
(OUT/'operational_export_failure.json').write_text(json.dumps({'exit_code':137,'meaning':'API application and protected raw/UID export assertions completed; bulk point metadata export exhausted memory','recipe_sha256':proof['executed_recipe_sha256'],'application_outputs_preserved':partial,'recovery':'Streaming export only, no repeated API or State load'},indent=2)+'\n')
outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file() and p.name!='application_receipt.json'}
result={'status':'applied_actual_frozen64_sourcepositive_alias_ownpoints_and_reviewed_current_point_supersession_batch','baseline_stage':64,'intended_working_stage':65,'frozen_baseline_commit':config['baseline_commit'],'API_sha256':sha(api),'actual_State_loads':0,'cache_hydration_used':True,'baseline_reproduced':True,'canonical_State_API_replay_passed':True,'accepted_edges':120,'accepted_point_uses':219,'point_replacements':44,'new_unique_point_targets':175,'integration_holds':0,'before':before,'before_core_formation_plus_direct_axis':before_core,'after_core_formation_plus_direct_axis':after_core,'after_appearance_axis':after_appearance,'after_inclusion_axis':after_inclusion,'after_legacy_available_year_lifecycle_axis':after_legacy,'after_explicit_inclusion65':after,'after':after,'explicit_Gorodok17_source_IDs':sorted(g17ids),'explicit_Gorodok17_new_source_ID_population':{'2002':5495,'2010':0,'2021':0},'explicit_Gorodok17_admin_date_vs_statistical_grain_caveat_preserved':True,'typed_inclusion65_UF_allowed':False,'typed_context65_new_population_credit':0,'source_observation_additions':0,'source_population_quality_names_codes_and_grain_unchanged':True,'official_population_overlay_included':False,'prior_typed_lifecycle_UIDs_preserved_without_UF':True,'actual_gain_by_unique_source_ID_union':gains,'after_State_metrics':metrics,'source_control_signed_gap':EXTERNAL,'input_pins':PINS,'output_pins':outputs,'export_only_recovery':proof,'recovery_wall_seconds':round(time.monotonic()-START,3)}
(OUT/'application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':result['status'],'after':after,'gains':gains,'finite':{y:after[y]['finite_all3_ownpoints_rows'] for y in after}},ensure_ascii=False))

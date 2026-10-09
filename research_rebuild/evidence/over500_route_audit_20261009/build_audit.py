from pathlib import Path
import pandas as pd, json,hashlib,re
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;B=ROOT/'publication/stage71'
pins={}; ledger_hits={}; warnings=[]
def pin(f):
 pins[str(f)]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
def read(f):
 pin(f);return pd.read_parquet(f) if f.suffix=='.parquet' else pd.read_csv(f,keep_default_na=False)
r=read(Path('/dev/shm/over500-20261009/residual.csv'));obs=read(B/'applied_state_observations.parquet');comp=read(B/'applied_component_snapshot.csv.gz');credit=read(B/'applied_primary_credited_UID_roster.csv.gz');scope=read(B/'accepted_large_record_scope_classification_overlay.csv');scope2=read(B/'accepted_source_scope_interpretation_overlay.csv')
# Inspect exact UID witnesses only in inherited application-pinned explicit credit ledgers.
paths=set()
for receipt in [B/'application_receipt.json',ROOT/'publication/stage70/application_receipt.json',ROOT/'research_rebuild/evidence/main_axis_residual_application68_20261008/application_receipt.json']:
 pin(receipt);paths.update(json.load(open(receipt)).get('input_pins',{}))
paths.update(str(f) for f in (ROOT/'research_rebuild/evidence/main_axis_residual_application68_20261008').glob('g17_accepted*'))
for raw in sorted(paths):
 f=Path(raw);f=f if f.is_absolute() else ROOT/f
 if not f.exists() or not (f.name.endswith('.csv') or f.name.endswith('.csv.gz')):continue
 if not any(x in f.name for x in ['credit','accepted_actual_available_year_observations','g17_accepted_own_sourceyear_observation']):continue
 if any(x in f.name for x in ['roster','newly_credited','lost_primary']):continue
 try:d=read(f)
 except Exception as e:warnings.append(str(f)+': '+str(e));continue
 col='credited_source_uid' if 'credited_source_uid' in d else 'source_record_id' if 'source_record_id' in d else None
 if col:
  for row in d[d[col].isin(set(r.source_record_id))].to_dict('records'):
   ledger_hits.setdefault(row[col],[]).append({'ledger':str(f),'scope_id':row.get('scope_id',''),'witness':row})
cm=comp.set_index('source_record_id');cr=credit.set_index('source_record_id');sm=scope.set_index('source_record_id');s2=scope2.set_index('source_record_id'); members=comp.groupby('root').source_record_id.apply(list).to_dict()
rows=[]
for row in r.to_dict('records'):
 sid=row['source_record_id'];yrs=str(row['component_years']);part=bool(re.search(r'\(\s*часть\s*\d',row['settlement_name'],re.I));adm=bool(re.search(r'сельсовет|муниципал',row['settlement_name'],re.I));flags=[]
 if sid in cr.index:flags=[c for c in cr.columns if ('credit' in c or c in ['finite_ordinary_full3_all_ownpoints','joint_reporting_scope_association','point_presence']) and str(cr.loc[sid,c]).lower()=='true']
 if row['region_norm']=='крым':classification='outside_common_three_census_territory_requires_separate_available_year_axis'
 elif part:classification='literal_part_not_whole_NP_scope_review_required'
 elif adm:classification='administrative_label_wrong_object_scope_review_required'
 elif yrs=='2002,2010,2021':classification='accepted_full_three_year_identity_component_omitted_primary_credit'
 elif sid in cr.index:classification='accepted_primary_credit_inherited_typed_route_missing_ownpoint'
 elif ledger_hits.get(sid):classification='explicit_pinned_ledger_UID_witness_omitted_primary_credit_requires_scope_check'
 elif ',' in yrs:classification='accepted_partial_identity_component_missing_explicit_available_year_or_event_route'
 else:classification='singleton_missing_explicit_available_year_or_event_route'
 rows.append(dict(row,actual_route_classification=classification,accepted_component_UIDs=json.dumps(members.get(row['root'],[sid]),ensure_ascii=False),primary_credit_flags=';'.join(flags),explicit_pinned_ledger_witnesses=json.dumps(ledger_hits.get(sid,[]),ensure_ascii=False),ordinary_full3_identity=yrs=='2002,2010,2021',scope_exemption_is_applied=False))
a=pd.DataFrame(rows);a.to_csv(OUT/'residual_actual_route_audit.csv',index=False)
# All current >500 scope labels plus known38, retaining review/application distinction.
large=obs[pd.to_numeric(obs.population,errors='coerce')>500].copy();known=set(scope.source_record_id);mask=large.source_record_id.isin(known)|large.settlement_name.str.contains(r'\(\s*часть\s*\d|сельсовет|муниципал',case=False,regex=True,na=False);ex=large[mask].copy();ex['scope_exemption_status']=ex.source_record_id.map(lambda x:'already_applied_stage71_scope_exemption' if x in known else 'literal_scope_review_needed_not_new_admission');ex.to_csv(OUT/'over500_scope_exemption_inventory.csv',index=False)
summary={'residual_records':len(a),'original_absent_primary_credit':int((~a.has_admitted_route).sum()),'actual_route_counts':a.actual_route_classification.value_counts().to_dict(),'scope_inventory':ex.scope_exemption_status.value_counts().to_dict(),'pinned_ledger_witness_count':sum(bool(ledger_hits.get(x)) for x in a.source_record_id),'warnings':warnings,'decision_changes':0,'criterion':'Whole NP >500: own admitted point AND (accepted full-three-year same-place component OR explicit accepted available-year/lifecycle source-year route). Territory, literal part/admin, and national accounting exclusions must remain typed; absent years unknown unless explicit evidence says otherwise.'}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(OUT/'input_manifest.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))

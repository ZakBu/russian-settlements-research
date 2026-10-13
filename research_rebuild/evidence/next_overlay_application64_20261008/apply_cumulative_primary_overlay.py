"""Stage-aware additive observation readback for the frozen 1775-claim overlay.

Derived from the stage63 recipe; original selected 2010 rows remain byte-pinned.
"""
from pathlib import Path
import argparse,csv,gzip,hashlib,io,json,math,collections,os
import pandas as pd
E=Path(__file__).resolve().parent
REPO=E.parents[2]
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
DELTA=E/'normalized_cumulative_claims.csv.gz'
PDF=E.parent/'official_population_residual_sources_20261008'/'leningrad_2010_official_archived.pdf'
DELTA_SHA='df21311a80d61ed3e3d9e8cd9d160d93d6cbb27459184fbbf9c2fce52b237640'
PDF_SHA='57cb1e6e9ea1c5803a860048941ddd51b40640372797229d0010e758155b8792'
S_SHA='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'
YEARS=(2002,2010,2021)
NATIONAL={2002:145166731,2010:142856536,2021:147182123}
MUTABLE=['population_2010','population_value_quality_2010','source_file_2010','source_path_2010','source_sha256_2010','source_locator_2010','source_actual_path_2010','source_actual_sha256_2010','source_actual_resolution_status_2010']
EXTRA=['original_'+k for k in MUTABLE]+['original_source_record_id_2010','population_source_record_id_2010','population_source_binding_native_record_id_2010','population_source_name_raw_2010','population_source_type_raw_2010','population_source_census_date_2010','population_source_publication_date_2010','population_source_binding_status_2010','population_source_application_status_2010','population_source_context_method_2010','population_source_overlay_input_sha256_2010']
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def integer(x):
 v=float(x);assert math.isfinite(v) and v==int(v);return int(v)
def nullable(x):
 if x is None or str(x).strip() in ['','nan','NaN','None']:return None
 return integer(x)
def truth(x):return str(x).lower() in ['true','1','1.0']
def stable(h,row,fields):h.update(json.dumps([row.get(k,'') for k in fields],ensure_ascii=False,separators=(',',':')).encode()+b'\n')
def csvreader(path):return csv.DictReader(gzip.open(path,'rt',encoding='utf8',newline=''))
def writegzip(path,fieldnames,rows):
 with Path(path).open('wb') as raw:
  with gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0,compresslevel=9) as zipped:
   with io.TextIOWrapper(zipped,encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(rows)
def run(a):
 assert a.stage>=62,'Requires final admitted native stage >=62'
 assert a.main.resolve()!=a.delivery_output_dir.resolve()/'ordinary_full3_with_primary_population_sources.csv.gz'
 inputs={str(p):sha(p) for p in [S,DELTA,PDF,a.main,a.primary_credit_roster,a.composer_receipt,a.current_observations]}
 assert inputs[str(a.current_observations)]==a.expected_current_observations_sha256
 assert inputs[str(S)]==S_SHA and inputs[str(DELTA)]==DELTA_SHA and inputs[str(PDF)]==PDF_SHA
 assert inputs[str(a.main)]==a.expected_main_sha256 and inputs[str(a.primary_credit_roster)]==a.expected_credit_sha256
 composer=json.loads(a.composer_receipt.read_text())
 # Root confirms final admitted stage membership by supplying both finalized byte pins. Main IDs are checked below.
 d=pd.read_csv(DELTA,keep_default_na=False);assert len(d)>0 and d.old_source_record_id.is_unique
 assert d.followup_context_status.str.startswith('accepted').all()
 assert d.decision_status.eq('accepted_population_publication_binding').all()
 original_selected=pd.read_parquet(S);assert original_selected.source_record_id.is_unique
 selected_all=pd.read_parquet(a.current_observations);assert selected_all.source_record_id.is_unique
 # The source parent retains its raw population in selected_all; it is not additive.
 selected=selected_all.loc[selected_all.is_additive_settlement_record.eq(True)].copy()
 original2010=original_selected.loc[original_selected.census_year.eq(2010)].set_index("source_record_id")
 current2010=selected.loc[selected.census_year.eq(2010)].set_index("source_record_id")
 assert set(original2010.index)==set(current2010.index)
 for key in ["population","population_value_quality","source_file","source_path","source_sha256","source_locator"]:
  assert original2010[key].fillna("").sort_index().equals(current2010[key].fillna("").sort_index()),key
 sr=selected.set_index('source_record_id');claims={r['old_source_record_id']:r for r in d.to_dict('records')}
 for sid,r in claims.items():
  old=sr.loc[sid];assert int(old.census_year)==2010
  assert integer(old.population)==integer(r['old_population']) and old.population_value_quality==r['old_quality']
  assert integer(r['population'])==integer(r['men'])+integer(r['women'])
  source=Path(r['official_source_path']);assert source.is_file() and sha(source)==r['official_source_sha256'];inputs[str(source)]=r['official_source_sha256']
 delta=sum(integer(r['population'])-integer(r['old_population']) for r in claims.values())
 before_selected={y:int(selected[selected.census_year.eq(y)].population.sum()) for y in YEARS};after_selected=dict(before_selected);after_selected[2010]+=delta
 assert NATIONAL[2010]-before_selected[2010]==493512
 credits=pd.read_csv(a.primary_credit_roster,keep_default_na=False)
 assert {'source_record_id','census_year','population','entity_uid','finite_ordinary_full3_all_ownpoints'}<=set(credits.columns)
 assert credits.source_record_id.is_unique,'Credit roster must be exclusive selected source-ID union'
 assert set(credits.source_record_id)<=set(sr.index),'No fabricated/non-native source nodes'
 for r in credits.to_dict('records'):
  old=sr.loc[r['source_record_id']];assert int(r['census_year'])==int(old.census_year)
  assert nullable(r['population'])==(None if pd.isna(old.population) else integer(old.population)),'Roster must use untouched raw population'
 creditIDs=set(credits.source_record_id);creditMap=credits.set_index('source_record_id').to_dict('index')
 credit_before={y:sum(integer(r['population']) for r in credits.to_dict('records') if int(r['census_year'])==y and nullable(r['population']) is not None) for y in YEARS}
 credit_delta=sum(integer(r['population'])-integer(r['old_population']) for sid,r in claims.items() if sid in creditIDs)
 credit_after=dict(credit_before);credit_after[2010]+=credit_delta
 reader=csvreader(a.main);basefields=reader.fieldnames;assert set(MUTABLE+['entity_uid','source_record_id_2010'])<=set(basefields)
 assert not set(EXTRA)&set(basefields),'Refuse reapplying overlay'
 unchanged=[k for k in basefields if k not in MUTABLE];fields=basefields+EXTRA
 result=a.delivery_output_dir/'ordinary_full3_with_primary_population_sources.csv.gz'
 final_result=result
 retained={}
 if final_result.exists():
  assert a.retain_existing_as_stage is not None and a.expected_existing_effective_sha256
  assert sha(final_result)==a.expected_existing_effective_sha256
  keep=final_result.with_name(final_result.name.replace('.csv.gz',f'.retained_stage{a.retain_existing_as_stage}.csv.gz'))
  if keep.exists():assert sha(keep)==sha(final_result)
  else:os.link(final_result,keep)
  retained[str(keep)]={'sha256':sha(keep),'bytes':keep.stat().st_size,'method':'hardlink_original_inode_retained_before_atomic_effective_replace'}
 result=final_result.with_name(final_result.name+f'.writing_stage{a.stage}')
 assert not result.exists(),'Unfinished output must be reviewed before retry'
 a.delivery_output_dir.mkdir(parents=True,exist_ok=True)
 beforeMain={y:0 for y in YEARS};afterMain={y:0 for y in YEARS};hbefore=hashlib.sha256();mainMap={};seen=set();counter={'rows':0,'overridden_main_rows':0}
 def transform():
  for row in reader:
   counter['rows']+=1;sid=row['source_record_id_2010'];assert sid not in seen;seen.add(sid)
   assert sid in creditIDs,'Every ordinary exported native ID must be credited in actual post_stage primary roster'
   cr=creditMap[sid];assert truth(cr['finite_ordinary_full3_all_ownpoints'])
   assert row['entity_uid']==cr['entity_uid']
   for y in YEARS:beforeMain[y]+=integer(row[f'population_{y}'])
   stable(hbefore,row,unchanged)
   if sid in claims:
    r=claims[sid];assert integer(row['population_2010'])==integer(r['old_population'])
    assert row['population_value_quality_2010']==r['old_quality']
    mainMap[sid]=dict(row);counter['overridden_main_rows']+=1
    for k in MUTABLE:row['original_'+k]=row[k]
    row['original_source_record_id_2010']=sid
    row.update(population_2010=integer(r['population']),population_value_quality_2010='reviewed_primary_reported_value',source_file_2010=Path(r['official_source_path']).name,source_path_2010=r['official_source_path'],source_sha256_2010=r['official_source_sha256'],source_locator_2010=r['official_source_locator'],source_actual_path_2010=r['official_source_path'],source_actual_sha256_2010=r['official_source_sha256'],source_actual_resolution_status_2010='official_2010_locality_count_exact_cached_PDF_primary_overlay',population_source_record_id_2010=r['official_source_record_id'],population_source_binding_native_record_id_2010=sid,population_source_name_raw_2010=r['name_raw'],population_source_type_raw_2010=r['type_raw'],population_source_census_date_2010='2010-10-14',population_source_publication_date_2010=r['official_publication_date'],population_source_binding_status_2010=r['followup_context_status'],population_source_application_status_2010='applied_primary_population_source_overlay',population_source_context_method_2010=r['followup_context_method'],population_source_overlay_input_sha256_2010=DELTA_SHA)
   for y in YEARS:afterMain[y]+=integer(row[f'population_{y}'])
   yield row
 writegzip(result,fields,transform())
 ordinaryCredit=set(credits.loc[credits.finite_ordinary_full3_all_ownpoints.map(truth)&credits.census_year.eq(2010),'source_record_id'])
 assert seen==ordinaryCredit,'Final stage main UID set must match composer finiteordinary source IDs exactly'
 mainDelta=sum(integer(claims[sid]['population'])-integer(claims[sid]['old_population']) for sid in mainMap)
 assert afterMain[2010]-beforeMain[2010]==mainDelta and afterMain[2002]==beforeMain[2002] and afterMain[2021]==beforeMain[2021]
 overlay=[]
 for sid,r in claims.items():
  old=sr.loc[sid];mr=mainMap.get(sid);cr=creditMap.get(sid,{})
  rec=dict(original_source_record_id=sid,census_year=2010,entity_uid=mr['entity_uid'] if mr else cr.get('entity_uid',''),ordinary_full3_main_membership=bool(mr),primary_native_UID_credit_membership=sid in creditIDs,primary_credit_component_root=cr.get('component_root',''),original_population=integer(old.population),original_population_value_quality=old.population_value_quality,population=integer(r['population']),population_value_quality='reviewed_primary_reported_value',population_source_record_id=r['official_source_record_id'],population_source_path=r['official_source_path'],population_source_sha256=r['official_source_sha256'],population_source_locator=r['official_source_locator'],population_source_name_raw=r['name_raw'],population_source_type_raw=r['type_raw'],census_date='2010-10-14',publication_date=r['official_publication_date'],population_source_binding_status=r['followup_context_status'],population_source_application_status='applied_primary_population_source_overlay',binding_context_method=r['followup_context_method'],official_municipality=r['municipal_unit_source_label'],official_SP_GP=r['settlement_group_source_label'],official_men=integer(r['men']),official_women=integer(r['women']),original_source_metadata_json=json.dumps({k:None if pd.isna(v) else v.item() if hasattr(v,'item') else v for k,v in old.items() if k.startswith('source_')},ensure_ascii=False,default=str),point_reuse_or_new_identity_created=False)
  for k in ['latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_ledger_path']:
   rec[k]=mr.get(k+'_2010','') if mr else ''
  rec['point_binding_status']='existing_post_stage_ordinary_ownpoint_unchanged' if mr else 'no_new_point_asserted_by_population_overlay'
  overlay.append(rec)
 final_longpath=a.delivery_output_dir/'applied_primary_population_source_overlay_2010.csv.gz'
 if final_longpath.exists():
  assert a.retain_existing_as_stage is not None
  keep=final_longpath.with_name(final_longpath.name.replace('.csv.gz',f'.retained_stage{a.retain_existing_as_stage}.csv.gz'))
  if keep.exists():assert sha(keep)==sha(final_longpath)
  else:os.link(final_longpath,keep)
  retained[str(keep)]={'sha256':sha(keep),'bytes':keep.stat().st_size,'method':'hardlink_original_inode_retained_before_atomic_effective_replace'}
 longpath=final_longpath.with_name(final_longpath.name+f'.writing_stage{a.stage}');assert not longpath.exists();writegzip(longpath,list(overlay[0]),overlay)
 # Independent exported-byte readback: cardinality, sums, native UID/point fields and preserved old claims.
 readback={y:0 for y in YEARS};afterhash=hashlib.sha256();overrides=0;n=0
 for row in csvreader(result):
  n+=1;stable(afterhash,row,unchanged)
  for y in YEARS:readback[y]+=integer(row[f'population_{y}'])
  if row['population_source_application_status_2010']:
   overrides+=1;sid=row['source_record_id_2010'];assert sid in mainMap
   assert row['original_source_record_id_2010']==sid
   for k in MUTABLE:assert row['original_'+k]==mainMap[sid][k]
 assert n==counter['rows'] and overrides==len(mainMap) and readback==afterMain and afterhash.hexdigest()==hbefore.hexdigest()
 assert sha(a.main)==inputs[str(a.main)] and sha(S)==S_SHA,'Raw main/selected must remain unchanged'
 os.replace(result,final_result);result=final_result
 os.replace(longpath,final_longpath);longpath=final_longpath
 receipt={'status':'applied_separate_cumulative_primary_population_source_overlay_raw_State_export_unchanged','working_native_stage':a.stage,'reviewed_primary_claim_rows':len(claims),'effective_long_overlay_rows':len(overlay),'wide_rows':counter['rows'],'wide_overridden_rows':len(mainMap),'new_identity_nodes':0,'new_point_uses':0,'full_selected_population_before':before_selected,'full_selected_population_after_effective_primary':after_selected,'selected_population_delta':delta,'ordinary_main_population_before':beforeMain,'ordinary_main_population_after_effective_primary':afterMain,'ordinary_main_population_delta':mainDelta,'primary_credited_native_unknown_population_rows_preserved':int(credits.population.map(nullable).isna().sum()),'primary_credited_native_UID_rows_before_and_after':len(credits),'primary_credited_native_population_before':credit_before,'primary_credited_native_population_after_effective_primary':credit_after,'primary_credited_native_2010_delta':credit_delta,'reviewed_claims_matching_primary_UID_credit':len(set(claims)&creditIDs),'reviewed_claims_outside_primary_UID_credit':len(set(claims)-creditIDs),'national_controls_unchanged':NATIONAL,'external2010_source_deficit_before':493512,'external2010_source_deficit_after':NATIONAL[2010]-after_selected[2010],'raw_source_counts_qualities_and_metadata_preserved':True,'unknown_population_not_zeroed':True,'no_whole_municipal_or_boundary_closure_claim':True,'independent_readback':{'rows':n,'populations':readback,'unchanged_native_UID_and_coordinate_fields_sha256':afterhash.hexdigest(),'all_applied_old_source_fields_match_raw_export':True},'input_pins':inputs,'output_pins':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [result,longpath]},'composer_receipt_path':str(a.composer_receipt),'retained_prior_effective_exports':retained,'claim_input_pins':{str(path):sha(path) for path in a.claim_file},'identical_claim_duplicates_deduplicated':a.deduplicated_count}
 receipt['primary2010_axis_with_fixed_federal']={'native_UID_population_before':credit_before[2010],'native_UID_population_after':credit_after[2010],'fixed_federal_population':16383067,'combined_population_before':credit_before[2010]+16383067,'combined_population_after':credit_after[2010]+16383067,'official_national_control':NATIONAL[2010],'percent_of_national_control_after':100*(credit_after[2010]+16383067)/NATIONAL[2010],'selected_ordinary_denominator_before':before_selected[2010]-16383067,'selected_ordinary_denominator_after':after_selected[2010]-16383067,'UID_membership_unchanged_by_population_overlay':True}
 receipt['current_stage_additive_source_readback']={'observations_path':str(a.current_observations),'sha256':a.expected_current_observations_sha256,'all_source_rows':len(selected_all),'additive_rows':len(selected),'nonadditive_raw_population_retained':int(selected_all.loc[~selected_all.is_additive_settlement_record.eq(True),'population'].sum()),'signed_national_control_minus_selected_before':{y:NATIONAL[y]-before_selected[y] for y in YEARS},'signed_national_control_minus_selected_after':{y:NATIONAL[y]-after_selected[y] for y in YEARS},'original_selected_2010_UID_population_quality_and_source_fields_unchanged':True}
 receipt['implementation_sha256']=sha(Path(__file__))
 (E/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))
def normalize_claims(a):
 assert len(a.claim_file)==len(a.expected_claim_sha256)
 normalized={};duplicates=0
 for file,expected in zip(a.claim_file,a.expected_claim_sha256):
  assert sha(file)==expected,(str(file),'claim bytes differ')
  data=pd.read_csv(file,keep_default_na=False)
  for r in data.to_dict('records'):
   sid=r['old_source_record_id'];prior='followup_context_status' in r
   assert (r.get('followup_context_status')=='accepted_positive_literal_roster_municipal_context' if prior else r.get('status') in ['ready_positive_literal_county_roster_context','ready_closed_unique_same2010_primary_publication_binding','ready_exact_same2010_typed_NP_positive_literal_county_with_all_rivals_bound'])
   path=PDF if prior else Path(r['official_source_path'])
   q=dict(r)
   q.update(official_publication_date='2012-04-23' if prior else '',old_source_record_id=sid,old_population=integer(r['old_population']),old_quality=r['old_quality'],population=integer(r['population'] if prior else r['official_population']),men=integer(r['men'] if prior else r['official_men']),women=integer(r['women'] if prior else r['official_women']),official_source_path=str(path),official_source_sha256=r['official_source_sha256'],official_source_record_id=r['official_source_record_id'],official_source_locator=r['official_source_locator'] if prior else f"pdf_page={int(r['official_page'])};pypdf_line_start={int(r['official_line_start'])};pypdf_line_end={int(r['official_line_end'])}",name_raw=r['name_raw'] if prior else r['official_name'],type_raw=r['type_raw'] if prior else r['official_type'],municipal_unit_source_label=r['municipal_unit_source_label'] if prior else r.get('official_district',''),settlement_group_source_label=r['settlement_group_source_label'] if prior else '',followup_context_status='accepted_reviewed_same2010_primary_publication_binding',followup_context_method=r['followup_context_method'] if prior else r['context_method'],decision_status='accepted_population_publication_binding')
   if sid in normalized:
    old=normalized[sid]
    assert all(q[k]==old[k] for k in ['population','men','women','name_raw','type_raw','official_source_record_id','official_source_sha256']),'Conflicting sameSID primary claims must be held'
    duplicates+=1;continue
   normalized[sid]=q
 pd.DataFrame(list(normalized.values())).to_csv(DELTA,index=False,compression='gzip')
 a.deduplicated_count=duplicates
 return sha(DELTA)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--current-observations',type=Path,required=True);p.add_argument('--expected-current-observations-sha256',required=True);p.add_argument('--stage',type=int,required=True);p.add_argument('--main',type=Path,required=True);p.add_argument('--primary-credit-roster',type=Path,required=True);p.add_argument('--composer-receipt',type=Path,required=True);p.add_argument('--expected-main-sha256',required=True);p.add_argument('--expected-credit-sha256',required=True);p.add_argument('--delivery-output-dir',type=Path,required=True);p.add_argument('--claim-file',type=Path,action='append',required=True);p.add_argument('--expected-claim-sha256',action='append',required=True);p.add_argument('--retain-existing-as-stage',type=int);p.add_argument('--expected-existing-effective-sha256');a=p.parse_args();DELTA_SHA=normalize_claims(a);run(a)

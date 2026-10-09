from pathlib import Path
import pandas as pd,xlrd,json,hashlib,re
OUT=Path(__file__).parent;RAW=Path('/workspace/settlements-raw');ROOT=Path('/workspace/russian-settlements-research')
a=pd.read_csv(OUT/'over500_scope_exemption_inventory.csv');a=a[a.scope_exemption_status.eq('literal_scope_review_needed_not_new_admission')];assert len(a)==15
w=[];rows=[];cache={}
for r in a.to_dict('records'):
 f=RAW/r['source_file'];digest=hashlib.sha256(f.read_bytes()).hexdigest();sid=r['source_record_id'];rn=int(sid.rsplit(':',1)[1]);sheet=sid.rsplit(':',2)[1]
 if f.suffix=='.xls':
  if f not in cache:cache[f]=xlrd.open_workbook(f)
  s=cache[f].sheet_by_name(sheet);v=s.row_values(rn-1)
  if int(r['census_year'])==2010:ni,pi=3,4
  else:ni=1 if isinstance(v[0],float) else 0;pi=ni+1
  rawname=str(v[ni]);pop=float(v[pi]);loc=f'{sheet}!{chr(65+ni)}{rn} (name); {sheet}!{chr(65+pi)}{rn} (population); Excel row {rn}, 1-based'
  neighborhood=[{'row_1based':i+1,'cells':s.row_values(i)} for i in range(max(0,rn-3),min(s.nrows,rn+2))]
 else:
  d=pd.read_parquet(f,columns=['object_level','object_name','settlement','population','region','mun_lower','mun_upper']);z=d.iloc[rn-1];rawname=z.object_name;pop=float(z.population);loc=f'parquet row {rn} 1-based / iloc[{rn-1}]; object_name,settlement,population,object_level,mun_lower';neighborhood=d.iloc[rn-2:rn+1].to_dict('records')
 assert pop==float(r['population']),(sid,pop,r['population'])
 part=bool(re.search(r'\(\s*часть\s*[12]\s*\)',rawname,re.I));admin=rawname.strip()=='Селогорский сельсовет';assert part or admin,(sid,rawname)
 proof={};scope='literal_part_source_observation' if part else 'municipal_council_aggregate'
 if admin:
  subs=[{'row_1based':i+1,'name_cell':f'A{i+1}','population_cell':f'B{i+1}','source_name':s.cell_value(i,0),'population':int(s.cell_value(i,1))} for i in range(2288,2302)]
  assert sum(x['population'] for x in subs)==586 and 'сельсовет' in s.cell_value(2302,0)
  proof={'admin_header_raw':rawname,'subordinate_villages':subs,'subordinate_population_sum':586,'next_admin_header':s.cell_value(2302,0),'next_admin_header_row_1based':2303,'imported_name_type_is_parser_error':True,'whole_locality_Selo_Gora_count':259,'whole_locality_Selo_Gora_cell':'B2289'}
 w.append({'source_record_id':sid,'source_file':str(f),'source_sha256':digest,'source_locator':loc,'literal_source_name':rawname,'source_population':pop,'source_population_quality_retained':r['population_value_quality'],'neighborhood':neighborhood,'aggregate_proof':proof})
 rows.append(dict(source_record_id=sid,census_year=r['census_year'],source_name=r['settlement_name'],literal_source_name=rawname,population_raw=r['population'],source_population_quality=r['population_value_quality'],scope_class=scope,acceptance_status='checked_rule_accepted',decision_status='checked_rule_accepted',scope_review_status='exact source bytes and object level independently checked',whole_named_NP_ownpoint_target=False,ordinary_whole_settlement_admission=False,is_additive_settlement_record_original=r['is_additive_settlement_record'],existing_part_series_graph_preserved=True,existing_source_year_scope_credit_preserved=True,existing_point_uses_preserved=True,threshold_axis_correction_only=True,reviewed_population_scope=scope,source_file=str(f),source_sha256=digest,source_locator=loc,sourcewitnessfile=str(OUT/'literal_scope_source_witnesses.json'),sourcewitnesslocator=f'source_record_id={sid}',historic_part_exact_coordinate='unknown',point_scope_interpretation='part exact location unknown; existing coarse whole-locality associations retained separately' if part else 'administrative aggregate; no constituent point projected to aggregate',population_value_modified_or_allocated=False,source_count_or_quality_changed=False,population_quality_modified=False,raw_population_modified=False,source_count_raw_population_retained=True,ordinary_identity_or_population_equivalence_asserted=False,evidence_basis='Literal source explicitly labels a numbered part of named NP; do not interpret as a whole NP' if part else 'Literal council header586 and14 distinct subordinate village counts sum586; imported truncation does not create an NP',raw_source_sha256=digest))
wf=OUT/'literal_scope_source_witnesses.json';wf.write_text(json.dumps(w,ensure_ascii=False,indent=2,default=str));wh=hashlib.sha256(wf.read_bytes()).hexdigest()
for r in rows:r['sourcewitnesshash']=wh
z=pd.DataFrame(rows);assert z.source_record_id.is_unique;old=pd.read_csv(ROOT/'publication/stage71/accepted_large_record_scope_classification_overlay.csv');assert not set(z.source_record_id)&set(old.source_record_id);z.to_csv(OUT/'accepted_scope_overlay.csv',index=False)
receipt={'status':'exact_source_literal_scope_checked','accepted_scope_rows':len(z),'literal_part_rows':int(z.scope_class.eq('literal_part_source_observation').sum()),'municipal_council_aggregate_rows':int(z.scope_class.eq('municipal_council_aggregate').sum()),'overlap_existing38':0,'candidate_uid_count':len(a),'candidate_population_total':float(a.population.sum()),'accepted_raw_population_total':float(z.population_raw.sum()),'protected_secondary2010_count':int(z.source_population_quality.str.contains('protected').sum()),'raw_population_or_quality_changes':0,'point_or_identity_decisions':0,'source_witness_sha256':wh,'accepted_overlay_sha256':hashlib.sha256((OUT/'accepted_scope_overlay.csv').read_bytes()).hexdigest()};assert receipt['candidate_population_total']==receipt['accepted_raw_population_total'];(OUT/'scope_verification_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))

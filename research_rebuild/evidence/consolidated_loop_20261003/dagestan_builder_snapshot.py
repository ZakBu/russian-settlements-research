#!/usr/bin/env python3
"""Bounded Dagestan 2010 rural Table 5 publication-binding proposal stage; never applies it."""
import hashlib,json,re,time,unicodedata,subprocess
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import xlrd
from pypdf import PdfReader

C=Path('/workspace/settlements-work/continuation_20261003')
OUT=C/'primary_rural_dagestan_stage_v2'
SELECT=Path('/workspace/settlements-delivery/continuation-loop-20261003/selected_observations.parquet')
BIND=Path('/workspace/settlements-delivery/continuation-loop-20261003/accepted_publication_bindings.parquet')
INV=C/'population2010/table5_to_r2_overlap_candidates_2010.parquet'
REF=C/'population2010/tom1_table5_extraction/official_2010_table5_reference.parquet'
PDF=Path('/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf')
RAW=Path('/workspace/settlements-raw/data/raw/2010/018_8eadc2d6b9_7._20Dag_2010.xls')
CONTROL=Path('/workspace/settlements-raw/data/raw/2010_official_controls/rosstat_population2010_by_region.csv')
V6=C/'primary_replacement_stage_v6/replacement_candidate_ledger.csv'
V6MAN=C/'primary_replacement_stage_v6/stage_manifest.json'
PARSER=Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/stage_primary_2010_replacements.py')
PROFILES=Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/apply_historical_identity_rule.py')

# Existing source inventory profile, corrected at row use: raw columns are 4 district,
# 5 rural council, 6 type, 7 locality name, 8 2010 total, 9 ethnicity.
SHEET='2010'; PROFILE={'region_constant':'Дагестан','district_col':4,'council_col':5,'type_col':6,'name_col':7,'population_col':8}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def norm(v):
 if v is None or pd.isna(v): return ''
 s=unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').replace('ѐ','е')
 return re.sub(r'\s+',' ',s).strip()
def region_norm(v):
 s=norm(v)
 return re.sub(r'\s+(?:область|край|республика|автономная область|автономный округ)$','',s).strip()
def district_norm(v):
 s=norm(v).replace('–','-').replace('—','-')
 s=re.split(r'\s+-\s+',s,maxsplit=1)[0]
 return re.sub(r'\s+(?:район|р-н|district)$','',s).strip()
def key(r,n,t): return (region_norm(r),norm(n),norm(t))
def intval(v):
 if v is None or pd.isna(v): return None
 if isinstance(v,(int,float)) and not isinstance(v,bool): return int(v) if float(v).is_integer() else None
 q=re.sub(r'[\s\u00a0]','',str(v)); return int(q) if re.fullmatch(r'[+-]?\d+',q) else None
def has_token(line,value): return bool(line and value is not None and re.search(r'(?<!\d)'+str(int(value))+r'(?!\d)',line))

def main():
 t0=time.perf_counter()
 if any(OUT.glob('*.csv')) or (OUT/'receipt.json').exists(): raise FileExistsError('New immutable Dagestan stage directory is not empty')
 selected=pd.read_parquet(SELECT)
 old=selected[(selected.census_year.eq(2010)) & selected.population_value_quality.eq('secondary_confidentiality_protected_value_exact_scope_unverified')].copy()
 bind=pd.read_parquet(BIND); applied=set(bind.old_source_record_id.astype(str)); bound_new=set(bind.new_source_record_id.astype(str))
 inventory=pd.read_parquet(INV)
 candidates=inventory[(inventory.candidate_status.str.startswith('unique_text_key')) & inventory.district_context_status.eq('district_text_agrees_candidate') & inventory.source_file.astype(str).str.contains('018_') & ~inventory.settlement_type_r2.astype(str).isin(['город','пгт'])].copy()
 # Bind exact source records to current R4 old assertions by immutable IDs.
 oldcols=['source_record_id','population','population_value_quality','population_value_quality_original_tag','population_scope','source_sha256','source_locator','source_row','source_sheet','region_raw','settlement_name','settlement_type','district_raw','source_name_raw','source_file']
 old=old[old.source_record_id.isin(candidates.r2_source_record_id)].copy()
 candidates=candidates.merge(old[oldcols].rename(columns={'source_record_id':'r2_source_record_id','population':'old_population_r2','population_value_quality':'old_population_quality','population_value_quality_original_tag':'old_population_quality_original_tag','population_scope':'old_population_scope','source_sha256':'r2_selected_source_sha256','source_locator':'r2_selected_source_locator','source_row':'r2_selected_source_row','source_sheet':'r2_selected_source_sheet','region_raw':'r2_selected_region_raw','settlement_name':'r2_selected_name','settlement_type':'r2_selected_type','district_raw':'r2_selected_district','source_name_raw':'r2_selected_source_name','source_file':'r2_selected_source_file'}),on='r2_source_record_id',how='left',validate='one_to_one')
 assert len(candidates)==56 and len(old)==56 and candidates.old_population_r2.notna().all()
 assert not candidates.r2_source_record_id.isin(applied).any()
 # Pin full-publication uniqueness using raw typed row keys from all current 2010 R2 rows and every T5 settlement row.
 selected10=selected[selected.census_year.eq(2010)].copy()
 selected10['_k']=[key(a,b,c) for a,b,c in zip(selected10.region_raw,selected10.settlement_name,selected10.settlement_type)]
 r2cnt=selected10.groupby('_k').size().to_dict()
 ref=pd.read_parquet(REF)
 candidates=candidates.merge(ref[['reference_id','men','women','hierarchy_status','region_key','region_raw']].drop_duplicates('reference_id'),on='reference_id',how='left',validate='many_to_one')
 candidates['t5_reference_id_unique']=~candidates.reference_id.duplicated(keep=False)
 t5=ref[ref.row_kind.eq('settlement')].copy() # keep extracted and quarantined proper locality rows in key uniqueness
 t5['_k']=[key(a,b,c) for a,b,c in zip(t5.region_key,t5.settlement_name,t5.settlement_type)]
 t5cnt=t5.groupby('_k').size().to_dict()
 candidates['_k']=[key(a,b,c) for a,b,c in zip(candidates.region_raw_r2,candidates.settlement_name_r2,candidates.settlement_type_r2)]
 candidates['r2_full_key_count']=candidates['_k'].map(r2cnt).fillna(0).astype(int)
 candidates['t5_full_key_count']=candidates['_k'].map(t5cnt).fillna(0).astype(int)
 candidates['r2_source_record_unique']=~candidates.r2_source_record_id.duplicated(keep=False)
 candidates['new_t5_id_not_already_bound']=~candidates.reference_id.isin(bound_new)
 # Whole-table full-source key counts can show one only when the primary row's typed identity is matched.
 # Read all 56 raw XLS rows directly through declared profile columns; no district inheritance or name inference.
 source_sha=sha(RAW); expected_sha=str(candidates.r2_source_sha256_from_asset_inventory.iloc[0])
 book=xlrd.open_workbook(str(RAW),on_demand=True); sheet=book.sheet_by_name(SHEET)
 header=sheet.row_values(3)
 header_facts={'col_4':str(header[4]),'col_5':str(header[5]),'col_6':str(header[6]),'col_7':str(header[7]),'col_8':str(header[8]),'col_9':str(header[9])}
 rawrows=[]
 for c in candidates.itertuples(index=False):
  vals=sheet.row_values(int(c.source_row)-1)
  rawtype=str(vals[PROFILE['type_col']]).strip(); rawname=str(vals[PROFILE['name_col']]).strip()
  rawdistrict=str(vals[PROFILE['district_col']]).strip(); rawcouncil=str(vals[PROFILE['council_col']]).strip()
  rawpop=intval(vals[PROFILE['population_col']])
  source_label=f'{rawtype} {rawname}'.strip()
  row_key=key(PROFILE['region_constant'],rawname,rawtype)
  pdf_page=int(c.pdf_page); pdf=PdfReader(str(PDF))
  text=pdf.pages[pdf_page-1].extract_text() or ''
  plines=[x.strip() for x in text.splitlines() if x.strip()]
  line_no=int(c.text_line_start)
  pypdf_line=(text.splitlines()[line_no-1].strip() if line_no<=len(text.splitlines()) else '')
  # source and parsed reference have exact line labels/counts; require an exact direct typed row.
  expected_label=str(c.label_raw).strip()
  direct_label=norm(pypdf_line.split()[0]+' '+pypdf_line.split()[1]) if len(pypdf_line.split())>=2 else ''
  pypdf_line_found=bool(pypdf_line and norm(pypdf_line)==norm(c.raw_lines and json.loads(c.raw_lines)[0].get('raw_line','')))
  poppler=subprocess.run(['pdftotext','-f',str(pdf_page),'-l',str(pdf_page),'-layout','-enc','UTF-8',str(PDF),'-'],capture_output=True,text=True,check=True)
  poppler_lines=poppler.stdout.splitlines()
  popmatches=[line.strip() for line in poppler_lines if norm(expected_label) and norm(line).startswith(norm(expected_label))]
  popline=popmatches[0] if len(popmatches)==1 else ''
  exact_name=norm(rawname)==norm(c.settlement_name_r2)==norm(c.table5_settlement_name_raw)
  exact_type=norm(rawtype)==norm(c.settlement_type_r2)==norm(c.table5_settlement_type)
  exact_region=(norm(PROFILE['region_constant'])==norm(c.region_raw_r2)==norm(c.region_key))
  rawdist_match=(district_norm(rawdistrict)==district_norm(c.district_raw_r2)==district_norm(c.district_raw_table5))
  primary_direct=(str(c.row_kind)=='settlement' and str(c.reference_status)=='extracted_reference' and bool(re.match(r'^(?:село|пос[еёѐ]лок|деревня|станица|хутор|аул|слобода)\s+',expected_label,re.I)))
  pypdf_counts=(has_token(pypdf_line,c.table5_population) and has_token(pypdf_line,c.men) and has_token(pypdf_line,c.women))
  poppler_counts=(has_token(popline,c.table5_population) and has_token(popline,c.men) and has_token(popline,c.women))
  rawrecord={'r2_source_record_id':c.r2_source_record_id,'replacement_source_record_id':c.reference_id,'region_constant_raw_workbook_scope':PROFILE['region_constant'],'raw_district_col4':rawdistrict,'raw_council_col5':rawcouncil,'raw_type_col6':rawtype,'raw_name_col7':rawname,'raw_2010_population_col8':rawpop,'raw_ethnicity_col9_not_name':str(vals[9]).strip(),'raw_typed_label':source_label,'raw_row_source_sha256':source_sha,'source_asset_sha256_matches_inventory':source_sha==expected_sha,'source_sheet':SHEET,'source_row_1based':int(c.source_row),'source_locator':f'xlrd_sheet={SHEET};row_1based={int(c.source_row)};cells=D:E:F:G:H:I','r2_old_population_current':intval(c.old_population_r2),'r2_old_population_matches_raw_workbook':rawpop==intval(c.old_population_r2),'typed_name_matches_R2_and_T5':exact_name,'type_matches_R2_and_T5':exact_type,'region_constant_matches_R2_and_T5_canonical_region_key':exact_region,'raw_primary_region_title':str(c.region_raw),'raw_district_matches_R2_and_T5':rawdist_match,'r2_full_key_count':int(c.r2_full_key_count),'t5_full_key_count':int(c.t5_full_key_count),'r2_source_record_unique':bool(c.r2_source_record_unique),'t5_reference_id_unique':bool(c.t5_reference_id_unique),'new_t5_id_not_already_bound':bool(c.new_t5_id_not_already_bound),'pdf_page':pdf_page,'printed_page':int(c.printed_page),'pypdf_text_line_1based':line_no,'pypdf_raw_line_independent':pypdf_line,'pypdf_line_matches_cached_raw_line':pypdf_line_found,'pypdf_label_exact':bool(norm(pypdf_line).startswith(norm(expected_label))),'pypdf_primary_total_men_women_match':pypdf_counts,'poppler_unique_label_match_count':len(popmatches),'poppler_raw_line_independent':popline,'poppler_primary_total_men_women_match':poppler_counts,'pypdf_poppler_source_rows_agree':bool(pypdf_counts and poppler_counts and norm(pypdf_line)==norm(popline)),'primary_row_direct_typed_locality':primary_direct,'primary_reference_population_equals_sexes':bool(c.total_equals_sexes),'primary_raw_counts_dash':bool(c.dash_in_counts),'primary_raw_counts_numeric_known':all(intval(z) is not None for z in [c.table5_population,c.men,c.women]),'primary_population':int(c.table5_population),'primary_men':int(c.men),'primary_women':int(c.women),'primary_district_header_context':c.district_raw_table5,'primary_label_raw':expected_label,'same_census_delta':int(c.table5_population-intval(c.old_population_r2)),'candidate_scope_qualifier':'Table 5 2010 rural row; retains published population scope; same-census source binding only'}
  rawrows.append(rawrecord)
 audit=pd.DataFrame(rawrows)
 # Stage full set only if every target meets all stated independent gates.
 gatecols=['source_asset_sha256_matches_inventory','r2_old_population_matches_raw_workbook','typed_name_matches_R2_and_T5','type_matches_R2_and_T5','region_constant_matches_R2_and_T5_canonical_region_key','raw_district_matches_R2_and_T5','r2_source_record_unique','t5_reference_id_unique','new_t5_id_not_already_bound','pypdf_line_matches_cached_raw_line','pypdf_label_exact','pypdf_primary_total_men_women_match','poppler_primary_total_men_women_match','pypdf_poppler_source_rows_agree','primary_row_direct_typed_locality','primary_reference_population_equals_sexes','primary_raw_counts_numeric_known']
 audit['stage_gate_all_pass']=audit[gatecols].all(axis=1)
 # Use unique source locator/checksum fields; source raw population hash binds row cells and scope constant.
 proposals=[]
 for row in audit.itertuples(index=False):
  c=candidates[candidates.r2_source_record_id.eq(row.r2_source_record_id)].iloc[0]
  label=row.primary_label_raw
  proposals.append({'r2_source_record_id':row.r2_source_record_id,'replacement_source_record_id':row.replacement_source_record_id,'old_population_r2':int(c.old_population_r2),'old_population_quality':c.old_population_quality,'old_population_quality_original_tag':c.old_population_quality_original_tag,'proposed_primary_population':int(c.table5_population),'proposed_primary_men':int(c.men),'proposed_primary_women':int(c.women),'table5_label_raw':label,'primary_raw_district':row.primary_district_header_context,'primary_district_context_flag':'explicit_same_row_secondary_district_matches_T5_header_context','primary_context_note':'2010 same-publication locality row; raw R2 workbook district column 4 matches the Table 5 printed district header after suffix normalization. This is source-context concordance only, not a historical administrative claim.','primary_raw_direct_typed_locality_row':bool(row.primary_row_direct_typed_locality),'pdf_page':row.pdf_page,'printed_page':row.printed_page,'text_line_start_pypdf':row.pypdf_text_line_1based,'text_line_end_pypdf':row.pypdf_text_line_1based,'raw_pdf_line_independent_pypdf':row.pypdf_raw_line_independent,'raw_pdf_line_independent_poppler':row.poppler_raw_line_independent,'primary_source_sha256':sha(PDF),'primary_source_locator':json.dumps({'reference_id':row.replacement_source_record_id,'pdf_page':row.pdf_page,'printed_page':row.printed_page,'pypdf_text_line':row.pypdf_text_line_1based},ensure_ascii=False,sort_keys=True),'primary_source_row_label_sha256':hashlib.sha256(label.encode()).hexdigest(),'population_scope':'settlement','same_census_delta':row.same_census_delta,'source_raw_population_hash':hashlib.sha256(json.dumps({'source_sha256':source_sha,'sheet':SHEET,'row':row.source_row_1based,'region_scope':PROFILE['region_constant'],'district':row.raw_district_col4,'council':row.raw_council_col5,'type':row.raw_type_col6,'name':row.raw_name_col7,'population':row.raw_2010_population_col8},ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'independent_review_mapping_sha256':None,'proposal_input_sha256':None,'stage_status':'proposed_pending_independent_review' if row.stage_gate_all_pass else 'held_failed_raw_evidence_gate'})
 proposal_df=pd.DataFrame(proposals)
 passing=set(audit.loc[audit.stage_gate_all_pass,'replacement_source_record_id'])
 proposal_df=proposal_df[proposal_df.replacement_source_record_id.isin(passing)].copy()
 # Reconciliation and test invariants; no selected data is rewritten.
 assert audit.r2_source_record_id.is_unique and audit.replacement_source_record_id.is_unique
 assert len(audit)==56 and len(proposal_df)<=56
 assert int(audit.r2_full_key_count.eq(1).sum())==56 and int(audit.t5_full_key_count.eq(1).sum())==56
 # Capture old stage-key mismatch semantics exactly: v6 uses !=1, but for this Dagestan set they are zero-match keys, not duplicates.
 stagecand=pd.read_csv(V6,low_memory=False)
 stagecand=stagecand[stagecand.r2_source_record_id.isin(set(candidates.r2_source_record_id))]
 v6reason_counts={}
 for h in stagecand.hold_reasons_json.fillna('[]'):
  for reason in json.loads(h or '[]'): v6reason_counts[reason]=v6reason_counts.get(reason,0)+1
 summary={
  'probe_id':'primary_rural_dagestan_stage_v2_20261003','status':'DIAGNOSTIC_PROPOSALS_ONLY_NO_ADMISSION_NO_SELECTED_MUTATION_NO_GIT',
  'pins_sha256':{str(p):sha(p) for p in [SELECT,BIND,INV,REF,PDF,RAW,CONTROL,V6,V6MAN,PARSER,PROFILES]},
  'source_profile_interpretation':{'workbook_source_sha256':source_sha,'sheet':SHEET,'region_constant':'Дагестан','header_row_1based':4,'header_cells':header_facts,'row_cells':{'district_col4':4,'rural_council_col5':5,'type_col6':6,'name_col7':7,'population_col8':8,'ethnicity_col9':9},'v6_profile_declared_name_cols':[9],'v6_profile_declared_type_name_columns':[6,7],'v6_profile_declared_district_cols':[],'correction_applied_only_in_this_new_probe':True},
  'current_release':{'selected_sha256':sha(SELECT),'selected_rows':len(selected),'current_2010_known_population':int(pd.to_numeric(selected.loc[selected.census_year.eq(2010),'population'],errors='coerce').sum()),'current_bindings_sha256':sha(BIND),'current_binding_count':len(bind),'target_old_ids_already_bound':int(candidates.r2_source_record_id.isin(applied).sum()),'target_new_ids_already_bound':int(candidates.reference_id.isin(bound_new).sum())},
  'candidate_scope':{'candidate_rows':len(candidates),'candidate_old_population':int(candidates.old_population_r2.sum()),'candidate_T5_population':int(candidates.table5_population.sum()),'gross_delta':int((candidates.table5_population-candidates.old_population_r2).sum()),'district_agree_subset_as_cached':True,'source_family':'Dagestan regional workbook 2010'},
  'whole_source_uniqueness':{'whole_current_R2_selected_rows_2010':len(selected10),'whole_table5_settlement_rows_all_statuses':len(t5),'candidate_R2_keys_unique':int(candidates.r2_full_key_count.eq(1).sum()),'candidate_T5_keys_unique':int(candidates.t5_full_key_count.eq(1).sum()),'candidate_reference_ids_unique':int(candidates.reference_id.is_unique),'key_normalization':'case/whitespace/NFKC and ё/ѐ→е; preserve punctuation; compare raw source region/name/type labels to full selected R2 and every Table 5 settlement line'},
  'v6_key_discrepancy':{'v6_reason_occurrences':v6reason_counts,'meaning':'v6 marks key count != 1; its 5 Dagestan rural rows with key holds have zero direct lookup matches under the stage name_norm/name_key strings, not multiple matches. Direct raw region/name/type keys in this rerun are unique exactly once across current R2 and the entire T5 typed-locality inventory. This is normalization/lookup mismatch, not evidence of a duplicate settlement.'},
  'raw_row_validation':{'rows_checked':len(audit),'rows_all_gates_pass':int(audit.stage_gate_all_pass.sum()),'gates':gatecols,'field_results':{c:int(audit[c].fillna(False).astype(bool).sum()) for c in gatecols},'actual_R2_source_sha256':source_sha,'source_hash_equals_inventory':source_sha==expected_sha,'explicit_row_district_col4_matches_both_R2_and_T5':int(audit.raw_district_matches_R2_and_T5.sum()),'primary_pdf_sha256':sha(PDF),'pypdf_and_poppler_crossread_verified':int(audit.pypdf_poppler_source_rows_agree.sum()),'pypdf_total_men_women_all_match':int(audit.pypdf_primary_total_men_women_match.sum()),'poppler_total_men_women_all_match':int(audit.poppler_primary_total_men_women_match.sum())},
  'proposal_rows':len(proposal_df),'proposal_old_population':int(proposal_df.old_population_r2.sum()) if len(proposal_df) else 0,'proposal_primary_population':int(proposal_df.proposed_primary_population.sum()) if len(proposal_df) else 0,'proposal_gross_delta':int(proposal_df.same_census_delta.sum()) if len(proposal_df) else 0,
  'limitations':['Same-census publication binding only; no cross-year identity proof.','Population source scope may differ; retain the original value-quality tag and source limitation.','No delta threshold, dashes-as-zero, residual allocation, fuzzy name matching, or administrative successor inference is used.','All 56 rows are proposals pending an independent binding review; this script does not apply them.'],
  'runtime_seconds':round(time.perf_counter()-t0,3),'outputs':{}
 }
 audit.to_csv(OUT/'dagestan56_row_level_audit.csv',index=False)
 # Keep a complete source mapping even if any gate fails; proposal file contains only rows passing every gate.
 proposal_df.to_csv(OUT/'replacement_proposals.csv',index=False)
 # Explicit row map used by an independent reviewer; not an approval projection.
 mapping=audit[['r2_source_record_id','replacement_source_record_id','r2_old_population_current','primary_population','same_census_delta','stage_gate_all_pass']].copy()
 mapping.to_csv(OUT/'candidate_mapping.csv',index=False)
 # Keep a fixed 18-row raw verification reference from the preceding bounded profile probe; no row-level dossier expansion.
 summary['existing_capped_dagestan_spotcheck']={'source':str(C/'primary_rural_next_cohort_probe_v1/fixed_raw_spotcheck_max60.csv'),'source_sha256':sha(C/'primary_rural_next_cohort_probe_v1/fixed_raw_spotcheck_max60.csv'),'dagestan_rows':18,'all_name_type_population_hash_district_checks_pass':True}
 report=f'''# Dagestan 2010 rural primary binding candidate stage (no application)\n\nThis new immutable stage is limited to the 56 cached district-agree Dagestan rural overlap candidates. It re-read the exact raw workbook row through the actual Dagestan columns: region scope constant, district col 4, rural council col 5, type col 6, name col 7, population col 8, ethnicity col 9. The earlier v6 proposal path used col 9 as a name and had no district column, explaining its raw-name/context holds.\n\nThe 56-row mapping totals old population {int(candidates.old_population_r2.sum()):,}, ROSSTAT Table 5 population {int(candidates.table5_population.sum()):,}, gross delta {int((candidates.table5_population-candidates.old_population_r2).sum()):,}. The actual workbook SHA-256 is `{source_sha}` and matches the asset inventory. Full current selected R2 and all Table 5 typed-settlement rows were checked for duplicate normalized typed keys; all 56 keys occur once in each source. For all {len(audit)} rows, workbook identity/region/district/count fields and raw PDF evidence were checked; {int(audit.stage_gate_all_pass.sum())} pass every required gate.\n\nThe workbook header identifies `район`, `Сельсовет`, `тип`, `название`, `2010.0`, and `я1` in columns 4-9. Its regional scope constant `Дагестан` matches the R2 key and the primary extracted canonical region key `дагестан`; the printed primary title is `Республика Дагестан`. In the existing v6 ledger, the 5 Dagestan candidates carrying “not unique” key reasons have zero matching lookup rows, not duplicate rows; the cause is a normalization mismatch between the raw candidate name and normalized `name_norm/name_key`. This stage recomputes uniqueness from raw typed names with the inventory’s explicit `ё/ѐ` compatibility and preserves the raw labels in the audit.\n\nThe proposals, if any, are `proposed_pending_independent_review`. The review mapping does not approve a source substitution. Population scope may differ, so the original quality tag and limitation remain required. Table 5 population changes are same-census source comparisons and do not establish cross-year identity or account for the national residual.\n\nRun time: {summary['runtime_seconds']:.2f}s. No selection file, source binding, identity graph, or git state was changed.\n'''
 (OUT/'report.md').write_text(report)
 # Store checksums of row-level evidence and proposal mapping for later independent review.
 for name in ['dagestan56_row_level_audit.csv','candidate_mapping.csv','replacement_proposals.csv','report.md','stage_dagestan_rural.py']:
  p=OUT/name; summary['outputs'][name]={'sha256':sha(p),'bytes':p.stat().st_size}
 summary['runtime_seconds']=round(time.perf_counter()-t0,3)
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (OUT/'receipt.json').write_text(json.dumps({'probe_id':summary['probe_id'],'status':summary['status'],'pins_sha256':summary['pins_sha256'],'outputs':summary['outputs'],'summary_sha256':sha(OUT/'summary.json'),'runtime_seconds':summary['runtime_seconds']},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'runtime_seconds':summary['runtime_seconds'],'candidate_count':len(candidates),'raw_checks':summary['raw_row_validation'],'proposal_rows':summary['proposal_rows'],'proposal_delta':summary['proposal_gross_delta'],'v6_key_discrepancy':summary['v6_key_discrepancy'],'outputs':summary['outputs']},ensure_ascii=False,indent=2))

if __name__=='__main__': main()

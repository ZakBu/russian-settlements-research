from pathlib import Path
import pandas as pd,numpy as np,fitz,json,re,hashlib,time
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');P=B/'demography2010_recovery_cycle06';O=B/'reviews/cycle07_primary2010_independent';checks=[]
def ck(k,v):checks.append({'check':k,'pass':bool(v)})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'\s+',' ',re.sub(r'[^\w\s]',' ',str(x).casefold().replace('ѐ','е').replace('ё','е'))).strip()
def parent(x):return re.sub(r'\s+',' ',re.sub(r'\b(муниципальный|муниципальная|район|района|городской|городского|округ|округа|г)\b',' ',norm(x))).strip()
freeze=json.load(open(P/'national_table5_source_freeze_manifest.json'))
for fn,h in freeze['files_sha256'].items():ck('input_source_hash_'+fn,sha(B/fn)==h)
d=pd.read_parquet(P/'national_table5_all_source_rows.parquet');literal=pd.read_parquet(P/'national_table5_literal_NP_inventory.parquet');l=pd.read_parquet(P/'national_table5_full_identity_and_recovery_candidates.parquet');new=pd.read_parquet(P/'national_table5_all_new_primary2010_numeric_candidates.parquet');a=pd.read_parquet(B/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet');native=a[a.source_record_id_2010.notna()].copy();pdf=fitz.open(P/'sources/national2010_official_volume1_exact.pdf');ck('actual1073page_primaryPDF',len(pdf)==1073)
actual=[];issues=[];literal_label_failures=[]
for pg in sorted(d.source_pdf_page.unique()):
 lines=[x.strip() for x in pdf[int(pg)-1].get_text().splitlines() if x.strip()];nums=[]
 for i in range(3,len(lines)-1):
  seq=lines[i-3:i+2]
  if all(re.fullmatch(r'[0-9]+|-',v) for v in seq[:3]) and all(re.fullmatch(r'[0-9]+,[0-9]+|-',v) for v in seq[3:]):nums.append(tuple(seq))
 expected=[tuple(str(r[c]) for c in ['source_total_cell_raw','source_male_cell_raw','source_female_cell_raw','source_male_pct_raw','source_female_pct_raw']) for _,r in d[d.source_pdf_page.eq(pg)].iterrows()]
 ck('independent_PyMuPDF_allnumericcells_page_'+str(pg),nums==expected)
 labels=d[d.source_pdf_page.eq(pg)].reset_index(drop=True); positions=[]
 for i in range(3,len(lines)-1):
  seq=lines[i-3:i+2]
  if all(re.fullmatch(r'[0-9]+|-',v) for v in seq[:3]) and all(re.fullmatch(r'[0-9]+,[0-9]+|-',v) for v in seq[3:]):positions.append((i-3,i+1))
 previous=-1
 for idx,(start,end) in enumerate(positions):
  rr=labels.iloc[idx];block=' '.join(lines[previous+1:start]);previous=end
  if rr.source_row_grain=='literal_settlement' and not norm(block).endswith(norm(rr.source_label_raw)):literal_label_failures.append({'source_row_id':rr.source_row_id,'label':rr.source_label_raw,'actual_preceding_text':block})
 if nums!=expected:issues.append({'page':int(pg),'actual':len(nums),'expected':len(expected),'first_diff':next(((k,aa,bb) for k,(aa,bb) in enumerate(zip(nums,expected)) if aa!=bb),None)})
ck('ALL4316_literal_NP_labels_at_their_actual_PDF_numeric_rows',len(literal_label_failures)==0)
(O/'independent_literal_label_mismatches.json').write_text(json.dumps(literal_label_failures,ensure_ascii=False,indent=2)+'\n')
num=d[['population2010_primary_numeric_cell','male2010_primary_numeric_cell','female2010_primary_numeric_cell']].notna().all(axis=1);ck('all9671_source_sex_sums_exact',num.sum()==9671 and np.array_equal(d.loc[num,'population2010_primary_numeric_cell'],d.loc[num,'male2010_primary_numeric_cell']+d.loc[num,'female2010_primary_numeric_cell']))
# Independently form full native2010 identity universe. No population participates in keys.
for fr in [native,literal]:
 fr['nk']=fr['name' if fr is native else 'settlement_name_raw'].map(norm);fr['tk']=fr['type' if fr is native else 'settlement_type_raw'].map(norm);fr['pk']=fr['district_raw_2010' if fr is native else 'source_native2010_parent_raw'].fillna('').map(parent)
ng={k:g for k,g in native.groupby(['region','tk','nk'],dropna=False)};sg={k:g for k,g in literal.groupby(['source_region_axis_key','tk','nk'],dropna=False)};lookup=a.set_index('id');accepted=['unique_literal_2010_region_type_name_in_both_source_and_native_axis_inventories','unique_literal_native2010_region_type_name_parent_in_both_sources'];expectedids={};statuses={}
for row in literal.to_dict('records'):
 key=(row['source_region_axis_key'],row['tk'],row['nk']);nc=ng.get(key,native.iloc[:0]);sc=sg.get(key,literal.iloc[:0]);uid=None;status=None
 if len(nc)==1 and len(sc)==1:uid=nc.id.iloc[0];status=accepted[0]
 elif row['pk']:
  ncp=nc[nc.pk.eq(row['pk'])];scp=sc[sc.pk.eq(row['pk'])]
  if len(ncp)==len(scp)==1:uid=ncp.id.iloc[0];status=accepted[1]
 expectedids[row['source_row_id']]=uid;statuses[row['source_row_id']]=status
ck('all4316_literal_identity_independent',all((expectedids[r.source_row_id]==r.strict_uid) if pd.notna(r.strict_uid) else expectedids[r.source_row_id] is None for r in l.itertuples()))
strict=l[l.eligible_numeric_recovery];ck('all3743_strict_numeric_rows_and_no_dash_admission',len(strict)==3743 and strict.strict_uid.is_unique and strict.population2010_primary_numeric_cell.notna().all() and strict.source_total_cell_raw.str.fullmatch(r'[0-9]+').all());ck('all169_new_identity_exact',len(new)==169 and new.strict_uid.is_unique and all(expectedids[r.source_row_id]==r.strict_uid and statuses[r.source_row_id]==r.link_status for r in new.itertuples()));ck('no_population_identity_or_federalaggregate_adoption',not l.link_identity_uses_population.any() and new.source_row_grain.eq('literal_settlement').all() and not new.source_region_axis_key.isin(['москва','санкт петербург']).any());ck('all169_legacysecondary_not_counted_prior_primary',new.prior_effective_quality2010.eq('secondary_confidentiality_protected_value_exact_scope_unverified').all() and not new.already_in_accepted_four_regions.any());ck('148changed21qualityonly',new.numeric_delta_vs_prior_effective2010.ne(0).sum()==148 and new.numeric_delta_vs_prior_effective2010.eq(0).sum()==21)
# Effective-prior sourcecontrols explicitly retained; proposed new values cannot silently contradict known primary.
prior=pd.read_parquet(P/'national_table5_effective_prior_and_new_source_candidates.parquet');conflicts=pd.read_parquet(P/'national_table5_prior_primary_conflicts.parquet');ck('no_existing_primary_count_conflicts',len(conflicts)==0)
(O/'source_cell_extraction_issues.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2)+'\n')
r={'status':'ACCEPTED' if all(c['pass'] for c in checks) else 'REJECTED','all_checks_passed':all(c['pass'] for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'checks':checks,'accepted_new_numeric_candidates_sha256':sha(P/'national_table5_all_new_primary2010_numeric_candidates.parquet'),'accepted_identity_statuses':accepted,'source_freeze_manifest_sha256':sha(P/'national_table5_source_freeze_manifest.json'),'source_pdf_sha256':sha(P/'sources/national2010_official_volume1_exact.pdf'),'scope':'Full Table5 PDF all numericcells independently read withPyMuPDF vsproducerlayout extraction;169newtyped-native2010identity/value candidates andall4316identity universe independently checked. Primary published NPpopulation, not complete allruralroster or unchanged2010/2021territory. Eightdash rows notzero. Actualoverlay notyetaccepted.','allowed_next_step':'Build NEWversioned full-axis2010overlay withsource/candidate/reviewSHA andpreserve oldvalues/qualities, then independentfullrow readback before newmodels.'};(O/'source_admission.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r['status'],r['n_checks'],r['n_failed']);print([c for c in checks if not c['pass']][:20]);print(issues[:5])

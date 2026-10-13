from pathlib import Path
import pandas as pd,xlrd,ast,re,json,hashlib,collections
E=Path(__file__).resolve().parent;P=E.parent;RAW=Path('/workspace/settlements-raw');SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');STATE=P/'main_axis_residual_application67_20261008/applied_state_observations.parquet';CREDIT=P/'main_axis_residual_application67_20261008/applied_primary_credited_UID_roster.csv.gz';PRIOR=P/'next_overlay_application67_20261008/normalized_cumulative_claims.csv.gz'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
a=ast.parse((P/'official_next_region_source_residual_20261008/build_closed_unique_supplement.py').read_text());ns={'re':re};nodes=[x for x in a.body if isinstance(x,ast.FunctionDef)and x.name in ['norm','key','classify','county'] or isinstance(x,ast.Assign)and any(isinstance(y,ast.Name)and y.id in ['T','pat']for y in x.targets)];exec(compile(ast.Module(body=nodes,type_ignores=[]),'classifier','exec'),ns);norm,key,classify,county=[ns[x]for x in ['norm','key','classify','county']]
cols=['source_record_id','census_year','settlement_name','settlement_type','region_raw','population','population_value_quality','source_file','source_sheet','source_row'];s=pd.read_parquet(SEL,columns=cols);s=s[s.census_year.eq(2010)&s.region_raw.isin(['тульская'])].copy();actual=pd.read_parquet(STATE,columns=['source_record_id','census_year','is_additive_settlement_record']);s['key']=[key(t,n)for t,n in zip(s.settlement_type,s.settlement_name)];sc={reg:collections.Counter(g.key)for reg,g in s.groupby('region_raw')};f=pd.read_csv(E/'tula_primary2010_full_NP_inventory.csv.gz');f['source_sheet']='Table12';f['source_row']=f.source_line;f['official_county_header_row']=f.county_header_locator;f['source_locator']=['PDFpage'+str(p)+':lines'+str(l)+'-'+str(e)for p,l,e in zip(f.source_pdf_page,f.source_line,f.source_line_end)];f['key']=[key(t,n)for t,n in zip(f.settlement_type,f.settlement_name)];fc={reg:collections.Counter(g.key)for reg,g in f.groupby('region')};fg={(reg,k):g for (reg,k),g in f.groupby(['region','key'])};prior=pd.read_csv(PRIOR);excluded=set(prior.old_source_record_id);credits=pd.read_csv(CREDIT,keep_default_na=False).set_index('source_record_id').to_dict('index');books={};rawcounts={};pins={str(p):sha(p)for p in [SEL,STATE,CREDIT,PRIOR,E/'tula_primary2010_full_NP_inventory.csv.gz']};rows=[];holds=[]
actualadditive=set(actual.loc[actual.is_additive_settlement_record,'source_record_id'])
for old in s.itertuples():
 if old.source_record_id in excluded or old.source_record_id not in actualadditive:continue
 cand=fg.get((old.region_raw,old.key))
 if cand is None:continue
 p=RAW/old.source_file
 if p.suffix!='.xls':continue
 if str(p) not in books:books[str(p)]=xlrd.open_workbook(p);pins[str(p)]=sha(p)
 sh=books[str(p)].sheet_by_name(old.source_sheet);vv=sh.row_values(int(old.source_row)-1);target=[q for q in classify(vv)if q['key']==old.key];reason=''
 if len(target)!=1:reason='raw_literal_propertype_name_not_verified'
 else:
  q=target[0];token=vv[2];ck=(str(p),old.source_sheet,str(token))
  if ck not in rawcounts:
   count=collections.Counter()
   for i in range(sh.nrows):
    v=sh.row_values(i)
    if v[2]==token:
     for z in classify(v):count[z['key']]+=1
   rawcounts[ck]=count
  if sc[old.region_raw][old.key]!=1 or fc[old.region_raw][old.key]!=1 or rawcounts[ck][old.key]!=1:reason='full_regional_literal_typed_competition_not_unique'
  else:
   r=cand.iloc[0];actualcounty=[]
   if q['type_col']!=q['name_col']:actualcounty=[v.strip()for v in vv[3:q['type_col']]if isinstance(v,str)and v.strip()and norm(v)!=norm(q['name_raw'])]
   else:actualcounty=[v.strip()for v in vv[:q['caption_col']]if isinstance(v,str)and re.search(r'\b(район|округ)\b',v,re.I)]
   if actualcounty and pd.notna(r.official_county)and any(county(x)!=county(r.official_county)for x in actualcounty):reason='actual_literal_county_conflict'
   elif pd.isna(r.official_population):reason='literal_primary_population_NULL'
   elif pd.isna(old.population):reason='old_population_NULL_separate_observation_recovery_required'
   else:
    popcols=[j for j in range(q['name_col']+1,min(12,len(vv)))if isinstance(vv[j],(int,float))and vv[j]==old.population]
    if not popcols:reason='old_raw_population_cell_not_verified'
    else:
     record=dict(old_source_record_id=old.source_record_id,region=old.region_raw,old_population=int(old.population),old_quality=old.population_value_quality,old_source_file=old.source_file,old_source_sheet=old.source_sheet,old_source_row=int(old.source_row),old_source_sha256=pins[str(p)],raw_old_NP_caption=q['caption'],raw_type_cell_or_prefix=q['type_raw'],raw_name_cell_or_caption=q['name_raw'],raw_old_cells_json=json.dumps(vv,ensure_ascii=False),actual_printed_county_cells_json=json.dumps(actualcounty,ensure_ascii=False),official_source_record_id=r.primary_source_record_id,official_population=int(r.official_population),official_men=r.official_men,official_women=r.official_women,official_name=r.settlement_name,official_type=r.settlement_type,official_district=r.official_county,official_municipality=r.official_municipality,official_county_header_row=r.official_county_header_row,official_source_path=r.source_path,official_source_sha256=r.source_sha256,official_source_sheet=r.source_sheet,official_source_row=int(r.source_row),official_source_locator=r.source_locator,official_page=int(r.source_pdf_page),official_line_start=int(r.source_line),official_line_end=int(r.source_line_end),independent_poppler_lines=r.raw_pdf_line,official_raw_NP_caption=r.raw_NP_caption,official_raw_count_cells_json=r.raw_count_cells_json,official_source_grade=r.source_grade,census_reference_date=r.census_reference_date,delta=int(r.official_population)-int(old.population),status='ready_exact_same2010_primary_literal_PDF_NP_context',context_method='exact_literal_propertype_name_region_samecensus_unique_FULL_selected_raw_primary_NP_rosters_no_actual_county_conflict',population_used_for_binding_context=False,selected_full_region_competitors=1,raw_full_region_NP_competitors=1,official_full_region_NP_competitors=1,already_primary_UID_credited_post67=old.source_record_id in credits,existing_entity_uid_post67=credits.get(old.source_record_id,{}).get('entity_uid',''),already_effective_prior_override=False,selection_applied=False)
     rows.append(record)
 if reason:holds.append(dict(old_source_record_id=old.source_record_id,region=old.region_raw,settlement_name=old.settlement_name,settlement_type=old.settlement_type,old_population=old.population,hold_reason=reason))
d=pd.DataFrame(rows);d.to_csv(E/'ready_primary2010_regional_claims.csv.gz',index=False);pd.DataFrame(holds).to_csv(E/'primary2010_binding_holds.csv.gz',index=False);sample=pd.concat([d.sort_values('delta',ascending=False).head(5),d.sort_values('delta').head(3),d.sort_values('official_population').head(2)]).drop_duplicates('old_source_record_id');sample.to_csv(E/'fixed10_primary_claim_review.csv',index=False)
r={'status':'candidate_primary_claims_not_applied_review_pending','ready_rows':len(d),'delta':int(d.delta.sum()),'old_population_sum':int(d.old_population.sum()),'official_population_sum':int(d.official_population.sum()),'credited_rows':int(d.already_primary_UID_credited_post67.sum()),'credited_delta':int(d.loc[d.already_primary_UID_credited_post67,'delta'].sum()),'by_region':d.groupby('region').agg(rows=('delta','size'),delta=('delta','sum'),old_population=('old_population','sum'),primary_population=('official_population','sum')).to_dict('index'),'holds':dict(collections.Counter(x['hold_reason']for x in holds)),'input_pins':pins,'excluded_prior_claims':len(excluded),'output_pins':{x:sha(E/x)for x in ['ready_primary2010_regional_claims.csv.gz','primary2010_binding_holds.csv.gz','fixed10_primary_claim_review.csv']},'fixed_sample_method':'deterministic top5 positive delta + top3 negative delta + smallest2 primary counts, deduplicated; no population identity matching'};(E/'primary_claims_candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items()if k!='input_pins'},ensure_ascii=False,indent=2))

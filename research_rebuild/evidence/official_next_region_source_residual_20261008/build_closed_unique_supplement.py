from pathlib import Path
import pandas as pd,xlrd,re,json,hashlib,collections,subprocess
from pypdf import PdfReader
O=Path(__file__).resolve().parent;RAW=Path('/workspace/settlements-raw');SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');REF=Path('/workspace/settlements-work/continuation_20261003/population2010/tom1_table5_extraction/official_2010_table5_reference.parquet');PDF=RAW/'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf';ALL=O/'national_cached_Table5_all_remaining_candidates.csv.gz';READY=O/'national_cached_Table5_ready_primary_override_candidates.csv.gz';PRIOR=O.parent/'official_population_residual_sources_20261008/followup_context_accepted_delta.csv.gz';CREDIT=O.parent/'primary_residual_mass_application_20261008/applied_primary_credited_UID_roster.csv.gz'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'\bимени\b','им',re.sub(r'[^а-яa-z0-9]+',' ',str(x).casefold().replace('ё','е').replace('ѐ','е')).strip())
def key(t,n):return norm(t),norm(n)
T={'г':'город','город':'город','пгт':'пгт','рп':'пгт','р п':'пгт','рабочий поселок':'пгт','дачный поселок':'пгт','курортный поселок':'пгт','поселок':'поселок','п':'поселок','село':'село','с':'село','деревня':'деревня','д':'деревня','станица':'станица','хутор':'хутор','аул':'аул','починок':'починок','слобода':'слобода','заимка':'заимка','выселок':'выселок','кишлак':'кишлак','населенный пункт':'населенный пункт','станция':'станция'}
pat=re.compile(r'^(г\.|д\.|с\.|п\.|р\.п\.|город\s+|пгт\s+|рп\s+|деревня\s+|пос[еёѐ]лок\s+|село\s+|станица\s+|хутор\s+|аул\s+|починок\s+|слобода\s+|заимка\s+|кишлак\s+|насел[её]нный пункт\s+|станция\s+)\s*(.+)$',re.I)
def classify(vals):
 found={}
 for j,v in enumerate(vals[:10]):
  if not isinstance(v,str):continue
  m=pat.match(v.strip())
  if m and norm(m[1]) in T:
   t=T[norm(m[1])];n=re.sub(r'\s+(рп|дп|кп)$','',m[2],flags=re.I);k=key(t,n);found[k]={'key':k,'type_raw':m[1].strip(),'name_raw':n.strip(),'caption':v,'caption_col':j,'name_col':j,'type_col':j}
  elif norm(v) in T and j+1<len(vals) and isinstance(vals[j+1],str) and vals[j+1].strip():
   k=key(T[norm(v)],vals[j+1]);found[k]={'key':k,'type_raw':v,'name_raw':vals[j+1],'caption':v.strip()+' '+vals[j+1].strip(),'caption_col':j,'name_col':j+1,'type_col':j}
 return list(found.values())
def county(x):return re.sub(r'\b(муниципальный|район|городской|округ)\b','',norm(x)).strip()
s=pd.read_parquet(SEL);s=s[s.census_year.eq(2010)].copy();s['key']=s.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);sd=s.set_index('source_record_id');sc={reg:collections.Counter(g.key) for reg,g in s.groupby('region_raw')};fileRegions=s.groupby('source_file').region_raw.apply(lambda x:set(x)).to_dict()
f=pd.read_parquet(REF);f=f[f.row_kind.eq('settlement')].copy();f['key']=f.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);fc={reg:collections.Counter(g.key) for reg,g in f.groupby('region_key')};ref=f.set_index('reference_id').to_dict('index')
c=pd.read_csv('/workspace/settlements-work/continuation_20261003/primary_population_next_cohort_probe_v1/remaining_table5_unique_candidates.csv',low_memory=False).set_index('r2_source_record_id');allc=pd.read_csv(ALL);base=pd.read_csv(READY);prior=pd.read_csv(PRIOR);excluded=set(base.old_source_record_id)|set(prior.old_source_record_id);h=allc[~allc.old_source_record_id.isin(excluded)].copy();credits=pd.read_csv(CREDIT,keep_default_na=False).set_index('source_record_id').to_dict('index')
books={};counts={};pins={str(p):sha(p) for p in [SEL,REF,PDF,ALL,READY,PRIOR,CREDIT]};poppler=subprocess.check_output(['pdftotext','-layout',str(PDF),'-']).decode().split('\f');reader=PdfReader(PDF);pages={};rows=[];holdreasons=collections.Counter()
for r in h.to_dict('records'):
 sid=r['old_source_record_id'];old=sd.loc[sid];region=old.region_raw;p=ref[c.loc[sid]['reference_id']];path=RAW/old.source_file;pk=str(path)
 if pk not in books:books[pk]=xlrd.open_workbook(path);pins[pk]=sha(path)
 sh=books[pk].sheet_by_name(old.source_sheet);n=int(old.source_row);vals=sh.row_values(n-1);target=[q for q in classify(vals) if q['key']==key(old.settlement_type,old.settlement_name)]
 if len(target)!=1:holdreasons['no_exact_positive_raw_type_name_classifier']+=1;continue
 q=target[0];popcols=[j for j in range(q['name_col']+1,min(12,len(vals))) if isinstance(vals[j],(int,float)) and float(vals[j])==float(old.population)]
 if not popcols:holdreasons['no_exact_raw_population_cell']+=1;continue
 # Region scope comes from published region token, or a genuinely single-region workbook.
 mono=fileRegions.get(old.source_file,set())=={region};token=vals[2] if isinstance(vals[2],str) and vals[2].strip() else None
 if not mono and token is None:holdreasons['full_raw_region_scope_unresolved']+=1;continue
 ck=(pk,old.source_sheet,region,None if mono else token)
 if ck not in counts:
  count=collections.Counter()
  for i in range(sh.nrows):
   vv=sh.row_values(i)
   if not mono and vv[2]!=token:continue
   for z in classify(vv):count[z['key']]+=1
  counts[ck]=count
 k=q['key'];unique=sc.get(region,{}).get(k,0)==counts[ck].get(k,0)==fc.get(region,{}).get(k,0)==1 and k==p['key']
 if not unique:holdreasons['full_raw_selected_official_typed_competitor_or_literal_key_conflict']+=1;continue
 # Published county cells before the NP columns are positive source context when present.
 # A bare county adjective is recognized only in the structured district/type/name format.
 actual=[]
 if q['type_col']!=q['name_col']:
  for v in vals[3:q['type_col']]:
   if isinstance(v,str) and v.strip() and norm(v)!=norm(q['name_raw']):actual.append(v.strip())
 else:
  actual=[v.strip() for v in vals[:q['caption_col']] if isinstance(v,str) and re.search(r'\b(район|округ)\b',v,re.I)]
 primarycounty=p['district_raw'] if pd.notna(p['district_raw']) else None
 contradictory=bool(actual and primarycounty and any(county(v)!=county(primarycounty) for v in actual))
 if contradictory:holdreasons['actual_printed_county_contradiction']+=1;continue
 page=int(p['pdf_page']);start=int(p['text_line_start']);end=int(p['text_line_end']);nums=[str(int(p[x])) for x in ['population','men','women']];hits=[];lines=poppler[page-1].splitlines()
 for i,l in enumerate(lines):
  ns=re.findall(r'\d+',l)
  if any(ns[j:j+3]==nums for j in range(len(ns)-2)) and norm(p['settlement_name']) in norm(' '.join(lines[max(0,i-2):i+1])):hits.append(' | '.join(lines[max(0,i-2):i+1]))
 if not hits or int(p['population'])!=int(p['men'])+int(p['women']):holdreasons['independent_official_count_readback_not_resolved']+=1;continue
 if page not in pages:pages[page]=reader.pages[page-1].extract_text().splitlines()
 rows.append({'old_source_record_id':sid,'region':region,'old_population':int(old.population),'old_quality':old.population_value_quality,'old_source_file':old.source_file,'old_source_sheet':old.source_sheet,'old_source_row':n,'raw_old_NP_caption':q['caption'],'raw_type_cell_or_prefix':q['type_raw'],'raw_name_cell_or_caption':q['name_raw'],'raw_population_cell_column_zero_based':popcols[0],'raw_population_cell':vals[popcols[0]],'actual_printed_county_cells_json':json.dumps(actual,ensure_ascii=False),'old_source_sha256':pins[pk],'official_source_record_id':c.loc[sid]['reference_id'],'official_population':int(p['population']),'official_men':int(p['men']),'official_women':int(p['women']),'official_name':p['settlement_name'],'official_type':p['settlement_type'],'official_district':primarycounty,'official_standalone_regional_NP_no_inherited_parent':primarycounty is None,'official_source_path':str(PDF),'official_source_sha256':pins[str(PDF)],'official_page':page,'official_line_start':start,'official_line_end':end,'independent_pypdf_lines':' | '.join(pages[page][start-1:end]),'independent_poppler_lines':hits[0],'delta':int(p['population'])-int(old.population),'status':'ready_closed_unique_same2010_primary_publication_binding','context_method':'positive_literal_native_NP_name_type_region_census_date_full_source_unique_1to1_no_actual_county_contradiction','selected_full_region_competitors':sc[region][k],'raw_full_region_NP_competitors':counts[ck][k],'official_Table5_competitors':fc[region][k],'full_raw_region_scope_method':'single_region_workbook_all_NP_rows' if mono else 'published_literal_region_token_all_NP_rows','already_primary_UID_credited_post62':sid in credits,'existing_entity_uid_post62':credits.get(sid,{}).get('entity_uid',''),'already_effective_prior_override':False,'population_used_for_binding_context':False,'selection_applied':False})
d=pd.DataFrame(rows);assert not set(d.old_source_record_id)&excluded and d.old_source_record_id.is_unique;d.to_csv(O/'closed_unique_same2010_ready_supplement.csv.gz',index=False,compression='gzip');d.groupby('region').agg(rows=('old_source_record_id','size'),delta=('delta','sum')).sort_values('delta',ascending=False).to_csv(O/'closed_unique_supplement_by_region.csv')
r={'status':'append_only_closed_unique_same2010_primary_binding_supplement_not_applied','frozen_base501_rows':len(base),'supplement_ready_rows':len(d),'supplement_delta':int(d.delta.sum()),'supplement_primary_UID_rows_post62':int(d.already_primary_UID_credited_post62.sum()),'supplement_primary_UID_delta_post62':int(d.loc[d.already_primary_UID_credited_post62,'delta'].sum()),'total_new_ready_rows':len(base)+len(d),'total_new_ready_delta':int(base.delta.sum()+d.delta.sum()),'total_cumulative_prior510_plus_new_ready_rows':510+len(base)+len(d),'total_cumulative_delta':10478+int(base.delta.sum()+d.delta.sum()),'new_ready_effective_source_deficit_if_applied':483034-int(base.delta.sum()+d.delta.sum()),'still_held_rows':len(h)-len(d),'remaining_hold_reasons':dict(holdreasons),'rule':'Same-census primary population publication binding only: exact literal original raw NP name and propertype, region/date, one-to-one key across FULL regional originalraw NP roster, allselected competitors and allofficialTable5 NP rows. Official P/M/F independently verified. Actual printed county contradictions hold; absent county or anchors are not a contradiction. This creates no temporalidentity or new point. Official standalone urbanNP context remains distinct; false inherited urbanparent ignored. Separate-column raw type/name is explicitly parsed, not inferred from selected label. No fuzzy/name-only matching and no residual allocation.','no_prior510_or_frozen501_overlap':True,'input_pins':pins,'output':{'path':'closed_unique_same2010_ready_supplement.csv.gz','sha256':sha(O/'closed_unique_same2010_ready_supplement.csv.gz'),'bytes':(O/'closed_unique_same2010_ready_supplement.csv.gz').stat().st_size}}
(O/'closed_unique_supplement_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins']},ensure_ascii=False,indent=2))

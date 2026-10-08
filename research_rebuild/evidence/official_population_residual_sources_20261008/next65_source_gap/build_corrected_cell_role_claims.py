from pathlib import Path
import pandas as pd,xlrd,re,json,hashlib,collections,subprocess
from pypdf import PdfReader
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
E=Path(__file__).resolve().parent;BASE=E.parents[1];RAW=Path('/workspace/settlements-raw');S=BASE/'main_axis_residual_application65_20261008/applied_state_observations.parquet';ORIG=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');REF=Path('/workspace/settlements-work/continuation_20261003/population2010/tom1_table5_extraction/official_2010_table5_reference.parquet');PDF=RAW/'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf';C=BASE/'main_axis_residual_application65_20261008/applied_primary_credited_UID_roster.csv.gz';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
s=pd.read_parquet(S,columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm','population','population_value_quality']);s=s[s.census_year.eq(2010)].copy();s['key']=s.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);orig=pd.read_parquet(ORIG,columns=['source_record_id','census_year','source_file','source_sheet','source_row','region_raw']);s=s.merge(orig.drop(columns=['census_year']),on='source_record_id',validate='one_to_one');f=pd.read_parquet(REF);f=f[f.row_kind.eq('settlement')].copy();f['key']=f.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);used=set();pins={str(p):sha(p)for p in [S,ORIG,REF,PDF,C]}
for p in [BASE/'next_overlay_application_20261008/normalized_cumulative_claims.csv.gz',BASE/'residual_source_followup_20261008/accepted_county_bound_primary2010_addon_8.csv.gz',BASE/'residual_source_followup_20261008/accepted_all_regions_county_bound_primary2010_addon_127.csv.gz']:
 used.update(pd.read_csv(p,usecols=['old_source_record_id']).old_source_record_id);pins[str(p)]=sha(p)
assert len(used)==1910;c=pd.read_csv(C,usecols=['source_record_id','census_year','population','entity_uid'],keep_default_na=False);credited=c[c.census_year.eq(2010)].set_index('source_record_id').to_dict('index');books={};rawcounts={};counts=collections.Counter((r.region_norm,r.key)for r in s.itertuples());refs=collections.defaultdict(list)
for r in f.to_dict('records'):refs[(r['region_key'],r['key'])].append(r)
fulltokens=s.groupby(['source_file','source_sheet','region_norm']).source_row.apply(list).to_dict();fregions=s.groupby('source_file').region_norm.apply(set).to_dict();ready=[];held=[];witness=[];poppler=subprocess.check_output(['pdftotext','-layout',str(PDF),'-']).decode().split('\f');reader=PdfReader(str(PDF));pagecache={}
for r in s[~s.source_record_id.isin(used)&s.population_value_quality.fillna('').str.startswith('secondary_confidentiality')].to_dict('records'):
 rk=(r['region_norm'],r['key']);official=refs.get(rk,[])
 if not official:continue
 reason=None
 if len(official)!=1 or counts[rk]!=1:
  held.append(dict(source_record_id=r['source_record_id'],region=r['region_norm'],name=r['settlement_name'],type=r['settlement_type'],population=r['population'],reason='full_actual65_regional_typed_competition',official_competitors=len(official),selected_competitors=counts[rk]));continue
 p=official[0];path=RAW/r['source_file']
 if path.suffix.lower()!='.xls':continue
 if str(path)not in books:books[str(path)]=xlrd.open_workbook(str(path));pins[str(path)]=sha(path)
 sh=books[str(path)].sheet_by_name(r['source_sheet']);rn=int(r['source_row']);vals=sh.row_values(rn-1);q=[x for x in classify(vals)if x['key']==r['key']]
 if len(q)!=1:reason='literal_raw_type_name_not_uniquely_classified'
 else:
  q=q[0];popcols=[j for j in range(q['name_col']+1,min(12,len(vals)))if isinstance(vals[j],(int,float))and vals[j]==r['population']]
  if not popcols:reason='exact_raw_count_cell_not_found'
 if reason:held.append(dict(source_record_id=r['source_record_id'],region=r['region_norm'],name=r['settlement_name'],reason=reason));continue
 ck=(str(path),r['source_sheet'],r['region_norm'])
 if ck not in rawcounts:
  mono=fregions[r['source_file']]=={r['region_norm']};tokens={sh.row_values(int(n)-1)[2]for n in fulltokens[(r['source_file'],r['source_sheet'],r['region_norm'])]};counter=collections.Counter();rawwitnesses=collections.defaultdict(list)
  for i in range(sh.nrows):
   vv=sh.row_values(i)
   if not mono and vv[2]not in tokens:continue
   for z in classify(vv):counter[z['key']]+=1;rawwitnesses[z['key']].append(i+1)
  rawcounts[ck]=(counter,rawwitnesses)
 counter,rivals=rawcounts[ck]
 if counter[r['key']]!=1:held.append(dict(source_record_id=r['source_record_id'],region=r['region_norm'],name=r['settlement_name'],reason='full_raw_regional_NP_typed_competition',raw_competitor_rows=json.dumps(rivals[r['key']])));continue
 actual=[];ignored=[]
 for j,v in enumerate(vals[3:q['type_col']],3):
  if not isinstance(v,str)or not v.strip():continue
  # Published repeated fullNPcaption before separatetypename is a redundant NP field, never a county.
  parsed=classify([v]);cc=county(v)
  if parsed:ignored.append(dict(column=j,literal=v,role='explicit_typed_NP_caption_not_county',parsed_keys=parsed));continue
  if not cc:ignored.append(dict(column=j,literal=v,role='generic_administrative_label_without_proper_name'));continue
  actual.append(dict(column=j,literal=v,county_norm=cc))
 pc=county(p['district_raw'])if pd.notna(p['district_raw'])else ''
 if actual and (not pc or any(x['county_norm']!=pc for x in actual)):
  held.append(dict(source_record_id=r['source_record_id'],region=r['region_norm'],name=r['settlement_name'],reason='actual_printed_county_or_object_conflict',actual_cells=json.dumps(actual,ensure_ascii=False),official_county=p['district_raw']));continue
 # Fullpropertyped key is uniquely closed across actual65, ALLrawregionNPs andALLofficialNPs, with no contradictory codes present in publication fields.
 page=int(p['pdf_page']);nums=[str(int(p[k]))for k in ['population','men','women']];hits=[];lines=poppler[page-1].splitlines()
 for i,line in enumerate(lines):
  n=re.findall(r'\d+',line)
  if any(n[j:j+3]==nums for j in range(len(n)-2))and norm(p['settlement_name'])in norm(' '.join(lines[max(0,i-2):i+1])):hits.append(' | '.join(lines[max(0,i-2):i+1]))
 if not hits or int(p['population'])!=int(p['men'])+int(p['women']):held.append(dict(source_record_id=r['source_record_id'],region=r['region_norm'],name=r['settlement_name'],reason='independent_primary_count_readback'));continue
 if page not in pagecache:pagecache[page]=reader.pages[page-1].extract_text().splitlines()
 start,end=int(p['text_line_start']),int(p['text_line_end']);row=dict(old_source_record_id=r['source_record_id'],region=r['region_norm'],old_population=int(r['population']),old_quality=r['population_value_quality'],old_source_file=r['source_file'],old_source_sheet=r['source_sheet'],old_source_row=rn,raw_old_NP_caption=q['caption'],raw_type_cell_or_prefix=q['type_raw'],raw_name_cell_or_caption=q['name_raw'],raw_population_cell_column_zero_based=popcols[0],raw_population_cell=vals[popcols[0]],old_source_sha256=pins[str(path)],actual_printed_county_cells_json=json.dumps(actual,ensure_ascii=False),redundant_NP_caption_or_generic_field_roles_json=json.dumps(ignored,ensure_ascii=False),official_source_record_id=p['reference_id'],official_population=int(p['population']),official_men=int(p['men']),official_women=int(p['women']),official_name=p['settlement_name'],official_type=p['settlement_type'],official_district=p['district_raw']if pd.notna(p['district_raw'])else '',official_source_path=str(PDF),official_source_sha256=pins[str(PDF)],official_page=page,official_line_start=start,official_line_end=end,delta=int(p['population'])-int(r['population']),status='ready_closed_unique_same2010_primary_publication_binding',context_method='independent_literal_cell_role_full_actual65_rawregional_official_typed_unique_samecensus_no_real_county_or_code_contradiction',selected_full_region_competitors=counts[rk],raw_full_region_NP_competitors=counter[r['key']],official_Table5_competitors=len(official),population_used_for_binding_context=False,independent_count_readback=True,independent_poppler_lines=hits[0],independent_pypdf_lines=' | '.join(pagecache[page][start-1:end]),already_primary_UID_credited_post65=r['source_record_id']in credited,existing_entity_uid_post65=credited.get(r['source_record_id'],{}).get('entity_uid',''),old_population_effective_prior=int(r['population']),source_grade='direct_official_primary_2010_census_Table5',census_year=2010,census_reference_date='2010-10-14',official_publication_date='',new_identity_or_point_assertions=False,selection_applied=False)
 ready.append(row);witness.append(dict(source_record_id=r['source_record_id'],raw_cells=vals[:12],cell_role_readback=ignored,real_county_cells=actual,raw_typed_competitor_rows=rivals[r['key']]))
d=pd.DataFrame(ready);assert not d.empty and d.old_source_record_id.is_unique and not set(d.old_source_record_id)&used;d.to_csv(E/'corrected_cell_role_ready_primary2010_claims.csv.gz',index=False);pd.DataFrame(held).to_csv(E/'remaining_exact_literal_Table5_holds.csv.gz',index=False);(E/'literal_raw_cell_role_readback.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2));d.groupby('region').agg(rows=('delta','size'),delta=('delta','sum')).to_csv(E/'ready_by_region.csv');r={'status':'new_scoped_samecensus_source_packet_not_applied','actual_stage':65,'prior1910_disjoint':True,'rows':len(d),'delta':int(d.delta.sum()),'actual65_primary_credit_rows':int(d.already_primary_UID_credited_post65.sum()),'actual65_primary_credit_delta':int(d.loc[d.already_primary_UID_credited_post65,'delta'].sum()),'held':len(held),'source_control_gap_before':324742,'source_control_gap_if_allclaims_applied':324742-int(d.delta.sum()),'rule':'Exactpropertyped NPkey mustbe unique across all actual65regional observations, fullrawregional NPpublication, and allprimary2010Table5settlementrows. ExplicitrepeatedtypedNPcaption isNPfield, notcounty. Blankcounty alone isnotconflict. Anyrealprintedcounty orobjectconflictheld. Populations notusedforbinding. NoState/identity/point changes.','input_pins':pins,'output_pins':{p.name:sha(p)for p in E.iterdir()if p.is_file()and p.name!='receipt.json'},'held_reasons':dict(collections.Counter(x['reason']for x in held))};(E/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(d[['region','official_name','old_population','official_population','delta']].to_string(index=False));print(json.dumps({k:v for k,v in r.items()if k not in ['input_pins','output_pins','rule']},ensure_ascii=False,indent=2))

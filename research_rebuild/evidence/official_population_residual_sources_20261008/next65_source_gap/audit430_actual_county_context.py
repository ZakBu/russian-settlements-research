from pathlib import Path
import pandas as pd,json,xlrd,re,ast,hashlib,collections
E=Path(__file__).resolve().parent;B=E.parents[1];P=E/'build_corrected_cell_role_claims.py';tree=ast.parse(P.read_text());nodes=[]
for n in tree.body:
 if isinstance(n,ast.FunctionDef)and n.name in ['norm','key','classify','county']:nodes.append(n)
 if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id in ['T','pat']for t in n.targets):nodes.append(n)
ns={'re':re};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(P),'exec'),ns);norm,key,classify,county=[ns[n]for n in ['norm','key','classify','county']];sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();holds=pd.read_csv(E/'remaining_exact_literal_Table5_holds.csv.gz',keep_default_na=False);h=holds[holds.reason.eq('full_actual65_regional_typed_competition')];S=B/'main_axis_residual_application65_20261008/applied_state_observations.parquet';s=pd.read_parquet(S,columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm']);s=s[s.census_year.eq(2010)].copy();s['key']=s.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);orig=pd.read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',columns=['source_record_id','source_file','source_sheet','source_row']);s=s.merge(orig,on='source_record_id',validate='one_to_one');REF=Path('/workspace/settlements-work/continuation_20261003/population2010/tom1_table5_extraction/official_2010_table5_reference.parquet');f=pd.read_parquet(REF);f=f[f.row_kind.eq('settlement')].copy();f['key']=f.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);bound={};inputs={str(S):sha(S),str(REF):sha(REF)}
for p in [B/'next_overlay_application_20261008/normalized_cumulative_claims.csv.gz',B/'residual_source_followup_20261008/accepted_county_bound_primary2010_addon_8.csv.gz',B/'residual_source_followup_20261008/accepted_all_regions_county_bound_primary2010_addon_127.csv.gz',E/'corrected_cell_role_ready_primary2010_claims.csv.gz']:
 d=pd.read_csv(p,keep_default_na=False);inputs[str(p)]=sha(p)
 for r in d.to_dict('records'):
  if str(r.get('official_source_record_id','')).startswith('ROSSTAT2010:'):bound[r['official_source_record_id']]=r['old_source_record_id']
books={};contexts={};rows=[];mono=s.groupby('source_file').region_norm.apply(lambda x:len(set(x))==1).to_dict()
for (file,sheet,reg),sg in s.groupby(['source_file','source_sheet','region_norm']):
 if not set(sg.source_record_id)&set(h.source_record_id):continue
 path=Path('/workspace/settlements-raw')/file
 if path.suffix.lower()!='.xls':continue
 books.setdefault(str(path),xlrd.open_workbook(path));inputs[str(path)]=sha(path);sh=books[str(path)].sheet_by_name(sheet);tokens={sh.row_values(int(r)-1)[2]for r in sg.source_row};known={county(x)for x in f[f.region_key.eq(reg)].district_raw if pd.notna(x)};current='';anchor=None
 for i in range(sh.nrows):
  vv=sh.row_values(i)
  if not mono[file]and vv[2]not in tokens:continue
  qq=classify(vv);col=min([q['type_col']for q in qq],default=8);actual=[];redundant=[]
  for j,v in enumerate(vv[3:col],3):
   if not isinstance(v,str)or not v.strip():continue
   if classify([v]):redundant.append({'column':j,'literal':v,'role':'typedNPcaption_not_county'});continue
   cc=county(v)
   if cc in known and cc:actual.append({'row':i+1,'column':j,'literal':v,'county_norm':cc})
  if len(set(x['county_norm']for x in actual))==1 and actual:current=actual[0]['county_norm'];anchor=actual[0]
  for q in qq:contexts[(file,sheet,i+1,q['key'])]={'county':current,'anchor':anchor,'redundant_caption_fields':redundant}
for r in h.to_dict('records'):
 x=s[s.source_record_id.eq(r['source_record_id'])].iloc[0];ff=f[f.region_key.eq(x.region_norm)&f.key.map(lambda q:q==x['key'])];full=s[s.region_norm.eq(x.region_norm)&s.key.map(lambda q:q==x['key'])];rivals=[]
 for z in full.to_dict('records'):
  ctx=contexts.get((z['source_file'],z['source_sheet'],int(z['source_row']),z['key']),{});rivals.append({'source_record_id':z['source_record_id'],'actual_printed_county':ctx.get('county',''),'county_anchor':ctx.get('anchor'),'NPcaption_roles':ctx.get('redundant_caption_fields',[])})
 official=[{'reference_id':z['reference_id'],'literal_county':z['district_raw']if pd.notna(z['district_raw'])else '', 'already_bound_to_source_id':bound.get(z['reference_id'],'')}for z in ff.to_dict('records')];free=[z for z in official if not z['already_bound_to_source_id']];status='held_missing_positive_county_or_same_county_rivals'
 if not free:status='official_NP_count_already_exclusively_bound_to_other_source_row'
 elif any(z['literal_county']for z in free):status='held_eligible_unbound_official_county_needs_unique_raw_county_context'
 else:status='held_official_county_blank_with_full_regional_typed_homonyms'
 rows.append({'source_record_id':r['source_record_id'],'region':r['region'],'name':r['name'],'type':r['type'],'original_population':pd.to_numeric(r['population'],errors='coerce'),'status':status,'official_targets_json':json.dumps(official,ensure_ascii=False),'full_actual65_regional_rival_count':len(rivals),'full_actual65_rivals_printed_county_json':json.dumps(rivals,ensure_ascii=False),'new_claim_accepted':False})
d=pd.DataFrame(rows);assert len(d)==430;d.to_csv(E/'audited430_exclusive_official_binding_and_actual_county.csv.gz',index=False);rp={'status':'bounded430_actual_county_reservoir_audit_not_applied','rows':430,'status_counts':d.status.value_counts().to_dict(),'new_accepted_claims':0,'no_reassignment_of_already_exclusively_bound_official_NP_counts':True,'printedcounty_reader_ignores_semantic_NPcaption_fields':True,'input_pins':inputs,'output_sha256':sha(E/'audited430_exclusive_official_binding_and_actual_county.csv.gz')};(E/'audit430_receipt.json').write_text(json.dumps(rp,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in rp.items()if k!='input_pins'},indent=2))

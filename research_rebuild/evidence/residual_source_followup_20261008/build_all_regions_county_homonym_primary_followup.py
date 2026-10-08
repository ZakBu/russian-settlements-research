from pathlib import Path
import pandas as pd,xlrd,re,json,hashlib,collections,subprocess,ast
from pypdf import PdfReader
E=Path(__file__).resolve().parent;B=E.parent/'official_next_region_source_residual_20261008';RAW=Path('/workspace/settlements-raw');S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');REF=Path('/workspace/settlements-work/continuation_20261003/population2010/tom1_table5_extraction/official_2010_table5_reference.parquet');PDF=RAW/'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf';PRIOR=E.parent/'next_overlay_application_20261008/normalized_cumulative_claims.csv.gz';SOURCEPARSER=B/'build_closed_unique_supplement.py';REGIONS=None
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
# Reuse pure exact raw caption/type classifier, without running frozen pack builder.
node=ast.parse(SOURCEPARSER.read_text());chosen=[]
for n in node.body:
 if isinstance(n,ast.FunctionDef)and n.name in {'norm','key','classify'}:chosen.append(n)
 if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id in {'T','pat'}for t in n.targets):chosen.append(n)
ns={'re':re};exec(compile(ast.Module(body=chosen,type_ignores=[]),str(SOURCEPARSER),'exec'),ns);norm,key,classify=[ns[k]for k in ['norm','key','classify']]
def county(v):return re.sub(r'\b(муниципальный|район|городской|округ|р н)\b','',norm(v)).strip()
s=pd.read_parquet(S);s=s[s.census_year==2010].copy();s['key']=s.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);sd=s.set_index('source_record_id');f=pd.read_parquet(REF);f=f[f.row_kind=='settlement'].copy();f['key']=f.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);f['county']=f.district_raw.map(lambda v:county(v)if pd.notna(v)else '');prior=pd.read_csv(PRIOR,keep_default_na=False);used=set(prior.old_source_record_id)|set(pd.read_csv(E/'accepted_county_bound_primary2010_addon_8.csv.gz').old_source_record_id);REGIONS=set(s.region_raw);sources={};rawkeys={};rowctx={};pins={str(p):sha(p)for p in [S,REF,PDF,PRIOR,SOURCEPARSER]};allwitnesses=[];ready=[];holds=[];newbooks={}
for reg in sorted(REGIONS):
 sg=s[s.region_raw==reg];ff=f[f.region_key==reg];officialcount=collections.Counter((r.key,r.county)for r in ff.itertuples());knowncounty={q for q in ff.county if q};refglobal=collections.Counter(ff.key)
 # Full original selected/raw regional competitors, including small and zero-valued NP rows.
 for file,fg in sg.groupby('source_file'):
  path=RAW/file
  if not path.suffix.lower()=='.xls':continue
  if str(path)not in newbooks:newbooks[str(path)]=xlrd.open_workbook(str(path));pins[str(path)]=sha(path)
  book=newbooks[str(path)]
  for shname,hg in fg.groupby('source_sheet'):
   sh=book.sheet_by_name(shname);tokenrows=collections.Counter()
   for rr in hg.itertuples():
    vv=sh.row_values(int(rr.source_row)-1)
    if len(vv)>2 and isinstance(vv[2],str):tokenrows[vv[2]]+=1
   tokens=set(tokenrows);mono=len(set(s[s.source_file==file].region_raw))==1;current='';anchor=None;seq=[]
   for i in range(sh.nrows):
    vv=sh.row_values(i)
    if len(vv)<=2 or (not mono and vv[2]not in tokens):continue
    labels=classify(vv);col=min([q['type_col']for q in labels],default=8)
    county_cells=[]
    for j,v in enumerate(vv[3:col],start=3):
     if isinstance(v,str)and v.strip():
      cc=county(v)
      if cc in knowncounty:county_cells.append((j,v,cc))
    if len(set(cc for _,_,cc in county_cells))==1 and county_cells:
     current=county_cells[0][2];anchor=dict(source_row=i+1,source_cell_column_zero_based=county_cells[0][0],literal_county_caption=county_cells[0][1],normalized_county=current,raw_cells=vv[:12])
    for q in labels:
     seq.append(dict(row=i+1,key=q['key'],classifier=q,county=current,county_anchor=anchor))
   sources[(reg,file,shname)]=seq
   counts=collections.Counter((q['key'],q['county'])for q in seq);rawkeys[(reg,file,shname)]=counts
   for q in seq:rowctx[(reg,file,shname,q['row'],q['key'])]=q
 # Iterate each exact official type/name key, permit homonyms only under a positive literal county.
 for p in ff.to_dict('records'):
  hit=sg[sg.key.eq(p['key'])] if False else sg[sg.key.map(lambda k:k==p['key'])]
  remain=hit[~hit.source_record_id.isin(used)&hit.population_value_quality.fillna('').str.startswith('secondary_confidentiality')]
  if remain.empty:continue
  pos=[];rivals=[]
  for r in hit.to_dict('records'):
   q=rowctx.get((reg,r['source_file'],r['source_sheet'],int(r['source_row']),r['key']))
   rivals.append(dict(source_record_id=r['source_record_id'],source_row=int(r['source_row']),name=r['settlement_name'],type=r['settlement_type'],raw_literal_county=q['county']if q else '',actual_county_anchor=q['county_anchor']if q else None,population=int(r['population'])if pd.notna(r['population'])else None))
   if q and p['county'] and q['county']==p['county']:pos.append((r,q))
  if len(pos)!=1 or officialcount[(p['key'],p['county'])]!=1:
   holds.append(dict(official_source_record_id=p['reference_id'],region=reg,official_name=p['settlement_name'],official_type=p['settlement_type'],official_district=p['district_raw'],official_population=int(p['population']),regional_selected_typed_competitors=len(hit),positive_county_candidate_count=len(pos),reason='actual_printed_county_not_unique_or_unavailable',rival_source_records=json.dumps(rivals,ensure_ascii=False)));continue
  r,q=pos[0]
  if r['source_record_id']in used or r['source_record_id']not in set(remain.source_record_id):continue
  if rawkeys[(reg,r['source_file'],r['source_sheet'])][(q['key'],q['county'])]!=1:
   holds.append(dict(official_source_record_id=p['reference_id'],region=reg,official_name=p['settlement_name'],reason='full_raw_county_typed_competition'));continue
  # All name rivals need an actual raw county anchor to exclude an unbound competitor.
  if any(not x['actual_county_anchor']for x in rivals):
   holds.append(dict(official_source_record_id=p['reference_id'],region=reg,official_name=p['settlement_name'],reason='one_or_more_full_regional_selected_rivals_lack_actual_county_context',rival_source_records=json.dumps(rivals,ensure_ascii=False)));continue
  sh=newbooks[str(RAW/r['source_file'])].sheet_by_name(r['source_sheet']);vals=sh.row_values(int(r['source_row'])-1);popcols=[j for j in range(q['classifier']['name_col']+1,min(12,len(vals)))if isinstance(vals[j],(int,float))and float(vals[j])==float(r['population'])];assert popcols
  ready.append(dict(old_source_record_id=r['source_record_id'],region=reg,old_population=int(r['population']),old_quality=r['population_value_quality'],old_source_file=r['source_file'],old_source_sheet=r['source_sheet'],old_source_row=int(r['source_row']),raw_old_NP_caption=q['classifier']['caption'],raw_type_cell_or_prefix=q['classifier']['type_raw'],raw_name_cell_or_caption=q['classifier']['name_raw'],raw_population_cell_column_zero_based=popcols[0],raw_population_cell=vals[popcols[0]],old_source_sha256=pins[str(RAW/r['source_file'])],actual_printed_county_cells_json=json.dumps([q['county_anchor']],ensure_ascii=False),official_source_record_id=p['reference_id'],official_population=int(p['population']),official_men=int(p['men']),official_women=int(p['women']),official_name=p['settlement_name'],official_type=p['settlement_type'],official_district=p['district_raw'],official_source_path=str(PDF),official_source_sha256=pins[str(PDF)],official_page=int(p['pdf_page']),official_line_start=int(p['text_line_start']),official_line_end=int(p['text_line_end']),delta=int(p['population'])-int(r['population']),status='ready_exact_same2010_typed_NP_positive_literal_county_with_all_rivals_bound',context_method='printed_county_header_carry_forward_full_regional_typed_rivals_actual_county_bound_full_raw_county_key_unique',selected_full_region_competitors=len(hit),raw_full_county_NP_competitors=rawkeys[(reg,r['source_file'],r['source_sheet'])][(q['key'],q['county'])],official_full_region_typed_competitors=refglobal[p['key']],official_full_county_typed_competitors=officialcount[(p['key'],p['county'])],regional_rivals_json=json.dumps(rivals,ensure_ascii=False),population_used_for_binding_context=False,selection_applied=False))
  allwitnesses.append(dict(old_source_record_id=r['source_record_id'],raw_cells=vals[:12],county_anchor=q['county_anchor'],full_selected_rivals=rivals))
# Independent primary PDF count triples and locator text, before ready claims are frozen.
reader=PdfReader(str(PDF));poppler=subprocess.check_output(['pdftotext','-layout',str(PDF),'-']).decode().split('\f');final=[]
for r in ready:
 page=r['official_page'];nums=[str(r[c])for c in ['official_population','official_men','official_women']];lines=poppler[page-1].splitlines();hits=[]
 for i,line in enumerate(lines):
  n=re.findall(r'\d+',line)
  if any(n[j:j+3]==nums for j in range(len(n)-2))and norm(r['official_name'])in norm(' '.join(lines[max(0,i-2):i+1])):hits.append(' | '.join(lines[max(0,i-2):i+1]))
 if not hits or r['official_population']!=r['official_men']+r['official_women']:
  holds.append(dict(official_source_record_id=r['official_source_record_id'],region=r['region'],official_name=r['official_name'],reason='independent_official_count_readback'));continue
 r['independent_poppler_lines']=hits[0];pp=reader.pages[page-1].extract_text().splitlines();r['independent_pypdf_lines']=' | '.join(pp[r['official_line_start']-1:r['official_line_end']]);r['independent_count_readback']=True;final.append(r)
d=pd.DataFrame(final);assert d.old_source_record_id.is_unique and not set(d.old_source_record_id)&used
d.to_csv(E/'all_regions_county_bound_homonym_primary2010_candidates.csv.gz',index=False);pd.DataFrame(holds).to_csv(E/'all_regions_county_bound_homonym_holds.csv',index=False);(E/'all_regions_county_bound_literal_raw_witnesses.json').write_text(json.dumps(allwitnesses,ensure_ascii=False,indent=2));d.groupby('region').agg(rows=('old_source_record_id','size'),delta=('delta','sum')).to_csv(E/'all_regions_county_bound_primary_by_region.csv')
r=dict(status='new_immutable_source_population_candidate_addon_not_applied',regions_scanned=sorted(REGIONS),ready_claims=len(d),population_delta=int(d.delta.sum()),hold_records=len(holds),source_grade='direct_official_primary_2010_census_Table5',census_date='2010-10-14',publication_date_unknown=True,disjoint_prior1783=True,new_identity_nodes=0,new_points=0,primary_replacement_binding_not_temporal_identity=True,county_rule='Actual raw printed county header; all regional exact typed-name rivals independently county-bound; full raw county+typedname uniqueness and official county+typedname uniqueness. No population comparison used to bind.',input_pins=pins,output_pins={p.name:sha(p)for p in E.glob('all_regions_county_bound_*')if p.is_file()});(E/'all_regions_county_bound_primary_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(d[['region','official_name','old_population','official_population','delta']].to_string(index=False));print(json.dumps({k:r[k]for k in ['ready_claims','population_delta','hold_records']},indent=2))

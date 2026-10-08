from pathlib import Path
import sys,json,re,bisect,collections,gzip
import pandas as pd,duckdb,xlrd
from bs4 import BeautifulSoup
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(38);f=pd.read_csv(O/'all_regional2010_native_candidates.csv.gz',keep_default_na=False);inventory=pd.read_csv(O/'all_missing2010_components.csv.gz',keep_default_na=False);SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');c=duckdb.connect(config={'threads':1,'memory_limit':'500MB'});meta=c.execute('select source_record_id,source_sheet,source_row,source_name_raw from read_parquet(?)where census_year=2010',[str(SEL)]).fetchdf().set_index('source_record_id').to_dict('index');by=s.by_id;books={};headers={};hashes={};literalchecks={};contextproof={};resolved={};rawpins={};competing=[];holds=[];candidates=[]
def county(v):
 text=normalize(v);text=re.sub(r'(?<=район)\s*[-–—:]\s*(?:все сельское население|всего|все население).*$','',text);text=re.sub(r'(?<=р-н)\s*[-–—:]\s*(?:все сельское население|всего|все население).*$','',text);text=re.sub(r'(?<=улус)\s*[-–—:]\s*(?:все сельское население|всего|все население).*$','',text)
 if re.search(r'\bсс\b|сельсовет|сельск(?:ий|ое) (?:совет|поселение)|с[.]\s*а[.]',text):return ''
 return county_key(text)
def typeclass(v):
 t=normalize(v)
 return 'unknown' if t in ['','объект'] else 'urban' if t in ['город','пгт','рп','поселок городского типа','рабочий поселок','дачный поселок','курортный поселок'] else 'rural'
HTML=Path('/workspace/settlements-work/sources/r2-missing/arkhangelsk_2010_archived_original.html');rawpins[str(HTML)]=sha(HTML);soup=BeautifulSoup(HTML.read_bytes(),'html.parser');trs=soup.table.find_all('tr');htmlrows={};hd='';hr=0
for num,tr in enumerate(trs):
 cells=[' '.join(td.get_text(' ',strip=True).split()) for td in tr.find_all(['td','th'])];label=cells[0] if cells else '';text=' '.join(cells)
 if re.search(r'муниципальный\s+район|городской\s+округ',normalize(label)) and not re.match(r'^(?:село|деревня|поселок|хутор)\b',normalize(label)):hd=label;hr=num+1
 htmlrows[num]={'label':label,'cells':cells,'county':county(hd),'parent_label':hd,'parent_row':hr,'source_row_1based':num+1,'text':text}
PDF=Path('/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf');pdflayout=Path('/workspace/settlements-work/native_missing2010_all_components_20261008/tom1_layout.txt');pages=pdflayout.read_text().split('\f');rawpins[str(PDF)]=sha(PDF);rawpins[str(pdflayout)]=sha(pdflayout)
def literal(sid):
 if sid in literalchecks:return literalchecks[sid]['literal_pass']
 a=by.loc[sid];m=meta[sid];kind='';label='';rawpop=[];loc='';path=None;okay=False
 if sid.startswith('ARK2010:'):
  num=int(re.search(r'tr(\d+)$',sid).group(1));h=htmlrows[num];label=h['label'];rawpop=[v for v in h['cells'][1:] if re.fullmatch(r'[0-9 ]+',v)];okay=normalize(label)==normalize(m['source_name_raw']) and any(int(v.replace(' ',''))==a.population for v in rawpop);kind='original_archive_HTML_own_NP_leaf';path=HTML;loc=f'table1;tr_zero_based={num};row1based={num+1}';resolved[sid]=h['county'];contextproof[sid]={'rule':'original_HTML_explicit_upper_municipal_parent','parent_label':h['parent_label'],'parent_row_1based':h['parent_row']}
 elif sid.startswith('ROSSTAT2010:T5:'):
  locator=json.loads(a.source_locator);page=int(locator['pdf_page_1based']);lo=int(locator['text_line_start_1based']);hi=int(locator['text_line_end_1based']);lines=pages[page-1].splitlines();label=locator['raw_label'];matches=[(i+1,line) for i,line in enumerate(lines) if normalize(label) in normalize(line)];text=matches[0][1] if len(matches)==1 else '';nums=re.findall(r'(?<!\d)\d+(?!\d)',text);okay=normalize(label) in normalize(text) and str(int(a.population)) in nums;rawpop=nums;kind='published_table5_standalone_urban_or_native_NP_leaf';path=PDF;loc=str(a.source_locator);dc=locator.get('raw_district','');
  if county(dc):resolved[sid]=county(dc);contextproof[sid]={'rule':'printed_primary_table5_parent','parent_label':dc}
 elif str(a.source_file).endswith('.xls'):
  path=Path('/workspace/settlements-raw')/a.source_file
  if path not in books:books[path]=xlrd.open_workbook(str(path),on_demand=True);hashes[path]=sha(path);rawpins[str(path)]=hashes[path]
  sh=books[path].sheet_by_name(str(m['source_sheet']));row=int(m['source_row']);values=sh.row_values(row-1);labels=[str(v) for v in values if isinstance(v,str) and normalize(v)==normalize(m['source_name_raw'])];label=labels[0] if labels else '';rawpop=[v for v in values if (isinstance(v,(int,float)) and v==a.population) or (isinstance(v,str) and re.fullmatch('[0-9]+',v.strip()) and int(v.strip())==a.population)];okay=len(labels)==1 and bool(rawpop);kind='original_secondary_XLS_own_NP_leaf';loc=f'sheet={sh.name};row1based={row}'
  # Actual district headers alone; сельсовет/admin captions do not override upper district.
  key=(path,sh.name)
  if key not in headers:
   found=[]
   for num in range(sh.nrows):
    heads=[str(v) for v in sh.row_values(num) if isinstance(v,str) and re.search(r'\bрайон\b|\bр-н\b|\bулус\b',normalize(v)) and not re.match(r'^\s*(?:село|деревня|поселок|хутор|станция|разъезд)\b',normalize(v))]
    if heads:found.append((num+1,heads[0],county(heads[0])))
   headers[key]=found
  found=headers[key];positions=[x[0] for x in found];ix=bisect.bisect_left(positions,row)-1
  if ix>=0 and found[ix][2] and row-found[ix][0]<=20:
   num,labelparent,dc=found[ix];resolved[sid]=dc;contextproof[sid]={'rule':'original_XLS_explicit_upper_district_header','parent_label':labelparent,'parent_row_1based':num}
 literalchecks[sid]={'source_record_id':sid,'raw_source_file':str(path) if path else '', 'raw_source_sha256':rawpins.get(str(path),hashes.get(path,'')),'raw_source_locator':loc,'raw_own_label':label,'selected_population_unmodified':a.population,'printed_population_witness':json.dumps(rawpop),'literal_pass':bool(okay),'raw_source_kind':kind};return okay
# All competitors receive available actual source county or historical accepted-neighbor brackets.
targets=set(f.target2010_source_record_id);obs=s.obs[s.obs.census_year.eq(2010)].copy();groups={key:g for key,g in obs.assign(sheet=obs.source_record_id.map(lambda sid:meta[sid]['source_sheet']),row=obs.source_record_id.map(lambda sid:meta[sid]['source_row'])).groupby(['source_file','sheet','region_norm'],dropna=False)};rootold={s.uf.find(a.source_record_id):county(a.district_raw) for a in s.obs[s.obs.census_year.eq(2002)].itertuples()};rootcur={s.uf.find(a.source_record_id):county(a.district_raw) for a in s.obs[s.obs.census_year.eq(2021)].itertuples()}
for sid in targets:
 a=by.loc[sid];dc=county(a.district_raw)
 if dc:resolved[sid]=dc;contextproof[sid]={'rule':'selected_printed2010_county','raw_parent':a.district_raw}
 if str(a.source_file).endswith('.xls') or sid.startswith(('ARK2010:','ROSSTAT2010:')):literal(sid)
# Certify a real district-header interval only when ALL accepted native anchors agree.
for key,g in groups.items():
 path=Path('/workspace/settlements-raw')/str(key[0]);h=headers.get((path,key[1]),[])
 if len(h)<2:continue
 positions=[x[0] for x in h];ag=[]
 for v in g.to_dict('records'):
  root=s.uf.find(v['source_record_id']);dc=rootold.get(root) or rootcur.get(root)
  if dc and s.years[root]!={2010} and pd.notna(v['row']) and v['is_additive_settlement_record']:ag.append((int(v['row']),v['source_record_id'],dc))
 for sid in set(g.source_record_id)&targets:
  if sid in resolved:continue
  row=int(meta[sid]['source_row']);ix=bisect.bisect_left(positions,row)-1
  if ix<0 or ix+1>=len(h):continue
  lower,upper=h[ix],h[ix+1];aa=[a for a in ag if lower[0]<a[0]<upper[0]]
  if not lower[2] or len(aa)<3 or any(a[2]!=lower[2] for a in aa):continue
  chosen=[aa[0],aa[len(aa)//2],aa[-1]]
  if len({a[1] for a in chosen})<3 or not all(literal(a[1]) for a in chosen):continue
  resolved[sid]=lower[2];contextproof[sid]={'rule':'literal_header_interval_certified_by_all_accepted_native2010_anchors','parent_label':lower[1],'parent_row_1based':lower[0],'next_parent_label':upper[1],'next_parent_row_1based':upper[0],'all_interval_anchors_count':len(aa),'all_interval_anchor_counties_agree':True,'raw_anchor_ids':[a[1] for a in chosen]}
# Dedicated printed county columns: preserve source blocks, never free-text inheritance.
for key,g in groups.items():
 if not str(key[0]).endswith('.xls') or not (set(g.source_record_id)&targets):continue
 path=Path('/workspace/settlements-raw')/str(key[0]);book=books.get(path)
 if book is None:book=xlrd.open_workbook(str(path),on_demand=True);books[path]=book;rawpins[str(path)]=sha(path)
 sh=book.sheet_by_name(str(key[1]));countycols=[(i,j,str(sh.cell_value(i,j))) for i in range(min(8,sh.nrows)) for j in range(min(6,sh.ncols)) if normalize(str(sh.cell_value(i,j))) in {'район','р н','р-н'}]
 if not countycols:continue
 hi,col,caption=countycols[0];regioncol=max(1,col-1);blocks=[];current=None;lastregion=''
 for i in range(hi+1,sh.nrows):
  rr=sh.row_values(i);rv=normalize(str(rr[regioncol])) if isinstance(rr[regioncol],str) else '';cv=str(rr[col]).strip() if isinstance(rr[col],str) else '';ck=county(cv);validcounty=bool(ck) and cv not in ['–','--','-'] and not re.match(r'^(?:село|деревня|поселок|хутор|станция)\b',normalize(cv));reset=rv not in ['','–','--','-'] and lastregion and rv!=lastregion
  if reset or validcounty:
   if current:current['end']=i+1;blocks.append(current);current=None
   if validcounty:current={'start':i+1,'end':sh.nrows+1,'raw_county':cv,'county':ck,'region_caption':rv or lastregion}
  if rv not in ['','–','--','-']:lastregion=rv
 if current:blocks.append(current)
 anchors=[]
 for v in g.to_dict('records'):
  root=s.uf.find(v['source_record_id']);contexts={rootold.get(root),rootcur.get(root)}-{None,''}
  if contexts and s.years[root]!={2010} and pd.notna(v['row']) and v['is_additive_settlement_record']:anchors.append((int(v['row']),v['source_record_id'],contexts))
 for b in blocks:
  aa=[a for a in anchors if b['start']<=a[0]<b['end']];certified=len(aa)>=2 and all(b['county'] in a[2] for a in aa)
  for sid in set(g.source_record_id)&targets:
   row=int(meta[sid]['source_row'])
   if not b['start']<=row<b['end']:continue
   owncell=sh.cell_value(row-1,col);direct=isinstance(owncell,str) and county(owncell)==b['county']
   if not direct and not certified:continue
   chosen=[aa[0],aa[-1]] if certified else []
   if chosen and not all(literal(a[1]) for a in chosen):continue
   if sid in resolved and resolved[sid]!=b['county']:continue
   resolved[sid]=b['county'];contextproof[sid]={'rule':'dedicated_printed_county_column_bounded_block','county_column_1based':col+1,'column_header_raw':caption,'column_header_row1based':hi+1,'parent_label':b['raw_county'],'parent_row1based':b['start'],'next_block_row1based':b['end'],'own_row_county_cell_is_explicit':direct,'all_block_accepted_anchor_counties_agree':certified,'all_block_accepted_anchor_count':len(aa),'raw_anchor_ids':[a[1] for a in chosen]}
# Retain already source-verified county contexts when a sparse flat XLS has no nearby real parent.
for sid,g in f.groupby('target2010_source_record_id'):
 if sid in resolved:continue
 cached=county(g.native2010_county_context.iloc[0])
 if cached:
  resolved[sid]=cached;contextproof[sid]={'rule':'previous_frozen_native2010_county_context','original_context_proof':g.context_proof_json.iloc[0]}
for key,g in groups.items():
 tg=[sid for sid in g.source_record_id if sid in targets and sid not in resolved]
 if not tg or not str(key[0]).endswith('.xls'):continue
 anchors=[]
 for a in g.to_dict('records'):
  root=s.uf.find(a['source_record_id']);dc=rootold.get(root) or rootcur.get(root)
  if dc and s.years[root]!={2010} and pd.notna(a['row']) and a['is_additive_settlement_record']:anchors.append((int(a['row']),a['source_record_id'],dc))
 anchors.sort();nums=[a[0] for a in anchors]
 for sid in tg:
  row=int(meta[sid]['source_row']);lo=bisect.bisect_left(nums,row)-1;hi=bisect.bisect_right(nums,row)
  if lo<0 or hi>=len(anchors):continue
  lower,upper=anchors[lo],anchors[hi]
  if lower[2]!=upper[2] or row-lower[0]>20 or upper[0]-row>20 or normalize(by.loc[lower[1],'settlement_name'])==normalize(by.loc[upper[1],'settlement_name']):continue
  if not all(literal(x) for x in [sid,lower[1],upper[1]]):continue
  # Genuine contradictory printed upper headers remain a hold.
  contradictions=[x for x in [resolved.get(lower[1]),resolved.get(upper[1])] if x and x!=lower[2]]
  if contradictions:continue
  resolved[sid]=lower[2];contextproof[sid]={'rule':'two_sided_accepted_native2010_neighbors_historical_or_current_county','lower_source_id':lower[1],'upper_source_id':upper[1],'lower_row':lower[0],'target_row':row,'upper_row':upper[0]}
# All same-name region competitors are partitioned by actual NP type and independently resolved source county BEFORE graph eligibility.
for cid,g in f.groupby('current2021_source_record_id',sort=False):
 cur=by.loc[cid];oldid=g.old2002_source_record_id.iloc[0];old=by.loc[oldid];acceptedclasses={typeclass(cur.type_norm),typeclass(old.type_norm)}-{'unknown'};allrows=g.drop_duplicates('target2010_source_record_id').to_dict('records');typed=[z for z in allrows if typeclass(by.loc[z['target2010_source_record_id'],'type_norm']) in acceptedclasses];counties={county(cur.district_raw),county(old.district_raw)}-{''};eligible=[]
 for z in typed:
  sid=z['target2010_source_record_id'];dc=resolved.get(sid,'');a=by.loc[sid];positivecounty=bool(dc) and dc in counties;urbanunique=typeclass(a.type_norm)=='urban' and typeclass(old.type_norm)=='urban' and sum(typeclass(by.loc[v['target2010_source_record_id'],'type_norm'])=='urban' for v in allrows)==1 and sid.startswith('ROSSTAT2010:T5:');regionalunique=len(typed)==1;countyothers=[v for v in typed if v['target2010_source_record_id']!=sid and (not resolved.get(v['target2010_source_record_id']) or resolved[v['target2010_source_record_id']]==dc)];countyunique=positivecounty and not countyothers;owncode=bool(z['native_own_code_agreement']);ratiookay=bool(z['adjacent_population_ratio_0_5_to2_or_actual_zero']);sp=s.point_rows.get(sid);cp=s.point_rows[cid];pointokay=float(z['historical_current_point_distance_km'])<=5 and (sp is None or distance_km((sp['latitude'],sp['longitude']),(cp['latitude'],cp['longitude']))<=5);graphokay=not ({2002,2021}&s.years[s.uf.find(sid)]);identity=(countyunique or (regionalunique and (positivecounty or owncode)) or urbanunique) and pointokay and a.is_additive_settlement_record and graphokay and (ratiookay or owncode or urbanunique or (countyunique and contextproof.get(sid,{}).get('rule') in {'dedicated_printed_county_column_bounded_block','original_HTML_explicit_upper_municipal_parent','selected_printed2010_county','original_XLS_explicit_upper_district_header','literal_header_interval_certified_by_all_accepted_native2010_anchors','two_sided_accepted_native2010_neighbors_historical_or_current_county'})) and literalchecks.get(sid,{}).get('literal_pass',False)
  competing.append({**z,'native2010_resolved_county':dc,'source_county_proof_json':json.dumps(contextproof.get(sid,{}),ensure_ascii=False),'same_physical_type_region_competitors':len(typed),'same_or_unresolved_type_county_rivals':len(countyothers),'typed_primary_urban_regionunique':urbanunique,'identity_source_positive_candidate':bool(identity),'growth_flag_only_if_strong_owncode_or_standaloneurban':not ratiookay})
  if identity:eligible.append({**z,'native2010_resolved_county':dc,'source_county_proof_json':json.dumps(contextproof.get(sid,{}),ensure_ascii=False),'typed_primary_urban_regionunique':urbanunique,'same_physical_type_region_competitors':len(typed),'same_or_unresolved_type_county_rivals':len(countyothers),'growth_flag':not ratiookay})
 if len(eligible)==1:candidates.extend(eligible)
 else:holds.append({'current2021_source_record_id':cid,'name':cur.settlement_name,'region':cur.region_norm,'eligible_source_positive_targets':len(eligible),'all2010_name_options':len(allrows),'same_type_options':len(typed),'reason':'multiple_positive_targets' if len(eligible)>1 else 'raw_source_county_competitor_ratio_or_graph_hold'})
pd.DataFrame(candidates).to_csv(O/'refined_native2010_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(competing).to_csv(O/'refined_all_competitor_witness.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(literalchecks.values()).to_csv(O/'all_literal_native2010_source_checks.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(holds).to_csv(O/'refined_component_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'stage':38,'candidate_count':len(candidates),'candidate_population2002':int(sum(x['old2002_population'] for x in candidates)),'candidate_population2010':int(sum(x['native2010_population'] for x in candidates)),'candidate_population2021':int(sum(x['current2021_population'] for x in candidates)),'all_native2010_literal_checks':len(literalchecks),'explicit_OR_bracketed_county_resolutions':len(resolved),'input_raw_pins':rawpins,'candidate_only_until_actual38_replay':True};(O/'refined_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='input_raw_pins'},ensure_ascii=False))

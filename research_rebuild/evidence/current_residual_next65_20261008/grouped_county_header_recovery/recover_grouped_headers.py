from pathlib import Path
import pandas as pd,duckdb,xlrd,ast,json,re,unicodedata,sys,collections,time,resource,bisect
START=time.monotonic();O=Path(__file__).parent;E=O.parent.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize
RULE=E/'current_cached_ownarticle_residual_expansion_20261008/review_articles.py';tree=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
F=O/'priority_current_singleton_carriers_actual66.csv.gz';H=O/'native_historic_source_observations_scoped.parquet';RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');RES=E/'temporal_published_code_alias_mass_20261008/candidate_identity_pairs.csv.gz';reserved=pd.read_csv(RES,dtype=str,keep_default_na=False);reserved=set(reserved.from_source_record_id)|set(reserved.to_source_record_id);f=pd.read_csv(F,dtype=str,keep_default_na=False);f=f[~f.source_record_id.isin(reserved)];targets=collections.defaultdict(list)
for z in f.to_dict('records'):targets[(namekey(z['settlement_name']),regionkey(z['region_norm']))].append(z)
c=duckdb.connect();c.execute("SET memory_limit='192MB'");cur=c.execute("select row_number() over() rn,object_level,object_name,region,mun_upper,mun_lower,oktmo from read_parquet(?)",[str(RAW)]);cols=[x[0] for x in cur.description];modern=collections.defaultdict(list);targetnative={}
while True:
 bs=cur.fetchmany(5000)
 if not bs:break
 for tup in bs:
  n=dict(zip(cols,tup))
  if n['object_level']!='Населенный пункт':continue
  name,typ=splitname(n['object_name']);nr=(namekey(name),regionkey(n['region']))
  if nr in targets:modern[(nr[0],nr[1],county(n['mun_upper']))].append(n);targetnative[int(n['rn'])]=n
c.close();hist=pd.read_parquet(H);groups=collections.defaultdict(list)
for tup in hist.itertuples(index=False,name=None):
 q=dict(zip(hist.columns,tup));nr=(namekey(q['settlement_name']),regionkey(q['region_norm']))
 if nr not in targets:continue
 sf=str(q['source_file'] or '');p=Path('/workspace/settlements-raw')/sf;parts=str(q['source_record_id']).split(':');
 if not p.is_file() or p.suffix.lower()!='.xls' or not parts[-1].isdigit():continue
 if int(q['census_year'])==2002 and p.name=='1_TOM_01_04.xls':continue
 groups[p].append(q)
del hist
PREFIX={'с':'село','д':'деревня','п':'поселок','х':'хутор','ст-ца':'станица','нп':'населенный пункт','пгт':'пгт','рп':'рабочий поселок'}
def physical(s):
 ma=re.match(r'^\s*(с|д|п|х|ст-ца|н\.?п|пгт|рп)\.\s*(.+)$',str(s),re.I)
 if ma:return ma.group(2),PREFIX[ma.group(1).lower().replace('.','')]
 s=str(s).strip();types=['железнодорожная станция','железнодорожный разъезд','поселок при станции','посёлок при станции','населенный пункт','населённый пункт','рабочий поселок','рабочий посёлок','поселок','посёлок','деревня','село','город','хутор','станица','слобода','местечко','аул','арбан','пгт','станция','разъезд']
 for typ in types:
  if s.lower().startswith(typ+' '):return s[len(typ):].strip(),typ
 return '', ''
rows=[];holds=[];pins={};books=0
for p,qs in sorted(groups.items(),key=lambda item:-max(float(q['population']) if pd.notnull(q['population']) else 0 for q in item[1])):
 pins[str(p)]=sha(p);b=xlrd.open_workbook(str(p),on_demand=True);books+=1;bysh=collections.defaultdict(list)
 for q in qs:bysh[str(q['source_record_id']).split(':')[-2]].append(q)
 for sn,ss in bysh.items():
  try:s=b.sheet_by_name(sn)
  except xlrd.biffh.XLRDError:
   if sn.isdigit() and int(sn)<b.nsheets:s=b.sheet_by_index(int(sn))
   else:continue
  yr=int(ss[0]['census_year']);headers=[];regionstarts=[];parishes=[];scores={k:sum(bool(physical(s.cell_value(i,k))[0]) for i in range(min(s.nrows,500))) for k in range(min(s.ncols,5))};namecol=max(scores,key=scores.get);popcol=namecol+1
  if not scores[namecol]:continue
  if yr==2010 and namecol!=4:
   for q in ss:holds.append({**q,'historical_raw_origin_file':str(p),'historical_raw_origin_sha256':pins[str(p)],'raw_source_validation_holds':'table_namecolumn'+str(namecol+1)+'_county_column_not_independently_identified_no_blindcarry','NULL_population_scope_not_exclusion':True})
   continue
  if yr==2010:
   if s.ncols<6:continue
   for i in range(s.nrows):
    reg=str(s.cell_value(i,2)).strip();co=str(s.cell_value(i,3)).strip()
    if reg and (not regionstarts or reg!=regionstarts[-1][1]):regionstarts.append((i+1,reg))
    if co:headers.append((i+1,co,reg))
  else:
   for i in range(s.nrows):
    text=str(s.cell_value(i,namecol));low=bare(text)
    if re.search(r'\b(?:район|кожуун|улус)\b',low) and not physical(text)[0]:headers.append((i+1,text.strip(),''))
    if re.search(r'\b(?:сельсовет|сельский совет|сумон|сельское поселение|сельская администрация)\b',low) and not physical(text)[0]:parishes.append((i+1,text.strip()))
  hnums=[x[0] for x in headers];pnums=[x[0] for x in parishes];rnums=[x[0] for x in regionstarts]
  for q in ss:
   rn=int(str(q['source_record_id']).split(':')[-1]);nr=(namekey(q['settlement_name']),regionkey(q['region_norm']));ix=bisect.bisect_right(hnums,rn)-1;reason=[]
   if rn<1 or rn>s.nrows:continue
   raw=s.row_values(rn-1)[:6];label=raw[namecol];nm,tp=physical(label)
   if not nm or namekey(nm)!=nr[0] or typekey(tp)!=typekey(q['settlement_type']):reason.append('literal_raw_physical_NP_name_or_type_not_equal_native_observation')
   if ix<0:reason.append('no_positive_printed_county_header_before_target');co='';begin=None;end=None;header=[];nextheader=[]
   else:
    begin,co,reg=headers[ix];co=re.split(r'\s+-\s+|\s+—\s+',co,1)[0].strip();header=s.row_values(begin-1)[:6];end=headers[ix+1][0] if ix+1<len(headers) else s.nrows+1;nextheader=s.row_values(end-1)[:6] if end<=s.nrows else []
    if yr==2010:
     ri=bisect.bisect_right(rnums,rn)-1;rstart,rlabel=regionstarts[ri] if ri>=0 else (None,'');rend=regionstarts[ri+1][0] if ri+1<len(regionstarts) else s.nrows+1;rh=[h for h in headers if rstart and rstart<=h[0]<rend]
     if len(rh)<2:reason.append('region_has_only_one_county_header_unbounded_blank_county_scope_not_positive')
     if begin<rstart or end>rend:reason.append('no_next_printed_county_boundary_in_same_region')
     rawreg=str(raw[2]);
     if regionkey(rawreg)!=nr[1]:reason.append('literal_raw_region_label_requires_documented_alias_not_in_closed_rule')
   try:rp=float(raw[popcol]);equalpop=pd.notnull(q['population']) and rp==float(q['population'])
   except (ValueError,TypeError):equalpop=False
   if pd.notnull(q['population']) and not equalpop:reason.append('literal_population_field_not_equal_native_observation')
   parish='';parishrow=None;pi=bisect.bisect_right(pnums,rn)-1
   if pi>=0 and begin and parishes[pi][0]>begin:parishrow,parish=parishes[pi]
   ev={**q,'historical_raw_origin_file':str(p),'historical_raw_origin_sha256':pins[str(p)],'historical_raw_origin_locator':f'{s.name}:row:{rn}:physicalNPcol{namecol+1}:populationcol{popcol+1}', 'historical_raw_row_fields_first6_json':json.dumps(raw,ensure_ascii=False),'literal_physical_NP_type':tp,'literal_physical_NP_name':nm,'historical_raw_county_header_literal':co,'historical_raw_county_header_row':begin,'historical_raw_county_scope_end_exclusive_row':end,'historical_raw_county_header_row_first6_json':json.dumps(header,ensure_ascii=False),'historical_raw_next_county_header_row_first6_json':json.dumps(nextheader,ensure_ascii=False),'historical_raw_specific_parish_header_literal':parish,'historical_raw_specific_parish_header_row':parishrow,'raw_source_validation_holds':';'.join(reason),'NULL_population_scope_not_exclusion':True}
   if not reason:rows.append(ev)
   else:holds.append(ev)
 b.release_resources();del b
 print('book',books,'/',len(groups),'positive',len(rows),'held',len(holds),p.name,flush=True)
for fn,zs in [('raw_scope_positive_historic_observations',rows),('raw_scope_recovery_holds',holds)]:pd.DataFrame(zs).to_csv(O/(fn+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
# All candidate native historical names within a positively printed county are retained, regardless historical subtype, when checking uniqueness.
hi=collections.defaultdict(list)
for q in rows:hi[(int(q['census_year']),namekey(q['settlement_name']),regionkey(q['region_norm']),county(q['historical_raw_county_header_literal']))].append(q)
proposals=[];pairholds=[]
for z in f.to_dict('records'):
 sid=z['source_record_id'];key=(namekey(z['settlement_name']),regionkey(z['region_norm']),county(z['district_raw']));mr=modern.get(key,[]);native=targetnative.get(int(sid.rsplit(':',1)[1]));
 if len(mr)!=1 or not native:continue
 for yr in [2002,2010]:
  olds=hi.get((yr,*key),[])
  if len(olds)!=1:continue
  q=olds[0];reason=[]
  if q['source_record_id'] in reserved:continue
  if typekey(z['settlement_type'])!=typekey(q['settlement_type']):reason.append('current_historic_physical_type_mismatch')
  if q['root']==z['root']:continue
  if int(q['census_year'])!=yr:raise AssertionError()
  row={'current_source_record_id':sid,'historic_source_record_id':q['source_record_id'],'current_population2021':z['population'],'historic_population':q['population'],'current_name':z['settlement_name'],'current_type':z['settlement_type'],'region':z['region_norm'],'current_native_county':z['district_raw'],'current_native_specific_parish':native['mun_lower'],'current_raw_primary_row_json':json.dumps(native,ensure_ascii=False),'current_alltype_samecounty_native_rivals_json':json.dumps(mr,ensure_ascii=False),'historic_raw_scope_evidence_json':json.dumps(q,ensure_ascii=False,default=str),'historical_sameyear_samecounty_alltype_namesakes':len(olds),'current_root_actual66':z['root'],'historic_root_actual66':q['root'],'source_binding_rule':'positive actual raw physical NP name/type and printed county hierarchy; unique alltype names within same propercounty/region in both native censuses; historical NULL legacy population_scope does not exclude positively typed raw NP; modern physical ownpoint not proof of temporal continuity by itself','source_rule_holds':';'.join(reason),'status':'SOURCE_BOUND_COUNTY_HISTORY_CANDIDATE_NOT_ADMITTED'}
  (pairholds if reason else proposals).append(row)
for fn,zs in [('source_bound_county_history_candidates',proposals),('source_bound_county_history_type_holds',pairholds)]:pd.DataFrame(zs).to_csv(O/(fn+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
u={z['current_source_record_id']:z for z in proposals};receipt={'actual_baseline':66,'priority_current_singleton_carriers':len(f),'workbooks_one_at_a_time':books,'raw_name_population_columns_selected_once_per_sheet_from_literal_physical_NP_headers':True,'raw_historic_source_positive_scope_rows':len(rows),'raw_scope_holds':len(holds),'source_bound_counterpart_candidates':len(proposals),'current_native_UIDs':len(u),'current_known_population2021':sum(float(z['current_population2021']) for z in u.values() if z['current_population2021']),'historical_year_counts':dict(collections.Counter(json.loads(z['historic_raw_scope_evidence_json'])['census_year'] for z in proposals)),'type_holds':len(pairholds),'NULL_scope_rejection_used':False,'population_or_source_counts_unchanged':True,'identity_edges_or_point_uses_admitted':0,'seconds':time.monotonic()-START,'peak_RSS_MB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'input_pins':{str(p):sha(p) for p in [F,H,RAW,RES,RULE,O/'recover_grouped_headers.py']},'raw_workbook_pins':pins};(O/'grouped_source_recovery_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','raw_workbook_pins']},ensure_ascii=False))

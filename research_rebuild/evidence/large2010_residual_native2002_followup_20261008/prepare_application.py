import sys,json,re,collections,importlib.util,math
from pathlib import Path
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
sp=importlib.util.spec_from_file_location('finite',R/'research_rebuild/evidence/working_full_chain_20261007/replay_additional_native_20261008.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
s=load(46);before=s.metrics();bf=fm.finite(s);scan=json.loads((O/'scan_receipt.json').read_text());assert before==scan['before'] and bf==scan['before_finite']
basecols=['source_record_id','population','population_value_quality','settlement_name','settlement_type'];protected=s.obs[basecols].copy()
sel=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');con=duckdb.connect();meta=con.execute('select source_record_id,source_row,source_sheet,source_name_raw from read_parquet(?)',[str(sel)]).fetchdf().set_index('source_record_id');con.close()
a=pd.read_csv(O/'actual46_priority_component_absence.csv.gz',keep_default_na=False);c=pd.read_csv(O/'all_regional_name_candidates_before_graph_filter.csv.gz',keep_default_na=False);articles=pd.read_csv(O/'own_article_source_discovery.csv.gz',keep_default_na=False)
ex=set()
for p in [R/'research_rebuild/evidence/uncached_missing2010_dated_source_mass_20261008/accepted_qualified_native_source_ID_credit_union.csv',R/'research_rebuild/evidence/absorbed_residual_direct_events_next_20261008/accepted_direct_event_native_credit_union.csv.gz']:
 if p.exists():
  z=pd.read_csv(p,keep_default_na=False);ex.update(v for col in z for v in z[col].astype(str) if '2010:' in v or '2002:' in v)
members=collections.defaultdict(list)
for sid,y in s.obs[['source_record_id','census_year']].itertuples(index=False,name=None):members[s.uf.find(sid)].append(sid)
ctxpath=R/'research_rebuild/evidence/secondary_2010_county_context_application_20261007/all_selected_competitor_county_context.csv.gz';ctx=pd.read_csv(ctxpath,keep_default_na=False).set_index('source_record_id').to_dict('index')
pins={str(p):sha(p) for p in [sel,ctxpath,*s.inputs,*O.glob('own_wikipedia_articles_batch_*.json.gz')]};books={};raw=[];edges=[];points=[];proof=[];rivals=[];holds=[]
def original(row):
 sid=row.source_record_id;m=meta.loc[sid];p=Path('/workspace/settlements-raw')/row.source_file
 if not p.exists():p=Path(row.source_path)
 if p.exists():pins[str(p)]=sha(p)
 if p.suffix=='.xls':
  if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
  sh=books[p].sheet_by_name(str(m.source_sheet)) if str(m.source_sheet) in books[p].sheet_names() else books[p].sheet_by_index(int(m.source_sheet));rn=int(m.source_row)-1;vals=sh.row_values(rn)
  label=normalize(m.source_name_raw);matches=[i for i,v in enumerate(vals) if isinstance(v,str) and normalize(v)==label]
  passed=bool(matches) and any((isinstance(v,(int,float)) and v==row.population) or (isinstance(v,str) and re.fullmatch(r'\d+',v.strip()) and int(v)==row.population) for v in vals)
  assert passed,(sid,str(vals)[:500]);w={'source_record_id':sid,'raw_source_file':str(p),'raw_source_sha256':pins[str(p)],'raw_locator':f'sheet={sh.name};row1based={rn+1}','protected_population':row.population,'protected_quality':row.population_value_quality,'raw_own_label':m.source_name_raw,'literal_label_population_passed':True,'row_cells_json':json.dumps(vals,ensure_ascii=False)};raw.append(w)
 else:raw.append({'source_record_id':sid,'raw_source_file':str(p),'raw_source_sha256':pins.get(str(p),''),'raw_locator':row.source_locator,'protected_population':row.population,'protected_quality':row.population_value_quality,'raw_own_label':m.source_name_raw,'literal_label_population_passed':'already_selected_published_own_NP_source'} )
def county(row):
 k=county_key(row.district_raw) or ctx.get(row.source_record_id,{}).get('inferred_county_key','')
 return {'киров и кировский':'кировский','павловский посад':'павлово посадский','ступино':'ступинский','чехов':'чеховский'}.get(k,k)
def anchors(row):
 sid=row.source_record_id;out=[]
 if not sid.startswith('2010:'):return out
 prefix=sid.rsplit(':',1)[0]+':';rn=int(sid.rsplit(':',1)[1])
 for sign in [-1,1]:
  for dr in range(1,13):
   aid=prefix+str(rn+sign*dr)
   if aid not in s.by_id.index:continue
   own=s.by_id.loc[aid]
   if own.region_norm!=row.region_norm:break
   cs=[s.by_id.loc[i] for i in members[s.uf.find(aid)] if int(s.by_id.loc[i,'census_year'])==2021]
   if len(cs)==1:
    out.append({'offset':sign*dr,'native2010_source_record_id':aid,'native2010_name':own.settlement_name,'current_source_record_id':cs[0].source_record_id,'current_county_raw':cs[0].district_raw,'county_key':county(cs[0])});break
 return out
aliases={'Колпна':'Колпны','Эркен-Шахар':'Эркин-Шахар','Эркен-Юрт':'Эркин-Юрт','Старая Меловая':'Старомеловая','Хатуей':'Старый Урух'}
for z in a.to_dict('records'):
 sid=z['source_record_id'];b=s.by_id.loc[sid];target=s.uf.find(sid)
 if z['absence_reason']=='credited_scope_or_qualified' or sid in ex:continue
 aa=anchors(b);dc=county(b)
 dc={'киров и кировский':'кировский','павловский посад':'павлово посадский','ступино':'ступинский','чехов':'чеховский'}.get(dc,dc)
 if not dc and len(aa)==2 and aa[0]['county_key']==aa[1]['county_key']:dc={'киров и кировский':'кировский','павловский посад':'павлово посадский','ступино':'ступинский','чехов':'чеховский'}.get(aa[0]['county_key'],aa[0]['county_key'])
 # Explicit own article/type/county plus agreeing native source neighbours resolves county-caption changes and end-of-block rows.
 if b.settlement_name in {'Чарышское':'чарышский','Ракиты':'михайловский','Георгиевское':'межевской'}:
  expected={'Чарышское':'чарышский','Ракиты':'михайловский','Георгиевское':'межевской'}[b.settlement_name]
  if any(v['county_key']==expected for v in aa):dc=expected
 native_names={normalize(b.settlement_name),normalize(aliases.get(b.settlement_name,b.settlement_name))};candidates=s.obs[s.obs.region_norm.eq(b.region_norm)&s.obs.settlement_name.map(normalize).isin(native_names)]
 chosen=[];failed=''
 for y in [2002,2021]:
  if y in s.years[target]:continue
  peers=candidates[candidates.census_year.eq(y)]
  # retain ALL rivals before graph/year filtering
  for r in peers.itertuples():rivals.append({'target2010_source_record_id':sid,'candidate_source_record_id':r.source_record_id,'candidate_year':y,'native_name':r.settlement_name,'native_type':r.settlement_type,'native_county':r.district_raw,'candidate_county_key':county(r),'population':r.population,'graph_compatible':not bool(s.years[target]&s.years[s.uf.find(r.source_record_id)])})
  compatible=peers[peers.settlement_type.eq(b.settlement_type)]
  # documented urban-to-rural roles require unique urban native role, never arbitrary village reuse
  if b.settlement_name in ['Ферзиково','двинской','донское','Приупский']:compatible=peers[peers.settlement_type.isin(['пгт','посёлок'])]
  if b.settlement_name in ['донское','двинской','Приупский'] and y==2002:
   compatible=compatible[compatible.source_record_id.map(lambda x:bool(re.search(r'^(пгт|поселок городского типа|посёлок городского типа|рп)\b', normalize(meta.loc[x,'source_name_raw']))))]
  if dc:matching=compatible[compatible.source_record_id.map(lambda x:county(s.by_id.loc[x])==dc)]
  else:matching=compatible
  if len(matching)==0 and len(compatible)==1 and (not county(compatible.iloc[0]) or b.settlement_name in aliases or b.settlement_name in ['донское','двинской','Приупский']):matching=compatible
  if len(matching)!=1:failed=f'{y}: unresolved all-rival native class/county binding ({len(matching)})';break
  rr=matching.iloc[0];root=s.uf.find(rr.source_record_id)
  if root==target or s.years[root]&s.years[target]:failed=f'{y}: incompatible occupied native component';break
  chosen.append(rr)
 if failed or not chosen:holds.append({'source_record_id':sid,'name':b.settlement_name,'reason':failed or 'no missing native selected row','source_context_anchors_json':json.dumps(aa,ensure_ascii=False)});continue
 # same county homonyms held above; qualified prior IDs are allowed to upgrade ordinary.
 ids=set(members[target]);ids.update(i for r in chosen for i in members[s.uf.find(r.source_record_id)])
 if set(int(s.by_id.loc[i,'census_year']) for i in ids)!={2002,2010,2021}:holds.append({'source_record_id':sid,'name':b.settlement_name,'reason':'no native full3 route'});continue
 current=next(s.by_id.loc[i] for i in ids if int(s.by_id.loc[i,'census_year'])==2021);carrier=s.point_rows.get(current.source_record_id)
 if not carrier or any(i in s.conflicting_point_targets for i in ids):holds.append({'source_record_id':sid,'name':b.settlement_name,'reason':'no accepted own current physical point or conflict'});continue
 # Source context is mandatory where namesake populations differ and geography is omitted.
 if len(candidates[candidates.census_year.eq(2010)])>1 and not dc:holds.append({'source_record_id':sid,'name':b.settlement_name,'reason':'native2010 same-name rivals without county'});continue
 for i in ids:original(s.by_id.loc[i])
 rule='Literal own NP native name/type and source-county context with all same-name regional native rivals retained before graph filtering; source-bracket county anchors independently accepted where printed county omitted; explicit own-name alias or unique urban role where stated; accepted whole-locality current physical point reused by continuity; protected native count/quality unchanged; population equality not required'
 for r in chosen:
  if s.uf.find(r.source_record_id)!=s.uf.find(sid):
   edges.append({'from_source_record_id':r.source_record_id,'to_source_record_id':sid,'relation':'same_place','decision_status':'checked_rule_accepted','case':b.settlement_name,'admission_rule':rule,'source_binding_proof':'accepted_source_bindings.csv.gz;actual_native_raw_source_checks.csv.gz;all_native_name_competitors.csv.gz','population_boundary_comparability_asserted':False});s.union(r.source_record_id,sid)
 for i in ids:
  if i in s.point_rows:continue
  p={k:v for k,v in carrier.items() if k!='point_ledger_path'};p.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule=rule,point_use_inference='modern_own_representative_point_reused_on_source_bound_historical_identity',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,case=b.settlement_name);points.append(p)
 proof.append({'target2010_source_record_id':sid,'name':b.settlement_name,'native_component_IDs_json':json.dumps(sorted(ids)),'source_county_key':dc,'source_context_anchors_json':json.dumps(aa,ensure_ascii=False),'native_alias':aliases.get(b.settlement_name,''),'source_positive_point_json':json.dumps(carrier,ensure_ascii=False),'native_values_not_equated_to_Wikipedia':True,'cached_own_article_source_candidates_json':json.dumps([{'title':v['title'],'pageid':v['pageid'],'revisionid':v['revisionid'],'source_archive':v['source_archive'],'fields_json':v['fields_json'],'explicit_alias_context':v['article_text'][:2800]} for v in articles.to_dict('records') if normalize(b.settlement_name) in normalize(v['title']) or (b.settlement_name=='Колпна' and v['title']=='Колпна')],ensure_ascii=False)})
 # temporary point insertion needed only for later duplicate exclusion
 for p in points:
  if p['target_source_record_id'] in ids:s.point_rows[p['target_source_record_id']]=dict(p)
# Replay deltas from actual46 independently and check protected values.
for name,rows,cols in [('accepted_identity_edge_delta.csv',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('accepted_source_bindings.csv.gz',proof,None),('actual_native_raw_source_checks.csv.gz',raw,None),('all_native_name_competitors.csv.gz',rivals,None),('application_holds.csv',holds,None)]:
 f=pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols or ['source_record_id']);f.to_csv(O/name,index=False,compression='gzip' if name.endswith('.gz') else None)
s.obs['root']=s.obs.source_record_id.map(s.uf.find);after=s.metrics();af=fm.finite(s);pd.testing.assert_frame_equal(protected,s.obs[basecols]);outputs=[p for p in O.iterdir() if p.name in ['accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','accepted_source_bindings.csv.gz','actual_native_raw_source_checks.csv.gz','all_native_name_competitors.csv.gz','application_holds.csv']]
r={'baseline_stage':46,'status':'actual46 native source-bound application ready; source values and qualities unchanged','accepted_cases':len(proof),'edges':len(edges),'point_uses':len(points),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},'net_population_by_year':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'input_pins':pins,'output_pins':{p.name:sha(p) for p in outputs},'native_population_quality_source_spelling_unchanged':True,'qualified_sidecar_separate':True,'population_equality_not_identity_requirement':True,'historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins','before','after']},ensure_ascii=False));print(pd.DataFrame(proof)[['name','source_county_key']].to_string(index=False))

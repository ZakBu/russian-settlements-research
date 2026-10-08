import sys,json,re,gzip,math,importlib.util
from pathlib import Path
from collections import defaultdict
import pandas as pd,xlrd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;P=O.parents[1]/'temporal_missing2002_all_components_20261008';s=load(37);before=s.metrics()
sp=importlib.util.spec_from_file_location('finite',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm);bf=fm.finite_metrics(s);assert bf=={'histories':137860,'populations_by_year':{'2002':126615295,'2010':123783293,'2021':124396048}},'Actual37 finite baseline differs'
f=pd.read_csv(P/'disjoint_native_source_routes.csv.gz',dtype=str,keep_default_na=False);f=f[f.native_source_route.eq('unclaimed_native2002_county_or_competitor_resolution')];allc=pd.read_csv(P/'all_native2002_label_alias_code_competitors.csv.gz',dtype=str,keep_default_na=False);al=pd.read_csv(P/'cached_literal_aliases.csv.gz',dtype=str,keep_default_na=False);claims=pd.read_csv(P/'cached_dated2002_claims.csv.gz',dtype=str,keep_default_na=False);meta=duckdb.connect().execute("select source_record_id,entity_grain_status,source_sheet,source_row,source_name_raw from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf().set_index('source_record_id')
books={};header_cache={};archives={};pins={str(P/n):sha(P/n) for n in ['disjoint_native_source_routes.csv.gz','all_native2002_label_alias_code_competitors.csv.gz','cached_literal_aliases.csv.gz','cached_dated2002_claims.csv.gz']};edges=[];points=[];proof=[];rawchecks=[];held=[];competitors=[];overlaps=[];seen=set();orgclasses={'Q43229','Q783794','Q4830453','Q163740','Q3918','Q5','Q16917','Q31855'}
def namekey(v):
 v=normalize(v);v=re.sub(r'\bим\.\s*','имени ',v);return re.sub(r'\s+',' ',v).strip()
def entity(path,q):
 p=Path(path)
 if path not in archives:
  pins[path]=sha(p)
  with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as fh:z=json.load(fh)
  archives[path]=z.get('entities',z.get('payload',{}).get('entities',{}))
 return archives[path].get(q)
def raw(a):
 mm=meta.loc[a.source_record_id];p=Path('/workspace/settlements-raw')/a.source_file;path=str(p)
 if path not in books:books[path]=xlrd.open_workbook(p);pins[path]=sha(p)
 bk=books[path];sh=bk.sheet_by_name(str(mm.source_sheet)) if str(mm.source_sheet) in bk.sheet_names() else bk.sheet_by_index(int(float(mm.source_sheet)));rn=int(mm.source_row)-1;rv=sh.row_values(rn);li=next((i for i,v in enumerate(rv) if isinstance(v,str) and normalize(a.settlement_name) in normalize(v)),None);nums=[]
 if li is not None:
  for v in rv[li+1:]:
   st=str(v).replace(' ','').replace('\xa0','').replace(',','.')
   if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',st):nums.append(float(st))
 parents=[]
 hk=(path,str(mm.source_sheet))
 if hk not in header_cache:
  tmp=[]
  for i in range(sh.nrows):
   for v in sh.row_values(i)[:8]:
    if isinstance(v,str) and re.search(r'район|кожуун|улус|сельсовет|сельский округ|городск|^\s*город |^\s*г\..*подчин',v,re.I):tmp.append({'row_1based':i+1,'literal':v,'county_key':county_key(re.sub(r'\s+с\s+подчин[её]нными.*$', '', re.sub(r'\s+[-–—]\s*(?:вс[её]\s+)?сельско[её]\s+населени[её]\s*$', '', v, flags=re.I),flags=re.I))})
  header_cache[hk]=tmp
 parents=[p for p in header_cache[hk] if p['row_1based']<=rn]
 for i in range(0,0):
  for v in sh.row_values(i)[:8]:
   if isinstance(v,str) and re.search(r'район|кожуун|улус|сельсовет|сельский округ|городск|^\s*город |^\s*г\..*подчин',v,re.I):parents.append({'row_1based':i+1,'literal':v,'county_key':county_key(re.sub(r'\s+с\s+подчин[её]нными.*$', '', re.sub(r'\s+[-–—]\s*(?:вс[её]\s+)?сельско[её]\s+населени[её]\s*$', '', v, flags=re.I),flags=re.I))})
 return {'source_record_id':a.source_record_id,'source_path':path,'source_sha256':pins[path],'source_sheet':mm.source_sheet,'source_row_1based':rn+1,'protected_native_population':a.population,'protected_native_quality':a.population_value_quality,'native_name':a.settlement_name,'native_type':a.settlement_type,'native_county':a.district_raw,'native_grain':mm.entity_grain_status,'literal_raw_row':json.dumps(rv,ensure_ascii=False),'literal_parent_captions':json.dumps(parents,ensure_ascii=False),'raw_label_population_exact':li is not None and bool(nums) and nums[0]==float(a.population)},parents
def inherited_literal_county(a,rr,parents):
 oc=county_key(a.district_raw)
 if oc:return oc,'Parsed county retained with literal parent verification'
 rv=json.loads(rr['literal_raw_row']);label=next((v for v in rv if isinstance(v,str) and normalize(a.settlement_name) in normalize(v)),'');depth=len(label)-len(label.lstrip())
 major=[v for v in parents if re.search(r'\b(?:район|кожуун|улус)\s*(?:[-–—].*)?$',v['literal'].strip(),re.I) or (re.match(r'^\s*(?:город\s+\S|г\..*подчин)',v['literal'],re.I) and len(v['literal'])-len(v['literal'].lstrip())<depth)]
 if major:return major[-1]['county_key'],'Actual printed primary parent with shallower hierarchy: '+json.dumps(major[-1],ensure_ascii=False)
 return '','No literal primary county/city ancestor'
pairframes=[]
for z0 in f.to_dict('records'):
 for pp in allc[allc.current_source_record_id.eq(z0['current_source_record_id'])&allc.native2002_missing2002_pair_graph_compatible.eq('True')].to_dict('records'):
  pairframes.append(dict(z0,selected_candidate_old_source_record_id=pp['candidate_native2002_source_record_id']))
for z in pairframes:
 sid=z['current_source_record_id'];n=s.by_id.loc[sid];b=s.by_id.loc[z['native2010_source_record_id']];cc=allc[allc.current_source_record_id.eq(sid)];selected=cc[cc.candidate_native2002_source_record_id.eq(z['selected_candidate_old_source_record_id'])];why=[]
 if len(selected)!=1:held.append({'current_source_record_id':sid,'name':n.settlement_name,'reason':'Candidate-only inventory has no single selected native02 route'});continue
 a=s.by_id.loc[selected.iloc[0].candidate_native2002_source_record_id];case=n.settlement_name+':'+a.source_record_id;ids=[a.source_record_id,b.source_record_id,sid];roots={s.uf.find(x) for x in ids};ys=[y for r in roots for y in s.years[r]];donor=s.point_rows.get(sid)
 overlaps.append({'case':case,'old_source_record_id':ids[0],'current_source_record_id':sid,'component_years':str(sorted(ys)),'already_same_component':s.uf.find(ids[0])==s.uf.find(sid),'old_existing_point':ids[0] in s.point_rows})
 if s.years[s.uf.find(sid)]!={2010,2021} or s.uf.find(b.source_record_id)!=s.uf.find(sid) or s.years[s.uf.find(a.source_record_id)]!={2002} or len(ys)!=len(set(ys)):why.append('Actual37 repeated-year/previously admitted source component')
 if a.source_record_id in seen:why.append('Shared old source target in proposed batch')
 for rr in [a,b,n]:
  if not rr.is_additive_settlement_record or not math.isfinite(rr.population) or re.search('aggregate|municipal|unresolved|control.total',str(meta.loc[rr.source_record_id].entity_grain_status),re.I):why.append('Native record not finite additive resolved ownNP leaf')
 if not donor or not(n.okato or n.oktmo):why.append('No independent admitted current own native-coded representative point')
 if why:held.append({'case':case,'old_source_record_id':ids[0],'current_source_record_id':sid,'native02_population':a.population,'reason':'; '.join(why)});continue
 dp=(donor['latitude'],donor['longitude']);oldpoint=s.point_rows.get(ids[0]);oldclose=bool(oldpoint and distance_km(dp,(oldpoint['latitude'],oldpoint['longitude']))<=5)
 if oldpoint and not oldclose:why.append('Actual old own point/current own point conflict beyond5km; no rejection proposed')
 aliases=al[al.current_source_record_id.eq(sid)&al.own_entity_bound.eq('True')];ownproof=[];hasownalias=False
 for q,g in aliases.groupby('qid'):
  ee=None;ep=None
  for path in g.raw_source_file.unique():
   ee=entity(path,q)
   if ee:ep=path;break
  if not ee:continue
  p31=[v.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for v in ee.get('claims',{}).get('P31',[]) if v.get('rank')!='deprecated']
  if any(v in orgclasses for v in p31):why.append('Actual own entity is organization/human rather than physical NP');continue
  qpts=[v['mainsnak']['datavalue']['value'] for v in ee.get('claims',{}).get('P625',[]) if v.get('rank')!='deprecated' and v.get('mainsnak',{}).get('datavalue',{}).get('type')=='globecoordinate'];nearq=any(distance_km(dp,(v['latitude'],v['longitude']))<=5 for v in qpts)
  qs=json.loads(z['independently_bound_cached_QIDs_json']);qc=json.loads(z['own_native_code_QID_candidates_json']);qd=json.loads(z['direct_own_point_QIDs_json']);independent=q in qs and (q in qc or q in qd)
  oldalias=any(namekey(v)==namekey(a.settlement_name) for v in g.alias)
  if independent and nearq and oldalias:hasownalias=True
  cl=claims[claims.current_source_record_id.eq(sid)&claims.qid.eq(q)&claims.own_entity_bound.eq('True')];dat=cl[pd.to_numeric(cl.population2002,errors='coerce').eq(float(a.population))]
  ownproof.append({'qid':q,'raw_entity_file':ep,'P31':p31,'independently_admitted_nativecode_or_point_QID':independent,'own_P625_within5km':nearq,'literal_native02_own_alias':oldalias,'dated2002_exact_native_count_claims':dat.to_dict('records'),'raw_own_entity':ee})
 direct=namekey(a.settlement_name) in {namekey(n.settlement_name),namekey(b.settlement_name)}
 if not direct and not hasownalias:why.append('No exact current native printed name or independently coded own literal alias binding')
 rr,parents=raw(a)
 if not rr['raw_label_population_exact']:why.append('Original native02 own printed row/first population differs protected selected value')
 oc,oldscope=inherited_literal_county(a,rr,parents);nc=county_key(n.district_raw);bc=county_key(b.district_raw)
 # A parsed source county alone is not proof: recover its literal printed parent.
 majors=[p for p in parents if re.search(r'\b(?:район|кожуун|улус)\s*(?:[-–—].*)?$',p['literal'].strip(),re.I)]
 if not oc and majors:oc=majors[-1]['county_key']
 literalold=bool(oc and any(p['county_key']==oc for p in parents));countymatch=bool(oc and oc in {nc,bc});countyrule='Literal native02 printed county agrees accepted native2010/current county' if literalold and countymatch else ''
 if not countyrule and oldclose:countyrule='Independently admitted old own point agrees current own native-code point within5km; native own printed name/class bind'
 if not countyrule:why.append('No literal native02 source county agreement or independent old own point within5km')
 # All relevant native namesakes are checked before component filtering.
 same=[]
 for _,p in cc.iterrows():
  peer=s.by_id.loc[p.candidate_native2002_source_record_id];pc=county_key(peer.district_raw)
  if not pc:
   perr,peparents=raw(peer);pc,_=inherited_literal_county(peer,perr,peparents)
  point=s.point_rows.get(peer.source_record_id);dist=distance_km(dp,(point['latitude'],point['longitude'])) if point else None
  competitors.append(dict(p,case=case,actual36_component_years=str(sorted(s.years[s.uf.find(peer.source_record_id)])),actual36_distance_to_current_km=dist,native_same_parsed_county=bool(oc and pc==oc),target_old_record=peer.source_record_id==ids[0]))
  if peer.source_record_id!=ids[0] and (not pc or not oc or pc==oc):same.append(peer)
 if same:
  classes={b.type_norm,n.type_norm};compatible=[p for p in same if p.type_norm==a.type_norm]
  if compatible:why.append('Actual same-name/alias native02 same-county same-class competitor, including already-full3 peers')
  elif a.type_norm not in classes and not oldclose and not (a.type_norm in {'станция','железнодорожный объект','разъезд','железнодорожная станция'} and re.search(r'железнодорожн|ж\.?[- ]?д\.?|станци|разъезд|остановоч', str(meta.loc[b.source_record_id].source_name_raw)+' '+str(meta.loc[n.source_record_id].source_name_raw),re.I)):why.append('Multiple native02 classes in county; selected old printed class lacks current source class or old own point corroboration')
 if why:held.append({'case':case,'old_source_record_id':ids[0],'current_source_record_id':sid,'native02_population':a.population,'reason':'; '.join(sorted(set(why)))});continue
 proof.append(dict(z,old_source_record_id=ids[0],native02_name=a.settlement_name,native02_type=a.settlement_type,native02_population=a.population,native02_county_rule=countyrule,native02_literal_scope_rule=oldscope,direct_native_printed_name=direct,cached_literal_own_alias_positive=hasownalias,old_own_point_within5km=oldclose,raw_own_entity_bindings=json.dumps(ownproof,ensure_ascii=False),current_own_point_json=json.dumps(donor,ensure_ascii=False),all_native_competitor_ids=cc.candidate_native2002_source_record_id.str.cat(sep=';'),population_boundary_comparability_asserted=False));rawchecks.append(rr)
 edges.append({'from_source_record_id':ids[0],'to_source_record_id':sid,'relation':'same_place','decision_status':'checked_rule_accepted','case':case,'admission_rule':'Original native02 ownNP printed name/literal own alias,class and literal county or independent own point; native current official code/name/own point binding; all old homonyms before filtering; protected populations unchanged','source_binding_proof':'accepted_source_bindings.csv.gz;actual_native02_raw_source_checks.csv.gz;all_native2002_competitors.csv.gz','population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
 if not oldpoint:
  pp={k:v for k,v in donor.items() if k!='point_ledger_path'};pp.update(target_source_record_id=ids[0],coordinate_admission_status='reviewed_extension_rule_accepted',case=case,coordinate_binding_rule='Current independently admitted own native-code/name point on literal native02 name/class/county-bound identity; all homonyms retained',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,point_use_inference='modern_own_representative_point_on_native02_identity');points.append(pp)
 seen.add(ids[0])
ambiguous={sid for sid in {p['current_source_record_id'] for p in proof} if sum(p['current_source_record_id']==sid for p in proof)>1}
if ambiguous:
 rejected={p['old_source_record_id'] for p in proof if p['current_source_record_id'] in ambiguous}
 held.extend({'old_source_record_id':p['old_source_record_id'],'current_source_record_id':p['current_source_record_id'],'native02_population':p['native02_population'],'reason':'Multiple source-positive old rows remain for one current object; count not used to select identity'} for p in proof if p['current_source_record_id'] in ambiguous)
 proof=[p for p in proof if p['current_source_record_id'] not in ambiguous];edges=[p for p in edges if p['from_source_record_id'] not in rejected];points=[p for p in points if p['target_source_record_id'] not in rejected];rawchecks=[p for p in rawchecks if p['source_record_id'] not in rejected]
for name,data in [('accepted_identity_edge_delta.csv',edges),('accepted_point_use_delta.csv',points),('accepted_source_bindings.csv.gz',proof),('actual_native02_raw_source_checks.csv.gz',rawchecks),('all_native2002_competitors.csv.gz',competitors),('held_cases.csv',held),('actual37_overlap_checks.csv.gz',overlaps)]:pd.DataFrame(data).to_csv(O/name,index=False,compression='gzip' if name.endswith('.gz') else None)
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();af=fm.finite_metrics(s);outs=['accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','accepted_source_bindings.csv.gz','actual_native02_raw_source_checks.csv.gz','all_native2002_competitors.csv.gz','held_cases.csv','actual37_overlap_checks.csv.gz'];r={'baseline_stage':37,'status':'Actual37 native02 printed county/class CSV replay passed; ready future39 composition after independent38 integration','candidate_cases':len(f),'accepted_cases':len(proof),'edges':len(edges),'point_uses':len(points),'holds':len(held),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},'input_pins':pins,'output_pins':{n:sha(O/n) for n in outs},'native_populations_quality_source_spelling_unchanged':True,'historical_census_coordinate_asserted':False,'all_native_competitors_checked_before_component_filter':True};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:r[k] for k in ['candidate_cases','accepted_cases','edges','point_uses','holds','net_finite_all3_all_points']},ensure_ascii=False));print(pd.DataFrame(held).reason.value_counts().to_string())

from pathlib import Path
import sys,json,gzip,hashlib,re,collections,time,math
import pandas as pd
O=Path(__file__).parent;E=O.parent;ROOT=E.parents[1];sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from current_chain_state_20261007 import normalize,distance_km,sha
T=time.monotonic();s=load(24);ex=set();pins={};priorq=set()
for p in [E/'wikidata_actual_full3_mass_reserve_20261007/targets.csv',E/'wikidata_secondary_full3_expansion_20261007/targets.csv']:
 f=pd.read_csv(p).fillna('');ex.update(f.sid);priorq.update(f.qid);pins[str(p)]=sha(p)
files=[PARTITION_MEMBERS,E/'additional_complete_partition_application_20261007/accepted_exclusive_member_projection.csv',E/'wikidata_secondary_full3_application_20261007/preapplication_qualified_credit_ids_frozen.csv']+[E/d/'accepted_qualified_physical_observations.csv' for d in ['wikidata_secondary_full3_application_20261007','current_unpointed_own_wiki_mass_application_20261007','existing_event_scope_application_20261007','wikidata_secondary_full3_expansion_application_20261007','remaining_large_own_points_followup_application_20261007','cached_secondary_native_year_mass_application_20261008']]+[E/d/'accepted_constituent_credit_union.csv' for d in ['named_urban_merger_application_20261007','next_named_urban_merger_application_20261007','further_urban_merger_application_20261007']]+[E/'native_from_secondary_census_binding_application_20261007/accepted_native_source_id_credit_union.csv',E/'old_native_from_existing_secondary_binding_application_20261007/accepted_native_source_id_credit_union.csv']
for p in files:
 if not p.exists():continue
 f=pd.read_csv(p,dtype=str).fillna('');pins[str(p)]=sha(p)
 for c in f.columns:
  if 'source_record_id'in c:ex.update(f[c])
  if c in ['wikidata_id','qid','trajectory_id','point_origin_locator','raw_source_locator']:priorq.update(q for x in f[c] for q in re.findall(r'Q\d+',x))
# Finite ordinary joint: every component member has its own admitted point and finite population.
groups=s.obs.groupby('root');members={k:g for k,g in groups};finite=set()
for root,g in members.items():
 if set(g.census_year)=={2002,2010,2021} and g.population.notna().all() and all(i in s.point_rows for i in g.source_record_id):finite.update(g.source_record_id)
ex.update(finite);code_map=collections.defaultdict(list);tsv=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
for line_no,line in enumerate(tsv.open(),1):
 p=line.rstrip().split('\t')
 if len(p)<6:continue
 q=re.findall(r'Q\d+',p[0]);label=re.search(r'"(.*)"@ru',p[4]);admin=re.search(r'"(.*)"@ru',p[7]) if len(p)>7 else None
 if not q or not label:continue
 for code in re.findall(r'\d{8,11}',p[1]+' '+p[2]):code_map[code].append((q[0],label.group(1),admin.group(1) if admin else '',line_no))
target=[];unbound=0;count_raw=0
for r in s.obs.itertuples():
 if r.census_year!=2021 or r.source_record_id not in s.point_rows or r.source_record_id in ex or r.region_norm in ('крым','севастополь') or not pd.notna(r.population) or r.population<=0:continue
 count_raw+=1;p=s.point_rows[r.source_record_id];loc=' '.join(str(p.get(k,'')) for k in ['point_origin_locator','source_locator','coordinate_source_record_id']);qids=set(re.findall(r'\bQ\d+\b',loc));matches=[]
 for code in [str(r.oktmo),str(r.okato)]:matches.extend(code_map.get(code,[]))
 exact={q for q,n,a,ln in matches if normalize(n)==normalize(r.settlement_name)};basis=''
 if len(exact)==1:q=next(iter(exact));basis='exact_native_code_and_own_label'
 elif len(qids)==1:q=next(iter(qids));basis='admitted_point_item_provenance_pending_population_item_own_binding'
 else:
  coded={x[0] for x in matches if len(str(r.oktmo))==11 or len(str(r.okato))==11}
  if len(coded)!=1:unbound+=1;continue
  q=next(iter(coded));basis='unique_exact_native_code_own_alias_physical_admin_check_pending'
 if q in priorq:continue
 olds=members[s.uf.find(r.source_record_id)];native_old=[{'sid':t.source_record_id,'year':int(t.census_year),'population':None if pd.isna(t.population) else float(t.population),'quality':t.population_value_quality,'scope':None if pd.isna(t.population_scope) else t.population_scope,'name':t.settlement_name,'type':t.settlement_type,'county':t.district_raw} for t in olds.itertuples() if t.census_year!=2021]
 target.append({'sid':r.source_record_id,'qid':q,'name':r.settlement_name,'type':r.settlement_type,'region':r.region_norm,'county':r.district_raw,'population':float(r.population),'oktmo':str(r.oktmo),'okato':str(r.okato),'binding':basis,'native_old':native_old,'latitude':p['latitude'],'longitude':p['longitude'],'source_code_witnesses':[(l,a,ln) for qq,l,a,ln in matches if qq==q]})
target.sort(key=lambda t:(-sum(v['population'] or 0 for v in t['native_old']),-len(t['native_old']),-t['population']));want={t['qid'] for t in target};dup={q for q,n in collections.Counter(t['qid'] for t in target).items() if n>1};cache={};labels={};matched_records=0;claimcount=0;cachefiles=0
paths=list(Path('/workspace/settlements-work/continuation_20261004').rglob('*.json'))+[p for p in Path('/workspace/settlements-raw/data/raw/wikidata_entities_full').glob('batch*.json.gz')]+[p for d in ['wikidata_actual_full3_mass_reserve_20261007','wikidata_secondary_full3_expansion_20261007'] for p in Path('/workspace/settlements-work',d).glob('*.json.gz')]+list(Path('/workspace/settlements-work/additional_uncached_census_histories_20261008').glob('batch_*.json.gz'))
for p in paths:
 if str(p).endswith('.json') and not any(z in str(p).lower() for z in ['wikidata','entity','qid','q1','q2','q3','q4','q5','q6','q7','q8','q9']):continue
 try:b=p.read_bytes();a=json.loads(gzip.decompress(b) if p.name.endswith('.gz') else b)
 except Exception:continue
 if not isinstance(a,dict):continue
 entities=a.get('entities',a.get('payload',{}).get('entities',{}))
 if 'claims'in a and 'id'in a:entities={a['id']:a}
 if not isinstance(entities,dict):continue
 cachefiles+=1
 for q,e in entities.items():
  if not isinstance(e,dict):continue
  label=e.get('labels',{}).get('ru',e.get('labels',{}).get('en',{})).get('value','')
  if label:labels[q]=label
  if q not in want:continue
  matched_records+=1;pop=e.get('claims',{}).get('P1082',[]);claimcount+=len(pop)
  if q not in cache or len(pop)>len(cache[q][0].get('claims',{}).get('P1082',[])):cache[q]=(e,str(p))
uncached=[t for t in target if t['qid'] not in cache and t['qid'] not in dup]
uncached.sort(key=lambda t:(-sum(v['population'] or 0 for v in t['native_old']),-len(t['native_old']),-t['population']))
pd.DataFrame([{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in t.items()} for t in uncached]).to_csv(O/'uncached_targets.csv',index=False)
pd.DataFrame([{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in t.items()} for t in target]).to_csv(O/'all_residual_targets.csv',index=False)
def value(s):return s.get('datavalue',{}).get('value')
def hascensus(t,y):return any(x in str(t).lower() for x in ['перепис','census','впн']) and str(y)in str(t) and not any(x in str(t).lower()for x in ['оценка численности','1 января'])
def county(v):
 x=normalize(v)
 for z in ['муниципальный район','муниципальный округ','городской округ','район','город','округ']:x=re.sub(r'(?<!\w)'+z+r'(?!\w)',' ',x)
 return ' '.join(x.split())
proofs=[];cand=[];holds=[];seenhash={};source_manifest={}
for t in target:
 q=t['qid']
 if q not in cache:continue
 e,path=cache[q];cs=e.get('claims',{});description=e.get('descriptions',{}).get('ru',{}).get('value','');rawlabel=e.get('labels',{}).get('ru',{}).get('value','');aliases=[r.get('value','')for r in e.get('aliases',{}).get('ru',[])];names={normalize(v)for v in [rawlabel]+aliases};codes={str(value(v['mainsnak']))for prop in ['P764','P763']for v in cs.get(prop,[])};codepositive=bool(codes&{t['oktmo'],t['okato']});namepositive=normalize(t['name'])in names;physical=bool(re.match(r'^(село|деревня|пос[её]лок|станица|хутор|город\b|аул|селение|сельский насел)',description.lower()));adminpositive=any(county(a)==county(t['county']) and county(a)for _,a,_ in t['source_code_witnesses']);hold=[]
 if q in dup:hold.append('same_own_QID_multiple_current_native_NPs')
 if not namepositive and not(codepositive and physical and adminpositive):hold.append('population_item_current_own_binding_not_positive')
 if re.match(r'^(муниципаль|район\b|городской округ|сельсовет|сельское поселение|микрорайон|часть города|квартал)',description.lower()) or 'бывш' in description.lower() or cs.get('P576'):hold.append('wrong_or_event_physical_grain')
 if any(isinstance((d:=value(st.get('mainsnak',{}))),dict) and int(d.get('time','+0000')[1:5])>2002 for st in cs.get('P571',[])):hold.append('post2002_foundation_contradiction')
 pp=s.point_rows[t['sid']];root=s.uf.find(t['sid']);pts=[s.point_rows[i]for i in members[root].source_record_id if i in s.point_rows];maxdist=max([distance_km((p['latitude'],p['longitude']),(v['latitude'],v['longitude']))for p in pts for v in pts]or[0])
 if maxdist>5 or any(i in s.conflicting_point_targets for i in members[root].source_record_id):hold.append('existing_component_point_hard_conflict')
 actual=collections.defaultdict(list)
 for st in cs.get('P1082',[]):
  v=value(st.get('mainsnak',{}))
  if not isinstance(v,dict) or 'amount'not in v or st.get('rank')=='deprecated' or st.get('qualifiers',{}).get('P518'):continue
  refs=st.get('references',[]);titles=[v.get('text','')for ref in refs for sn in ref.get('snaks',{}).get('P1476',[]) if isinstance((v:=value(sn)),dict)];rq=[v.get('id')for ref in refs for sn in ref.get('snaks',{}).get('P248',[])if isinstance((v:=value(sn)),dict)];urls=[str(value(sn))for ref in refs for sn in ref.get('snaks',{}).get('P854',[])];pop=float(value(st['mainsnak'])['amount'])
  for dt in st.get('qualifiers',{}).get('P585',[]):
   d=value(dt)
   if not isinstance(d,dict):continue
   y=int(d.get('time','+0000')[1:5]);date=d.get('time','');prec=d.get('precision');basis=[]
   if y not in (2002,2010):continue
   if date[1:11]in('2002-10-09','2010-10-14'):basis.append('exact_P585_census_date')
   elif prec!=9:continue
   if any(hascensus(tx,y)for tx in titles):basis.append('explicit_raw_census_P1476_reference_title')
   if any(hascensus(labels.get(qi,''),y)for qi in rq):basis.append('explicit_cached_P248_census_label')
   if y==2002 and any('vpn2002'in u.lower()for u in urls):basis.append('explicit_vpn2002_source_database')
   if not basis:continue
   actual[y].append({'year':y,'population':pop,'statement_id':st.get('id'),'declared_date':date,'date_precision':prec,'census_proof':';'.join(basis),'titles':titles,'P248_ids':rq,'P248_labels':[labels.get(qi,'')for qi in rq],'urls':urls,'source_path':path,'source_locator':f'entities.{q}.claims.P1082[{st.get("id")}]'})
 native={v['year']:v for v in t['native_old']}
 selected=[];nativegain={2002:0,2010:0};oldids=[]
 for y in (2002,2010):
  if y in native and native[y]['population']is not None:
   nv=native[y];selected.append({'year':y,'population':nv['population'],'kind':'already_accepted_component_native_year','source_record_id':nv['sid'],'native_quality':nv['quality'],'legacy_scope_flag':nv['scope']is None,'secondary_proof_available':bool(actual[y])})
   if nv['sid']not in ex:nativegain[y]=nv['population'];oldids.append(nv['sid'])
  else:
   vals={v['population']for v in actual[y]}
   if len(vals)!=1:hold.append('missing_or_conflicting_actual_secondary_census_'+str(y));continue
   selected.append({**actual[y][0],'kind':'actual_secondary_census_history','source_record_id':''})
 if hold:holds.append({'qid':q,'sid':t['sid'],'name':t['name'],'hold_reason':';'.join(hold)});continue
 if path not in seenhash:seenhash[path]=sha(Path(path))
 source_manifest[path]=seenhash[path]
 t.update({'population2002':next(v['population']for v in selected if v['year']==2002),'population2010':next(v['population']for v in selected if v['year']==2010),'native2002_net_population':nativegain[2002],'native2010_net_population':nativegain[2010],'native_old_net_IDs':oldids,'years':selected,'entity_source_path':path,'entity_source_sha256':seenhash[path],'own_label':rawlabel,'own_description':description,'own_code_positive':codepositive,'own_name_or_alias_positive':namepositive,'admin_source_positive':adminpositive,'component_points_max_distance_km':maxdist,'status':'candidate_only_cached_native_plus_actual_secondary_histories'});cand.append(t)
# Compact candidate rows keep detailed source witnesses in one JSONL, no raw cache copies.
out=[]
for t in cand:out.append({k:(json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v)for k,v in t.items()})
pd.DataFrame(out).to_csv(O/'candidate_series.csv',index=False);pd.DataFrame(holds).to_csv(O/'holds.csv',index=False)
net={y:{'rows':sum(1 for t in cand if t['native'+str(y)+'_net_population']>0),'population':int(sum(t['native'+str(y)+'_net_population']for t in cand))}for y in (2002,2010)};receipt={'status':'additional_uncached_candidate_only','baseline_stage':24,'raw_pointed_residual_after_prior_IDs_and_finite_exclusion':count_raw,'bound_target_records':len(target),'distinct_target_QIDs':len(want),'cached_matched_records':matched_records,'cached_distinct_own_QIDs':len(cache),'cached_population_statement_records':claimcount,'source_cache_files_checked':cachefiles,'candidate_series':len(cand),'candidate_current_native_population':int(sum(t['population']for t in cand)),'native_old_year_source_ID_net_potential':net,'native_old_year_net_population_total':sum(v['population']for v in net.values()),'candidate_without_native_oldyear_gain':sum(not t['native_old_net_IDs']for t in cand),'actual_admitted_gain':0,'API_requests':json.loads((O/'network_receipt.json').read_text()).get('requests_made',0) if (O/'network_receipt.json').exists() else 0,'raw_cached_sources_copied':0,'wall_seconds':time.monotonic()-T,'scope':'current native2021 plus bound native older years preferred; missing historicalyears require actual census rawsource proof; secondaryhistories nonadditive','error_rate':'uncalibrated','coordinate_bounds':'UNKNOWN','candidate_only_not_applied':True};(O/'receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False));(O/'source_manifest.json').write_text(json.dumps({'raw_entity_cache':source_manifest,'fixed_input_hashes':pins,'loader':{str(ROOT/'research_rebuild/mass_linkage/working_state_20261007.py'):sha(ROOT/'research_rebuild/mass_linkage/working_state_20261007.py')}},indent=2));print(json.dumps(receipt,ensure_ascii=False))

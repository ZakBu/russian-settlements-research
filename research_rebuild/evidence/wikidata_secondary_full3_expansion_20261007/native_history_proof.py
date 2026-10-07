from pathlib import Path
import pandas as pd,json,gzip,hashlib,re,collections,time
O=Path(__file__).parent;W=Path('/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007');T=time.monotonic();a=pd.read_csv(O/'actual_target_year_claims.csv').fillna('');targets=pd.read_csv(O/'targets.csv').fillna('');other=json.load(open('/workspace/settlements-work/existing_event_scope_reserve_20261007/residual.json'));otherids={r['sid'] for r in other};dup={q for q,g in targets.groupby('qid') if g.sid.nunique()>1};labels={}
for root in [Path('/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007'),W]:
 for p in root.glob('*reference*.json.gz'):
  data=json.loads(gzip.decompress(p.read_bytes()))
  for q,e in data.get('entities',{}).items():labels[q]=e.get('labels',{}).get('ru',e.get('labels',{}).get('en',{})).get('value','')
def val(s):return s.get('datavalue',{}).get('value')
def hascensus(t,y):
 t=str(t).lower();return ('перепис' in t or 'census' in t or 'впн' in t) and str(y) in t and not any(w in t for w in ['оценка численности','1 января'])
proof=[];byq={};metadata={}
for path,group in a.groupby('source_path'):
 b=Path(path).read_bytes();data=json.loads(gzip.decompress(b) if path.endswith('.gz') else b);h=hashlib.sha256(b).hexdigest()
 for q,g in group.groupby('qid'):
  if q not in data.get('entities',{}):continue
  e=data['entities'][q];metadata[q]=(e,path,h);stmap={s.get('id'):s for s in e.get('claims',{}).get('P1082',[])}
  for r in g[g.year.isin([2002,2010])].itertuples():
   if r.date_class=='non_census_date_observation_hold' or r.rank=='deprecated':continue
   st=stmap[r.statement_id];refs=st.get('references',[]);texts=[];refq=[];urls=[]
   for ref in refs:
    sn=ref.get('snaks',{});refq.extend(v.get('id') for x in sn.get('P248',[]) if isinstance((v:=val(x)),dict));texts.extend(v.get('text','') for x in sn.get('P1476',[]) if isinstance((v:=val(x)),dict));urls.extend(str(val(x)) for x in sn.get('P854',[]))
   methods=[v.get('id') for x in st.get('qualifiers',{}).get('P459',[]) if isinstance((v:=val(x)),dict)];evidence=[]
   if r.date_class=='exact_census_date_secondary':evidence.append('exact_census_P585_date')
   if any(hascensus(labels.get(qi,''),r.year) for qi in refq):evidence.append('explicit_census_P248_reference_label')
   if any(hascensus(t,r.year) for t in texts):evidence.append('explicit_census_P1476_raw_reference_title')
   if r.year==2002 and any('vpn2002' in u.lower() for u in urls):evidence.append('explicit_vpn2002_database_P854_locator')
   # Census method is retained as supporting provenance; unsupported year-only
   # method-only rows remain held unless another actual reference/date establishes census.
   if not evidence:continue
   pr={**r._asdict(),'census_proof_class':';'.join(evidence),'raw_reference_titles_json':json.dumps(texts,ensure_ascii=False),'raw_P248_ids_json':json.dumps(refq),'P248_labels_json':json.dumps([labels.get(q,'') for q in refq],ensure_ascii=False),'raw_P459_method_ids_json':json.dumps(methods),'raw_reference_urls_json':json.dumps(urls),'raw_statement_json':json.dumps(st,ensure_ascii=False),'source_sha256':h};proof.append(pr)
pd.DataFrame(proof).to_csv(O/'census_history_proof_rows.csv',index=False);by=collections.defaultdict(lambda:collections.defaultdict(list))
for p in proof:by[p['qid']][p['year']].append(p)
res=[];held=[];obs=[]
for t in targets.itertuples():
 q=t.qid
 if t.sid in otherids or q in dup or q not in metadata:continue
 e,path,h=metadata[q];cs=e.get('claims',{});des=e.get('descriptions',{}).get('ru',{}).get('value','');hold=[]
 if 'бывш' in des.lower() or cs.get('P576'):hold.append('former_or_dissolved_event_scope')
 if re.match(r'^(муниципаль|район\b|городской округ|сельское поселение|сельсовет)',des.lower()):hold.append('municipal_or_admin_entity_description')
 for st in cs.get('P571',[]):
  dt=val(st.get('mainsnak',{}))
  if isinstance(dt,dict) and int(dt.get('time','+0000')[1:5])>2002:hold.append('founding_after2002_time_contradiction')
 selected={}
 for y in (2002,2010):
  rr=by[q][y];vals={r['population'] for r in rr}
  if len(vals)!=1:hold.append('missing_or_conflicting_actual_census_'+str(y));continue
  selected[y]=sorted(rr,key=lambda r:(not('P248' in r['census_proof_class']),r['statement_id']))[0]
 if hold:held.append({'qid':q,'sid':t.sid,'name':t.name,'population_2021':t.population_2021_selected,'hold_reason':';'.join(hold)});continue
 r={'qid':q,'sid':t.sid,'name':t.name,'type':t.type,'region':t.region,'district':t.district,'population_2021_selected':t.population_2021_selected,'oktmo':t.oktmo,'okato':t.okato,'identity_binding':t.identity_binding,'latitude':t.latitude,'longitude':t.longitude,'point_origin_kind':t.point_origin_kind,'point_origin_locator':t.point_origin_locator,'p2002':selected[2002]['population'],'p2010':selected[2010]['population'],'p2021_native':t.population_2021_selected,'description':des,'P31_json':json.dumps([val(x.get('mainsnak',{})) for x in cs.get('P31',[])]),'optional_Wiki_P625_count':len(cs.get('P625',[])),'source_path':path,'source_sha256':h,'status':'candidate_only_secondary_census_proven_histories_native2021'};res.append(r)
 for y,pr in selected.items():obs.append({**pr,'trajectory_id':'wikidata_native_history:'+q,'source_record_id':'','nonadditive_observation':True,'native_current_source_record_id':t.sid,'ordinary_NP3_asserted':False,'boundary_comparability':'UNKNOWN','point_reuse':'existing accepted own native2021 point; retrospective continuity inference'})
 obs.append({'trajectory_id':'wikidata_native_history:'+q,'qid':q,'year':2021,'population':t.population_2021_selected,'source_record_id':t.sid,'native_current_source_record_id':t.sid,'nonadditive_observation':False,'census_proof_class':'existing_selected_direct_2021_census_value_preserved','ordinary_NP3_asserted':False,'boundary_comparability':'UNKNOWN','point_reuse':'existing accepted own native2021 point'})
pd.DataFrame(res).to_csv(O/'native2021_census_history_candidates.csv',index=False);pd.DataFrame(obs).to_csv(O/'candidate_qualified_physical_observations.csv',index=False);pd.DataFrame(held).to_csv(O/'history_proof_scope_holds.csv',index=False)
r=json.loads((O/'receipt.json').read_text());r.update({'native2021_history_proven_candidate_series':len(res),'native2021_history_proven_population_potential':sum(r['population_2021_selected'] for r in res),'other_route508_IDs_excluded':len(otherids),'all_history_proof_rows':len(proof),'native2021_history_proof_elapsed_seconds':time.monotonic()-T,'historical_source_ID_credit':0,'native2021_rule':'actual selected native2021 census row, not optional Wiki2021 annual claim','method_only_year_precision9_admitted':False});(O/'receipt.json').write_text(json.dumps(r,indent=2,ensure_ascii=False));print(json.dumps({'series':len(res),'population':sum(r['population_2021_selected'] for r in res),'historical_proof_rows':len(proof),'holds':len(held),'elapsed':time.monotonic()-T}));print(pd.DataFrame(res)[['qid','name','population_2021_selected','p2002','p2010']].head(10).to_string(index=False))

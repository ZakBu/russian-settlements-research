from pathlib import Path
import json,gzip,re,pandas as pd,hashlib
O=Path(__file__).parent;E=O.parent;resolved=pd.read_csv(O/'candidate_resolved_components.csv').fillna('');screen=pd.read_csv(O/'own_article_component_point_screen.csv').fillna('');lookup=screen.set_index('wikidata_id');labels={};labelpins={}
for folder in ['additional_uncached_census_histories_20261008','additional_uncached_census_histories_application_20261008']:
 for q,v in json.loads((E/folder/'census_reference_source_witnesses.json').read_text()).items():labels[q]=v['cached_label'];labelpins[q]=v
for folder in ['wikidata_secondary_full3_application_20261007','wikidata_secondary_full3_expansion_application_20261007']:
 f=pd.read_csv(E/folder/'accepted_qualified_physical_observations.csv').fillna('')
 if 'P248_ids_json' not in f.columns:continue
 for t in f.to_dict('records'):
  for q,label in zip(json.loads(t['P248_ids_json']),json.loads(t['P248_labels_json'])):
   if label:labels.setdefault(q,label)
def value(s):return s.get('datavalue',{}).get('value')
def census(tx,y):return any(z in str(tx).lower()for z in ['перепис','census','впн']) and str(y)in str(tx) and not any(z in str(tx).lower()for z in ['оценка численности','1 января'])
rows=[];holds=[]
for t in resolved.to_dict('records'):
 q=t['wikidata_id'];r=lookup.loc[q];native=json.loads(r.all_component_native_context_json);years={v['census_year']for v in native};p=Path(r.source_entity_path);raw=p.read_bytes();d=json.loads(gzip.decompress(raw) if p.name.endswith('.gz') else raw);es=d.get('entities',d.get('payload',{}).get('entities',{})) if 'claims'not in d else {d['id']:d};e=es[q];cs=e['claims']
 if q in ['Q1050596','Q18807511']:
  holds.append({'qid':q,'name':t['name'],'reason':'known_2005_constituent_merger' if q=='Q1050596' else 'own_article_creation_act13Nov2002_after_census; no ordinary2002-own-NP assertion','point_correction_candidate_retained':True});continue
 for y in [2002,2010]:
  if y in years:continue
  actual=[]
  for st in cs.get('P1082',[]):
   v=value(st.get('mainsnak',{}))
   if not isinstance(v,dict)or'amount'not in v or st.get('rank')=='deprecated' or st.get('qualifiers',{}).get('P518'):continue
   refs=st.get('references',[]);titles=[vv.get('text','')for ref in refs for sn in ref.get('snaks',{}).get('P1476',[])if isinstance((vv:=value(sn)),dict)];rq=[vv.get('id')for ref in refs for sn in ref.get('snaks',{}).get('P248',[])if isinstance((vv:=value(sn)),dict)];urls=[str(value(sn))for ref in refs for sn in ref.get('snaks',{}).get('P854',[])]
   for dt in st.get('qualifiers',{}).get('P585',[]):
    d=value(dt)
    if not isinstance(d,dict) or int(d.get('time','+0000')[1:5])!=y:continue
    date=d.get('time');prec=d.get('precision');basis=[]
    if date[1:11]in['2002-10-09','2010-10-14']:basis.append('exact_P585_census_date')
    elif prec!=9:continue
    if any(census(z,y)for z in titles):basis.append('explicit_raw_census_P1476_reference_title')
    if any(census(labels.get(qi,''),y)for qi in rq):basis.append('explicit_cached_P248_census_label')
    if y==2002 and any('vpn2002'in u.lower()for u in urls):basis.append('explicit_vpn2002_source_database')
    if basis:actual.append({'qid':q,'name':t['name'],'year':y,'population':float(v['amount']),'source_record_id':'','nonadditive_observation':True,'statement_id':st['id'],'declared_date':date,'date_precision':prec,'census_proof_class':';'.join(basis),'census_reference_titles_json':json.dumps(titles,ensure_ascii=False),'P248_ids_json':json.dumps(rq),'P248_labels_json':json.dumps([labels.get(qi,'')for qi in rq],ensure_ascii=False),'reference_urls_json':json.dumps(urls),'source_path':str(p),'source_sha256':hashlib.sha256(raw).hexdigest(),'source_locator':'entities.'+q+'.claims.P1082['+st['id']+']','candidate_only':True})
  if len({v['population']for v in actual})==1:rows.append(actual[0])
  else:holds.append({'qid':q,'name':t['name'],'year':y,'reason':'actual_missing_censusyear_no_unique_dated_census_proof','actual_referenced_values':[v['population']for v in actual],'point_correction_candidate_retained':True})
pd.DataFrame(rows).to_csv(O/'actual_secondary_missingyear_census_proofs.csv',index=False);pd.DataFrame(holds).to_csv(O/'historical_scope_or_missing_census_proof_holds.csv',index=False);(O/'census_reference_label_source_witnesses.json').write_text(json.dumps(labelpins,indent=2,ensure_ascii=False));print({'actual_secondary_missingyear_proofs':len(rows),'rows':[{k:v for k,v in r.items()if k in ['qid','name','year','population','census_proof_class']}for r in rows],'holds':holds})

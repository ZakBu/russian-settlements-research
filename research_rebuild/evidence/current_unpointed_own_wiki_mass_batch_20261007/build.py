from pathlib import Path
import sys,json,re,hashlib,time,gzip,collections,urllib.request,urllib.parse
import pandas as pd
T=time.monotonic();R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;W=R/'research_rebuild/work/current_unpointed_own_wiki_mass_batch_20261007';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
s=load(17);before=s.metrics();x=pd.read_csv(W/'exact_code_candidates.csv.gz',dtype={'oktmo':str,'okato':str,'?oktmo':str,'?okato':str}).fillna('');wanted=set(x.qid);found={}
for p in Path('/workspace/settlements-work/continuation_20261004').rglob('*.json'):
 if not any(z in str(p).lower() for z in ['wikidata','entity','qid','q1','q2','q3','q4','q5','q6','q7','q8','q9']):continue
 try:a=json.loads(p.read_text())
 except (ValueError,UnicodeDecodeError):continue
 es=a.get('entities',{}) if isinstance(a,dict) else {}
 if isinstance(a,dict) and 'id'in a and 'claims'in a:es={a['id']:a}
 if not isinstance(es,dict):continue
 for q,e in es.items():
  if q in wanted and isinstance(e,dict) and (q not in found or len(e.get('claims',{}).get('P1082',[]))>len(found[q][0].get('claims',{}).get('P1082',[]))):found[q]=(e,str(p))
missing=set(x[x.population>=1000].qid)-set(found)
if missing:
 u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(sorted(missing)),'props':'labels|descriptions|claims|sitelinks','languages':'ru|en','format':'json'})
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(2000000);p=W/'top_missing_entities.json.gz';p.write_bytes(gzip.compress(b))
  for q,e in json.loads(b).get('entities',{}).items():found[q]=(e,str(p))
 except Exception as ex:print('entity fetch hold',ex)
print('cached targets',len(found),'of',len(wanted),flush=True)
def value(sn):return sn.get('datavalue',{}).get('value')
# Native own codes and names only; no suffix truncation or municipality fallback.
s.obs['n']=s.obs.settlement_name.map(normalize)
idx=collections.defaultdict(list)
for r in s.obs.to_dict('records'):
 for c in ['oktmo','okato']:
  v=str(r[c]);v=v.zfill(11) if v.isdigit() and len(v) in (10,11) else v
  idx[(int(r['census_year']),r['region_norm'],r['n'],c,v)].append(r)
refs={}; rp=R/'research_rebuild/work/current_unpointed_own_wiki_mass_batch_20261007/reference_entities.json.gz'
refids=set()
for q,(e,p) in found.items():
 for st in e.get('claims',{}).get('P1082',[]):
  for ref in st.get('references',[]):
   refids.update(v.get('id') for z in ref.get('snaks',{}).get('P248',[]) if isinstance((v:=value(z)),dict))
for p in [R/'research_rebuild/evidence/wikidata_actual_full3_mass_reserve_20261007/census_reference_checks.csv']:
 if p.exists():
  for a in pd.read_csv(p).fillna('').to_dict('records'):
   for q,l in zip(a['reference_ids'].split(';'),json.loads(a['reference_labels_json'])):refs[q]=l
needed=refids-set(refs)
if needed:
 for n in range(0,len(needed),50):
  ids=sorted(needed)[n:n+50];u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(ids),'props':'labels','languages':'ru|en','format':'json'})
  try:
   b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=20).read(1000000)
   for q,e in json.loads(b).get('entities',{}).items():refs[q]=e.get('labels',{}).get('ru',e.get('labels',{}).get('en',{})).get('value','')
  except Exception as ex:print('ref hold',ex)
rp.write_bytes(gzip.compress(json.dumps(refs,ensure_ascii=False).encode()))
rows=[];points=[];edges=[];holds=[];popclaims=[];series=[]
for sid,g in x.groupby('source_record_id',sort=False):
 t=g.iloc[0].to_dict(); exact=g[g['?oktmo']==t['oktmo'].zfill(11)];gg=exact if len(exact) else g
 qs=set(gg.qid)
 if len(qs)!=1:holds.append({'sid':sid,'name':t['settlement_name'],'reason':'multiple_own_qids_exact_code_name'});continue
 q=next(iter(qs));gg=gg[gg.qid==q];t=gg.iloc[0].to_dict()
 if q not in found:continue
 e,path=found[q];cs=e.get('claims',{});desc=e.get('descriptions',{}).get('ru',{}).get('value','');label=e.get('labels',{}).get('ru',{}).get('value','')
 if any(z in desc.lower() for z in ['муниципальное образование','сельсовет','район города','часть города']) or desc.lower().startswith(('городской округ','муниципальный район','сельское поселение')):
  holds.append({'sid':sid,'name':t['settlement_name'],'reason':'wrong_object_level','qid':q});continue
 coords=[(value(st.get('mainsnak',{})),st.get('rank')) for st in cs.get('P625',[]) if st.get('rank')!='deprecated'];coords=[(v,rank) for v,rank in coords if isinstance(v,dict) and 'latitude'in v and v.get('globe','').endswith('Q2')]
 if not coords:continue
 preferred=[a for a in coords if a[1]=='preferred'];choices=preferred or coords
 if len(choices)>1:
  pair=[(v['latitude'],v['longitude']) for v,rank in choices]
  if max(distance_km(a,b) for a in pair for b in pair)>.5:holds.append({'sid':sid,'name':t['settlement_name'],'qid':q,'reason':'multiple_P625_spatial_conflict'});continue
 v,rank=choices[0];lat,lon=v['latitude'],v['longitude'];point={'target_source_record_id':sid,'latitude':lat,'longitude':lon,'coordinate_admission_status':'candidate_only_requires_independent_review','coordinate_source_record_id':q,'point_origin_file':path,'point_origin_sha256':sha(Path(path)),'point_origin_locator':f'entities.{q}.claims.P625; rank={rank}; coherent_candidates={len(choices)}','point_origin_kind':'wikidata_own_physical_locality_P625','coordinate_binding_rule':'exact_current_native_own_code_and_exact_name;leading_zero_restore_only11digit; own_entity_description; source_county_context','source_county':t['district_raw'],'own_description':desc,'wikidata_label':label,'own_code':t['?oktmo'],'own_okato':t['?okato'],'source_name':t['settlement_name'],'source_type':t['settlement_type'],'target_year':2021,'population':t['population'],'bounds':'UNKNOWN','error_rate':'uncalibrated'}
 points.append(point); ids={2021:sid};native={2021:s.by_id.loc[sid].to_dict()};used={s.uf.find(sid)}
 for year in (2002,2010):
  existing=s.obs[(s.obs.root==s.uf.find(sid))&(s.obs.census_year==year)]
  if len(existing)==1:rr=existing.iloc[0].to_dict();ids[year]=rr['source_record_id'];native[year]=rr;continue
  matches={}
  for c,prop in [('oktmo','P764'),('okato','P635')]:
   codes={str(t[c]).zfill(11),str(t['?'+c])}
   codes.update(str(value(st.get('mainsnak',{}))) for st in cs.get(prop,[]))
   for code in codes:
    for rr in idx.get((year,t['region_norm'],normalize(t['settlement_name']),c,code),[]):
     if normalize(rr['settlement_type'])==normalize(t['settlement_type']):matches[rr['source_record_id']]=rr
  if len(matches)==1:
   rr=next(iter(matches.values()));root=s.uf.find(rr['source_record_id'])
   if not s.years[root]&{2021} and root not in used:
    ids[year]=rr['source_record_id'];native[year]=rr;used.add(root)
    edges.append({'from_source_record_id':sid,'to_source_record_id':rr['source_record_id'],'relation':'same_place','decision_status':'candidate_only_requires_independent_review','evidence_rule':'own_raw_current_or_entity_OKATO_OKTMO_exact_code_name_type_region;county_pending','wikidata_qid':q,'source_file':rr['source_file'],'source_locator':rr['source_locator'],'source_sha256':rr['source_sha256'],'native_county':rr['district_raw'],'current_county':t['district_raw']})
 by=collections.defaultdict(list)
 for st in cs.get('P1082',[]):
  val=value(st.get('mainsnak',{}))
  if not isinstance(val,dict) or 'amount'not in val:continue
  for dt in st.get('qualifiers',{}).get('P585',[]):
   d=value(dt)
   if not isinstance(d,dict):continue
   y=int(d.get('time','+0000')[1:5])
   if y not in (2002,2010,2021):continue
   rids=[v.get('id') for ref in st.get('references',[]) for z in ref.get('snaks',{}).get('P248',[]) if isinstance((v:=value(z)),dict)];ls=[refs.get(q,'') for q in rids];confirmed=any(('перепис' in l.lower() or 'census' in l.lower()) and (str(y) in l or y==2021 and '2020' in l) for l in ls);qualified=confirmed and d.get('precision')==9 or confirmed and d.get('time','')[1:11] in ('2002-10-09','2010-10-14','2021-10-01')
   pr={'sid':sid,'qid':q,'year':y,'population':float(val['amount']),'declared_date':d.get('time'),'precision':d.get('precision'),'statement_id':st.get('id'),'references':';'.join(rids),'reference_labels_json':json.dumps(ls,ensure_ascii=False),'qualified_explicit_census':qualified,'source_file':path,'source_sha256':point['point_origin_sha256'],'source_locator':f'entities.{q}.claims.P1082[{st.get("id")}]','rank':st.get('rank')};popclaims.append(pr)
   if qualified and st.get('rank')!='deprecated':by[y].append(pr)
 full=True;sr=[]
 for y in (2002,2010,2021):
  rr=native.get(y)
  if rr:r={'sid':sid,'qid':q,'year':y,'population':rr['population'],'selected_source_record_id':rr['source_record_id'],'source_file':rr['source_file'],'source_sha256':rr['source_sha256'],'source_locator':rr['source_locator'],'population_quality':rr['population_value_quality'],'native_county':rr['district_raw'],'status':'candidate_native_own_identity_county_review_pending'}
  elif by[y] and len({p['population'] for p in by[y]})==1:r={**by[y][0],'selected_source_record_id':'','population_quality':'secondary_explicit_census_reference','status':'candidate_secondary_own_physical_observation_continuity_pending'}
  else:full=False;continue
  sr.append(r)
 if full:
  for rr in native.values():
   if rr['source_record_id'] not in s.point_rows:
    pp=point.copy();pp.update(target_source_record_id=rr['source_record_id'],target_year=int(rr['census_year']),population=rr['population']);pp['point_use_inference']='modern_own_representative_point_historical_sameplace_continuity_pending';
    if pp['target_source_record_id']!=sid:points.append(pp)
  series.extend(sr)
 rows.append({'sid':sid,'qid':q,'name':t['settlement_name'],'type':t['settlement_type'],'region':t['region_norm'],'current_county':t['district_raw'],'population_2021':t['population'],'native_years':';'.join(map(str,sorted(ids))),'actual_full3_available':full,'description':desc,'source_file':path,'source_sha256':point['point_origin_sha256'],'latitude':lat,'longitude':lon,'status':'candidate_only_not_admitted'})
for name,data in [('candidate_points',points),('candidate_identity_edges',edges),('candidate_actual_full3_series',series),('own_current_inventory',rows),('target_census_claims',popclaims),('holds',holds)]:pd.DataFrame(data).to_csv(O/(name+'.csv'),index=False)
receipt={'stage':17,'baseline_ordinary':before,'unpointed_scope':3436,'unpointed_population_2021':261318,'cache_code_name_point_candidates':len(x),'cached_own_entity_qids':len(found),'own_current_point_candidate_count':len(rows),'own_current_candidate_population':sum(r['population_2021'] for r in rows),'actual_full3_series_candidate_count':sum(r['actual_full3_available'] for r in rows),'actual_full3_population_2021':sum(r['population_2021'] for r in rows if r['actual_full3_available']),'candidate_edges':len(edges),'actual_admitted_gain':0,'wall_seconds':time.monotonic()-T,'population_native_protected':True,'caveat':'Native-code/current own binding and all actual3 observations available; historical county/type continuity and coordinate-object conflicts need independent review before admission.'}
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))

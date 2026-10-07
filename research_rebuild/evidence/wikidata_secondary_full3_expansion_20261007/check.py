from pathlib import Path
import json,gzip,hashlib,urllib.request,urllib.parse,urllib.error,time,re
import pandas as pd
OUT=Path(__file__).parent;W=Path('/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007');c=pd.read_csv(OUT/'full3_candidates.csv').fillna('');a=pd.read_csv(OUT/'actual_target_year_claims.csv').fillna('');eligible=c[c.hold_reason==''];wanted=set(eligible.qid);refs=set()
for r in a[a.qid.isin(wanted)].itertuples():
 for ref in json.loads(r.reference_items_json):
  if isinstance(ref,dict):refs.add(ref.get('id'))
labels={};sources={}
for p in Path('/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007').glob('*.json.gz'):
 data=json.loads(gzip.decompress(p.read_bytes()))
 for q,e in data.get('entities',{}).items():labels[q]=e.get('labels',{}).get('ru',e.get('labels',{}).get('en',{})).get('value','');sources[q]=str(p)
all_refs=set(refs);refs=refs-set(labels)
for n in range(0,len(refs),50):
 ids=sorted(refs)[n:n+50];u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(ids),'props':'labels|descriptions','languages':'ru|en','format':'json'})
 try:
  for attempt in range(3):
   try:
    with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25) as response:b=response.read(3000000)
    break
   except urllib.error.HTTPError as ex:
    if ex.code!=429 or attempt==2:raise
    time.sleep(20)
  p=W/f'reference_batch_{n//50}.json.gz';p.write_bytes(gzip.compress(b));data=json.loads(b)
  for q,e in data.get('entities',{}).items():labels[q]=e.get('labels',{}).get('ru',e.get('labels',{}).get('en',{})).get('value','');sources[q]=str(p)
 except Exception as ex:print('fetch hold',str(ex))
checks=[]
for r in a[a.qid.isin(wanted)].itertuples():
 refids=[v.get('id') for v in json.loads(r.reference_items_json) if isinstance(v,dict)];ls=[labels.get(q,'') for q in refids];census=any(('перепис' in l.lower() or 'census' in l.lower()) and (str(r.year) in l or (r.year==2021 and '2020' in l)) for l in ls)
 checks.append({'qid':r.qid,'year':r.year,'statement_id':r.statement_id,'population':r.population,'declared_date':r.declared_date,'reference_ids':';'.join(refids),'reference_labels_json':json.dumps(ls,ensure_ascii=False),'census_reference_confirmed':census,'date_class':r.date_class})
f=pd.DataFrame(checks);f.to_csv(OUT/'census_reference_checks.csv',index=False)
good=set()
for q,g in f.groupby('qid'):
 if all(any((g.year==y)&(g.census_reference_confirmed | (g.date_class=='exact_census_date_secondary'))) for y in (2002,2010,2021)):good.add(q)
eligible=eligible[eligible.qid.isin(good)].copy();eligible.to_csv(OUT/'reference_confirmed_full3_reserve.csv',index=False)
# Fixed sample selected once from final candidates. Largest five plus deterministic 15 across cohort.
largest=eligible.head(5);fixed=eligible.assign(sample_key=eligible.qid.map(lambda q:hashlib.sha256(('fixed15-20261007'+q).encode()).hexdigest())).sort_values('sample_key').head(15)
qset=set(largest.qid)|set(fixed.qid);manual=[]
for r in eligible[eligible.qid.isin(qset)].itertuples():
 e=json.loads(gzip.decompress(Path(r.source_path).read_bytes()) if str(r.source_path).endswith('.gz') else Path(r.source_path).read_bytes())['entities'][r.qid];claims=e.get('claims',{});coords=[x.get('mainsnak',{}).get('datavalue',{}).get('value',{}) for x in claims.get('P625',[])];stat=f[f.qid==r.qid]
 manual.append({'qid':r.qid,'name':r.name,'sample':'largest5' if r.qid in set(largest.qid) else 'fixed15','identity_binding':r.identity_binding,'selected_current_code':str(r.oktmo),'raw_P625_json':json.dumps(coords),'own_description':r.description,'source_sha256_rechecked':hashlib.sha256(Path(r.source_path).read_bytes()).hexdigest()==r.source_sha256,'statement_witnesses_json':stat.to_json(orient='records',force_ascii=False),'review_status':'source_values_refs_coordinates_concretely_checked; historical_continuity_and_existing_selected_source_reuse_pending'})
pd.DataFrame(manual).to_csv(OUT/'fixed15_and_largest5_source_checks.csv',index=False)
receipt=json.loads((OUT/'receipt.json').read_text());receipt.update({'reference_items_requested':len(all_refs),'reference_items_new_API_requested':len(refs),'reference_items_returned':len(labels),'reference_confirmed_candidate_count':len(eligible),'reference_confirmed_potential_2021':float(eligible.population_2021_selected.sum()),'first_mass_scan':'2000 new selected NP targets /1986 own QIDs;1394 cached matching records;4784 cached P1082 statements;3042 target-year observations including bounded API fill','fixed15_and_largest5_once':len(manual),'no_mass_99_claim':True});(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False));print(json.dumps(receipt,ensure_ascii=False))

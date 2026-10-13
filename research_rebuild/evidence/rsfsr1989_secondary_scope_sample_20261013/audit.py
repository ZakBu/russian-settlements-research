from pathlib import Path
import pyarrow.parquet as pq,random,json,urllib.request,urllib.parse,hashlib,datetime,collections
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/rsfsr1989_secondary_scope_sample_20261013');P=Path('/workspace/scratch/rsfsr1989_secondary_mass_20261013/secondary_population_1989_long.parquet')
rows=pq.read_table(P).to_pylist();rows=sorted(rows,key=lambda x:(x['wikidata_qid'],x['statement_uri_raw']));rng=random.Random(19891013);chosen=[];seen=set()
def take(pool,n,stratum):
 pool=[r for r in pool if r['statement_uri_raw'] not in seen];rng.shuffle(pool)
 for r in pool[:n]:chosen.append({**r,'sample_stratum':stratum});seen.add(r['statement_uri_raw'])
# Explicit city subjects retained to test the known city/territory scope concern.
for r in rows:
 if r['wikidata_qid'] in ['Q649','Q656']:chosen.append({**r,'sample_stratum':'large_urban'});seen.add(r['statement_uri_raw'])
take([r for r in rows if r['current_type']=='город' and r['population_value']>=100000],8,'large_urban')
take([r for r in rows if 'tochno_20260925_oktmo_new_undated' in r['binding_code_axes_json']],4,'publisher_undated_code_alias')
take([r for r in rows if r['current_type']=='пгт'],8,'PGT')
take([r for r in rows if r['current_type'] in ['село','деревня','хутор','станица','аул']],8,'rural')
assert len(chosen)==30
(H/'sample.json').write_text(json.dumps(chosen,ensure_ascii=False,indent=2)+'\n')
qs=sorted({r['wikidata_qid'] for r in chosen});url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(qs),'props':'claims','format':'json'})
receipt={'seed':19891013,'population_frame_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'sample_claims':30,'sample_distinct_items':len(qs),'strata':dict(collections.Counter(r['sample_stratum'] for r in chosen)),'url':url,'TLS_verification':'default_normal_TLS','requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_mass_outputs_unchanged':True}
try:
 request=urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0 (source provenance scope audit)'})
 with urllib.request.urlopen(request,timeout=45) as response:data=response.read();receipt['http_status']=response.status
 O.joinpath('wbgetentities_sample.json').write_bytes(data);receipt['response_sha256']=hashlib.sha256(data).hexdigest();payload=json.loads(data);entities=payload.get('entities',{});out=[]
 for r in chosen:
  guid=r['statement_uri_raw'].split('/')[-1].rstrip('>').replace('-', '$',1);claims=entities.get(r['wikidata_qid'],{}).get('claims',{}).get('P1082',[]);candidates=[c for c in claims if c.get('id','').casefold()==guid.casefold()]
  a={'qid':r['wikidata_qid'],'statement_uri_raw':r['statement_uri_raw'],'sample_stratum':r['sample_stratum'],'anchor_source_record_id':r['anchor_source_record_id'],'flat_value':r['population_value'],'full_GUID_match_count':len(candidates)}
  if len(candidates)==1:
   c=candidates[0];qual=c.get('qualifiers',{});quantity=c.get('mainsnak',{}).get('datavalue',{}).get('value',{});a.update({'full_statement':c,'unit':quantity.get('unit'),'amount':quantity.get('amount'),'qualifier_properties':sorted(qual),'P518_present':'P518' in qual,'P585_values':[s.get('datavalue',{}).get('value') for s in qual.get('P585',[])],'reference_P248':[s.get('datavalue',{}).get('value') for ref in c.get('references',[]) for s in ref.get('snaks',{}).get('P248',[])],'rank':c.get('rank')})
  out.append(a)
 H.joinpath('claim_scope_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');receipt['audit_matched_GUIDs']=sum(r['full_GUID_match_count']==1 for r in out)
except Exception as e:receipt['request_blocked_or_failed']=str(e);receipt['failure_type']=type(e).__name__
H.joinpath('receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))

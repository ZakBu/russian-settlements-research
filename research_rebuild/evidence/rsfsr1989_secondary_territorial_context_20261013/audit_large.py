from pathlib import Path
import pyarrow.parquet as pq,json,urllib.request,urllib.parse,hashlib
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/rsfsr1989_secondary_territorial_context_20261013');rows=pq.read_table(O/'secondary_population_1989_long.parquet').to_pylist();old=pq.read_table('/workspace/scratch/rsfsr1989_secondary_okato_extension_20261013/secondary_population_1989_long.parquet').to_pylist();keys={r['statement_uri_raw'].casefold() for r in old};new=[r for r in rows if r['statement_uri_raw'].casefold() not in keys];large=new if len(new)<=50 else [r for r in new if r['population_value']>=100000];qs=sorted({r['wikidata_qid'] for r in large});entities={};requests=[]
for i in range(0,len(qs),50):
 ids=qs[i:i+50];url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(ids),'props':'claims|labels','languages':'ru|en','format':'json'});record={'url':url,'TLS':'normal_default_verification'}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0 (physical subject scope audit)'}),timeout=30) as resp:b=resp.read();record['http_status']=resp.status
  p=H/f'large_entity_batch_{i//50:03d}.json';p.write_bytes(b);record['sha256']=hashlib.sha256(b).hexdigest();entities.update(json.loads(b).get('entities',{}))
 except Exception as e:record['failure']=str(e)
 requests.append(record)
out=[]
for r in large:
 e=entities.get(r['wikidata_qid'],{});guid=r['statement_uri_raw'].split('/')[-1].rstrip('>').replace('-','$',1);claim=[c for c in e.get('claims',{}).get('P1082',[]) if c.get('id','').casefold()==guid.casefold()];p31=[s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for s in e.get('claims',{}).get('P31',[])];a={'qid':r['wikidata_qid'],'anchor_source_record_id':r['anchor_source_record_id'],'current_name':r['current_name'],'population1989':r['population_value'],'P31_ids':p31,'GUID_matched':len(claim)==1}
 if len(claim)==1:
  c=claim[0];v=c.get('mainsnak',{}).get('datavalue',{}).get('value',{});a.update({'unit':v.get('unit'),'amount':v.get('amount'),'qualifier_properties':sorted(c.get('qualifiers',{})),'full_statement':c,'P518_present':'P518' in c.get('qualifiers',{})})
 out.append(a)
(H/'large_subject_scope_audit.json').write_text(json.dumps({'requests':requests,'new_claims':len(new),'large_claims':len(large),'audit':out},ensure_ascii=False,indent=2)+'\n');print(json.dumps({'new_claims':len(new),'large_claims':len(large),'large_audit':[{k:v for k,v in a.items() if k!='full_statement'} for a in out]},ensure_ascii=False))

from pathlib import Path
import json,gzip,urllib.request,urllib.parse,datetime,hashlib
O=Path(__file__).parent
names=['Китой (Ангарск)', 'Менделеево', 'Иртышский (Тюменская область)', 'Опалиха', 'Фосфоритный', 'Берёзовка (Алтайский край)', 'Красноярская (Ростовская область)', 'Первомайский (Слободской)', 'Гундоровский (Ростовская область)', 'Гундоровский (посёлок)']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(names),'prop':'revisions|pageprops|coordinates','rvprop':'ids|content|timestamp','rvslots':'main','format':'json','redirects':1,'colimit':'max'})
try:
 with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30) as response:b=response.read(6500000);status=response.status
 (O/'own_wikipedia_qualified_batch.json.gz').write_bytes(gzip.compress(b));f=json.loads(b);records=[]
 for p in f.get('query',{}).get('pages',{}).values():records.append({'title':p['title'],'qid':p.get('pageprops',{}).get('wikibase_item'),'missing':'missing' in p,'pageid':p.get('pageid'),'revid':p.get('revisions',[{}])[0].get('revid')})
 print(json.dumps(records,ensure_ascii=False))
 (O/'qualified_fetch_receipt.json').write_text(json.dumps({'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'request_url':u,'normal_TLS_verification':True,'HTTP_status':status,'uncompressed_bytes':len(b),'compressed_bytes':(O/'own_wikipedia_qualified_batch.json.gz').stat().st_size,'requested_titles':names,'saved_sha256':hashlib.sha256((O/'own_wikipedia_qualified_batch.json.gz').read_bytes()).hexdigest(),'pages':records},ensure_ascii=False,indent=2))
except Exception as e:
 (O/'qualified_fetch_failure.json').write_text(json.dumps({'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'request_url':u,'normal_TLS_verification':True,'error':str(e),'retry_or_bypass_performed':False},ensure_ascii=False,indent=2));raise

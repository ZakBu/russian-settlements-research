from pathlib import Path
import requests,json,hashlib,datetime,sys
from bs4 import BeautifulSoup
H=Path(__file__).resolve().parent
session=requests.Session();session.headers['User-Agent']='Mozilla/5.0 (research source verification)'
def acquire(key,url):
 target=H/'sources'/key;target.mkdir(parents=True,exist_ok=True);receipt=target/'acquisition.json'
 if receipt.exists():return json.loads(receipt.read_text())
 result={'key':key,'requested_url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  r=session.get(url,timeout=45);raw=r.content;typ=r.headers.get('Content-Type','');ext='.pdf' if raw.startswith(b'%PDF') else '.html';p=target/('source'+ext);p.write_bytes(raw);result.update(status_code=r.status_code,final_url=r.url,content_type=typ,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),file=str(p.relative_to(H)),http_headers=dict(r.headers))
  if ext=='.html':
   r.encoding=r.apparent_encoding or r.encoding;text=BeautifulSoup(r.text,'html.parser').get_text('\n',strip=True);(target/'extracted_text.txt').write_text(text);result['text_sha256']=hashlib.sha256(text.encode()).hexdigest();result['decoding']=r.encoding
 except Exception as e:result.update(error=str(e),status_code=None)
 receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:result.get(k) for k in ['key','status_code','bytes','content_type','error']},ensure_ascii=False),flush=True);return result
if __name__=='__main__':
 for k,u in json.loads(Path(sys.argv[1]).read_text()):acquire(k,u)

"""Read-only public-source acquisition with bounded bodies and full local receipts."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,urllib.request,urllib.error

ROOT=Path(__file__).resolve().parent
def fetch(name,url,limit=20000000,timeout=30):
    bodyfile=ROOT/'raw'/name
    receipt=bodyfile.with_name(bodyfile.name+'.request.json')
    if bodyfile.exists() and receipt.exists():
        return bodyfile.read_bytes(),json.loads(receipt.read_text())
    meta={'url':url,'requested_at':datetime.now(timezone.utc).isoformat(),'limit_bytes':limit}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'settlement-research-public-source-audit/1.0'}),timeout=timeout)as r:
            b=r.read(limit+1);meta.update({'status':r.status,'resolved_url':r.url,'headers':dict(r.headers)})
    except urllib.error.HTTPError as e:
        b=e.read(limit+1);meta.update({'status':e.code,'error':str(e),'headers':dict(e.headers)})
    except Exception as e:
        b=b'';meta['error']=str(e)
    if len(b)>limit:
        meta['truncated']=True;b=b[:limit]
    meta.update({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'body':str(bodyfile.relative_to(ROOT))})
    bodyfile.write_bytes(b);receipt.write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    return b,meta

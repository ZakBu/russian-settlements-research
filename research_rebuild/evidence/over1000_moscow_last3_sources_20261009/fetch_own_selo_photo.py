from pathlib import Path
import urllib.request,gzip,json,re,time
O=Path(__file__).parent
for cid in [59686,1448580,754794]:
 u=f'https://pastvu.com/p/{cid}'
 with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:b=r.read(1500000);st=r.status
 (O/f'own_selo_photo_{cid}.html.gz').write_bytes(gzip.compress(b));(O/f'own_selo_photo_{cid}_request.json').write_text(json.dumps({'url':u,'status':st,'normal_TLS':True}))
 t=b.decode();m=re.search(r'\bphoto\s*:',t);j=json.JSONDecoder().raw_decode(t[m.end():].lstrip())[0]['photo'];safe={k:j.get(k)for k in ['cid','title','geo','year','year2','address','desc','source','file']};(O/f'own_selo_photo_{cid}_witness.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2));print(safe,flush=True);time.sleep(1.3)

"""Read-only acquisition of primary open literature used for methodological framing."""
import urllib.request,hashlib,json
from pathlib import Path
P=Path(__file__).resolve().parent
sources=[
 ('cheshire2018.pdf','https://eprints.lse.ac.uk/89191/1/Chesire_Take_me_to_centre_Published.pdf'),
 ('verhetsel2022.pdf','https://repository.uantwerpen.be/docman/irua/b606f4/regional_retail_landscapes_emerging_from_spatial_network_analysis__1_.pdf'),
 ('le2022_review.pdf','https://www.tandfonline.com/doi/pdf/10.1080/01441647.2021.1961917'),
 ('vansandt2025.html','https://link.springer.com/article/10.1186/s40008-025-00359-0'),
 ('butts2023.pdf','https://arxiv.org/pdf/2105.03737')]
r=[]
for name,url in sources:
 dest=P/name
 try:
  if dest.exists():raw=dest.read_bytes();status='reused_local'
  else:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
   with urllib.request.urlopen(req,timeout=25) as h:raw=h.read();status=h.status
   if name.endswith('.pdf'):assert raw.startswith(b'%PDF'),raw[:30]
   dest.write_bytes(raw)
  r.append({'file':name,'url':url,'status':status,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 except Exception as e:r.append({'file':name,'url':url,'error':str(e)})
 print(name,r[-1].get('bytes',r[-1].get('error')),flush=True)
(P/'source_acquisition.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))

from pathlib import Path
import json,re,hashlib,collections
H=Path(__file__).parent;E=H.parent;O=Path('/workspace/shared/historical_full_cache_gap');files=[E/'rsfsr1989_rural_volga_20261013'/'tatarica_download_manifest.jsonl',E/'rsfsr1989_rural_volga_20261013'/'bashenc_download_manifest.jsonl',E/'rsfsr1989_rural_bashenc_delta_20261013'/'bashenc_download_manifest.jsonl'];rows=[];summary=[]
for p in files:
 n=0;zc=collections.Counter();literal=collections.Counter();missing=0
 for i,line in enumerate(p.open()):
  r=json.loads(line);n+=1
  # Numeric manifest zero and explicitly year-associated literal zero only. null/missing never becomes zero.
  for y in [1979,1989]:
   if type(r.get(f'population_{y}')) in (int,float) and r[f'population_{y}']==0:zc[y]+=1;rows.append({'manifest':str(p),'row_0based':i,'year':y,'kind':'explicit_numeric_field_zero','record':r})
   t=r.get('popsec') or ''
   for m in re.finditer(r'(?<!\d)'+str(y)+r'\s*(?:г(?:од)?\.?\s*)?[,:—–−-]\s*0(?![\d.,])',t):literal[y]+=1;rows.append({'manifest':str(p),'row_0based':i,'year':y,'kind':'explicit_literal_year_zero','context':t[max(0,m.start()-60):m.end()+80],'record':r})
  if r.get('population_1989') is None:missing+=1
 summary.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'manifest_rows':n,'explicit_numeric_zero_by_year':dict(zc),'explicit_literal_zero_by_year':dict(literal),'population1989_null_rows_NOT_zero':missing})
receipt={'manifests':summary,'total_manifest_rows':sum(z['manifest_rows'] for z in summary),'explicit_zero_hits':len(rows),'zero_candidate_subjects':len({(z['record'].get('url'),z['year']) for z in rows}),'candidate_rows':rows,'no_api_or_new_downloads':True,'scope':'Tatarica and Bashenc existing population-section download manifests; excludes missing year/null and inference from depopulation prose','binding_required':bool(rows),'no_mass_gain':not bool(rows)}
(H/'manifest_explicit_zero_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));(O/'manifest_explicit_zero_receipt.json').write_text((H/'manifest_explicit_zero_receipt.json').read_text());print(json.dumps(receipt,ensure_ascii=False,indent=2))

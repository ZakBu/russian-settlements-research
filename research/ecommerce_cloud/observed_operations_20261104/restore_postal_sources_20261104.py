#!/usr/bin/env python3
"""Restore pinned 2023 geography and independent address documents to ignored work.

No requests dependency. Input documents are not copied to tracked outputs.
"""
import argparse,base64,gzip,hashlib,json,subprocess,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--work',type=Path,default=ROOT/'work/ecommerce_operations_20261104/sources')
 args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True)
 reg=json.loads((HERE/'postal_case_sources.json').read_text());oz=reg['ozon_historical_source']
 inputs=[{'source_id':oz['source_id'],'url':oz['archive_url'],'sha256':oz['sha256_decoded'],'filename':oz['filename'],'cdx_sha1':oz['cdx_sha1']}]+[{**r,'filename':Path(r['raw_file']).name} for r in reg['independent_address_sources']]
 result=[]
 for r in inputs:
  path=args.work/r['filename'];event={'source_id':r['source_id'],'url':r['url'],'filename':r['filename']}
  if path.exists():body=path.read_bytes();event['cached']=True
  else:
   with urllib.request.urlopen(urllib.request.Request(r['url'],headers={'User-Agent':'settlement-research/1.0'}),timeout=45) as response:
    wire=response.read(25*1024*1024+1);event['resolved_url']=response.url
   if len(wire)>25*1024*1024:raise ValueError('Source unexpectedly large')
   if 'cdx_sha1' in r:
    assert base64.b32encode(hashlib.sha1(wire).digest()).decode().rstrip('=')==r['cdx_sha1'],'CDX archive payload mismatch'
   body=gzip.decompress(wire) if wire[:2]==b'\x1f\x8b' else wire
   assert hashlib.sha256(body).hexdigest()==r['sha256'],'SHA256 mismatch'
   path.write_bytes(body);event['cached']=False
  assert hashlib.sha256(body).hexdigest()==r['sha256'],'Cached source differs from pin'
  subprocess.run(['pdftotext','-layout',str(path),str(path.with_suffix('.txt'))],check=True)
  event['sha256_matches']=True;result.append(event)
 (args.work/'restore_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'restored_sources_n':len(result),'all_pins_match':True}))
if __name__=='__main__':main()

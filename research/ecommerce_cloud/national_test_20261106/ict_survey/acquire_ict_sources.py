#!/usr/bin/env python3
"""Restore public Rosstat SAV payloads from pinned Internet Archive captures.

One request per missing file, no automatic retries and no CAPTCHA/rate-limit
bypasses. Existing local bodies are independently verified and reused.
"""
from pathlib import Path
from urllib.request import Request,urlopen
import argparse,base64,hashlib,json
ROOT=Path(__file__).resolve().parents[4]
D=Path(__file__).resolve().parent
W=ROOT/'work/ecommerce_national_test_20261106/ict_survey'
def main():
 p=argparse.ArgumentParser();p.add_argument('--years',nargs='+',type=int,default=[2024]);a=p.parse_args()
 W.mkdir(parents=True,exist_ok=True);members=json.loads((D/'ict_archive_members.json').read_text())['members'];manifest=[]
 for year in a.years:
  m=next(m for m in members if m['year']==year);out=W/m['file_name']
  if out.exists():body=out.read_bytes();via='verified_existing_local_body'
  else:
   req=Request(m['archive_url'],headers={'User-Agent':'settlements-research-public-ict/1.0'})
   with urlopen(req,timeout=90) as r:body=r.read(150*1024*1024);assert r.status==200
   via='public_archive'
  assert body.startswith(b'$FL2') or body.startswith(b'$FL3'), 'Not an SPSS system file'
  actual=base64.b32encode(hashlib.sha1(body).digest()).decode().rstrip('=')
  assert actual==m['archive_payload_sha1_base32'], 'Archived payload SHA1 differs from CDX'
  out.write_bytes(body);manifest.append({**m,'archive_index_only_until_body_verified':False,'sha1_verified':True,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'path':str(out.relative_to(ROOT)),'acquisition_mode':via})
  print(year,len(body),actual,'verified')
 (D/'ict_source_pins.json').write_text(json.dumps({'payloads':manifest},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()

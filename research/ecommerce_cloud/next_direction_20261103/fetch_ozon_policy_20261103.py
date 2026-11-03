#!/usr/bin/env python3
"""Restore byte-pinned primary tariff geography and its historical semantic link.

Default: 2022 list plus 2023 frontend. --include-contracts restores four legal
versions. --include-expanded-list also restores the larger 2023 list. Bodies
remain in ignored work/. Linux pdftotext is required for PDF extraction.
"""
import argparse,base64,gzip,hashlib,json,subprocess,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--work',type=Path,default=ROOT/'work/ecommerce_next_20261103/identification')
 p.add_argument('--include-contracts',action='store_true')
 p.add_argument('--include-expanded-list',action='store_true')
 args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((HERE/'identification_policy_sources.json').read_text());events=[]
 for row in manifest['sources']:
  if row['group']=='contract' and not args.include_contracts:continue
  if row['group']=='eligibility2023' and not args.include_expanded_list:continue
  path=args.work/row['filename'];event={'source_id':row['source_id'],'url':row['archive_url'],'filename':row['filename']}
  wire_path=args.work/row['wire_filename'] if 'wire_filename' in row else None
  if wire_path is not None and wire_path.exists():
   cached_wire=wire_path.read_bytes()
   if hashlib.sha256(cached_wire).hexdigest()!=row['sha256_wire_gzip']:
    raise ValueError('Cached compressed payload SHA256 mismatch')
   if base64.b32encode(hashlib.sha1(cached_wire).digest()).decode().rstrip('=')!=row['cdx_sha1']:
    raise ValueError('Cached compressed payload CDX SHA1 mismatch')
   event['cdx_sha1_payload_matches']=True
  if path.exists() and (wire_path is None or wire_path.exists()):
   body=path.read_bytes();event['retrieval']='cached_byte_pinned_body'
  else:
   with urllib.request.urlopen(urllib.request.Request(row['archive_url'],headers={'User-Agent':'settlement-research/1.0','Accept-Encoding':'gzip'}),timeout=45) as f:
    wire=f.read(25*1024*1024+1);headers=dict(f.headers);event.update(retrieval='HTTP',resolved_url=f.url,headers=headers)
   if len(wire)>25*1024*1024:raise ValueError('Unexpected source size')
   body=gzip.decompress(wire) if wire[:2]==b'\x1f\x8b' else wire
   if 'cdx_sha1' in row:
    actual=base64.b32encode(hashlib.sha1(wire).digest()).decode().rstrip('=')
    event['cdx_sha1_payload_matches']=actual==row['cdx_sha1']
    if not event['cdx_sha1_payload_matches']:
     raise ValueError('Archive payload differs from CDX digest; do not use as historical evidence')
   if hashlib.sha256(body).hexdigest()!=row['sha256_decoded']:raise ValueError('Decoded SHA256 mismatch')
   if wire_path is not None:
    if hashlib.sha256(wire).hexdigest()!=row['sha256_wire_gzip'] or len(wire)!=row['bytes_wire_gzip']:
     raise ValueError('Compressed source payload differs from pinned wire bytes')
    wire_path.write_bytes(wire)
   path.write_bytes(body)
  if len(body)!=row['bytes_decoded'] or hashlib.sha256(body).hexdigest()!=row['sha256_decoded']:
   raise ValueError('Cached file differs from pinned source')
  event['decoded_sha256_matches']=True
  if path.suffix=='.pdf':
   if not body.startswith(b'%PDF'):raise ValueError('Not PDF')
   subprocess.run(['pdftotext','-layout',str(path),str(path.with_suffix('.txt'))],check=True)
  events.append(event)
 (args.work/'policy_restore_results.json').write_text(json.dumps(events,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'restored_sources_n':len(events),'all_sha256_match':all(x['decoded_sha256_matches'] for x in events)},indent=2))
if __name__=='__main__':main()

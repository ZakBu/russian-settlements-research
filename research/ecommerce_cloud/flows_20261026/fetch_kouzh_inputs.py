#!/usr/bin/env python3
"""Restore pinned KOUZh public members using HTTP Range, not a full ZIP download.

The ZIP member CRC and the pinned SHA256 are verified. Individual rows remain in
ignored work/. Public microdata are used only for statistical aggregates. No
attempt is made to recover a named locality from anonymous household IDs.
"""
import argparse,hashlib,importlib.util,json,subprocess,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'work/ecommerce_flows_20261026')
    p.add_argument('--extract',action='store_true')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    pins=json.loads((HERE/'kouzh_source_members.json').read_text())
    spec=importlib.util.spec_from_file_location('survey_range_reader',HERE.parent/'continuation/surveys_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    remote=None;archive=None;receipt=[]
    try:
        for pin in pins['members']:
            out=args.output/pin['filename'];cached=out.exists()
            if cached:
                raw=out.read_bytes()
            else:
                if archive is None:
                    remote=module.RangeZIP(pins['archive_url'])
                    archive=zipfile.ZipFile(remote)
                info=archive.getinfo(pin['member'])
                if info.file_size!=pin['bytes'] or '%08x'%info.CRC!=pin['crc32']:
                    raise ValueError('ZIP member metadata changed: '+pin['filename'])
                raw=archive.read(info) # zipfile validates the decompressed member CRC
            if len(raw)!=pin['bytes'] or hashlib.sha256(raw).hexdigest()!=pin['sha256']:
                raise ValueError('Pinned SHA mismatch; existing file preserved: '+pin['filename'])
            if not cached:out.write_bytes(raw)
            if args.extract and out.suffix=='.pdf':
                subprocess.run(['pdftotext','-layout',str(out),str(out.with_suffix('.txt'))],check=True)
            receipt.append({'filename':pin['filename'],'bytes':len(raw),'sha256_matches':True,'cached':cached})
        (args.output/'restore_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        # Compatibility for the independent provenance check. It is derived
        # directly from the version-controlled pins, not a separate authority.
        (args.output/'acquisition_manifest.json').write_text(json.dumps(pins['members'],ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'members_verified':len(receipt),'full_zip_downloaded':False,'network_bytes':remote.used if remote else 0}))
    finally:
        if archive is not None:archive.close()
        if remote is not None:
            (args.output/'restore_ranges.json').write_text(json.dumps(remote.requests,indent=2)+'\n')
if __name__=='__main__':main()

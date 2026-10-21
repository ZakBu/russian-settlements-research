"""Restore the exact reviewed four-file numeric cache from retained byte parts."""
from pathlib import Path
import argparse,hashlib,json,os

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path)
    ap.add_argument('--verify-only',action='store_true')
    args=ap.parse_args()
    if not args.verify_only and args.output is None:ap.error('--output is required for restoration')
    manifest=json.loads((HERE/'manifest.json').read_text())
    if args.output is not None and not args.verify_only:args.output.mkdir(parents=True,exist_ok=True)
    for item in manifest['files']:
        name=item['file']
        assert name in {'cache_receipt.json','origin_mapping.parquet','provider_mapping.parquet','routes_180.npz'}
        destination=args.output/name if args.output is not None else None
        existing=destination is not None and destination.exists()
        if existing and not args.verify_only:
            if digest(destination)!=item['sha256']:raise ValueError(f'Refusing to overwrite different file: {destination}')
        temporary=None;writer=None
        if not args.verify_only and not existing:
            temporary=destination.with_name('.'+name+'.restoring')
            writer=temporary.open('xb')
        combined=hashlib.sha256();size=0
        try:
            for part in item['parts']:
                source=ROOT/part['path'];h=hashlib.sha256();n=0
                with source.open('rb') as f:
                    for block in iter(lambda:f.read(8<<20),b''):
                        combined.update(block);h.update(block);n+=len(block);size+=len(block)
                        if writer is not None:writer.write(block)
                if h.hexdigest()!=part['sha256'] or n!=part['bytes']:raise ValueError(f'Archive part mismatch: {source}')
            if combined.hexdigest()!=item['sha256'] or size!=item['bytes']:raise ValueError(f'Combined cache mismatch: {name}')
            if writer is not None:
                writer.flush();os.fsync(writer.fileno());writer.close();writer=None
                os.link(temporary,destination)  # Atomic creation; never replaces a concurrent file.
                temporary.unlink();temporary=None
        finally:
            if writer is not None:writer.close()
            if temporary is not None:temporary.unlink(missing_ok=True)
        print(f'Verified {name}: {size} bytes')

if __name__=='__main__':main()

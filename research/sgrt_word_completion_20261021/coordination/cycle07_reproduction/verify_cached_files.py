"""Read-only byte verification of the restored, independently admitted cache."""
from pathlib import Path
import argparse,hashlib,json

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'model/cycle07_scale_hierarchy/source477_numeric_cache_archive_v1/manifest.json'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8<<20),b''):h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads(MANIFEST.read_text())
    rows=[]
    for item in manifest['files']:
        path=args.cache/item['file']
        if not path.is_file():raise FileNotFoundError(path)
        size=path.stat().st_size;actual=digest(path)
        if size!=item['bytes'] or actual!=item['sha256']:
            raise ValueError(f'Cache bytes differ from reviewed archive: {path}')
        rows.append({'file':item['file'],'bytes':size,'sha256':actual})
    print(json.dumps({'status':'PASS_EXACT_REVIEWED_FOUR_FILE_CACHE','files':rows},indent=2))

if __name__=='__main__':main()

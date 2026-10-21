"""Download only pinned report inputs; verify all bytes before use."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'provenance/source_downloads.json').read_text())
def verified(p,row):
 return p.is_file() and p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
def download(row):
 p=ROOT/row['path']
 if verified(p,row):return 'cached '+row['path']
 p.parent.mkdir(parents=True,exist_ok=True)
 with urlopen(row['url'],timeout=180) as r:data=r.read()
 if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
  raise ValueError('Source bytes differ: '+row['path'])
 temp=p.with_suffix(p.suffix+'.download');temp.write_bytes(data);temp.replace(p)
 return 'downloaded '+row['path']
if __name__=='__main__':
 for result in ThreadPoolExecutor(6).map(download,manifest['files']):print(result)
 print('Verified',len(manifest['files']),'pinned source files')

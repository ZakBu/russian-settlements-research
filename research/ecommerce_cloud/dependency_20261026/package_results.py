"""Package only this project's new artifacts, excluding third-party full texts."""
from pathlib import Path
import hashlib
import json
import platform
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT/'work/ecommerce_dependency_20261026/export'
PACKAGE = ROOT/'work/ecommerce_dependency_20261026/release'
TAG = 'ecommerce-dependency-20261026-v1'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    PACKAGE.mkdir(parents=True,exist_ok=True)
    names = ['Dependency_and_Russian_Centres_20261026.pdf',
        'dependency_executed.ipynb','dependency_notebook.html',
        'online_ordering_2020_2025.png','periphery_selected_regions.png']
    files={n:OUT/n for n in names}
    files['national_options_contexts.csv']=OUT.parent/'national_options_contexts.csv'
    for p in HERE.iterdir():
        if p.is_file() and p.suffix in {'.py','.md','.csv','.json'}:
            files['research/'+p.name]=p
    manifest={'schema':'ecommerce.dependency_export.v1','release_tag':TAG,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'python':platform.python_version(),'scope':'Partial mediation mechanisms and fixed noncentral positive-record geography; not a national causal estimate.',
        'files':[{'archive_path':n,'bytes':p.stat().st_size,'sha256':digest(p)} for n,p in sorted(files.items())],
        'excluded':'Third-party complete scientific papers, survey microdata and raw source PDFs are not redistributed.'}
    (PACKAGE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=PACKAGE/'dependency_research_20261026.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,p in sorted(files.items()):z.write(p,n)
        z.write(PACKAGE/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive) as z:
        for row in manifest['files']:
            b=z.read(row['archive_path'])
            assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
    for n in names:shutil.copy2(files[n],PACKAGE/n)
    (PACKAGE/'SHA256SUMS.txt').write_text('\n'.join(
        f'{digest(p)}  {p.name}' for p in sorted(PACKAGE.iterdir())
        if p.is_file() and p.name!='SHA256SUMS.txt')+'\n')
    print(json.dumps({'source_commit':manifest['source_commit'],'files':len(files),
        'archive_bytes':archive.stat().st_size,'archive_sha256':digest(archive)},ensure_ascii=False))


if __name__=='__main__':main()

"""Package new aggregate evidence, not original person records or papers."""
from pathlib import Path
import hashlib,json,platform,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_flows_20261026/export'
PACKAGE=ROOT/'work/ecommerce_flows_20261026/release'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    PACKAGE.mkdir(parents=True,exist_ok=True)
    names=['Purchase_Geography_and_Centre_Functions_20261026.pdf',
        'purchase_geography_executed.ipynb','purchase_geography_notebook.html',
        'purchase_own_locality.png','school_other_locality.png','purchase_remote_groups2024.png']
    files={n:OUT/n for n in names}
    for p in HERE.iterdir():
        if p.is_file() and p.suffix in {'.py','.md','.csv','.json'}:files['research/'+p.name]=p
    files['shared_pdf_renderer.py']=HERE.parent/'dependency_20261026/build_deliverables.py'
    m={'schema':'ecommerce.purchase_geography_export.v1',
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'python':platform.python_version(),
        'scope':'Weighted declared purchase geography and observed school location; no named OD or WB/Ozon causal effect.',
        'original_person_records_redistributed':False,'third_party_complete_papers_redistributed':False,
        'files':[dict(archive_path=n,bytes=p.stat().st_size,sha256=digest(p))for n,p in sorted(files.items())]}
    (PACKAGE/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    archive=PACKAGE/'purchase_geography_research_20261026.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for n,p in sorted(files.items()):z.write(p,n)
        z.write(PACKAGE/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive)as z:
        for r in m['files']:
            b=z.read(r['archive_path']);assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256']
    for n in names:shutil.copy2(files[n],PACKAGE/n)
    (PACKAGE/'SHA256SUMS.txt').write_text('\n'.join(f'{digest(p)}  {p.name}'for p in sorted(PACKAGE.iterdir())
        if p.is_file()and p.name!='SHA256SUMS.txt')+'\n')
    print(json.dumps(dict(source_commit=m['source_commit'],files_n=len(files),
        zip_bytes=archive.stat().st_size,zip_sha256=digest(archive))))


if __name__=='__main__':main()

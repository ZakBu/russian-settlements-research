"""Publish derivatives and analytical extracts; no papers or user profiles."""
from pathlib import Path
import hashlib,json,subprocess,platform,zipfile,shutil
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
WORK=ROOT/'work/ecommerce_operations_20261104';OUT=WORK/'export';PACKAGE=WORK/'release'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    PACKAGE.mkdir(parents=True,exist_ok=True)
    names=['Observed_Centre_Links_20261104.pdf','observed_centre_links_executed.ipynb','observed_centre_links_notebook.html']
    files={n:OUT/n for n in names}
    for p in HERE.iterdir():
        if p.is_file()and p.suffix in {'.py','.md','.csv','.json','.txt'}:files['research/'+p.name]=p
    files['derived_data/ozon_tariff_geography2023_all.csv']=WORK/'ozon_tariff_geography2023_all.csv'
    files['source_dependencies/programme_pilot_row_disposition2022.csv']=HERE.parent/'next_direction_20261103/programme_pilot_row_disposition.csv'
    files['source_dependencies/shared_pdf_renderer.py']=HERE.parent/'dependency_20261026/build_deliverables.py'
    manifest=dict(schema='ecommerce.observed_centre_links.v1',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        python=platform.python_version(),original_person_records_redistributed=False,third_party_complete_papers_redistributed=False,
        full_user_profiles_redistributed=False,
        scope='Reported changes of named purchase destinations; operating-point reports, functional evidence and independently checked tariff-geography extraction. No national causal estimate.',
        files=[dict(archive_path=n,bytes=p.stat().st_size,sha256=sha(p))for n,p in sorted(files.items())])
    (PACKAGE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=PACKAGE/'observed_centre_links_20261104.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for n,p in sorted(files.items()):z.write(p,n)
        z.write(PACKAGE/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive)as z:
        for r in manifest['files']:
            b=z.read(r['archive_path']);assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256']
    for n in names:shutil.copy2(OUT/n,PACKAGE/n)
    (PACKAGE/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p)}  {p.name}'for p in sorted(PACKAGE.iterdir())if p.is_file()and p.name!='SHA256SUMS.txt')+'\n')
    print(json.dumps(dict(payload_files=len(files),archive_bytes=archive.stat().st_size,sha256=sha(archive))))
if __name__=='__main__':main()

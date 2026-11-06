"""Publish scientific derivatives and inspectable small aggregates only."""
from pathlib import Path
import hashlib,json,subprocess,platform,zipfile,shutil
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
WORK=ROOT/'work/ecommerce_national_test_20261106';OUT=WORK/'export';DEST=WORK/'release'
NAMES=['National_Orders_and_Centre_Functions_20261106.pdf','national_evidence_executed.ipynb',
       'national_evidence_notebook.html','rural_orders.png','municipal_marketplace_change.png']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    DEST.mkdir(parents=True,exist_ok=True)
    files={n:OUT/n for n in NAMES}
    for p in HERE.rglob('*'):
        if p.is_file()and p.suffix in {'.py','.md','.csv','.json','.txt'}:
            files['research/'+str(p.relative_to(HERE))]=p
    files['source_dependencies/shared_pdf_renderer.py']=HERE.parent/'dependency_20261026/build_deliverables.py'
    files['source_dependencies/requirements-report.txt']=HERE.parent/'extension/requirements-report.txt'
    manifest=dict(schema='ecommerce.national_evidence.v1',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        python=platform.python_version(),individual_records_redistributed=False,full_third_party_publications_redistributed=False,
        scope='National self-reported ordering, modelled municipal resident spending, descriptive functional outcomes. No identified national causal effect or local pickup-OD estimate.',
        clean_reproduction_scope='KOUZh and Sber raw inputs; ICT published aggregate arithmetic only. Full ICT raw recalculation completed locally, source access currently limited.',
        files=[dict(archive_path=n,bytes=p.stat().st_size,sha256=sha(p))for n,p in sorted(files.items())])
    (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=DEST/'national_evidence_20261106.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for n,p in sorted(files.items()):z.write(p,n)
        z.write(DEST/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive)as z:
        for r in manifest['files']:
            b=z.read(r['archive_path']);assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256']
    for n in NAMES:shutil.copy2(OUT/n,DEST/n)
    (DEST/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p)}  {p.name}'for p in sorted(DEST.iterdir())if p.is_file()and p.name!='SHA256SUMS.txt')+'\n')
    print(json.dumps(dict(payload_files=len(files),archive_bytes=archive.stat().st_size,sha256=sha(archive))))
if __name__=='__main__':main()

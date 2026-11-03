"""Package reviewed aggregate outputs and source provenance, no microrecords."""
from pathlib import Path
import hashlib,json,platform,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_joint_20261103/export'
PACKAGE=OUT.parent/'release'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    PACKAGE.mkdir(parents=True,exist_ok=True)
    names=['Joint_Dependencies_20261103.pdf','joint_dependencies_executed.ipynb',
        'joint_dependencies_notebook.html','joint_profiles_standardised.png','joint_profiles_size2024.png']
    files={n:OUT/n for n in names}
    for p in HERE.iterdir():
        if p.is_file()and p.suffix in {'.py','.md','.csv','.json'}:files['research/'+p.name]=p
    for name in ['eligibility_20221022_rows.csv','eligibility_pilot_links.csv','eligibility_pilot_summary.json']:
        p=ROOT/'work/ecommerce_next_20261103/identification'/name
        assert p.exists(),p
        files['programme_extraction/'+name]=p
    for name in ['analyze_purchase_geography.py','fetch_kouzh_inputs.py','kouzh_source_members.json']:
        files['source_dependencies/'+name]=HERE.parent/'flows_20261026'/name
    files['source_dependencies/shared_pdf_renderer.py']=HERE.parent/'dependency_20261026/build_deliverables.py'
    manifest=dict(schema='ecommerce.joint_dependencies.v1',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        python=platform.python_version(),original_person_records_redistributed=False,
        third_party_complete_papers_redistributed=False,
        scope='Joint reported geography, household co-occurrence and historical tariff geography; not a platform causal effect or opening dates.',
        files=[dict(archive_path=n,bytes=p.stat().st_size,sha256=sha(p))for n,p in sorted(files.items())])
    (PACKAGE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=PACKAGE/'joint_dependencies_20261103.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for n,p in sorted(files.items()):z.write(p,n)
        z.write(PACKAGE/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive)as z:
        for r in manifest['files']:
            data=z.read(r['archive_path']);assert len(data)==r['bytes']and hashlib.sha256(data).hexdigest()==r['sha256']
    for n in names:shutil.copy2(OUT/n,PACKAGE/n)
    (PACKAGE/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p)}  {p.name}'for p in sorted(PACKAGE.iterdir())if p.is_file()and p.name!='SHA256SUMS.txt')+'\n')
    print(json.dumps(dict(files_n=len(files),archive_bytes=archive.stat().st_size,sha256=sha(archive))))
if __name__=='__main__':main()

"""Package code, audited outputs and pilot inputs; exclude books and scratch."""
from pathlib import Path
import argparse,hashlib,json,zipfile,shutil


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();r=a.root.resolve();o=a.out.resolve();o.mkdir(parents=True,exist_ok=True)
    files=[];excluded=[]
    for p in sorted(r.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(r)
        if any(x in {'__pycache__','tmp','acquired','documented_graph_v1','documented_graph_v2','documented_graph_v3','inventory_comparison_pre_unmatched_fix'} for x in rel.parts) or '.tmp' in p.name or p.name.startswith('.'):
            excluded.append(str(rel));continue
        if p.suffix=='.csv' and p.stat().st_size>500000 and p.with_suffix('.parquet').exists():
            excluded.append(str(rel));continue
        files.append((p,str(rel)))
    manifest={'stage':'functional_anchoring_pilot_20261019','scope':'literature+documented_service_graph+national_candidate_presence; not national validated SGRT','files':[{'path':n,'bytes':p.stat().st_size,'sha256':sha(p)} for p,n in files],'excluded':excluded,'external_inputs':'Frozen RFSD/agriculture microdata available in previously saved SGRT_RESULTS.zip; see README and input manifests.'}
    package=o/'ANCHOR_RESEARCH_STAGE1.zip'
    with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for p,n in files:z.write(p,n)
        z.writestr('PACKAGE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        m=json.loads(z.read('PACKAGE_MANIFEST.json'))
        for item in m['files']:
            assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256'],item['path']
    pdf=r/'output/pdf/ANCHOR_RESEARCH_STAGE1.pdf';shutil.copy2(pdf,o/pdf.name)
    for src,name in [(r/'literature/RECOMMENDED_METHOD.md','ANCHOR_LITERATURE.md'),(r/'figures/01_documented_service_networks.png','ANCHOR_SERVICE_NETWORKS.png')]:shutil.copy2(src,o/name)
    result={'status':'PASS','archive_crc_and_member_SHA':'PASS','files':len(files),'excluded_files':len(excluded),'artifacts':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(o.iterdir()) if p.is_file() and not p.name.startswith('.') and p.name!='CHECKSUMS.json']}
    (o/'CHECKSUMS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

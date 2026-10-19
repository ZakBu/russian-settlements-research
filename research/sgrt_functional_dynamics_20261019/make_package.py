"""Build a self-contained research snapshot; verify every decompressed member."""
from pathlib import Path
import json,hashlib,zipfile,shutil
R=Path(__file__).resolve().parent;B=R.parent;D=B/'functional_deliverables_20261019'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for q in iter(lambda:f.read(1048576),b''):h.update(q)
 return h.hexdigest()
def skip(p,root):
 rel=p.relative_to(root)
 if any(a.startswith('.') or a in ['__pycache__','qa','tmp'] for a in rel.parts):return True
 if p.name.endswith(('.footer','.body.pdf')) or 'footer_probe' in p.name:return True
 if p.suffix=='.gz' and p.name.endswith('.csv.gz') and p.with_name(p.name[:-7]+'.parquet').exists():return True
 if p.name in ['wb_all_points_v10.json','wb_all_points_v11.json']:return True
 if root==R and p.name in ['ARTIFACT_MANIFEST.json','PACKAGE_VERIFICATION.json']:return True
 return False

def main():
 D.mkdir(exist_ok=True)
 for n in ['SGRT_FUNCTIONAL_DYNAMICS_REPORT.pdf','SGRT_FUNCTIONAL_DYNAMICS_BRIEF.pdf']:shutil.copyfile(R/'output/pdf'/n,D/n)
 selected={p.relative_to(B).as_posix():p for p in R.rglob('*') if p.is_file() and not skip(p,R)}
 # Frozen accepted predecessor inputs and its scientific method/evidence, excluding acquired books and duplicate outputs.
 old=B/'anchor_research_20261019'
 for p in old.rglob('*'):
  if not p.is_file() or skip(p,old) or 'acquired' in p.parts:continue
  rel=p.relative_to(old)
  if rel.parts[0]=='economy' and not (rel.parts[1]=='coded_results' or p.suffix in ['.py','.md','.json']):continue
  selected[p.relative_to(B).as_posix()]=p
 raw=B/'restored/extracted/inputs'
 for rel in ['publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz','recovery_inputs/columnar/agriculture.parquet','recovery_inputs/enrichment/rfsd_2016_selected.parquet','recovery_inputs/enrichment/rfsd_2021_selected.parquet','recovery_inputs/enrichment/world.geojson']:
  p=raw/rel;assert p.is_file();selected[p.relative_to(B).as_posix()]=p
 manifest={n:{'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in sorted(selected.items())}
 (R/'ARTIFACT_MANIFEST.json').write_text(json.dumps({'files':manifest,'exclusions':'hidden files, caches/footer, acquired copyrighted books, duplicate CSV.gz when Parquet available; CSV reproducible from code','layout':'extract at a working directory; python functional_dynamics_20261019/replay_all.py'},ensure_ascii=False,indent=2)+'\n')
 selected[(R/'ARTIFACT_MANIFEST.json').relative_to(B).as_posix()]=R/'ARTIFACT_MANIFEST.json'
 archive=D/'SGRT_FUNCTIONAL_DYNAMICS_REPRODUCIBLE.zip'
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
  for n,p in sorted(selected.items()):z.write(p,n)
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for n,m in manifest.items():
   h=hashlib.sha256()
   with z.open(n) as f:
    for q in iter(lambda:f.read(1048576),b''):h.update(q)
   assert h.hexdigest()==m['sha256'],n
 mapzip=D/'SGRT_MAPS_PNG_SVG_PDF.zip'
 mapfiles=[]
 for sub in ['model/figures','figures','economy/figures']:
  mapfiles += [p for p in (R/sub).glob('*') if p.suffix in ['.png','.svg','.pdf']]
 with zipfile.ZipFile(mapzip,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
  for p in mapfiles:assert p.stat().st_size>0;z.write(p,p.relative_to(R).as_posix())
 with zipfile.ZipFile(mapzip) as z:assert z.testzip() is None
 for n in ['claim_registry.csv','BIBLIOGRAPHY.csv','typology_hypotheses.csv']:shutil.copyfile(R/n,D/n)
 report={'status':'PASS','archive':archive.name,'members':len(selected),'each_member_sha256_verified':len(manifest),'uncompressed_bytes':sum(m['bytes']for m in manifest.values()),'map_formats_verified':len(mapfiles)}
 (R/'PACKAGE_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
 sums={p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in D.iterdir()if p.is_file() and p.name!='CHECKSUMS.json'}
 (D/'CHECKSUMS.json').write_text(json.dumps({'status':'PASS','files':sums,'verification':report},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report));print(json.dumps(sums,ensure_ascii=False))
if __name__=='__main__':main()

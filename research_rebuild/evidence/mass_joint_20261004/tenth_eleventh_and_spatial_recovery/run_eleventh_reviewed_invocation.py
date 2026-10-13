from pathlib import Path
import subprocess,os,json,time,resource,hashlib,datetime
R=Path('/workspace/russian-settlements-research');C=Path('/workspace/settlements-work/continuation_20261004');D=C/'root/eleventh_reviewed28_point2_invocation';D.mkdir(exist_ok=False);script=R/'research_rebuild/mass_linkage/apply_reviewed_mass_extensions_20261004.py';manifest=C/'root/next_batch_manifest_preparation/eleventh_gostsup_type12/eleventh_application_manifest.json';output=C/'accepted_mass_eleventh_reviewed28_point2';assert not output.exists()
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
cmd=['/workspace/settlements-venv/bin/python',str(script),'--manifest',str(manifest),'--output',str(output)];env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONPATH=str(R));start=time.monotonic();utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
with (D/'stdout.txt').open('w') as stdout,(D/'stderr.txt').open('w') as stderr:res=subprocess.run(cmd,cwd=R,env=env,stdout=stdout,stderr=stderr)
r={'command':cmd,'utc_start':utc,'utc_finish':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':res.returncode,'elapsed_seconds':time.monotonic()-start,'peak_child_rss_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'executed_script_sha256':sha(script),'manifest_sha256':sha(manifest),'wrapper_sha256':sha(Path(__file__))};(D/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));
if res.returncode:print((D/'stderr.txt').read_text()[-6000:]);raise SystemExit(res.returncode)
print((output/'receipt.json').read_text())

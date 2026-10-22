from pathlib import Path
import subprocess,sys,json,time
H=Path(__file__).resolve().parent;B=H.parent/'transport/cycle06_network2021';r=json.loads((B/'source_filter_receipt.json').read_text());code="import osmium,json; n=0\nfor o in osmium.FileProcessor(osmium.io.File('-', 'pbf')).with_filter(osmium.filter.KeyFilter('place')):\n n+=1\nprint(json.dumps({'place_objects':n,'stdin_pbf_read_complete':True}))"
p=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);n=0;start=time.monotonic()
try:
 for part in r['durable_parts']:
  with (B/part['path']).open('rb') as f:
   for block in iter(lambda:f.read(4*1024*1024),b''):p.stdin.write(block);n+=len(block)
 p.stdin.close();out=p.stdout.read().decode();err=p.stderr.read().decode();status=p.wait()
except BrokenPipeError:
 out=p.stdout.read().decode();err=p.stderr.read().decode();status=p.wait()
d=dict(status='PASS' if status==0 else 'FAIL',returncode=status,stream_bytes=n,stdout=out,stderr=err,seconds=time.monotonic()-start,source='same actual2021 referencecomplete road-source pieces; stdin capability test only, NOTnationalplaceinventory')
(H/'pbf_stdin_capability_receipt.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d),flush=True)

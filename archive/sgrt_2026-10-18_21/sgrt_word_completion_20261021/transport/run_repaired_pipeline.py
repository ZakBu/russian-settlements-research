#!/usr/bin/env python3
from pathlib import Path
import os,time,subprocess,json
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_transport')
def run(script,*args):
 print('START',script,args,time.ctime(),flush=True);subprocess.run(['python',str(ROOT/script),*args],check=True)
if not (ROOT/'access_repair_receipt.json').exists():run('repair_access.py')
assert (ROOT/'access_repair_receipt.json').exists(),'Repair failed; no completed receipt'
run('filter_yearround.py')
run('build_transport.py','compress')
for name in ['allroad_refs.bin','allroad_lat.bin','allroad_lon.bin']:(RAW/name).unlink(missing_ok=True)
run('build_transport.py','graph');run('build_transport.py','snap')
for name in ['rev_indptr.bin','rev_indices.bin','rev_weights.bin']:(RAW/name).unlink(missing_ok=True)
run('route_validation.py');run('build_isochrones.py');run('compute_matrix.py')
print('COMPLETE',time.ctime(),flush=True)

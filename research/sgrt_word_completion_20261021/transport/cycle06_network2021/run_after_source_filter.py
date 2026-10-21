"""Sequential build stages; source audit release required before memory-heavy compression."""
from pathlib import Path
import argparse,json,subprocess,sys,hashlib,os
H=Path(__file__).resolve().parent;T=Path('/tmp/sgrt_network2021')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['extract','compress','graph','snap','freeze']);a=ap.parse_args()
 if a.stage=='extract':target=[sys.executable,str(H/'extract_roads2021.py')]
 elif a.stage=='freeze':target=[sys.executable,str(H/'freeze_graph.py')]
 else:target=[sys.executable,str(H/'assemble_graph2021.py'),a.stage]
 # Full raw and temporary geometry must not coexist with memory-heavy sorting unless explicitly reviewed.
 if a.stage=='compress':
  assert (H/'temporary_raw_release_receipt.json').exists(),'Independent raw audit and explicit temporary release receipt required'
  assert not (T/'russia-210101.osm.pbf').exists(),'Release audited temporary raw before compression'
  assert not (T/'node_locations.idx').exists(),'Release disposable location index after accepted geometry verified'
  receipt=json.loads((H/'road_extraction_receipt.json').read_text());from graph_io import sha;assert sha(T/'road_ways.parquet')==receipt['working_geometry_sha256'];points=json.loads((H/'routing_points_receipt.json').read_text());assert sha(H/'routing_points.parquet')==points['routing_points_sha256']
 with (T/(a.stage+'.log')).open('w') as log:subprocess.run(target,stdout=log,stderr=subprocess.STDOUT,check=True)
 print('completed',a.stage,flush=True)
if __name__=='__main__':main()

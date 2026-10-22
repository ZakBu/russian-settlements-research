"""Read durable graph/source pieces with byte verification; no full raw download required."""
from pathlib import Path
import hashlib,io,json
import pandas as pd
from scipy.sparse import load_npz
H=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def materialize_source(target):
 target=Path(target);receipt=json.loads((H/'source_filter_receipt.json').read_text())
 if target.exists():assert sha(target)==receipt['reference_complete_filtered_pbf_sha256'];return target
 target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_suffix('.partial');h=hashlib.sha256()
 with temp.open('wb') as out:
  for part in receipt['durable_parts']:
   p=H/part['path'];assert p.stat().st_size==part['bytes'] and sha(p)==part['sha256']
   with p.open('rb') as stream:
    for block in iter(lambda:stream.read(4194304),b''):out.write(block);h.update(block)
 assert h.hexdigest()==receipt['reference_complete_filtered_pbf_sha256'];temp.replace(target);return target

def load_graph():
 receipt=json.loads((H/'graph_artifact_receipt.json').read_text());buf=io.BytesIO();h=hashlib.sha256()
 for part in receipt['graph_npz_parts']:
  p=H/part['path'];assert sha(p)==part['sha256'];b=p.read_bytes();buf.write(b);h.update(b)
 assert h.hexdigest()==receipt['graph_npz_sha256'];buf.seek(0);return load_npz(buf)
def load_nodes():
 receipt=json.loads((H/'graph_artifact_receipt.json').read_text())
 for part in receipt['node_parts']:assert sha(H/part['path'])==part['sha256']
 return pd.read_parquet(H/'road_nodes')

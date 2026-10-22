#!/usr/bin/env python3
"""Append independent graph/matrix admission to NEW immutable clones only."""
from pathlib import Path
import argparse,json,hashlib,shutil,datetime
H=Path(__file__).resolve().parent;REPO=H.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rel(p):return str(p.resolve().relative_to(REPO))
def run(a):
 source=a.source.resolve();out=a.output.resolve();review=a.review.resolve();receipt=json.loads(review.read_text());assert receipt.get('all_checks_passed') is True or (receipt.get('n_failed')==0 and receipt.get('n_checks',0)>0) or (receipt.get('n_failed_checks')==0 and receipt.get('n_checks',0)>0),'Review does not assert independent acceptance'
 # A numerically passing receipt for another dataset is not admission here.
 net=H.parent/'transport/cycle06_network2021';reviewtext=json.dumps(receipt,ensure_ascii=False)
 witness=sha(net/'artifact_manifest.json')
 exact=[sha(net/'candidate_travel_times_manifest.json'),sha(net/'settlement_road_snap.parquet'),json.loads((net/'routing_receipt.json').read_text())['graph_sha256']]
 routing=net/'routing_receipt.json';rj=json.loads(routing.read_text());transitive=sha(routing) in reviewtext and all(v in reviewtext for v in exact[::2]) and exact[1] in json.dumps(rj) and rj['output_manifest_sha256']==exact[0]
 assert witness in reviewtext or all(v in reviewtext for v in exact) or transitive,'Independent receipt is not bound to this exact frozen graph/matrix/snap artifact set'
 freeze=json.loads((source/'cycle06_config_freeze_manifest.json').read_text())
 for row in freeze['files']:assert sha(source/row['path'])==row['sha256'],row['path']
 out.mkdir(parents=True,exist_ok=True)
 assert not list(out.glob('config_*_provisional.json')),'Never overwrite bound configs'
 shutil.copyfile(source/'cycle05_preregistration.json',out/'cycle05_preregistration.json')
 protocol=out/'cycle06_independent_admission_binding_protocol.json';dump(protocol,dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scientific_settings_and_all_data_sources_unchanged=True,append_provenance_only=True,admission_receipt=rel(review),admission_receipt_sha256=sha(review),source_freeze_manifest=rel(source/'cycle06_config_freeze_manifest.json'),source_freeze_manifest_sha256=sha(source/'cycle06_config_freeze_manifest.json')))
 entries=[]
 for src in sorted(source.glob('config_*_provisional.json')):
  old=json.loads(src.read_text());new=json.loads(src.read_text());new['provenance_sidecars']=list(dict.fromkeys(new['provenance_sidecars']+[rel(review),rel(protocol)]));assert {k:v for k,v in old.items() if k!='provenance_sidecars'}=={k:v for k,v in new.items() if k!='provenance_sidecars'};dest=out/src.name;dump(dest,new);entries.append(dict(source=rel(src),source_sha256=sha(src),output=rel(dest),output_sha256=sha(dest)))
 dump(out/'cycle06_admission_binding_receipt.json',dict(status='INDEPENDENT_ADMISSION_PROVENANCE_APPENDED_ONLY',entries=entries,admission_receipt_sha256=sha(review),data_sources_and_six_scientific_designs_unchanged=True))
 files=[p for p in out.iterdir() if p.is_file()];dump(out/'freeze_manifest.json',dict(files=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(files)]))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=H);p.add_argument('--output',type=Path,required=True);p.add_argument('--review',type=Path,required=True);run(p.parse_args())

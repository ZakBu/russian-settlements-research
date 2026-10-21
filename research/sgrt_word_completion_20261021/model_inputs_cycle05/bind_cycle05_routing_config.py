#!/usr/bin/env python3
"""Append routing-completeness binding; all preregistered scientific settings unchanged."""
from pathlib import Path
import argparse,json,copy,hashlib,shutil,datetime
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=ROOT.parents[1]
VARIANTS=['baseline','narrow_general_health','broad_retail_plus_ATM','unknown_role_upper','P0_probability','inclusive_candidates']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return str(p.resolve().relative_to(REPO))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(a):
 manifest=a.travel_manifest.resolve();route_receipt=manifest.parent/'routing_receipt.json'
 if not manifest.exists() or not route_receipt.exists():raise FileNotFoundError('Actual completed new routing manifest/receipt needed')
 original_freeze=json.loads((H/'config_freeze_manifest.json').read_text())
 for n,v in original_freeze['files'].items():
  if sha(H/n)!=v['sha256']:raise ValueError('Original preregistered input changed '+n)
 out=a.output_directory.resolve()
 if out.exists() and any(out.iterdir()):raise FileExistsError('Routing binding destination already contains files')
 out.mkdir(parents=True,exist_ok=True);shutil.copyfile(H/'cycle05_preregistration.json',out/'cycle05_preregistration.json')
 protocol=out/'supplemental_routing_protocol.json';record=dict(status='ROUTING_COMPLETENESS_ONLY_APPEND_TO_FROZEN_SCIENTIFIC_DESIGN',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_preregistration_sha256=sha(H/'cycle05_preregistration.json'),new_manifest=rel(manifest),new_manifest_sha256=sha(manifest),new_routing_receipt_sha256=sha(route_receipt),unchanged=['source_axis','V3statisticalroles','5domainMi','serviceclasses','population_context','candidate_rules','decay','probability_thresholds','Ci_formula','external_labels'],new_routes_same_historical_graph=True,no_previous_memberships_or_ranks_reused=True,allowed_config_differences=['travel_manifest','travel_edges','provenance_sidecars_append_this_protocol_only'],code_sha256=sha(Path(__file__)));dump(protocol,record)
 clones=[]
 for v in VARIANTS:
  p=H/('config_'+v+'_provisional.json');c=json.loads(p.read_text());c['travel_manifest']=rel(manifest);c['travel_edges']=rel(manifest);c['provenance_sidecars']=c.get('provenance_sidecars',[])+[rel(protocol)];q=out/p.name;dump(q,c);clones.append(dict(variant=v,original=rel(p),original_sha256=sha(p),clone=rel(q),clone_sha256=sha(q)))
 dump(out/'routing_binding_receipt.json',dict(status='ROUTING_PROVISIONAL_CONFIG_CLONES_CREATED',protocol_sha256=sha(protocol),clones=clones,original17_frozen_files_unchanged=True));print(json.dumps(dict(status='READY',output_directory=rel(out),variants=len(clones),new_manifest=rel(manifest)),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--travel-manifest',type=Path,required=True);p.add_argument('--output-directory',type=Path,default=H/'routing_bound_v1');run(p.parse_args())

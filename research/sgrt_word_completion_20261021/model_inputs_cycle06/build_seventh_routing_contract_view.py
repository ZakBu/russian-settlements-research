#!/usr/bin/env python3
"""Byte-identical matrix, metadata-only compatibility with frozen model loader."""
from pathlib import Path
import json,shutil,hashlib,os
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=next(p for p in H.parents if (p/'.git').exists())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(REPO))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def run():
 ext=ROOT/'transport/cycle06_network2021_access_v2_seventh_extension';base=ROOT/'transport/cycle06_network2021_access_v2';out=ROOT/'transport/cycle06_network2021_access_v2_seventh_modelview';assert not out.exists();out.mkdir()
 original=ext/'candidate_travel_times_manifest.json';shutil.copyfile(original,out/original.name)
 links={'candidate_travel_times_parts':ext/'candidate_travel_times_parts','route_destination_index.parquet':ext/'route_destination_index.parquet','route_destination_rejections.parquet':ext/'route_destination_rejections.parquet','route_origin_index.parquet':base/'route_origin_index.parquet','settlement_road_snap.parquet':base/'settlement_road_snap.parquet'}
 for name,p in links.items():assert p.exists();(out/name).symlink_to(os.path.relpath(p,out),target_is_directory=p.is_dir())
 r=json.loads((ext/'routing_receipt.json').read_text());b=json.loads((base/'routing_receipt.json').read_text());assert r['manifest_sha256']==sha(original)
 r.update(output_manifest_sha256=r['manifest_sha256'],source_snapshot_utc=b['source_snapshot_utc'],origin_snap_max_km=b['origin_snap_max_km'],metadata_only_contract_view=True,original_extension_routing_receipt_sha256=sha(ext/'routing_receipt.json'),base_routing_receipt_sha256=sha(base/'routing_receipt.json'))
 dump(out/'routing_receipt.json',r)
 assert sha(out/original.name)==sha(original)
 # Validate every manifest relative path still targets the exact admitted bytes.
 manifest=json.loads(original.read_text());controls=[]
 for info in manifest['parts']+[manifest['origin_mapping'],manifest['destination_mapping']]:
  source=ext/info['path'];view=out/info['path'];assert source.resolve()==view.resolve() or sha(source)==sha(view);assert sha(view)==info['sha256'];controls.append(dict(path=info['path'],sha256=info['sha256'],same_actual_source_path=source.resolve()==view.resolve()))
 dump(out/'contract_view_receipt.json',dict(status='BYTE_IDENTICAL_MATRIX_WITH_METADATA_ONLY_LOADER_COMPATIBILITY',matrix_sha256=sha(original),original_extension_routing_receipt_sha256=sha(ext/'routing_receipt.json'),adapted_routing_receipt_sha256=sha(out/'routing_receipt.json'),snap_sha256=sha(base/'settlement_road_snap.parquet'),base_origin_mapping_sha256=sha(base/'route_origin_index.parquet'),destination_index_sha256=sha(ext/'route_destination_index.parquet'),all_numeric_parts_and_indices_unchanged=True,original_frozen_files_unmodified=True,all_manifest_relative_paths_hash_verified=controls,no_model_predictions_read=True,added_fields_only=['output_manifest_sha256 alias of existing manifest_sha256','source_snapshot_utc copied from acceptedbase','origin_snap_max_km copied from acceptedbase','provenance metadata'],code_sha256=sha(Path(__file__))))
 files=[p for p in out.iterdir() if p.is_file()];dump(out/'artifact_manifest.json',dict(status='METADATA_ONLY_MODEL_CONTRACT_VIEW_PENDING_INDEPENDENT_BRIDGE_ADMISSION',files={p.name:sha(p) for p in files}));print(out)
if __name__=='__main__':run()

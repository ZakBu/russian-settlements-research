"""Combine the independently reviewed WD193 identity and native-point cohorts."""
from pathlib import Path
import csv,json,hashlib
REPO=Path(__file__).resolve().parents[2]; BASE=Path('/workspace/settlements-work/continuation_20261004')
POINT_REVIEW=BASE/'R4/named_native_point_fifth_independent_review_20261004_final_v2'
POINT_PRODUCER=BASE/'R4/named_native_point_fifth_reprojection_20261004/freeze_v4'
IDENTITY_PREP=BASE/'root/next_batch_manifest_preparation/reviewed_wd193_extension'
OUT=BASE/'root/next_batch_manifest_preparation/sixth_reviewed'
PREVIOUS=BASE/'root/next_batch_manifest_preparation/combined_fifth_context_20261004/combined_nonoverlapping_application_manifest.json'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return {'path':str(p),'sha256':sha(p)}
def main():
 cfg=json.loads((REPO/'config/mass_joint_20261004.json').read_text())
 rp=POINT_REVIEW/'independent_review_receipt.json';ep=POINT_REVIEW/'eligible_point_candidate_ids.csv'
 assert sha(rp)=='1554f77e38dd338e7faf2e01dfeb9aacfded18c8b58612cc6badaaccac725af6'
 assert sha(ep)=='0e2a28c94a85e83c0770e4c89b664593e20233d450ae6a1ae43554b243b3475e'
 original=POINT_PRODUCER/'projected_point_candidates.csv';assert sha(original)=='954fd28516093fe469cc68a0de75a4dd49cefa487f06598a85dbe832a68b4e23'
 approved={r['target_source_record_id']:r for r in csv.DictReader(ep.open())}
 rows=[]
 for r in csv.DictReader(original.open()):
  sid=r['target_source_record_id']
  if sid not in approved:continue
  a=approved[sid]
  assert float(r['latitude'])==float(a['raw_dbf_lat_raw']) and float(r['longitude'])==float(a['raw_dbf_lon_raw'])
  r['source_point_origin_label_before_application']=r['point_origin_file'];r['point_origin_file']=a['raw_dbf_path']
  assert r['point_origin_sha256']==a['raw_dbf_sha256']
  r['point_origin_locator']=f"DBF_record_1based={a['raw_dbf_record_1based']};DBF_byte_offset_0based={a['raw_dbf_byte_offset_0based']};OKATO2011_raw={a['raw_dbf_okato_literal']}"
  r['target_year']=r['census_year'];r['coordinate_source']='raw named typed GeoKLADR 2011 representative point; reviewed source-coordinate concordance'
  r['coordinate_provider']='GeoKLADR 2011 source coordinate';r['coordinate_source_record_id']='DBF2011:'+a['raw_dbf_record_1based']
  r['coordinate_source_file']=r['point_origin_file'];r['coordinate_source_sha256']=r['point_origin_sha256'];r['coordinate_source_locator']=r['point_origin_locator']
  r['coordinate_quality']='automatically_accepted_checked_rule';r['coordinate_temporal_basis']='representative_raw2011_point_reused_across_accepted_same_place_component'
  r['coordinate_measurement_date_unknown']=True;r['census_date_point_measurement_proven']=False
  r['boundary_comparability_asserted']=False;r['population_scope_comparability_asserted']=False;r['native_id_binding_asserted']=False
  r['current_raw_Dadata_spatial_witness_distance_km']=a['distance_DBf_to_current_Dadata_spatial_witness_km']
  rows.append(r)
 assert len(rows)==193
 OUT.mkdir(parents=True,exist_ok=False);cand=OUT/'reviewed_193_literal_native_point_adapter.csv'
 with cand.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 spec={'candidate':pin(cand),'approved':pin(ep),'review_receipt':pin(rp),'origin':pin(Path(rows[0]['point_origin_file'])),
       'candidate_columns':{'target':'target_source_record_id','latitude':'latitude','longitude':'longitude','origin_file':'point_origin_file','origin_sha256':'point_origin_sha256','origin_locator':'point_origin_locator'},
       'approved_columns':{'target':'target_source_record_id','latitude':'raw_dbf_lat_raw','longitude':'raw_dbf_lon_raw','origin_file':'raw_dbf_path','origin_sha256':'raw_dbf_sha256'},
       'additional_review_receipts':[pin(POINT_PRODUCER/'receipt.json')]}
 prior=json.loads(PREVIOUS.read_text());manifest={k:prior[k] for k in ['frozen','blocked_targets','federal_points','federal_chains']}
 manifest.update(base={'graph':pin(Path(cfg['working_identity_graph'])),'points':pin(Path(cfg['working_point_uses']))},identity_sources=[json.loads((IDENTITY_PREP/'identity_source_spec.json').read_text())],point_sources=[spec],reviewed_at_utc='2026-10-04T04:25:00Z')
 for key in ['graph','points']:assert manifest['base'][key]['sha256']==cfg['working_'+('identity_graph' if key=='graph' else 'point_uses')+'_sha256']
 mp=OUT/'sixth_application_manifest.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 receipt={'status':'reviewed_manifest_preparation_no_scientific_admissions','new_identity_endpoint_pairs':214,'additional_existing_identity_confirmations_preserved':172,'direct_point_targets':193,'native_points_requiring_review_held':131,'point_source_origin_label_corrected_to_literal_reviewed_path':True,'input_pins':{str(p):sha(p) for p in [rp,ep,original,PREVIOUS,IDENTITY_PREP/'receipt.json']},'outputs':{str(p):sha(p) for p in [cand,mp]},'script_sha256':sha(__file__)}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()

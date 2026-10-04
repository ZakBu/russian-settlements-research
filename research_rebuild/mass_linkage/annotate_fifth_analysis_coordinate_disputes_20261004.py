"""Attach diagnostic point-disagreement flags to the existing display CSV."""
from pathlib import Path
import json,hashlib,duckdb
BASE=Path('/workspace/settlements-work/continuation_20261004')
LONG=BASE/'R4/final_long_preparation/fifth_canonical_long_v2'
AUDIT=BASE/'root/fifth_point_disagreement_audit_v2'
OUT=BASE/'root/fifth_analysis_coordinate_disputes'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 source=LONG/'settlements_analysis_view.csv.gz'
 expected=json.loads((LONG/'run_receipt.json').read_text())['outputs'][source.name]['sha256']
 assert sha(source)==expected
 r=json.loads((AUDIT/'receipt.json').read_text()); conflicts=AUDIT/'affected_census_point_records.parquet'
 assert sha(conflicts)==r['outputs'][str(conflicts)]
 OUT.mkdir(parents=True,exist_ok=False)
 con=duckdb.connect(config={'threads':1,'memory_limit':'2GB'})
 # CSV fields remain lexical strings, so identifier leading zeroes and raw
 # population source formatting cannot change through numeric inference.
 con.read_csv(str(source),header=True,all_varchar=True).create_view('analysis')
 con.read_parquet(str(conflicts)).project('entity_id,max_point_distance_km').distinct().create_view('disputes')
 con.execute("create view annotated as select a.*,d.max_point_distance_km interyear_accepted_point_max_distance_km, case when d.entity_id is null then 'no_interyear_point_disagreement_detected_or_no_comparable_points; not_individual_verification' else 'interyear_point_disagreement_over_5km_requires_resolution; accepted_ledger_status_preserved' end coordinate_disagreement_screen_status from analysis a left join disputes d on coalesce(a.current_place_entity_id,a.entity_id)=d.entity_id")
 assert con.execute('select count(*) from annotated').fetchone()[0]==864043
 output=OUT/'settlements_analysis_with_coordinate_disputes.csv.gz'
 con.execute('copy annotated to ? (format csv,header true,compression gzip)',[str(output)])
 receipt={'status':'analysis_display_annotations_only_no_scientific_ledger_changes','rows':864043,'disagreeing_components':r['disagreeing_components'],'input_csv_sha256':expected,'disagreement_receipt_sha256':sha(AUDIT/'receipt.json'),'all_original_csv_fields_preserved_lexically':True,'not_a_new_coordinate_or_identity_admission':True,'script_sha256':sha(__file__),'output':{'path':str(output),'sha256':sha(output),'bytes':output.stat().st_size}}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()

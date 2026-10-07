"""Read the delivered CSV independently and verify manifest and completeness."""
from pathlib import Path
import csv,gzip,hashlib,json,math,time,base64

HERE=Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    start=time.monotonic();receipt=json.loads((HERE/'export_receipt.json').read_text());target=Path(receipt['file'])
    assert sha(target)==receipt['sha256'] and target.stat().st_size==receipt['bytes']
    for name in ['input_hash_manifest.json','export_source_hash_manifest.json']:
        for path,record in json.loads((HERE/name).read_text()).items(): assert sha(Path(path))==record['sha256'],path
    actual_file_claims={};count=0;seen=set();totals={2002:0,2010:0,2021:0};unknown_quality={2002:0,2010:0,2021:0};unknown_source={2002:0,2010:0,2021:0};unknown_origin={2002:0,2010:0,2021:0}
    with gzip.open(target,'rt',encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            count+=1;ids=[row[f'source_record_id_{y}'] for y in (2002,2010,2021)]
            expected='np3:'+base64.urlsafe_b64encode(hashlib.sha256(json.dumps(ids,ensure_ascii=False,separators=(',',':')).encode()).digest()).decode().rstrip('=')
            assert row['entity_uid']==expected and expected not in seen;seen.add(expected)
            assert row['all_three_own_point_uses']=='True' and row['complete_number_count']=='3'
            for i,y in enumerate(totals):
                assert ids[i]==row[f'source_record_id_{y}']
                assert math.isfinite(float(row[f'population_{y}']))
                assert -90<=float(row[f'latitude_{y}'])<=90 and -180<=float(row[f'longitude_{y}'])<=180
                assert f'population_value_quality_{y}' in row
                if not row[f'population_value_quality_{y}']: unknown_quality[y]+=1
                assert row[f'native_codes_as_imported_no_cross_year_backfill_{y}']=='True'
                for path_field,hash_field in [('source_actual_path','source_actual_sha256'),('point_actual_origin_file','point_actual_origin_sha256')]:
                    path=row[f'{path_field}_{y}'];claimed=row[f'{hash_field}_{y}']
                    if path and claimed:
                        if path in actual_file_claims: assert actual_file_claims[path]==claimed
                        actual_file_claims[path]=claimed
                    elif path_field=='source_actual_path': assert row[f'source_actual_resolution_status_{y}']=='original_source_cache_unresolved_imported_provenance_retained'
                    else: assert row[f'point_origin_resolution_status_{y}']=='original_origin_unknown_admitted_ledger_pinned'
                unknown_source[y]+=int(row[f'source_actual_resolution_status_{y}']=='original_source_cache_unresolved_imported_provenance_retained')
                unknown_origin[y]+=int(row[f'point_origin_resolution_status_{y}']=='original_origin_unknown_admitted_ledger_pinned')
                totals[y]+=int(float(row[f'population_{y}']))
    assert count==receipt['rows'] and {str(k):v for k,v in totals.items()}==receipt['population_by_year']
    for path,h in actual_file_claims.items(): assert sha(Path(path))==h,path
    result={'actual_source_and_point_origin_files_verified':len(actual_file_claims),'status':'delivered_gzip_hash_all_input_hashes_UID_uniqueness_peryear_points_numbers_and_quality_verified','rows':count,'population_by_year':totals,'unknown_imported_population_quality_rows_by_year':unknown_quality,'unresolved_original_source_file_rows_by_year':unknown_source,'unknown_original_point_origin_rows_by_year':unknown_origin,'unknown_original_point_origin_is_coordinate_correctness_claim':False,'sha256':receipt['sha256'],'bytes':receipt['bytes'],'wall_seconds':round(time.monotonic()-start,3)}
    (HERE/'export_verification_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__': main()

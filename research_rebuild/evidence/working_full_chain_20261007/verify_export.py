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
    count=0;seen=set();totals={2002:0,2010:0,2021:0};unknown_quality={2002:0,2010:0,2021:0}
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
                totals[y]+=int(float(row[f'population_{y}']))
    assert count==receipt['rows'] and {str(k):v for k,v in totals.items()}==receipt['population_by_year']
    result={'status':'delivered_gzip_hash_all_input_hashes_UID_uniqueness_peryear_points_numbers_and_quality_verified','rows':count,'population_by_year':totals,'unknown_imported_population_quality_rows_by_year':unknown_quality,'sha256':receipt['sha256'],'bytes':receipt['bytes'],'wall_seconds':round(time.monotonic()-start,3)}
    (HERE/'export_verification_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__': main()

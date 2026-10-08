from pathlib import Path
import csv,json,hashlib,re
import xlrd
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent
raw=Path('/workspace/settlements-raw/data/raw/2010/003_eb441570b1_11._20Урал_ФО_2010.xls')
selected=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=xlrd.open_workbook(raw).sheet_by_name('Урал')
cols=['source_record_id','census_year','region_norm','district_raw','settlement_name','settlement_type','population','source_file','source_sheet','source_row']
t=pq.read_table(selected,columns=cols).to_pandas()
t=t[(t.census_year==2010)&t.region_norm.str.contains('ямало',case=False,na=False)]
rows=[]
for n in range(2800,2809):
 r=s.row_values(n-1)
 candidates=t[t.source_row.astype(float)==n]
 candidates=candidates[candidates.source_file.astype(str).str.contains('003_eb441570b1',regex=False)]
 assert len(candidates)==1,(n,len(candidates))
 q=candidates.iloc[0]
 assert q.district_raw=='сс',q.to_dict()
 assert float(q.population)==float(r[7]),(n,q.population,r[7])
 rows.append(dict(source_record_id=q.source_record_id,census_year=2010,raw_file=str(raw),raw_sha256=sha(raw),raw_sheet='Урал',raw_row_1based=n,settlement_name=q.settlement_name,settlement_type=q.settlement_type,population=q.population,selected_district_raw=q.district_raw,raw_col3_caption=r[3],literal_upper_county='Ямальский район',upper_county_header_row_1based=2799,next_city_header_row_1based=2809,diagnostic_relation='raw_caption_is_not_county_header',proposed_credit=False,source_population_modified=False,raw_original_row_json=json.dumps(r,ensure_ascii=False)))
assert s.cell_value(2798,3)=='Ямальский район'
assert s.cell_value(2808,3)=='г. Салехард'
f=D/'selected_rows_and_literal_upper_county.csv'
with f.open('w') as h:
 w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (D/'literal_raw_bracket.csv').open('w') as h:
 w=csv.DictWriter(h,fieldnames=['raw_row_1based','raw_original_row_json']);w.writeheader()
 for n in range(2799,2810):w.writerow(dict(raw_row_1based=n,raw_original_row_json=json.dumps(s.row_values(n-1),ensure_ascii=False)))
receipt=dict(status='diagnostic_only_literal_upper_county_lost_to_admin_caption',affected_selected_rows=len(rows),affected_native_population=sum(r['population'] for r in rows),accepted_binding_delta_count=0,population_values_modified=False,selected_metadata_modified=False,no_county_representative_point_credit=True,source_manifest={str(raw):sha(raw),str(selected):sha(selected)},outputs={p.name:sha(p) for p in D.glob('*.csv')},code_sha256=sha(Path(__file__)),interpretation='Rows2800–2808 belong to preceding explicit literal Ямальский район block; сс is administrative caption, not independent county. This sidecar diagnoses source context only; does not establish individual identity or coordinates.')
(D/'diagnostic_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ['status','affected_selected_rows','affected_native_population','accepted_binding_delta_count']},ensure_ascii=False))

from pathlib import Path
import xlrd,pyarrow.parquet as pq,json
D=Path(__file__).parent
names=['Тольятти','Улан-Удэ','Новомосковск','Пермь','Мурманск','Киржач','Бор']
s=xlrd.open_workbook('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls').sheet_by_index(0)
f=[]
for n in range(s.nrows):
 label=str(s.cell_value(n,0)).strip()
 if any(label.startswith('г. '+name) for name in names):
  f.append({'row':n+1,'block':[s.row_values(k)[:2] for k in range(max(0,n-1),min(s.nrows,n+24))]})
(D/'initial2002city_controls.json').write_text(json.dumps(f,ensure_ascii=False,indent=2))
t=pq.read_table('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',columns=['source_record_id','census_year','region_norm','district_raw','settlement_name','settlement_type','population','source_file','source_sheet','source_row']).to_pandas()
print(t[t.settlement_name.isin(names)&t.settlement_type.eq('город')].to_string(index=False))
print(json.dumps(f,ensure_ascii=False))

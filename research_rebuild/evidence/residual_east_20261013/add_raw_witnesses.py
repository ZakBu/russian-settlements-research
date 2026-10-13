import csv,json,pathlib,hashlib,xlrd
P=pathlib.Path(__file__).parent;E=list(csv.DictReader((P/'accepted_identity_edge_delta.csv').open()));W=[]
for sid in sorted({r[k]for r in E for k in ['from_source_record_id','to_source_record_id']}):
 bits=sid.split(':');yr=bits[0]
 if yr not in ['2002','2010'] or len(bits)!=4:continue
 f=pathlib.Path('/workspace/settlements-raw/data/raw')/yr/bits[1]
 if not f.exists():continue
 b=f.read_bytes();sh=xlrd.open_workbook(file_contents=b).sheet_by_name(bits[2]);i=int(bits[3])-1;rows=[dict(physical_row_1based=j+1,cells=sh.row_values(j))for j in range(max(0,i-4),min(sh.nrows,i+4))];z=dict(source_record_id=sid,source_file=str(f),source_sha256=hashlib.sha256(b).hexdigest(),sheet=bits[2],source_locator=f'physical_row_1based={i+1}',literal_rows=rows)
 if 'Amur' in str(f):
  records=sorted([(float(sh.cell_value(j,0)),j,sh.row_values(j))for j in range(sh.nrows)if isinstance(sh.cell_value(j,0),(int,float))]);o=sh.cell_value(i,0);pos=next(k for k,r in enumerate(records)if r[1]==i);prior=records[:pos];headers=[r for r in prior if any(t in str(r[2][1])for t in ['район','Сельсоветы'])];z['original_order_neighborhood']=[dict(original_list_index=o,physical_row_1based=j+1,cells=c)for o,j,c in records[max(0,pos-6):pos+7]];z['nearest_original_order_county_headers']=[dict(original_list_index=o,physical_row_1based=j+1,cells=c)for o,j,c in headers[-4:]]
 W.append(z)
(P/'native_exact_raw_rows.json').write_text(json.dumps(W,ensure_ascii=False,indent=2));pts=list(csv.DictReader((P/'accepted_point_use_delta.csv').open()));donor=next(r for r in pts if r['target_source_record_id'].endswith(':2158'));new=dict(donor);new['target_source_record_id']='2002:085_b44ee84c57_saxalin.xls:Sheet1:14';new['coordinate_binding_rule']='Admitted sameplace chain native2002SouthSakhalinskKlyuchi→2010ownvillage→2021ownvillage; physical2002headerexplicitly SouthSakhalinsk, ownarticle status2004.';new['evidence_locator']='[2]|[3]';pts.append(new)
with (P/'accepted_point_use_delta.csv').open('w')as f:w=csv.DictWriter(f,fieldnames=pts[0].keys());w.writeheader();w.writerows(pts)
m=json.loads((P/'manifest.json').read_text());m=[r for r in m if r['file']!=str(P/'accepted_point_use_delta.csv')]
for f in [P/'accepted_point_use_delta.csv',P/'native_exact_raw_rows.json',P/'add_raw_witnesses.py']:m.append(dict(file=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size))
(P/'manifest.json').write_text(json.dumps(m,indent=2));print('raw witness cases',len(W),'point uses',len(pts))

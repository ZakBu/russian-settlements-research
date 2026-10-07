"""Read fixed-plus-largest sample directly from pinned DBF and census source bytes."""
import sys,json,re
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from verify_geokladr_snapshot import parse_dbf_header
from current_chain_state_20261007 import normalize,sha
OUT=Path(__file__).parent
f=pd.read_csv(OUT/'fixed_plus_largest_sample.csv',dtype={'historical_okato_2011_raw':str,'historical_okato_2009_raw':str})
GEO=Path(f.point_origin_file.iloc[0]);results=[];sheets={}
with GEO.open('rb') as stream:
 head=stream.read(32);hlen=int.from_bytes(head[8:10],'little');stream.seek(0)
 count,hlen,rlen,fields=parse_dbf_header(stream.read(hlen))
 for a in f.to_dict('records'):
  locator=a['point_origin_locator'];offset=int(re.search(r'byte_offset_0based=(\d+)',locator).group(1));stream.seek(offset);raw=stream.read(rlen)
  values={q['name']:raw[q['offset']:q['offset']+q['width']].decode('cp1251').strip() for q in fields}
  named=normalize(values['NAME1'])==normalize(a['name_raw_2011']);point=float(values['LAT'])==a['latitude'] and float(values['LONG'])==a['longitude']
  code=values['TER'].zfill(2)+values['KOD1'].zfill(3)+values['KOD2'].zfill(3)+values['KOD3'].zfill(3)
  asset=Path(a['census_source_file']);asset=asset if asset.is_file() else Path('/workspace/settlements-raw')/asset
  sid=a['source_record_id'];sheet,row=sid.rsplit(':',2)[-2:];row=int(row)
  key=(str(asset),sheet)
  if key not in sheets:sheets[key]=pd.read_excel(asset,sheet_name=sheet,header=None)
  source=sheets[key].iloc[row-1];texts=' | '.join(str(v) for v in source if pd.notna(v))
  namepresent=normalize(a['settlement_name']) in normalize(texts)
  numeric=pd.to_numeric(source.astype(str).str.replace(' ','',regex=False).str.replace('\u00a0','',regex=False),errors='coerce')
  populationpresent=bool(numeric.eq(float(a['population'])).any())
  results.append({'source_record_id':sid,'population':a['population'],'dbf_raw_named_object_exact':named,'dbf_coordinate_bytes_exact':point,'dbf_code_exact':code==a['historical_okato_2011_raw'],'census_source_row_name_present':namepresent,'census_source_row_population_present':populationpresent,'census_raw_row_excerpt':texts[:600],'dbf_raw_name':values['NAME1'],'dbf_raw_lat':values['LAT'],'dbf_raw_long':values['LONG']})
g=pd.DataFrame(results);g.to_csv(OUT/'independent_raw_sample_checks.csv',index=False)
checks=['dbf_raw_named_object_exact','dbf_coordinate_bytes_exact','dbf_code_exact','census_source_row_name_present','census_source_row_population_present']
receipt={'sample_rows':len(g),'sample_selection':'top15 plus random25 seed20261007 deduplicated','pass_counts':{k:int(g[k].sum()) for k in checks},'all_checks_pass':bool(g[checks].all().all()),'dbf_sha256':sha(GEO),'sample_sha256':sha(OUT/'fixed_plus_largest_sample.csv'),'census_source_assets':len(sheets),'limitations':['This verifies raw object and exact source row values, not physical point accuracy or cross-year identity.']}
(OUT/'sample_check_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False))

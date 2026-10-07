"""Bounded literal old census/GeoKLADR/current publisher source-code review."""
import sys,re,json
from pathlib import Path
import pandas as pd,duckdb,xlrd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from verify_geokladr_snapshot import parse_dbf_header
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent;WORK=Path('/workspace/settlements-work/near_name_coordinate_bridge_20261007');SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
GEO=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');PARSED=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet');CURRENT=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');REFERENCE=Path('/workspace/settlements-work/continuation_20261003/population2010/tom1_table5_extraction/official_2010_table5_reference.parquet')
f=pd.read_csv(WORK/'candidates.csv.gz',dtype=str,keep_default_na=False)
sample=pd.concat([pd.read_csv(OUT/'largest5_candidates.csv',dtype=str,keep_default_na=False),pd.read_csv(OUT/'fixed15_candidates.csv',dtype=str,keep_default_na=False)]).drop_duplicates('old_source_record_id')
c=duckdb.connect(config={'threads':1,'memory_limit':'600MB'});ids=list(sample.old_source_record_id)+list(sample.current_source_record_id)
meta=c.execute('SELECT source_record_id,source_file,source_sheet,source_row,source_name_raw,source_sha256,source_locator FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))',[str(SEL),ids]).fetchdf().set_index('source_record_id').to_dict('index')
rawobjects=c.execute('SELECT * FROM read_parquet(?) WHERE historical_okato IN (SELECT UNNEST(?))',[str(PARSED),list(sample.own_raw_historical_code_from_coordinate)]).fetchdf()
rownumbers=[int(s.rsplit(':',1)[-1]) for s in sample.current_source_record_id];current=c.execute('WITH raw AS (SELECT row_number() OVER () AS raw_row_1based,object_level,object_name,oktmo,region,mun_upper,mun_lower,settlement,population,settlement_dadata,settlement_type_full_dadata,okato_dadata,oktmo_dadata,latitude_dadata,longitude_dadata FROM read_parquet(?)) SELECT * FROM raw WHERE raw_row_1based IN (SELECT UNNEST(?))',[str(CURRENT),rownumbers]).fetchdf().set_index('raw_row_1based').to_dict('index')
books={};hashes={};results=[]
def k(v):return re.sub(r'[^а-яa-z0-9]+',' ',normalize(v)).strip()
def number(v):
 if isinstance(v,(float,int)):return float(v)
 if isinstance(v,str) and re.fullmatch(r'\d+(?:\.0+)?',v.strip()):return float(v.strip())
 return None
with GEO.open('rb') as stream:
 header=stream.read(32);hlen=int.from_bytes(header[8:10],'little');stream.seek(0);_,_,rlen,fields=parse_dbf_header(stream.read(hlen))
 for a in sample.to_dict('records'):
  matches=rawobjects[rawobjects.historical_okato.eq(a['own_raw_historical_code_from_coordinate'])&rawobjects.latitude_from_lat.eq(float(a['old_latitude']))&rawobjects.longitude_from_long.eq(float(a['old_longitude']))&~rawobjects.is_deleted]
  if len(matches)!=1:raise ValueError('Ambiguous own raw record in bounded source sample')
  g=matches.iloc[0];stream.seek(int(g.record_byte_offset_0based));record=stream.read(rlen);vals={q['name']:record[q['offset']:q['offset']+q['width']].decode('cp1251').strip() for q in fields}
  code=vals['TER'].zfill(2)+vals['KOD1'].zfill(3)+vals['KOD2'].zfill(3)+vals['KOD3'].zfill(3)
  old=meta[a['old_source_record_id']];asset=Path(str(old['source_file']));asset=asset if asset.is_file() else Path('/workspace/settlements-raw')/asset
  hashes.setdefault(str(asset),sha(asset) if asset.is_file() else '')
  text='';label_ok=population_ok=False;count_column=None;source_available=asset.is_file()
  if source_available and asset.suffix.lower()=='.xls':
   if asset not in books:books[asset]=xlrd.open_workbook(str(asset),on_demand=True)
   book=books[asset];sheetname=old['source_sheet'];num=old['source_row']
   if pd.isna(sheetname) or pd.isna(num):sheetname,num=a['old_source_record_id'].rsplit(':',2)[-2:]
   try:sh=book.sheet_by_name(str(sheetname))
   except Exception:sh=book.sheet_by_index(int(sheetname))
   cells=sh.row_values(int(float(num))-1);text=' | '.join(str(v) for v in cells if v!='')
   labels=[(j,v) for j,v in enumerate(cells) if isinstance(v,str) and k(a['old_name']) in k(v)]
   exact=[(j,v) for j,v in labels if pd.notna(old['source_name_raw']) and normalize(v)==normalize(old['source_name_raw'])]
   if exact:labels=exact
   label_ok=len(labels)==1
   if label_ok:
    numeric=[(j,number(v)) for j,v in enumerate(cells) if j>labels[0][0] and number(v) is not None]
    population_ok=bool(numeric) and numeric[0][1]==float(a['old_population']);count_column=numeric[0][0]+1 if numeric else None
  elif source_available and asset.suffix.lower()=='.pdf':
   loc=json.loads(old['source_locator']);page=int(loc['pdf_page_1based']);line=int(loc['text_line_start_1based']);ref=c.execute('SELECT label_raw,raw_lines,population FROM read_parquet(?) WHERE pdf_page=? AND text_line_start=?',[str(REFERENCE),page,line]).fetchdf()
   if len(ref)==1:text=str(ref.iloc[0].raw_lines);label_ok=k(a['old_name']) in k(ref.iloc[0].label_raw);population_ok=int(ref.iloc[0].population)==float(a['old_population'])
  cur=current[int(a['current_source_record_id'].rsplit(':',1)[-1])];current_label_ok=k(a['current_name']) in k(str(cur['object_name'])+' '+str(cur['settlement']));current_pop_ok=float(cur['population'])==float(a['current_population']);current_county_ok=county_key(cur['mun_upper'])==a['county_key']
  results.append({'old_source_record_id':a['old_source_record_id'],'current_source_record_id':a['current_source_record_id'],'old_name':a['old_name'],'current_name':a['current_name'],'name_variant_family':a['name_variant_family'],'old_type':a['old_type'],'current_type':a['current_type'],'county_key':a['county_key'],'distance_km':a['distance_km'],'raw_geo_named_label':vals['NAME1'],'raw_geo_type':vals.get('TYPE',''),'raw_geo_code':code,'raw_geo_lat':vals['LAT'],'raw_geo_lon':vals['LONG'],'raw_geo_record_1based':int(g.record_number_1based),'raw_geo_byte_offset_0based':int(g.record_byte_offset_0based),'raw_geo_code_exact':code==a['own_raw_historical_code_from_coordinate'],'raw_geo_coordinate_bytes_exact':float(vals['LAT'])==float(a['old_latitude']) and float(vals['LONG'])==float(a['old_longitude']),'old_census_source_file':str(asset),'old_census_source_sha256':hashes[str(asset)],'old_census_source_locator':str(old['source_locator']),'old_source_available':source_available,'old_source_literal_name_present':label_ok,'old_source_first_count_exact':population_ok,'old_source_count_column_1based':count_column,'old_source_raw_row':text[:2000],'current_source_file':str(CURRENT),'current_raw_row_1based':int(a['current_source_record_id'].rsplit(':',1)[-1]),'current_raw_object_level':cur['object_level'],'current_raw_object_name':cur['object_name'],'current_raw_settlement':cur['settlement'],'current_raw_county':cur['mun_upper'],'current_raw_native_oktmo':cur['oktmo'],'current_raw_provider_okato':cur['okato_dadata'],'current_raw_provider_oktmo':cur['oktmo_dadata'],'current_raw_provider_settlement':cur['settlement_dadata'],'current_literal_name_present':current_label_ok,'current_population_exact':current_pop_ok,'current_county_exact':current_county_ok,'current_selected_okato_equals_raw_provider_field':a['current_okato']==str(cur['okato_dadata']),'native_census_code_binding_asserted':False})
r=pd.DataFrame(results);r.to_csv(OUT/'bounded_raw_source_code_checks.csv',index=False)
checks=['raw_geo_code_exact','raw_geo_coordinate_bytes_exact','old_source_available','old_source_literal_name_present','old_source_first_count_exact','current_literal_name_present','current_population_exact','current_county_exact']
receipt={'status':'bounded_source_checks','sample_rows':len(r),'selection':'largest5 plus fixed15 seed20261007 deduplicated','pass_counts':{key:int(r[key].sum()) for key in checks},'all_requested_checks_pass':bool(r[checks].all().all()),'inputs_sha256':{str(p):sha(p) for p in [WORK/'candidates.csv.gz',OUT/'largest5_candidates.csv',OUT/'fixed15_candidates.csv',SEL,GEO,PARSED,CURRENT,REFERENCE,Path(__file__)]},'old_census_source_hashes':hashes,'output_sha256':sha(OUT/'bounded_raw_source_code_checks.csv'),'limitations':['Sample verifies physical raw labels, counts, code and point bytes; candidate identity still requires review.','Current OKATO field is a frozen provider-derived identifier; this is not an originally printed historical census code.','Current accepted point anchors may use GeoNames/Wikidata instead of the frozen provider coordinate; baseline admissions retained.']}
(OUT/'source_check_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'sample_rows':len(r),'pass_counts':receipt['pass_counts'],'all_pass':receipt['all_requested_checks_pass']},ensure_ascii=False))

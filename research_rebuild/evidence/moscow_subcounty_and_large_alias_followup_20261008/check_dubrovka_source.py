import sys,json,struct
from pathlib import Path
import duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));from current_chain_state_20261007 import sha,distance_km
O=Path(__file__).parent;c=duckdb.connect();p=Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls');sh=xlrd.open_workbook(p).sheet_by_index(0);oldrow=sh.row_values(152);header=sh.row_values(151);assert 'Дубровка' in str(oldrow) and '8598' in str(oldrow)
f=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
with f.open('rb') as x:
 hd=x.read(32);hlen,rlen=struct.unpack('<HH',hd[8:12]);defs=[];off=1
 while x.tell()<hlen-1:
  d=x.read(32)
  if d[0]==13:break
  name=d[:11].split(b'\0')[0].decode();width=d[16];defs.append((name,off,width));off+=width
 x.seek(hlen+(13475-1)*rlen);raw=x.read(rlen)
fields={n:raw[o:o+w].decode('cp1251').strip() for n,o,w in defs};assert 'Дубровка' in str(fields);assert '52.927012' in str(fields)
curpath=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');cur=c.execute('select * from (select row_number() over() rn,* from read_parquet(?)) where rn=173865',[str(curpath)]).fetchdf().iloc[0];curdict={k:str(cur[k]) for k in ['object_name','settlement','mun_upper','okato_dadata','latitude_dadata','longitude_dadata','fias_level_dadata','settlement_type_full_dadata']};assert curdict['okato_dadata']=='15212551000'
w=c.execute('select * from read_parquet(?) where source_record_id=?',['/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:173865']).fetchdf().iloc[0];wiki={k:str(w[k]) for k in w.index if 'okato' in k or '625' in k or k=='wikidata_qid' or 'article_url' in k};assert wiki['wikidata_qid']=='Q1965217';assert '15212551000' in str(wiki)
doc={'old2002_source':str(p),'old2002_sha256':sha(p),'old2002_row_1based':153,'literal_old_own_row':oldrow,'literal_old_county_header_row_152':header,'2010_primary_source':'/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf','2010_pdf_sha256':sha(Path('/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf')),'2010_literal_witness':'Дубровский район; Городское население - пгт Дубровка рп (рц) 8015','wrong_modern2011_source':str(f),'wrong_modern2011_sha256':sha(f),'raw_record_1based':13475,'raw_fields':fields,'independent_current_publisher_source':str(curpath),'independent_current_publisher_sha256':sha(curpath),'publisher_raw_row_1based':173865,'publisher_raw_fields':curdict,'current_own_wiki_proof':wiki,'modern_wiki_publisher_distance_km':distance_km((53.690833,33.507222),(float(cur.latitude_dadata),float(cur.longitude_dadata))),'provider_identifier_binding_status':'Native own historic code/name/context retained; wrong modern coordinate claim rejected separately','no_historical_relocation_asserted':True,'no_boundary_comparability_asserted':True}
(O/'dubrovka_specific_wrong_modern_provider_positive_proof.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2));print('Dubrovka source witnesses passed',doc['modern_wiki_publisher_distance_km'])

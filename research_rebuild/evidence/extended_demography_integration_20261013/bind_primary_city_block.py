"""Attach image-checked historical city claims to named-city reference series.
Not a historical boundary reconstruction or census graph mutation.
"""
import csv,json,re,hashlib
from pathlib import Path
import duckdb
import pyarrow as pa,pyarrow.parquet as pq
REPO=Path('/workspace/russian-settlements-research')
OUT=Path('/workspace/scratch/extended-demography-integration-20261013');OUT.mkdir(exist_ok=True)
SOURCE=REPO/'research_rebuild/evidence/extended_population_sources_20261013/manual_image_checked_city_block.csv'
NATIVE=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
def norm(x):return re.sub(r'[^а-яa-z0-9]','',str(x).lower().replace('ё','е'))
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def main():
 c=duckdb.connect();native=c.execute('SELECT * FROM read_parquet(?) WHERE census_year=2002',[str(NATIVE)]).fetchdf();rows=[];holds=[]
 for r in csv.DictReader(SOURCE.open()):
  assert r['status']=='independently_image_checked', 'Candidate transcription is not admitted'
  regions={'архангельскаяобласть','архангельская'}
  if r['name_raw']=='Нарьян-Мар':regions.update({'ненецкийавтономныйокруг','ненецкий'})
  candidates=native[native['name_norm'].map(norm).eq(norm(r['name_raw'])) & native['region_norm'].map(norm).isin(regions)]
  candidates=candidates[candidates['type_norm'].isin(['г','город'])]
  if len(candidates)!=1:
   holds.append(dict(r,reason='current_reference_not_unique',candidates=len(candidates)));continue
  n=candidates.iloc[0]
  for year in (1979,1989):
   for basis in ('present','permanent'):
    value=int(r[f'population_{year}_{basis}_raw']);assert value>=0
    rows.append({'anchor_source_record_id':n.source_record_id,'root':n.root,'settlement_name':r['name_raw'],'year':year,'population':value,'population_basis':basis,'source_value_raw':r[f'population_{year}_{basis}_raw'],'source_pdf_sha256':r['source_pdf_sha256'],'source_pdf_page_1based':int(r['source_pdf_page_1based']),'printed_page':int(r['printed_page']),'source_row_label':r['name_raw'],'formation_year_raw':r['formation_year_raw'],'source_quality':'primary_published_image_checked','association_status':'historical_named_city_reference_series','historical_physical_identity_asserted':False,'boundary_comparability':'UNKNOWN','coordinate_role':'current_reference_point_not_historical_measurement','reference_latitude':n.accepted_latitude,'reference_longitude':n.accepted_longitude})
 assert rows
 pq.write_table(pa.Table.from_pylist(rows),OUT/'primary_city_population_1979_1989.parquet',compression='zstd')
 receipt={'source_csv_sha256':sha(SOURCE),'native_sha256':sha(NATIVE),'rows':len(rows),'cities':len(set(x['anchor_source_record_id'] for x in rows)),'held':holds,'output':str(OUT/'primary_city_population_1979_1989.parquet'),'output_sha256':sha(OUT/'primary_city_population_1979_1989.parquet'),'census_2002_2010_2021_coverage_unchanged':True,'historical_boundaries_verified':False}
 (REPO/'research_rebuild/evidence/extended_demography_integration_20261013/primary_city_binding_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()

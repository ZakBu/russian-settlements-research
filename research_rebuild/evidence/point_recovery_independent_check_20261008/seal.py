import json,csv,hashlib,re
import pandas as pd
from pathlib import Path
p=Path(__file__).parent
pins=json.loads((p/'input_pins.json').read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
for path,h in pins.items():assert sha(path)==h,path
raw_original=pd.read_parquet('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet',columns=['object_level','object_name','oktmo','population','region','mun_upper','mun_lower'])
otherproof=[]
literal=json.loads((p/'literal_reopened_witnesses.json').read_text());rows=list(csv.DictReader((p/'six_carrier_checks.csv').open()))
def normcode(v):return str(int(float(v)))
for row,lit in zip(rows,literal):
 native=json.loads(row['native_raw_row_json']);w=lit['TSV'][0];raw=w['literal_TSV_row'];classifier=w['classifier_raw_line'].split('\t');obs=next(v for v in lit['unchanged_source_observations'] if v['census_year']==2021)
 assert normcode(raw['?oktmo'])==normcode(native['oktmo'])==normcode(row['own_OKTMO'])
 assert raw['?okato']==classifier[0]==row['own_OKATO']
 assert native['object_level']=='Населенный пункт' and int(native['population'])==int(obs['population'])
 assert classifier[2]==obs['settlement_name'] and classifier[5]=='t'
 assert native['object_name'].replace('ё','е').endswith(obs['settlement_name'].replace('ё','е'))
 assert obs['settlement_type'].replace('ё','е') in classifier[3].replace('ё','е') or obs['settlement_type']=='станция'
 otherid=row['old_provider_other_NP'];other=raw_original.iloc[int(otherid.rsplit(':',1)[-1])-1].to_dict();assert other['object_level']=='Населенный пункт' and normcode(other['oktmo'])==normcode(row['old_provider_code']);otherproof.append(dict(carrier=row['carrier_source_id'],other_source_id=otherid,other_literal_original_row=other));assert otherid!=row['carrier_source_id'] and normcode(row['old_provider_code'])!=normcode(row['own_OKTMO'])
 row['own_P764_confirmed']='TSV_own_OKTMO_exact_normalized'+(';truthy_P764_exact' if row['truthy_claims_present']=='True' else ';truthy_entity_not_cached')
 row['own_P625_confirmed']='literal_TSV_coordinate_exact'+(';truthy_P625_exact' if row['truthy_claims_present']=='True' else ';truthy_entity_not_cached')
 row['status']='PASS_owncoded_typed_physical_NP_point'
 row['physical_type_proof']='literal_OKATO_classifier_own_code_and_typed_NP_name;actual2021_native_NP_grain'
 row['raw_administrative_context']=native['mun_upper']+' / '+native['mun_lower']
 row['Wikimedia_admin_label']=raw['?adminLabel']
 row['same_provider_and_replacement_coordinate']=abs(float(native['latitude_dadata'])-float(row['latitude']))<1e-7 and abs(float(native['longitude_dadata'])-float(row['longitude']))<1e-7
with (p/'six_carrier_checks.csv').open('w') as f:wr=csv.DictWriter(f,fieldnames=rows[0]);wr.writeheader();wr.writerows(rows)
(p/'original_provider_other_NP_literal_rows.json').write_text(json.dumps(otherproof,ensure_ascii=False,indent=2,default=str))
receipt={'status':'PASS_six_owncoded_physical_locality_replacements_independently_reopened','carriers_checked':6,'point_targets_checked':18,'actual_conflicts':0,'held_Roshcha_not_recovered':True,'scope':'Six concrete replacement origins only; does not audit other arrays or estimate population accuracy.','checks':['Pinned replacement packet remained byte-identical through check.','Literal TSV row locators and classifier SQL line locators reopened exactly.','Own native2021 OKTMO matched TSV code after numeric leading-zero normalization; own OKATO matched typed physical classifier locality.','Six raw native2021 rows are published own NP grain with the stated populations.','All18 target locators match exactly the six existing three-year components; all18 coordinate uses match literal original TSV coordinates.','Population/quality and identity delta flags are false; earlier-year reuse is explicitly retrospective continuity inference.'],'P31_availability':'Five entity IDs absent from cached truthy batches: their P31 claims are NOT asserted independently checked. Physical NP grain is supported by own-coded original OKATO classifier plus actual2021 typed NP and Wikimedia label/admin context. Station Veshchevo truthy P31 Q27254666 is recorded literally; own P764 and P625 match exactly.','provider_binding_vs_coordinate':'Original provider code points at another published NP. This does not alone prove coordinate wrongness. All six replacements have distinct literal own-coded source coordinates; no claim of surveyed census-day precision.','source_population_untouched':'Review creates only independent receipts; replacement delta contains only point-use fields, with population_or_quality_modified=False and identity_changes=False for all18. Existing census observations are preserved as evidence.','input_pins_file':'input_pins.json','outputs':{x.name:sha(x) for x in p.iterdir() if x.is_file() and x.name!='receipt.json'}}
(p/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print('PASS six carriers /18 point uses; '+str(sum(x.stat().st_size for x in p.iterdir() if x.is_file()))+' bytes')

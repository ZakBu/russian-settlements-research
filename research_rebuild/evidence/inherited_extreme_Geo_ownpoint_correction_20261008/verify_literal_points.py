import csv,gzip,json,hashlib,zipfile
from pathlib import Path
Z=Path(__file__).resolve().parent;sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest();w=json.load(gzip.open(Z/'native_ownpoint_recovery_witnesses.json.gz','rt'));dbf=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');raw=dbf.open('rb');header=raw.read(32);length=int.from_bytes(header[8:10],'little');record_length=int.from_bytes(header[10:12],'little');fields=[];offset=1
while raw.tell()<length-1:
 descriptor=raw.read(32)
 if descriptor[0]==13:break
 field=descriptor[:11].split(b'\0')[0].decode();size=descriptor[16];fields.append((field,offset,size));offset+=size
n=0
for case in w:
 for proof in case['old_native_and_classifier_proofs']:
  pos=length+(proof['Geo_record_1based']-1)*record_length;assert pos==proof['Geo_byte_offset'];raw.seek(pos);b=raw.read(record_length);values={field:b[start:start+size].decode('cp1251').strip() for field,start,size in fields};assert values['TER'].zfill(2)+values['KOD1'].zfill(3)+values['KOD2'].zfill(3)+values['KOD3'].zfill(3)==proof['own_historical_OKATO'];assert float(values['LAT'])==proof['Geo_literal_latitude'] and float(values['LONG'])==proof['Geo_literal_longitude'];assert values['NAME1']==proof['Geo_literal_name'].strip();assert b[0]==32;n+=1
TSV=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');needed={int(case['anchor_proof']['anchor_origin_locator'].rsplit(' ',1)[1]):case['anchor_proof']['literal_TSV_row'] for case in w if 'Wikimedia' in case['anchor_proof']['anchor_rule']};got=set()
with TSV.open() as stream:
 for line,row in enumerate(csv.DictReader(stream,delimiter='\t'),2):
  if line in needed:assert row==needed[line];got.add(line)
assert got==set(needed)
geonames=[case['anchor_proof'] for case in w if 'GeoNames' in case['anchor_proof']['anchor_rule']];geo_expected={r['literal_GeoNames_point_fields'][0]:r['literal_GeoNames_point_fields'] for r in geonames};region_expected={r['literal_GeoNames_ADM1_fields'][0]:r['literal_GeoNames_ADM1_fields'] for r in geonames};seen=set();seen_regions=set();geozip=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
with zipfile.ZipFile(geozip) as source:
 for line in source.open('RU.txt'):
  row=line.decode().rstrip('\n').split('\t')
  if row[0] in geo_expected:assert row==geo_expected[row[0]];seen.add(row[0])
  if row[0] in region_expected:assert row==region_expected[row[0]];seen_regions.add(row[0])
assert seen==set(geo_expected) and seen_regions==set(region_expected)
receipt=dict(independent_GeoNames_physical_records_checked=len(seen),independent_GeoNames_ADM1_records_checked=len(seen_regions),GeoNames_admin2_unknown_explicit=True,status='passed_independent_raw_point_byte_and_literal_TSV_checks',raw_dbf_records_independently_reopened=n,own_literal_TSV_rows_independently_reopened=len(got),raw_source_pins={str(p):sha(p) for p in [dbf,TSV,geozip]},code_sha256=sha(Path(__file__)));(Z/'independent_literal_point_checks.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,indent=2))

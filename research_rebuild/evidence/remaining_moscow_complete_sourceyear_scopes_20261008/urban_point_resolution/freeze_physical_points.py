from pathlib import Path
import struct,json,hashlib,pandas as pd,pyarrow.parquet as pq
D=Path(__file__).parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=Path('/workspace/settlements-raw/data/interim/historical_geography/geokladr_okato_2011/okato.dbf');parsed=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet');q=pq.read_table(parsed,filters=[('historical_okato','in',['46238558000','46238560000'])]).to_pandas();assert len(q)==2
with p.open('rb') as h:
 head=h.read(32);count=struct.unpack('<I',head[4:8])[0];hlen,rlen=struct.unpack('<HH',head[8:12]);fields=[];offset=1
 while True:
  d=h.read(32)
  if d[0]==13:break
  name=d[:11].split(b'\0')[0].decode('ascii');length=d[16];fields.append((name,offset,length));offset+=length
 assert offset==rlen
 proof=[]
 for r in q.itertuples():
  loc=hlen+(int(r.record_number_1based)-1)*rlen;assert loc==r.record_byte_offset_0based;h.seek(loc);row=h.read(rlen);assert row[:1]==b' '
  vals={name:row[o:o+n].decode('cp1251') for name,o,n in fields}
  # Existing parsedsource codec is cp1251; rawphysical value cells and true typedNP names independently reopened.
  label=vals['NAME1'].strip();typ=vals['SCOKATO'].strip();lat=float(vals['LAT']);lon=float(vals['LONG']);code=''.join(vals[z].strip() for z in ['TER','KOD1','KOD2','KOD3'])
  assert label==r.name_raw and typ=='пгт' and code==r.historical_okato and lat==r.latitude_from_lat and lon==r.longitude_from_long
  proof.append(dict(own_physical_pgt_name=label,historical_okato=code,own_kladr=r.kladr,physical_source_file=str(p),physical_source_sha256=sha(p),raw_record_number_1based=int(r.record_number_1based),raw_record_byte_offset_0based=loc,raw_record_length=rlen,deleted_marker='live',raw_typed_NP_label=label,raw_type=typ,latitude=lat,longitude=lon,physical_source_updated_at=r.source_updated_at,point_grain='own_physical_PGT_not_municipal_or_county',historical_census_location_exact_measurement_asserted=False,temporal_grade='2011ownphysicalNPpoint; inferredcontinuityfor2002and2010, notcensusdaymeasurement',raw_fields_json=json.dumps(vals,ensure_ascii=False)))
sql=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql');cp=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');c=pq.read_table(cp,filters=[('historical_okato','in',['46238558','46238560'])]).to_pandas();assert len(c)==2 and c.is_settlement_raw.eq('t').all() and c.status.eq('поселок городского типа').all()
lines={};wanted=set(c.source_line_1based.astype(int))
with sql.open() as h:
 for n,l in enumerate(h,1):
  if n in wanted:lines[n]=l.rstrip('\n')
  if n>max(wanted):break
classproof=[]
for r in c.itertuples():
 l=lines[int(r.source_line_1based)];assert r.historical_okato in l and r.name_raw in l;classproof.append(dict(historical_okato8=r.historical_okato,corresponding_geokladr_physical_okato11=r.historical_okato+'000',name_raw=r.name_raw,status=r.status,is_settlement_raw=r.is_settlement_raw,source_file=str(sql),source_sha256=sha(sql),source_line_1based=int(r.source_line_1based),original_sql_line=l,point_grain_disambiguation='2009classifier actualownPGT settlementflag t/status pgt; notmunicipal record;2011typedphysical record suffixed000'))
pd.DataFrame(proof).to_csv(D/'raw2011_own_physical_PGT_points.csv',index=False);pd.DataFrame(classproof).to_csv(D/'raw2009_ownPGT_classifier_evidence.csv',index=False)
# Source rivals enumerated before geographical/code/type selection.
x=pq.read_table(parsed,columns=['historical_okato','record_number_1based','name_raw','settlement_type_raw','kladrcode_raw_text','latitude_from_lat','longitude_from_long','is_deleted']).to_pandas();rivals=x[x.name_raw.str.contains(r'Киевский|Кокошкино',regex=True,na=False)];rivals.to_csv(D/'all_cached_literal_name_competitors_before_type_code_filter.csv',index=False)
r=dict(status='positive_2_cached_ownphysical_PGT_points_source_verified',State44_existing_native_points=0,physical_PGT_points=2,network_requests=0,point_source_not_municipal_P625=True,source2011_record_population_unused=True,old_census2002_or2010_location_measured_exactly=False,source_manifest={str(z):sha(z) for z in [p,parsed,sql,cp]},outputs={z.name:sha(z) for z in D.glob('*.csv')});(D/'physical_point_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('Verified2ownphysicalpoints')

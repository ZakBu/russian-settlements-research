from pathlib import Path
import struct,json,gzip,hashlib
O=Path(__file__).parent;p=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');b=p.read_bytes();n=struct.unpack('<I',b[4:8])[0];h,rl=struct.unpack('<HH',b[8:12]);fields=[]
for i in range(32,h-1,32):
 if b[i]==13:break
 fields.append((b[i:i+11].split(b'\0')[0].decode(),chr(b[i+11]),b[i+16]))
rows=[]
for ix in range(n):
 r=b[h+ix*rl:h+(ix+1)*rl];off=1;vals={}
 for name,ty,sz in fields:vals[name]=r[off:off+sz].decode('cp1251').strip();off+=sz
 if r[:1]==b'*':continue
 name=vals['NAME1'].lower();code=''.join(vals[k]for k in ['TER','KOD1','KOD2','KOD3']);hits=[]
 if code.startswith('80247')and'турнал'in name:hits.append('Novye_Turnaly_rivals_2011')
 if code.startswith('80')and'михайлов'in name:hits.append('Novomikhaylovsky_2011_rivals')
 if code.startswith('80202')and any(x in name for x in ['крым','раев','усадьб']):hits.append('Raevsky_estate_modern_recipient_or_rivals_2011')
 if code.startswith('64')and'восточ'in name:hits.append('Vostochny_Sakhalin_2011_rivals')
 if hits:rows.append(dict(cases=hits,source_file=str(p),source_sha256=hashlib.sha256(b).hexdigest(),source_locator=f'okato.dbf:physical_record_1based={ix+1}',raw_classification_code=code,raw_fields=vals,candidate_only=True))
(O/'exact_legacy_2011_own_feature_records.json.gz').write_bytes(gzip.compress(json.dumps(rows,ensure_ascii=False,indent=2).encode(),mtime=0));print(json.dumps([dict(cases=x['cases'],name=x['raw_fields']['NAME1'],code=x['raw_classification_code'],lat=x['raw_fields']['LAT'],lon=x['raw_fields']['LONG'])for x in rows],ensure_ascii=False,indent=2))
